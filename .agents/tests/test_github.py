from __future__ import annotations

import json
from typing import Any

import pytest
from tj_work_items.adapters.github import GitHubTracker
from tj_work_items.refs import ItemRef
from tj_work_items.states import State
from tj_work_items.tracker import Repository, TrackerError

REF = ItemRef("github", "github.com/tj-agents/core", "461")
OPTIONS = [{"id": name.lower(), "name": name} for name in ("Todo", "In Progress", "In Review", "Done")]


class FakeGitHub:
    def __init__(self, *, cards: int = 1, options: list[dict[str, str]] = OPTIONS) -> None:
        self.state = "OPEN"
        self.statuses = ["Todo"] * cards
        self.options = options
        self.comments: list[str] = []
        self.calls: list[list[str]] = []

    def issue(self) -> dict[str, Any]:
        return {
            "id": "I_1",
            "number": 461,
            "title": "Shared items",
            "url": "https://github.com/tj-agents/core/issues/461",
            "state": self.state,
            "body": "Body",
            "issueType": {"name": "Feature"},
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
            self.comments.append(body["body"])
            return "{}"
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


def test_issue_on_no_project_cannot_show_in_progress() -> None:
    with pytest.raises(TrackerError, match="no GitHub Project"):
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
