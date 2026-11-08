from __future__ import annotations

from typing import Any

import pytest
from tj_work_items.adapters.azure_devops import AzureDevOpsTracker, HttpStatusError
from tj_work_items.refs import ItemRef
from tj_work_items.states import State
from tj_work_items.tracker import ConfigError, TrackerError

REF = ItemRef("azure-devops", "dev.azure.com/contoso", "42")
STATES = [
    {"name": "New", "category": "Proposed"},
    {"name": "Active", "category": "InProgress"},
    {"name": "Resolved", "category": "Resolved"},
    {"name": "Closed", "category": "Completed"},
    {"name": "Removed", "category": "Removed"},
]


class FakeAzure:
    def __init__(self, *, strict: bool = False, states: list[dict[str, str]] = STATES) -> None:
        self.state, self.rev, self.strict, self.states = "New", 1, strict, states
        self.relations: list[dict[str, str]] = []
        self.comments: list[str] = []
        self.patches: list[str] = []

    def raw(self) -> dict[str, Any]:
        return {
            "id": 42,
            "rev": self.rev,
            "fields": {
                "System.Title": "Fix login",
                "System.State": self.state,
                "System.WorkItemType": "Bug",
                "System.TeamProject": "Product",
                "System.AssignedTo": {"uniqueName": "tommy@contoso.com"},
            },
            "relations": self.relations,
        }

    def __call__(self, method: str, url: str, body: Any, content_type: str) -> Any:
        if "/states" in url:
            return {"value": self.states}
        if method == "GET":
            return self.raw()
        if method == "PATCH":
            assert body[0] == {"op": "test", "path": "/rev", "value": self.rev}
            assert content_type == "application/json-patch+json"
            operation = body[1]
            if operation["path"] == "/fields/System.State":
                names = [entry["name"] for entry in self.states]
                if self.strict and names.index(operation["value"]) - names.index(self.state) > 1:
                    raise HttpStatusError(400, "invalid transition")
                self.state = operation["value"]
                self.patches.append(self.state)
            else:
                self.relations.append(operation["value"])
            self.rev += 1
            return self.raw()
        if "comments" in url:
            self.comments.append(body["text"])
            return {}
        if "wiql" in url:
            return {"workItems": [{"id": 42}]}
        return {"value": [self.raw()]}


def tracker(fake: FakeAzure, **settings: Any) -> AzureDevOpsTracker:
    return AzureDevOpsTracker({"organization": "contoso", "project": "Product", **settings}, None, send=fake)


def test_resolve_maps_the_state_category_to_canonical() -> None:
    item = tracker(FakeAzure()).resolve(REF)
    assert (item.state, item.native_state, item.kind) == (State.TO_DO, "New", "bug")
    assert item.url == "https://dev.azure.com/contoso/Product/_workitems/edit/42"


def test_progress_to_in_review_uses_the_resolved_category() -> None:
    fake = FakeAzure()
    assert tracker(fake).transition(REF, State.IN_REVIEW).state is State.IN_REVIEW
    assert fake.patches == ["Resolved"]


def test_rejected_jump_walks_each_intermediate_state() -> None:
    fake = FakeAzure(strict=True)
    tracker(fake).transition(REF, State.DONE)
    assert fake.patches == ["Active", "Resolved", "Closed"]


def test_profile_state_map_wins_per_work_item_type() -> None:
    states = [*STATES[:2], {"name": "Code Review", "category": "InProgress"}, *STATES[3:]]
    fake = FakeAzure(states=states)
    settings = {"states": {"In Review": "Resolved", "Bug": {"In Review": "Code Review"}}}
    item = tracker(fake, **settings).transition(REF, State.IN_REVIEW)
    assert (fake.patches, item.state) == (["Code Review"], State.IN_REVIEW)


def test_unmapped_blocked_state_asks_for_a_profile_mapping() -> None:
    with pytest.raises(TrackerError, match="map it with the profile"):
        tracker(FakeAzure()).transition(REF, State.BLOCKED)


def test_same_state_is_a_no_op() -> None:
    fake = FakeAzure()
    tracker(fake).transition(REF, State.TO_DO)
    assert fake.patches == []


def test_link_adds_one_hyperlink_relation() -> None:
    fake = FakeAzure()
    ado = tracker(fake)
    ado.link_artifact(REF, "https://github.com/contoso/app/pull/3")
    ado.link_artifact(REF, "https://github.com/contoso/app/pull/3")
    assert fake.relations == [{"rel": "Hyperlink", "url": "https://github.com/contoso/app/pull/3"}]


def test_comment_escapes_html() -> None:
    fake = FakeAzure()
    tracker(fake).comment(REF, "a < b\nnext")
    assert fake.comments == ["a &lt; b<br>next"]


def test_list_mine_drops_completed_items() -> None:
    fake = FakeAzure()
    assert [item.title for item in tracker(fake).list_mine()] == ["Fix login"]
    fake.state = "Closed"
    assert tracker(fake).list_mine() == []


def test_reference_from_another_organization_is_refused() -> None:
    with pytest.raises(ConfigError, match="outside this profile"):
        tracker(FakeAzure()).resolve(ItemRef("azure-devops", "dev.azure.com/other", "1"))


def test_profile_without_organization_is_refused() -> None:
    with pytest.raises(ConfigError, match="organization"):
        AzureDevOpsTracker({"project": "Product"}, None, send=FakeAzure())
