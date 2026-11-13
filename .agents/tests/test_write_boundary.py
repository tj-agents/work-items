from __future__ import annotations

import json
from importlib.metadata import distribution, entry_points
from typing import Any
from urllib.request import Request

import pytest
from tj_work_items.adapters import azure_devops
from tj_work_items.adapters.azure_devops import AzureDevOpsTracker
from tj_work_items.adapters.github import GitHubTracker
from tj_work_items.refs import ItemRef
from tj_work_items.states import State
from tj_work_items.tracker import Repository

STATES = [
    {"name": "New", "category": "Proposed"},
    {"name": "Active", "category": "InProgress"},
    {"name": "Resolved", "category": "Resolved"},
    {"name": "Closed", "category": "Completed"},
]
AZURE_SETTINGS = {
    "organization": "contoso",
    "project": "Product",
    "work_item_type": "Bug",
    "area_path": "Product\\Team",
    "create_fields": {"attribution": {"field": "Custom.Attribution", "values": ["TechOps"]}},
}
OPTIONS = [{"id": name.lower(), "name": name} for name in ("Todo", "In Progress", "In Review", "Done")]
GITHUB_REPOSITORY = Repository("github.com", "tj-agents/core")
GITHUB_REF = ItemRef("github", "github.com/tj-agents/core", "461")
AZURE_ADAPTERS_UNDER_TEST = {GitHubTracker.provider, AzureDevOpsTracker.provider}


def _console_script_for(import_package: str) -> str:
    for entry in entry_points(group="console_scripts"):
        if entry.value.split(":", 1)[0].split(".")[0] == import_package:
            return entry.name
    raise AssertionError(f"no console script registers the {import_package!r} package")


def _identity_fragments() -> frozenset[str]:
    import_package = AzureDevOpsTracker.__module__.split(".")[0]
    installed = distribution(import_package)
    fragments = {installed.metadata["Name"], import_package, _console_script_for(import_package)}
    for project_url in installed.metadata.get_all("Project-URL") or []:
        label, _, url = project_url.partition(",")
        if "marketplace" in label.casefold():
            fragments.add(url.strip())
    return frozenset(fragment.casefold() for fragment in fragments)


IDENTITY = _identity_fragments()


def assert_identity_absent(payload: object) -> None:
    text = json.dumps(payload, default=str).casefold()
    leaked = [fragment for fragment in IDENTITY if fragment in text]
    assert not leaked, f"tool identity leaked into a request: {leaked} in {payload!r}"


def test_identity_fragments_are_derived_from_the_installed_package_metadata() -> None:
    assert {"tj-work-items", "tj_work_items", "tj-item"} == IDENTITY


def test_every_adapter_registered_by_this_package_is_covered_below() -> None:
    from tj_work_items import adapters

    assert set(adapters.available()) == AZURE_ADAPTERS_UNDER_TEST


AzureBody = list[dict[str, Any]] | dict[str, Any] | None
AzureCall = tuple[str, str, AzureBody, str]


class RecordingAzureSender:
    """Records every raw call and answers each one like a minimal Azure DevOps project."""

    def __init__(self) -> None:
        self.calls: list[AzureCall] = []
        self.rev = 1
        self.state = "New"
        self.relations: list[dict[str, str]] = []

    def __call__(self, method: str, url: str, body: AzureBody, content_type: str) -> dict[str, Any]:
        self.calls.append((method, url, body, content_type))
        if method == "POST" and "/workitems/$" in url:
            assert isinstance(body, list)
            title = next(op["value"] for op in body if op["path"] == "/fields/System.Title")
            description = next((op["value"] for op in body if op["path"] == "/fields/System.Description"), "")
            return self._raw(title, description)
        if method == "GET":
            if "/states" in url:
                return {"value": STATES}
            return self._raw()
        if method == "PATCH":
            assert isinstance(body, list)
            operation = body[1]
            if operation["path"] == "/fields/System.State":
                self.state = operation["value"]
            else:
                self.relations.append(operation["value"])
            self.rev += 1
            return self._raw()
        return {}

    def _raw(self, title: str = "Fix login", description: str = "") -> dict[str, Any]:
        return {
            "id": 42,
            "rev": self.rev,
            "fields": {
                "System.Title": title,
                "System.State": self.state,
                "System.WorkItemType": "Bug",
                "System.TeamProject": "Product",
                "System.Description": description,
            },
            "relations": self.relations,
        }


