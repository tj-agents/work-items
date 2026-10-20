from __future__ import annotations

import copy
import io
import json
import re
import sys
from collections.abc import Mapping, Sequence
from email.message import Message
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import unquote, urlsplit

import pytest

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "work-items/utility/manage/runtime/src"),
)

from tj_work_items.azure_api import APIError, Client
from tj_work_items.azure_tracker import Tracker
from tj_work_items.records import ItemError

CONFIG: dict[str, object] = {
    "schema_version": 1,
    "organization": "tj-agents",
    "project": "Personal work items",
    "repository": "tommyboy4050/example",
    "kinds": {
        "feature": "Feature",
        "task": "Task",
        "bug": "Bug",
        "mistake": "Mistake",
        "debt": "Debt",
    },
}

LIFECYCLE: dict[str, Mapping[str, object]] = {
    kind: {"open": "New", "closed": "Closed", "inactive": ("Closed", "Removed")}
    for kind in ("feature", "task", "bug", "mistake", "debt")
}

FIELDS = {
    "repository": "Custom.PersonalRepository",
    "request": "Custom.PersonalRequestId",
    "record": "Custom.PersonalRecord",
}


class MemoryJournal:
    def __init__(self) -> None:
        self.receipts: dict[str, dict[str, int | str | None]] = {}

    def read(self, key: str, fingerprint: str) -> dict[str, int | str | None] | None:
        receipt = self.receipts.get(key)
        if receipt is not None and receipt["fingerprint"] != fingerprint:
            raise ItemError(
                "request receipt differs or is invalid; reconcile before submission"
            )
        return receipt

    def reserve(self, key: str, fingerprint: str) -> None:
        if key in self.receipts:
            raise ItemError(
                "request is already reserved; reconcile without another POST"
            )
        self.receipts[key] = {"fingerprint": fingerprint, "resource_id": None}

    def complete(self, key: str, fingerprint: str, resource_id: int) -> None:
        self.receipts[key] = {"fingerprint": fingerprint, "resource_id": resource_id}

    def writer(self) -> Any:
        from contextlib import nullcontext

        return nullcontext()


