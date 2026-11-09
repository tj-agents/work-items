from __future__ import annotations

import json
from typing import Any

import pytest
from tj_work_items.adapters.github import GitHubTracker
from tj_work_items.refs import ItemRef
from tj_work_items.states import State
from tj_work_items.tracker import ConfigError, Repository, TrackerError

REF = ItemRef("github", "github.com/tj-agents/core", "461")
PULL_NODE = {
    "url": "https://github.com/tj-agents/core/pull/9",
    "state": "MERGED",
    "title": "Fix it",
    "body": "Closes #461",
    "headRefName": "Fix/It",
}
OPTIONS = [{"id": name.lower(), "name": name} for name in ("Todo", "In Progress", "In Review", "Done")]


class FakeGitHub:
    def __init__(self, *, cards: int = 1, options: list[dict[str, str]] = OPTIONS) -> None:
        self.state = "OPEN"
        self.number = 461
        self.statuses = ["Todo"] * cards
        self.options = options
        self.comments: list[str] = []
        self.labels: list[str] = []
        self.linked = 0
        self.closing = False
        self.calls: list[list[str]] = []
        self.created: dict[str, Any] | None = None
        self.sub_issues: list[tuple[str, int]] = []

    def issue(self) -> dict[str, Any]:
        return {
            "id": "I_1",
            "number": self.number,
            "title": "Shared items",
            "url": f"https://github.com/tj-agents/core/issues/{self.number}",
            "state": self.state,
            "body": "Body",
            "issueType": {"name": "Task"} if self.labels else {"name": "Feature"},
            "labels": {"nodes": [{"name": name} for name in self.labels]},
            "assignees": {"nodes": [{"login": "tommy"}]},
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

    def __call__(self, arguments: list[str], payload: str | None) -> str:
        self.calls.append(arguments)
        body = json.loads(payload) if payload else {}
        if arguments[:2] == ["api", "graphql"]:
            query, variables = body["query"], body["variables"]
            if "closedByPullRequestsReferences" in query:
                nodes: list[dict[str, Any]] = [PULL_NODE] if self.closing else []
                issue = {"closedByPullRequestsReferences": {"nodes": nodes}}
                return json.dumps({"data": {"repository": {"issue": issue}}})
            if "pullRequest(" in query:
                node = {**PULL_NODE, "url": f"https://github.com/tj-agents/core/pull/{variables['number']}"}
                return json.dumps({"data": {"repository": {"pullRequest": node}}})
            if "addProjectV2ItemById" in query:
                self.statuses.append("")
                item = {"id": f"PVTI_{len(self.statuses) - 1}"}
                return json.dumps({"data": {"addProjectV2ItemById": {"item": item}}})
            if "projectsV2(" in query:
                projects: list[dict[str, Any]] = [
                    {"id": f"P_{i}", "title": f"Board {i}", "closed": False} for i in range(self.linked)
                ]
                return json.dumps({"data": {"repository": {"projectsV2": {"nodes": projects}}}})
            if "updateProjectV2ItemFieldValue" in query:
                index = int(variables["item"].removeprefix("PVTI_"))
                name = next(o["name"] for o in self.options if o["id"] == variables["option"])
                self.statuses[index] = name
                return json.dumps({"data": {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "x"}}}})
            if "field(name" in query:
                field = {"id": "F_status", "options": self.options}
                return json.dumps({"data": {"node": {"field": field}}})
            if "search(" in query:
                return json.dumps({"data": {"search": {"nodes": [self.issue()]}}})
            return json.dumps({"data": {"repository": {"issue": self.issue()}}})
        if arguments[1:3] == ["-X", "PATCH"]:
            self.state = "CLOSED" if body["state"] == "closed" else "OPEN"
            return "{}"
        if arguments[1:3] == ["-X", "POST"]:
            path = arguments[3]
            if path.endswith("/comments"):
                self.comments.append(body["body"])
                return "{}"
            if path.endswith("/sub_issues"):
                self.sub_issues.append((path, body["sub_issue_id"]))
                return "{}"
            self.created = body
            self.number = 500
            self.state = "OPEN"
            return json.dumps({"number": 500, "id": 90001, "node_id": "I_new"})
        return json.dumps([{"body": comment} for comment in self.comments])


def tracker(fake: FakeGitHub, **settings: Any) -> GitHubTracker:
    return GitHubTracker(settings, Repository("github.com", "tj-agents/core"), run=fake)


def test_resolve_reads_status_kind_and_assignees() -> None:
    item = tracker(FakeGitHub()).resolve(REF)
    assert (item.state, item.native_state, item.kind, item.assignees) == (
        State.TO_DO,
        "Todo",
        "feature",
        ("tommy",),
    )