def azure_writes(calls: list[AzureCall]) -> list[AzureCall]:
    return [call for call in calls if call[0] in {"POST", "PATCH"}]


def assert_azure_calls_are_clean(calls: list[AzureCall]) -> None:
    for _method, _url, body, _content_type in calls:
        assert_identity_absent(body)


def azure_ref(sender: RecordingAzureSender | None = None) -> ItemRef:
    del sender
    return ItemRef("azure-devops", "dev.azure.com/contoso", "42")


def test_azure_devops_create_sends_only_the_caller_and_profile_supplied_fields() -> None:
    sender = RecordingAzureSender()
    tracker = AzureDevOpsTracker(AZURE_SETTINGS, None, send=sender)

    tracker.create("New feature", "Details", None, {"attribution": "TechOps"})

    writes = azure_writes(sender.calls)
    assert len(writes) == 1
    method, _url, body, content_type = writes[0]
    assert isinstance(body, list)
    assert method == "POST"
    assert content_type == "application/json-patch+json"
    assert {operation["path"] for operation in body} == {
        "/fields/System.Title",
        "/fields/System.Description",
        "/fields/System.AreaPath",
        "/fields/Custom.Attribution",
    }
    assert all(set(operation) == {"op", "path", "value"} for operation in body)
    assert_azure_calls_are_clean(sender.calls)


def test_azure_devops_create_with_an_azure_parent_links_only_the_relation() -> None:
    sender = RecordingAzureSender()
    tracker = AzureDevOpsTracker(AZURE_SETTINGS, None, send=sender)
    parent = ItemRef("azure-devops", "dev.azure.com/contoso", "100")

    tracker.create("New feature", "Details", parent, {"attribution": "TechOps"})

    writes = azure_writes(sender.calls)
    assert len(writes) == 2
    method, _url, body, content_type = writes[1]
    assert isinstance(body, list)
    assert method == "PATCH"
    assert content_type == "application/json-patch+json"
    assert len(body) == 2
    assert body[0] == {"op": "test", "path": "/rev", "value": sender.rev - 1}
    relation = body[1]
    assert relation["path"] == "/relations/-"
    assert set(relation["value"]) == {"rel", "url"}
    assert relation["value"]["rel"] == "System.LinkTypes.Hierarchy-Reverse"
    assert_azure_calls_are_clean(sender.calls)


def test_azure_devops_transition_sends_only_the_state_patch() -> None:
    sender = RecordingAzureSender()
    tracker = AzureDevOpsTracker(AZURE_SETTINGS, None, send=sender)

    tracker.transition(azure_ref(), State.IN_PROGRESS)

    writes = azure_writes(sender.calls)
    assert len(writes) == 1
    method, _url, body, _content_type = writes[0]
    assert isinstance(body, list)
    assert method == "PATCH"
    assert len(body) == 2
    assert body[1] == {"op": "add", "path": "/fields/System.State", "value": "Active"}
    assert_azure_calls_are_clean(sender.calls)


def test_azure_devops_comment_sends_only_the_escaped_text() -> None:
    sender = RecordingAzureSender()
    tracker = AzureDevOpsTracker(AZURE_SETTINGS, None, send=sender)

    tracker.comment(azure_ref(), "a < b")

    writes = azure_writes(sender.calls)
    assert len(writes) == 1
    method, _url, body, _content_type = writes[0]
    assert isinstance(body, dict)
    assert method == "POST"
    assert set(body) == {"text"}
    assert body["text"] == "a &lt; b"
    assert_azure_calls_are_clean(sender.calls)


def test_azure_devops_link_artifact_adds_only_the_relation() -> None:
    sender = RecordingAzureSender()
    tracker = AzureDevOpsTracker(AZURE_SETTINGS, None, send=sender)

    tracker.link_artifact(azure_ref(), "https://github.com/contoso/app/pull/3")

    writes = azure_writes(sender.calls)
    assert len(writes) == 1
    method, _url, body, _content_type = writes[0]
    assert isinstance(body, list)
    assert method == "PATCH"
    relation = body[1]
    assert set(relation["value"]) == {"rel", "url"}
    assert relation["value"] == {"rel": "Hyperlink", "url": "https://github.com/contoso/app/pull/3"}
    assert_azure_calls_are_clean(sender.calls)


