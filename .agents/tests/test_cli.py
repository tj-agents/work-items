from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from tj_work_items import cli, profiles
from tj_work_items.refs import ItemRef
from tj_work_items.states import State
from tj_work_items.tracker import Item, Repository


@pytest.fixture
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(profiles, "repository_at", lambda cwd: Repository("github.com", "tj-agents/core"))
    monkeypatch.setattr(profiles, "installed_profiles", list)


def run(capsys: pytest.CaptureFixture[str], *arguments: str) -> tuple[int, Any]:
    code = cli.main(list(arguments))
    captured = capsys.readouterr()
    return code, json.loads(captured.out if code == 0 else captured.err)


@pytest.mark.parametrize(
    ("action", "arguments"),
    [
        (cli.Action.RESOLVE, ("resolve", "1")),
        (cli.Action.MINE, ("mine",)),
        (cli.Action.PROGRESS, ("progress", "1", "--state", "To do")),
        (cli.Action.COMMENT, ("comment", "1", "--body", "comment")),
        (cli.Action.LINK, ("link", "1", "https://example.com")),
        (cli.Action.PRS, ("prs", "1")),
        (cli.Action.CREATE, ("create", "--title", "Title")),
        (cli.Action.PROFILE, ("profile",)),
    ],
)
def test_parser_sets_an_action_member(action: cli.Action, arguments: tuple[str, ...]) -> None:
    assert cli.parser().parse_args(arguments).action is action


@pytest.mark.usefixtures("offline")
def test_profile_reports_the_github_default(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(capsys, "profile") == (
        0,
        {"profile": "github", "tracker": "github", "scope": "github.com/tj-agents/core"},
    )


@pytest.mark.usefixtures("offline")
def test_unknown_state_exits_with_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    code, error = run(capsys, "progress", "461", "--state", "Doing")
    assert code == cli.EXIT_USAGE
    assert "unknown state" in error["error"]


@pytest.mark.usefixtures("offline")
def test_reference_for_another_tracker_names_the_profile_option(capsys: pytest.CaptureFixture[str]) -> None:
    code, error = run(capsys, "resolve", "https://dev.azure.com/contoso/P/_workitems/edit/1")
    assert code == cli.EXIT_USAGE
    assert "--profile" in error["error"]


@pytest.mark.usefixtures("offline")
def test_empty_comment_file_is_refused(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    empty = tmp_path / "comment.md"
    empty.write_text("  \n", encoding="utf-8")
    code, error = run(capsys, "comment", "461", "--body-file", str(empty))
    assert (code, error["error"]) == (cli.EXIT_USAGE, "comment text is empty")


def test_prs_reports_all_merged_only_when_every_linked_pr_merged(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from tj_work_items.adapters.github import GitHubTracker
    from tj_work_items.tracker import PullRequest

    pulls = [
        PullRequest("https://github.com/o/r/pull/1", "merged", "A"),
        PullRequest("https://github.com/o/r/pull/2", "open", "B"),
    ]
    monkeypatch.setattr(profiles, "repository_at", lambda cwd: Repository("github.com", "tj-agents/core"))
    monkeypatch.setattr(profiles, "installed_profiles", list)
    monkeypatch.setattr(GitHubTracker, "linked_prs", lambda self, ref: pulls)
    code, result = run(capsys, "prs", "461")
    assert code == 0
    assert result["all_merged"] is False
    assert [pull["state"] for pull in result["prs"]] == ["merged", "open"]
    monkeypatch.setattr(GitHubTracker, "linked_prs", lambda self, ref: [])
    assert run(capsys, "prs", "461")[1]["all_merged"] is False


@pytest.mark.usefixtures("offline")
def test_create_prints_the_created_item_and_parses_the_parent_ref(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from tj_work_items.adapters.github import GitHubTracker

    created_item = Item(
        ref=ItemRef("github", "github.com/tj-agents/core", "500"),
        title="New feature",
        url="https://github.com/tj-agents/core/issues/500",
        native_state="Todo",
        state=State.TO_DO,
        kind=None,
    )
    captured: dict[str, Any] = {}

    def fake_create(
        self: GitHubTracker,
        title: str,
        body: str,
        parent: ItemRef | None,
        fields: Mapping[str, str],
    ) -> Item:
        captured.update(title=title, body=body, parent=parent, fields=dict(fields))
        return created_item

    monkeypatch.setattr(GitHubTracker, "create", fake_create)
    code, result = run(
        capsys,
        "create",
        "--title",
        "New feature",
        "--body",
        "Details",
        "--parent",
        "100",
        "--field",
        "attribution=TechPlatform",
    )
    assert code == 0
    assert result == created_item.to_json()
    assert captured == {
        "title": "New feature",
        "body": "Details",
        "parent": ItemRef("github", "github.com/tj-agents/core", "100"),
        "fields": {"attribution": "TechPlatform"},
    }


def test_create_rejects_a_field_without_a_value(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.main(["create", "--title", "New feature", "--field", "attribution"])
    assert raised.value.code == 2
    assert "expected NAME=VALUE" in capsys.readouterr().err