def test_progress_moves_every_card_to_in_review() -> None:
    fake = FakeGitHub(cards=2)
    item = tracker(fake).transition(REF, State.IN_REVIEW)
    assert fake.statuses == ["In Review", "In Review"]
    assert item.state is State.IN_REVIEW
    assert fake.state == "OPEN"


def test_done_closes_the_issue() -> None:
    fake = FakeGitHub()
    assert tracker(fake).transition(REF, State.DONE).state is State.DONE
    assert fake.state == "CLOSED"


def test_board_without_the_option_names_the_available_options() -> None:
    fake = FakeGitHub(options=[{"id": "t", "name": "Todo"}, {"id": "d", "name": "Done"}])
    with pytest.raises(TrackerError, match="available: Todo, Done"):
        tracker(fake).transition(REF, State.IN_REVIEW)


def test_profile_state_map_overrides_option_names() -> None:
    options = [*OPTIONS, {"id": "qa", "name": "QA"}]
    fake = FakeGitHub(options=options)
    item = tracker(fake, states={"In Review": "QA"}).transition(REF, State.IN_REVIEW)
    assert (fake.statuses, item.state) == (["QA"], State.IN_REVIEW)


def test_issue_on_no_project_is_placed_on_the_repository_projects() -> None:
    fake = FakeGitHub(cards=0)
    fake.linked = 1
    item = tracker(fake).transition(REF, State.IN_REVIEW)
    assert (fake.statuses, item.state) == (["In Review"], State.IN_REVIEW)


def test_repository_without_a_linked_project_says_so() -> None:
    with pytest.raises(TrackerError, match="no linked GitHub Project"):
        tracker(FakeGitHub(cards=0)).transition(REF, State.IN_PROGRESS)


def test_link_is_idempotent() -> None:
    fake = FakeGitHub()
    github = tracker(fake)
    github.link_artifact(REF, "https://github.com/tj-agents/core/pull/9")
    github.link_artifact(REF, "https://github.com/tj-agents/core/pull/9")
    assert fake.comments == ["Linked: https://github.com/tj-agents/core/pull/9"]


def test_list_mine_searches_the_repository_for_your_open_issues() -> None:
    fake = FakeGitHub()
    assert [str(item.ref) for item in tracker(fake).list_mine()] == [str(REF)]
    assert fake.calls[-1][:2] == ["api", "graphql"]


def test_kind_label_beats_the_issue_type() -> None:
    fake = FakeGitHub()
    fake.labels = ["enhancement", "Debt"]
    assert tracker(fake).resolve(REF).kind == "debt"


def test_linked_prs_combine_closing_references_and_linked_comments() -> None:
    fake = FakeGitHub()
    fake.closing = True
    github = tracker(fake)
    github.link_artifact(REF, "https://github.com/tj-agents/core/pull/12")
    pulls = github.linked_prs(REF)
    assert [(pull.url, pull.state, pull.head) for pull in pulls] == [
        ("https://github.com/tj-agents/core/pull/9", "merged", "Fix/It"),
        ("https://github.com/tj-agents/core/pull/12", "merged", "Fix/It"),
    ]


def test_create_places_the_issue_on_the_board_in_to_do() -> None:
    fake = FakeGitHub(cards=0)
    fake.linked = 1
    item = tracker(fake).create("New feature", "Details", None, {})
    assert fake.created == {"title": "New feature", "body": "Details"}
    assert fake.sub_issues == []
    assert (str(item.ref), item.state) == ("github:github.com/tj-agents/core:500", State.TO_DO)


def test_create_with_a_github_parent_adds_a_sub_issue() -> None:
    fake = FakeGitHub(cards=0)
    fake.linked = 1
    parent = ItemRef("github", "github.com/tj-agents/core", "100")
    tracker(fake).create("New feature", "Details", parent, {})
    assert fake.sub_issues == [("repos/tj-agents/core/issues/100/sub_issues", 90001)]
    assert fake.created == {"title": "New feature", "body": "Details"}


def test_create_with_a_foreign_parent_appends_a_body_note() -> None:
    fake = FakeGitHub(cards=0)
    fake.linked = 1
    parent = ItemRef("azure-devops", "dev.azure.com/contoso", "42")
    tracker(fake).create("New feature", "Details", parent, {})
    assert fake.created == {
        "title": "New feature",
        "body": "Details\nParent: azure-devops:dev.azure.com/contoso:42",
    }
    assert fake.sub_issues == []


def test_create_refuses_create_fields() -> None:
    fake = FakeGitHub()
    with pytest.raises(ConfigError, match="takes no create fields: attribution"):
        tracker(fake).create("New feature", "", None, {"attribution": "TechOps"})


def test_create_without_a_github_scope_errors() -> None:
    github = GitHubTracker({}, None)
    with pytest.raises(ConfigError, match=r"github\.com repository scope"):
        github.create("New feature", "", None, {})