class FakeAzure:
    def __init__(self) -> None:
        self.items: dict[int, dict[str, object]] = {}
        self.next_id = 1
        self.posts = 0
        self.persist_then_timeout = False
        self.conflict_next = False
        self.unauthorized_wiql = False
        self.drop_created_parent = False
        self.hide_query_results = False
        self.calls: list[tuple[str, str, object]] = []
        self.edit_after_write: str | None = None
        self.ignore_state_filter = False

    def request(
        self,
        method: str,
        suffix: str,
        payload: Mapping[str, object] | Sequence[Mapping[str, object]] | None = None,
        content_type: str = "application/json",
    ) -> object:
        self.calls.append((method, suffix, copy.deepcopy(payload)))
        if method == "POST" and suffix.startswith("wiql"):
            if self.unauthorized_wiql:
                raise APIError("Azure DevOps POST failed (HTTP 401)", 401)
            assert isinstance(payload, Mapping)
            if self.hide_query_results:
                return {"workItems": []}
            query = payload["query"]
            assert isinstance(query, str)
            return {
                "workItems": [
                    {"id": identifier}
                    for identifier, item in self.items.items()
                    if self._matches(item, query)
                ]
            }
        if method == "POST" and suffix.startswith("workitems/$"):
            assert isinstance(payload, Sequence)
            identifier = self.next_id
            self.next_id += 1
            fields: dict[str, object] = {
                "System.TeamProject": CONFIG["project"],
                "System.WorkItemType": unquote(suffix.removeprefix("workitems/$")),
                "System.State": "New",
            }
            item: dict[str, object] = {
                "id": identifier,
                "rev": 1,
                "fields": fields,
                "relations": [],
            }
            self._patch(item, payload)
            if self.edit_after_write is not None:
                fields = item["fields"]
                assert isinstance(fields, dict)
                fields[self.edit_after_write] = "Facts changed through Azure UI"
            if self.drop_created_parent:
                item["relations"] = []
            self.items[identifier] = item
            self.posts += 1
            if self.persist_then_timeout:
                self.persist_then_timeout = False
                raise APIError(
                    "Azure DevOps transport is unavailable; "
                    "a write outcome may be uncertain"
                )
            return copy.deepcopy(item)
        if method == "GET" and suffix.startswith("workitems/"):
            identifier = int(suffix.removeprefix("workitems/").split("?", 1)[0])
            return copy.deepcopy(self.items[identifier])
        if method == "PATCH" and suffix.startswith("workitems/"):
            identifier = int(suffix.removeprefix("workitems/"))
            if self.conflict_next:
                self.conflict_next = False
                raise APIError("Azure DevOps PATCH failed (HTTP 409)", 409)
            assert isinstance(payload, Sequence)
            item = self.items[identifier]
            self._patch(item, payload)
            if self.edit_after_write is not None:
                fields = item["fields"]
                assert isinstance(fields, dict)
                fields[self.edit_after_write] = "Facts changed through Azure UI"
            revision = item["rev"]
            assert isinstance(revision, int)
            item["rev"] = revision + 1
            return copy.deepcopy(item)
        raise AssertionError(f"unexpected Azure request: {method} {suffix}")

    def _matches(self, item: dict[str, object], query: str) -> bool:
        fields = item["fields"]
        assert isinstance(fields, dict)
        checks = {
            "System.TeamProject": fields["System.TeamProject"],
            "Custom.PersonalRepository": fields.get("Custom.PersonalRepository"),
            "Custom.PersonalRequestId": fields.get("Custom.PersonalRequestId"),
        }
        for field, value in checks.items():
            match = re.search(rf"\[{re.escape(field)}\] = '((?:''|[^'])*)'", query)
            if match is not None and str(value) != match.group(1).replace("''", "'"):
                return False
        type_clauses = re.findall(
            r"\(\[System.WorkItemType\] = '((?:''|[^'])*)'([^()]*)\)", query
        )
        if not type_clauses:
            return True
        for native_type, conditions in type_clauses:
            if fields["System.WorkItemType"] != native_type.replace("''", "'"):
                continue
            inactive = re.findall(r"\[System.State\] <> '((?:''|[^'])*)'", conditions)
            if self.ignore_state_filter or fields["System.State"] not in {
                state.replace("''", "'") for state in inactive
            }:
                return True
        return False

    def _patch(
        self, item: dict[str, object], patch: Sequence[Mapping[str, object]]
    ) -> None:
        fields = item["fields"]
        relations = item["relations"]
        assert isinstance(fields, dict)
        assert isinstance(relations, list)
        for operation in patch:
            path = operation["path"]
            assert isinstance(path, str)
            if operation["op"] == "test":
                assert path == "/rev"
                if operation["value"] != item["rev"]:
                    raise APIError("Azure DevOps PATCH failed (HTTP 409)", 409)
            elif path.startswith("/fields/"):
                fields[path.removeprefix("/fields/")] = operation["value"]
            elif operation["op"] == "remove" and path.startswith("/relations/"):
                relations.pop(int(path.removeprefix("/relations/")))
            elif operation["op"] == "add" and path == "/relations/-":
                relations.append(operation["value"])
            else:
                raise AssertionError(f"unexpected patch: {operation}")


def record(kind: str) -> dict[str, object]:
    common: dict[str, object] = {
        "kind": kind,
        "title": f"{kind} title",
        "summary": f"{kind} summary",
    }
    specific = {
        "feature": {"outcome": "outcome", "scope": "scope", "acceptance": "acceptance"},
        "task": {"action": "action", "done_when": "done"},
        "bug": {
            "expected": "expected",
            "actual": "actual",
            "evidence": "evidence",
            "impact": "impact",
            "resolution": "resolution",
        },
        "mistake": {
            "evidence": "evidence",
            "cause": "cause",
            "governing_rule": "rule",
            "prevention": "prevention",
            "verification": "verification",
        },
        "debt": {
            "compromise": "compromise",
            "deferred_reason": "reason",
            "impact": "impact",
            "exit_condition": "exit",
        },
    }
    return {**common, **specific[kind]}


def tracker() -> tuple[Tracker, FakeAzure]:
    api = FakeAzure()
    return Tracker(
        Path(), CONFIG, api, MemoryJournal(), fields=FIELDS, lifecycle=LIFECYCLE
    ), api


def item_id(item: Mapping[str, object]) -> int:
    value = item["id"]
    assert isinstance(value, int)
    return value


