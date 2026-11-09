from __future__ import annotations

import json
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
        self.id = 42
        self.title = "Fix login"
        self.description = ""
        self.created: list[dict[str, Any]] | None = None
        self.created_type: str | None = None

    def raw(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "rev": self.rev,
            "fields": {
                "System.Title": self.title,
                "System.State": self.state,
                "System.WorkItemType": "Bug",
                "System.TeamProject": "Product",
                "System.Description": self.description,
                "System.AssignedTo": {"uniqueName": "tommy@contoso.com"},
            },
            "relations": self.relations,
        }

    def __call__(self, method: str, url: str, body: Any, content_type: str) -> Any:
        if method == "POST" and "/workitems/$" in url:
            self.created_type = url.split("/workitems/$", 1)[1].split("?", 1)[0]
            self.created = body
            self.id, self.rev, self.state = 777, 1, "New"
            self.title = next(op["value"] for op in body if op["path"] == "/fields/System.Title")
            self.description = next(
                (op["value"] for op in body if op["path"] == "/fields/System.Description"), ""
            )
            return self.raw()
        if "/pullrequests/" in url:
            repository = {"webUrl": "https://dev.azure.com/contoso/Product/_git/app"}
            return {
                "status": "active",
                "sourceRefName": "refs/heads/Feature/X",
                "title": "X",
                "repository": repository,
            }
        if "githubconnections" in url:
            return {
                "value": [
                    {"gitHubRepositoryUrl": "https://github.com/contoso/one"},
                    {"gitHubRepositoryUrl": "https://github.com/contoso/two"},
                ]
            }
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


def test_rejected_move_that_still_committed_is_accepted() -> None:
    fake = FakeAzure()
    original = fake.__call__

    def committed_but_rejected(method: str, url: str, body: Any, content_type: str) -> Any:
        if method == "PATCH" and not fake.patches:
            original(method, url, body, content_type)
            raise HttpStatusError(400, "TF401320: Rule Error for field System Area")
        return original(method, url, body, content_type)

    ado = AzureDevOpsTracker(
        {"organization": "contoso", "project": "Product"}, None, send=committed_but_rejected
    )
    assert ado.transition(REF, State.IN_PROGRESS).native_state == "Active"
    assert fake.patches == ["Active"]


def test_linked_prs_read_azure_repos_github_artifacts_and_hyperlinks() -> None:
    fake = FakeAzure()
    fake.relations = [
        {"rel": "ArtifactLink", "url": "vstfs:///Git/PullRequestId/p1%2Fr1%2F7"},
        {"rel": "ArtifactLink", "url": "vstfs:///GitHub/PullRequest/conn%2F5"},
        {"rel": "Hyperlink", "url": "https://github.com/contoso/three/pull/8"},
        {"rel": "Hyperlink", "url": "https://example.com/wiki"},
    ]

    def gh(arguments: list[str], payload: str | None) -> str:
        variables = json.loads(payload or "{}")["variables"]
        repository = f"{variables['owner']}/{variables['name']}"
        body = "Fixes AB#42" if repository in {"contoso/two", "contoso/three"} else "unrelated"
        node = {
            "url": f"https://github.com/{repository}/pull/{variables['number']}",
            "state": "MERGED",
            "title": "t",
            "body": body,
            "headRefName": "AB#42",
        }
        return json.dumps({"data": {"repository": {"pullRequest": node}}})

    ado = AzureDevOpsTracker({"organization": "contoso", "project": "Product"}, None, send=fake, run=gh)
    assert [(pull.url, pull.state, pull.head) for pull in ado.linked_prs(REF)] == [
        ("https://dev.azure.com/contoso/Product/_git/app/pullrequest/7", "open", "Feature/X"),
        ("https://github.com/contoso/two/pull/5", "merged", "AB#42"),
        ("https://github.com/contoso/three/pull/8", "merged", "AB#42"),
    ]


def test_create_places_the_item_in_to_do() -> None:
    fake = FakeAzure()
    item = tracker(fake, work_item_type="Bug").create("Fix login", "Details", None, {})
    assert fake.created_type == "Bug"
    assert fake.created == [
        {"op": "add", "path": "/fields/System.Title", "value": "Fix login"},
        {"op": "add", "path": "/fields/System.Description", "value": "Details"},
    ]
    assert (item.title, item.state, fake.patches) == ("Fix login", State.TO_DO, [])


def test_create_files_the_item_under_the_profile_area_path() -> None:
    fake = FakeAzure()
    tracker(fake, work_item_type="Bug", area_path="Product\\Team").create("Fix login", "", None, {})
    assert fake.created is not None
    assert {"op": "add", "path": "/fields/System.AreaPath", "value": "Product\\Team"} in fake.created


def test_create_with_an_azure_parent_adds_a_hierarchy_relation() -> None:
    fake = FakeAzure()
    parent = ItemRef("azure-devops", "dev.azure.com/contoso", "10")
    tracker(fake, work_item_type="Bug").create("Fix login", "Details", parent, {})
    assert fake.relations == [
        {
            "rel": "System.LinkTypes.Hierarchy-Reverse",
            "url": "https://dev.azure.com/contoso/_apis/wit/workItems/10",
        }
    ]


def test_create_with_a_foreign_parent_appends_a_body_note() -> None:
    fake = FakeAzure()
    parent = ItemRef("github", "github.com/tj-agents/core", "100")
    tracker(fake, work_item_type="Bug").create("Fix login", "Details", parent, {})
    assert fake.created == [
        {"op": "add", "path": "/fields/System.Title", "value": "Fix login"},
        {
            "op": "add",
            "path": "/fields/System.Description",
            "value": "Details\nParent: github:github.com/tj-agents/core:100",
        },
    ]
    assert fake.relations == []


ATTRIBUTION = {"attribution": {"field": "Custom.Attribution", "values": ["TechOps", "TechPlatform"]}}


def test_create_sets_each_declared_field() -> None:
    fake = FakeAzure()
    tracker(fake, work_item_type="Bug", create_fields=ATTRIBUTION).create(
        "Fix login", "", None, {"attribution": "TechPlatform"}
    )
    assert fake.created is not None
    assert {"op": "add", "path": "/fields/Custom.Attribution", "value": "TechPlatform"} in fake.created


@pytest.mark.parametrize("fields", [{}, {"attribution": "Elsewhere"}])
def test_create_without_a_valid_declared_field_lists_its_values(fields: dict[str, str]) -> None:
    fake = FakeAzure()
    with pytest.raises(ConfigError, match=r"--field attribution=<TechOps\|TechPlatform>"):
        tracker(fake, work_item_type="Bug", create_fields=ATTRIBUTION).create("Fix login", "", None, fields)
    assert fake.created is None


def test_create_rejects_an_undeclared_field() -> None:
    with pytest.raises(ConfigError, match="no create field colour"):
        tracker(FakeAzure(), work_item_type="Bug").create("Fix login", "", None, {"colour": "red"})


def test_a_malformed_create_field_declaration_is_a_config_error() -> None:
    with pytest.raises(ConfigError, match="create field `attribution`"):
        tracker(FakeAzure(), create_fields={"attribution": {"field": "Custom.Attribution"}})


def test_create_without_a_configured_work_item_type_errors() -> None:
    with pytest.raises(ConfigError, match="work_item_type"):
        tracker(FakeAzure()).create("Fix login", "", None, {})