class _FakeHttpResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def __enter__(self) -> _FakeHttpResponse:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        return None

    def read(self) -> bytes:
        return self._data


def test_http_sender_adds_no_header_beyond_authorization_accept_and_content_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[Request] = []

    def fake_urlopen(request: Request, timeout: int = 60) -> _FakeHttpResponse:
        captured.append(request)
        return _FakeHttpResponse(b"{}")

    monkeypatch.setattr(azure_devops, "urlopen", fake_urlopen)
    send = azure_devops.http_sender(lambda: "Bearer token")

    send(
        "POST",
        "https://dev.azure.com/contoso/_apis/wit/workitems/$Bug?api-version=7.1",
        [{"op": "add", "path": "/fields/System.Title", "value": "x"}],
        "application/json-patch+json",
    )
    send(
        "GET",
        "https://dev.azure.com/contoso/_apis/wit/workitems/42?api-version=7.1",
        None,
        "application/json",
    )

    assert len(captured) == 2
    with_body, without_body = captured
    assert {name.lower() for name, _value in with_body.header_items()} == {
        "authorization",
        "accept",
        "content-type",
    }
    assert {name.lower() for name, _value in without_body.header_items()} == {"authorization", "accept"}
    for request in captured:
        assert "user-agent" not in {name.lower() for name, _value in request.header_items()}
        assert_identity_absent(dict(request.header_items()))


class RecordingGithubRunner:
    """Records every `gh` invocation and answers each one like a minimal GitHub repository."""

    def __init__(self, *, cards: int = 1, linked_projects: int = 0) -> None:
        self.calls: list[tuple[list[str], str | None]] = []
        self.state = "OPEN"
        self.number = 461
        self.statuses: list[str] = ["Todo"] * cards
        self.linked_projects = linked_projects
        self.comments: list[str] = []

    def __call__(self, arguments: list[str], payload: str | None) -> str:
        self.calls.append((list(arguments), payload))
        body: dict[str, Any] = json.loads(payload) if payload else {}
        if arguments[:2] == ["api", "graphql"]:
            return self._graphql(body["query"], body.get("variables", {}))
        if arguments[1:3] == ["-X", "PATCH"]:
            self.state = "CLOSED" if body["state"] == "closed" else "OPEN"
            return "{}"
        if arguments[1:3] == ["-X", "POST"]:
            return self._post(arguments[3], body)
        return json.dumps([{"body": comment} for comment in self.comments])

    def _graphql(self, query: str, variables: dict[str, Any]) -> str:
        if "addProjectV2ItemById" in query:
            self.statuses.append("")
            item = {"id": f"PVTI_{len(self.statuses) - 1}"}
            return json.dumps({"data": {"addProjectV2ItemById": {"item": item}}})
        if "projectsV2(" in query:
            projects = [
                {"id": f"P_{i}", "title": f"Board {i}", "closed": False} for i in range(self.linked_projects)
            ]
            return json.dumps({"data": {"repository": {"projectsV2": {"nodes": projects}}}})
        if "updateProjectV2ItemFieldValue" in query:
            index = int(str(variables["item"]).removeprefix("PVTI_"))
            name = next(option["name"] for option in OPTIONS if option["id"] == variables["option"])
            self.statuses[index] = name
            return json.dumps({"data": {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "x"}}}})
        if "field(name" in query:
            field = {"id": "F_status", "options": OPTIONS}
            return json.dumps({"data": {"node": {"field": field}}})
        return json.dumps({"data": {"repository": {"issue": self._issue()}}})

    def _post(self, path: str, body: dict[str, Any]) -> str:
        if path.endswith("/comments"):
            self.comments.append(str(body["body"]))
            return "{}"
        if path.endswith("/sub_issues"):
            return "{}"
        self.number = 500
        self.state = "OPEN"
        return json.dumps({"number": 500, "id": 90001, "node_id": "I_new"})

    def _issue(self) -> dict[str, Any]:
        return {
            "id": "I_1",
            "number": self.number,
            "title": "Shared items",
            "url": f"https://github.com/tj-agents/core/issues/{self.number}",
            "state": self.state,
            "body": "Body",
            "issueType": {"name": "Feature"},
            "labels": {"nodes": []},
            "assignees": {"nodes": []},
            "repository": {"nameWithOwner": "tj-agents/core"},
            "projectItems": {
                "nodes": [
                    {
                        "id": f"PVTI_{i}",
                        "project": {"id": f"P_{i}", "title": f"Board {i}"},
                        "status": {"name": s},
                    }
                    for i, s in enumerate(self.statuses)
                ]
            },
        }