@pytest.mark.parametrize(
    "fields",
    [
        {"repository": "Custom.Repository", "request": "Custom.Request"},
        {
            "repository": "Custom.Repository",
            "request": "Custom.Repository",
            "record": "Custom.Record",
        },
        {
            "repository": "not a reference",
            "request": "Custom.Request",
            "record": "Custom.Record",
        },
    ],
)
def test_tracker_requires_complete_distinct_azure_reference_fields(
    fields: Mapping[str, str],
) -> None:
    with pytest.raises(ItemError, match="managed-field"):
        Tracker(
            Path(),
            CONFIG,
            FakeAzure(),
            MemoryJournal(),
            fields=fields,
            lifecycle=LIFECYCLE,
        )


@pytest.mark.parametrize("kind", ["feature", "task", "bug", "mistake", "debt"])
def test_create_persists_every_supported_kind(kind: str) -> None:
    value, api = tracker()
    created = value.create(record(kind), f"create-{kind}")
    assert created["kind"] == kind
    assert created["state"] == "New"
    assert created["record"] == record(kind)
    fields = api.items[item_id(created)]["fields"]
    assert isinstance(fields, dict)
    assert fields["Custom.PersonalRepository"] == CONFIG["repository"]


def test_create_deduplicates_a_closed_work_item_without_reopening() -> None:
    value, _ = tracker()
    created = value.create(record("task"), "closed-task")
    value.set_state(str(created["url"]), "closed")
    repeated = value.create(record("task"), "closed-task")
    assert repeated["reconciled"] is True
    assert repeated["state"] == "Closed"


@pytest.mark.parametrize("mutation", ["kind", "hash", "repository"])
def test_read_rejects_wrong_managed_metadata(mutation: str) -> None:
    value, api = tracker()
    created = value.create(record("feature"), "metadata-feature")
    stored = api.items[item_id(created)]
    fields = stored["fields"]
    assert isinstance(fields, dict)
    if mutation == "kind":
        fields["System.WorkItemType"] = "Task"
    elif mutation == "hash":
        metadata = json.loads(str(fields["Custom.PersonalRecord"]))
        metadata["sha256"] = "0" * 64
        fields["Custom.PersonalRecord"] = json.dumps(metadata)
    else:
        fields["Custom.PersonalRepository"] = "tommyboy4050/other"
    with pytest.raises(ItemError):
        value.read(str(created["url"]))


def test_read_rejects_foreign_or_shorthand_url() -> None:
    value, _ = tracker()
    with pytest.raises(ItemError, match="full managed"):
        value.read("1")
    with pytest.raises(ItemError, match="full managed"):
        value.read(
            "https://dev.azure.com/other/Personal%20work%20items/_workitems/edit/1"
        )


def test_task_parent_uses_and_replaces_native_hierarchy_relation() -> None:
    value, api = tracker()
    first = value.create(record("feature"), "feature-first")
    second = value.create(
        {**record("feature"), "title": "other feature"}, "feature-second"
    )
    task = value.create(record("task"), "task-parented", str(first["url"]))
    changed = value.set_parent(str(task["url"]), str(second["url"]))
    relations = api.items[item_id(changed)]["relations"]
    assert relations == [
        {
            "rel": "System.LinkTypes.Hierarchy-Reverse",
            "url": f"https://dev.azure.com/tj-agents/_apis/wit/workItems/{second['id']}",
        }
    ]


def test_update_conflict_requires_reconciliation() -> None:
    value, api = tracker()
    created = value.create(record("task"), "conflict-task")
    api.conflict_next = True
    with pytest.raises(ItemError, match="changed"):
        value.update(str(created["url"]), {**record("task"), "title": "updated title"})


def test_timeout_after_persist_reconciles_without_a_second_post() -> None:
    value, api = tracker()
    api.persist_then_timeout = True
    created = value.create(record("bug"), "timeout-bug")
    assert created["reconciled"] is True
    assert api.posts == 1
    assert len(api.items) == 1


def test_duplicate_request_ids_fail_loudly() -> None:
    value, api = tracker()
    created = value.create(record("debt"), "duplicate-debt")
    duplicate = copy.deepcopy(api.items[item_id(created)])
    duplicate["id"] = 99
    api.items[99] = duplicate
    with pytest.raises(ItemError, match="multiple Azure"):
        value.create(record("debt"), "duplicate-debt")


def test_list_does_not_hide_an_unauthorized_query() -> None:
    value, api = tracker()
    api.unauthorized_wiql = True
    with pytest.raises(APIError, match="401"):
        value.list_items()


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def read(self) -> bytes:
        return self.body

    def close(self) -> None:
        return None


def test_client_uses_fixed_wit_endpoint_and_safe_pat_auth() -> None:
    captured: dict[str, object] = {}

    def open_request(request: Any, timeout: float) -> FakeResponse:
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        captured["timeout"] = timeout
        return FakeResponse(b'{"ok":true}')

    client = Client(CONFIG, "token-value", open_request)
    assert client.request("GET", "workitems/1") == {"ok": True}
    assert (
        captured["url"]
        == "https://dev.azure.com/tj-agents/Personal%20work%20items/_apis/wit/workitems/1?api-version=7.1"
    )
    assert captured["authorization"] == "Basic d29yay1pdGVtczp0b2tlbi12YWx1ZQ=="
    assert captured["timeout"] == 15.0


def test_client_error_does_not_expose_server_body_or_token() -> None:
    def fail_request(request: Any, timeout: float) -> FakeResponse:
        raise HTTPError(
            request.full_url,
            401,
            "unauthorized",
            Message(),
            io.BytesIO(b"server-secret"),
        )

    client = Client(CONFIG, "token-value", fail_request)
    with pytest.raises(APIError) as captured:
        client.request("GET", "workitems/1")
    assert "server-secret" not in str(captured.value)
    assert "token-value" not in str(captured.value)


def test_client_scopes_bearer_requests_to_the_configured_work_team() -> None:
    captured: dict[str, object] = {}

    def open_request(request: Any, timeout: float) -> FakeResponse:
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        return FakeResponse(b'{"value":[]}')

    client = Client(
        CONFIG,
        "bearer-token",
        open_request,
        authentication="bearer",
        api_area="work",
        team="CRIS Team",
    )
    assert client.request("GET", "teamsettings/iterations?$timeframe=current") == {
        "value": []
    }
    assert captured["url"] == (
        "https://dev.azure.com/tj-agents/Personal%20work%20items/CRIS%20Team/"
        "_apis/work/teamsettings/iterations?%24timeframe=current&api-version=7.1"
    )
    assert captured["authorization"] == "Bearer bearer-token"


def test_client_snapshots_the_validated_identity_before_request() -> None:
    config = {"organization": "tj-agents", "project": "Personal work items"}
    captured: dict[str, object] = {}

    def open_request(request: Any, timeout: float) -> FakeResponse:
        captured["url"] = request.full_url
        return FakeResponse(b'{"ok":true}')

    client = Client(config, "token-value", open_request)
    config["organization"] = "other"
    config["project"] = "Other"
    assert client.request("GET", "workitems/1") == {"ok": True}
    assert captured["url"] == (
        "https://dev.azure.com/tj-agents/Personal%20work%20items/"
        "_apis/wit/workitems/1?api-version=7.1"
    )


@pytest.mark.parametrize("suffix", ["%2e%2e/workitems/1", "a/%5cworkitems/1"])
def test_client_rejects_encoded_path_escape(suffix: str) -> None:
    client = Client(CONFIG, "token-value")
    with pytest.raises(APIError, match="endpoint"):
        client.request("GET", suffix)


def test_uncertain_create_requires_verified_parent_before_success() -> None:
    value, api = tracker()
    parent = value.create(record("feature"), "parent-for-uncertain-child")
    api.drop_created_parent = True
    api.persist_then_timeout = True
    for _ in range(2):
        with pytest.raises(ItemError, match="parent"):
            value.create(record("task"), "uncertain-child", str(parent["url"]))
    assert api.posts == 2


def test_completed_receipt_requires_parent_when_query_index_lags() -> None:
    value, api = tracker()
    parent = value.create(record("feature"), "parent-for-receipt-child")
    child = value.create(record("task"), "receipt-child", str(parent["url"]))
    api.items[item_id(child)]["relations"] = []
    api.hide_query_results = True
    with pytest.raises(ItemError, match="parent"):
        value.create(record("task"), "receipt-child", str(parent["url"]))
    assert api.posts == 2


@pytest.mark.parametrize("field", ["System.Title", "System.Description"])
@pytest.mark.parametrize("operation", ["read", "list"])
def test_current_facts_reject_human_content_edits(field: str, operation: str) -> None:
    value, api = tracker()
    created = value.create(record("bug"), "human-edited-bug")
    fields = api.items[item_id(created)]["fields"]
    assert isinstance(fields, dict)
    fields[field] = "New facts entered through Azure UI"
    with pytest.raises(ItemError, match="edited outside"):
        if operation == "read":
            value.read(str(created["url"]))
        else:
            value.list_items()