def github_writes(calls: list[tuple[list[str], str | None]]) -> list[tuple[list[str], str | None]]:
    writes = []
    for arguments, payload in calls:
        if arguments[1:3] in (["-X", "POST"], ["-X", "PATCH"]) or (
            arguments[:2] == ["api", "graphql"]
            and payload is not None
            and "mutation(" in json.loads(payload)["query"]
        ):
            writes.append((arguments, payload))
    return writes


def assert_github_calls_are_clean(calls: list[tuple[list[str], str | None]]) -> None:
    for arguments, payload in calls:
        assert "-H" not in arguments
        assert "--header" not in arguments
        assert_identity_absent(arguments)
        if payload is not None:
            assert_identity_absent(json.loads(payload))


def test_github_create_sends_only_title_and_body() -> None:
    runner = RecordingGithubRunner(cards=0, linked_projects=1)
    tracker = GitHubTracker({}, GITHUB_REPOSITORY, run=runner)

    tracker.create("New feature", "Details", None, {})

    writes = github_writes(runner.calls)
    rest_creates = [
        call
        for call in writes
        if call[0][1:3] == ["-X", "POST"] and call[0][3] == "repos/tj-agents/core/issues"
    ]
    assert len(rest_creates) == 1
    body = json.loads(rest_creates[0][1] or "{}")
    assert body == {"title": "New feature", "body": "Details"}

    variable_key_sets = {
        frozenset(json.loads(payload)["variables"])
        for arguments, payload in writes
        if arguments[:2] == ["api", "graphql"] and payload is not None
    }
    assert variable_key_sets == {
        frozenset({"project", "content"}),
        frozenset({"project", "item", "field", "option"}),
    }
    assert_github_calls_are_clean(runner.calls)


def test_github_create_with_a_github_parent_adds_only_the_sub_issue_id() -> None:
    runner = RecordingGithubRunner(cards=0, linked_projects=1)
    tracker = GitHubTracker({}, GITHUB_REPOSITORY, run=runner)
    parent = ItemRef("github", "github.com/tj-agents/core", "100")

    tracker.create("New feature", "Details", parent, {})

    sub_issue_calls = [
        call
        for call in github_writes(runner.calls)
        if call[0][1:3] == ["-X", "POST"] and call[0][3].endswith("/sub_issues")
    ]
    assert len(sub_issue_calls) == 1
    body = json.loads(sub_issue_calls[0][1] or "{}")
    assert set(body) == {"sub_issue_id"}
    assert body == {"sub_issue_id": 90001}
    assert_github_calls_are_clean(runner.calls)


def test_github_transition_to_done_sends_only_status_and_close_fields() -> None:
    runner = RecordingGithubRunner(cards=1)
    tracker = GitHubTracker({}, GITHUB_REPOSITORY, run=runner)

    tracker.transition(GITHUB_REF, State.DONE)

    writes = github_writes(runner.calls)
    patches = [call for call in writes if call[0][1:3] == ["-X", "PATCH"]]
    assert len(patches) == 1
    body = json.loads(patches[0][1] or "{}")
    assert body == {"state": "closed", "state_reason": "completed"}

    variable_key_sets = {
        frozenset(json.loads(payload)["variables"])
        for arguments, payload in writes
        if arguments[:2] == ["api", "graphql"] and payload is not None
    }
    assert variable_key_sets == {frozenset({"project", "item", "field", "option"})}
    assert_github_calls_are_clean(runner.calls)


def test_github_comment_and_link_artifact_send_only_the_body_text() -> None:
    runner = RecordingGithubRunner(cards=1)
    tracker = GitHubTracker({}, GITHUB_REPOSITORY, run=runner)

    tracker.comment(GITHUB_REF, "hello")
    tracker.link_artifact(GITHUB_REF, "https://github.com/tj-agents/core/pull/9")

    writes = github_writes(runner.calls)
    bodies = [json.loads(payload or "{}") for _arguments, payload in writes]
    assert all(set(body) == {"body"} for body in bodies)
    assert bodies == [
        {"body": "hello"},
        {"body": "Linked: https://github.com/tj-agents/core/pull/9"},
    ]
    assert_github_calls_are_clean(runner.calls)