@pytest.mark.parametrize("state", ["Closed", "Removed"])
def test_default_list_excludes_inactive_items_but_preserves_history(state: str) -> None:
    value, api = tracker()
    created = value.create(record("bug"), "inactive-bug")
    fields = api.items[item_id(created)]["fields"]
    assert isinstance(fields, dict)
    fields["System.State"] = state
    assert value.list_items() == []
    history = value.list_items(include_closed=True)
    assert len(history) == 1
    assert history[0]["state"] == state


@pytest.mark.parametrize("native_type", ["User Story", "User Story/Review #1?"])
def test_create_quotes_native_type_as_one_segment_through_http_client(
    native_type: str,
) -> None:
    config = copy.deepcopy(CONFIG)
    config["kinds"] = {"feature": native_type}
    api = FakeAzure()
    urls: list[str] = []

    def open_request(request: Any, timeout: float) -> FakeResponse:
        urls.append(request.full_url)
        suffix = urlsplit(request.full_url).path.split("/_apis/wit/", 1)[1]
        payload = json.loads(request.data) if request.data is not None else None
        result = api.request(request.method, suffix, payload)
        return FakeResponse(json.dumps(result).encode("utf-8"))

    value = Tracker(
        Path(),
        config,
        Client(config, "unused-token", open_request),
        MemoryJournal(),
        fields=FIELDS,
        lifecycle={"feature": LIFECYCLE["feature"]},
    )
    created = value.create(record("feature"), "quoted-type")
    assert created["kind"] == "feature"
    expected = {
        "User Story": "User%20Story",
        "User Story/Review #1?": "User%20Story%2FReview%20%231%3F",
    }[native_type]
    assert any(url.endswith(f"/workitems/${expected}?api-version=7.1") for url in urls)


@pytest.mark.parametrize(
    "lifecycle",
    [
        {},
        {"task": LIFECYCLE["task"]},
        {**LIFECYCLE, "unknown": LIFECYCLE["task"]},
        {**LIFECYCLE, "task": {"open": "ToDo", "closed": "Done"}},
        {**LIFECYCLE, "task": {"open": "ToDo", "closed": "Done", "inactive": "Done"}},
        {**LIFECYCLE, "task": {"open": "ToDo", "closed": "Done", "inactive": []}},
        {**LIFECYCLE, "task": {"open": "Done", "closed": "Done", "inactive": ["Done"]}},
        {**LIFECYCLE, "task": {"open": " ", "closed": "Done", "inactive": ["Done"]}},
        {**LIFECYCLE, "task": {"open": "ToDo", "closed": " ", "inactive": [" "]}},
        {
            **LIFECYCLE,
            "task": {"open": "ToDo", "closed": "Done", "inactive": ["Done", ""]},
        },
        {
            **LIFECYCLE,
            "task": {"open": "ToDo", "closed": "Done", "inactive": ["Done", 1]},
        },
        {
            **LIFECYCLE,
            "task": {
                "open": "ToDo",
                "closed": "Done",
                "inactive": ["Done"],
                "extra": "x",
            },
        },
    ],
)
def test_invalid_lifecycle_refuses_before_azure_access(
    lifecycle: Mapping[str, Mapping[str, object]],
) -> None:
    api = FakeAzure()
    with pytest.raises(ItemError, match="lifecycle"):
        Tracker(
            Path(), CONFIG, api, MemoryJournal(), fields=FIELDS, lifecycle=lifecycle
        )
    assert api.calls == []


def test_lifecycle_is_required() -> None:
    with pytest.raises(TypeError, match="lifecycle"):
        Tracker(Path(), CONFIG, FakeAzure(), MemoryJournal(), fields=FIELDS)


def test_per_kind_lifecycle_targets_filters_and_copies_policy() -> None:
    api = FakeAzure()
    task_inactive = ["Done", "Canceled"]
    lifecycle = {
        **LIFECYCLE,
        "task": {"open": "ToDo", "closed": "Done", "inactive": task_inactive},
        "feature": {
            "open": "Planned",
            "closed": "Delivered",
            "inactive": ["Delivered"],
        },
    }
    value = Tracker(
        Path(), CONFIG, api, MemoryJournal(), fields=FIELDS, lifecycle=lifecycle
    )
    task_inactive.clear()
    lifecycle["task"]["closed"] = "Wrong"
    lifecycle["feature"]["open"] = "Wrong"
    task = value.create(record("task"), "policy-task")
    feature = value.create(record("feature"), "policy-feature")
    assert value.set_state(str(task["url"]), "closed")["state"] == "Done"
    assert value.set_state(str(feature["url"]), "closed")["state"] == "Delivered"
    assert value.list_items() == []
    assert len(value.list_items(include_closed=True)) == 2
    assert value.set_state(str(task["url"]), "open")["state"] == "ToDo"
    assert value.set_state(str(feature["url"]), "open")["state"] == "Planned"
    fields = api.items[item_id(feature)]["fields"]
    assert isinstance(fields, dict)
    fields["System.State"] = "Done"
    assert {item["id"] for item in value.list_items()} == {task["id"], feature["id"]}
    assert [item["id"] for item in value.list_items("task")] == [task["id"]]
    value.set_state(str(task["url"]), "closed")
    assert [item["id"] for item in value.list_items()] == [feature["id"]]
    assert value.list_items("task") == []
    api.ignore_state_filter = True
    with pytest.raises(ItemError, match="closed work item"):
        value.list_items()


@pytest.mark.parametrize("count", [1000, 1001])
def test_list_limit_returns_exactly_1000_or_refuses_before_partial_reads(
    count: int,
) -> None:
    value, api = tracker()
    created = value.create(record("task"), "list-limit")
    seed = api.items[item_id(created)]
    api.items = {
        identifier: {**copy.deepcopy(seed), "id": identifier}
        for identifier in range(1, count + 1)
    }
    api.calls.clear()
    if count == 1000:
        result = value.list_items()
        assert len(result) == 1000
        assert {item["id"] for item in result} == set(range(1, 1001))
    else:
        with pytest.raises(ItemError, match="exceeds the 1000-item limit"):
            value.list_items()
        assert len(api.calls) == 1
    assert api.calls[0][0:2] == ("POST", "wiql?$top=1001")


@pytest.mark.parametrize("field", ["System.Title", "System.Description"])
@pytest.mark.parametrize(
    "operation", ["create", "uncertain-create", "receipt", "update"]
)
def test_write_readback_rejects_visible_content_edits(
    field: str, operation: str
) -> None:
    api = FakeAzure()
    journal = MemoryJournal()
    value = Tracker(Path(), CONFIG, api, journal, fields=FIELDS, lifecycle=LIFECYCLE)
    facts = record("task")
    if operation in {"receipt", "update"}:
        created = value.create(facts, "visible-content")
        if operation == "receipt":
            fields = api.items[item_id(created)]["fields"]
            assert isinstance(fields, dict)
            fields[field] = "Facts changed through Azure UI"
            api.hide_query_results = True
    api.edit_after_write = field
    api.persist_then_timeout = operation == "uncertain-create"
    with pytest.raises(ItemError, match="edited outside"):
        if operation == "update":
            value.update(str(created["url"]), {**facts, "title": "Updated task"})
        else:
            value.create(facts, "visible-content")
    assert api.posts == 1
    if operation in {"create", "uncertain-create"}:
        assert all(
            receipt["resource_id"] is None for receipt in journal.receipts.values()
        )
        with pytest.raises(ItemError, match="edited outside"):
            value.create(facts, "visible-content")
        assert api.posts == 1


@pytest.mark.parametrize("role", ["repository", "request", "record"])
@pytest.mark.parametrize(
    "native_field",
    [
        "System.Title",
        "System.Description",
        "System.State",
        "System.TeamProject",
        "System.WorkItemType",
        "System.Id",
        "System.Rev",
        "system.description",
    ],
)
def test_managed_field_collisions_refuse_before_writes(
    role: str, native_field: str
) -> None:
    api = FakeAzure()
    with pytest.raises(ItemError, match="managed-field"):
        Tracker(
            Path(),
            CONFIG,
            api,
            MemoryJournal(),
            fields={**FIELDS, role: native_field},
            lifecycle=LIFECYCLE,
        )
    assert api.calls == []


def test_managed_field_names_must_be_distinct_ignoring_case() -> None:
    api = FakeAzure()
    with pytest.raises(ItemError, match="managed-field"):
        Tracker(
            Path(),
            CONFIG,
            api,
            MemoryJournal(),
            fields={**FIELDS, "request": FIELDS["repository"].lower()},
            lifecycle=LIFECYCLE,
        )
    assert api.calls == []
