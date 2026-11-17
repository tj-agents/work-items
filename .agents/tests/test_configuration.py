from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from tj_work_items import configuration
from tj_work_items.tracker import ConfigError


def git(root: Path, *arguments: str) -> None:
    subprocess.run(["git", "-C", str(root), *arguments], check=True, capture_output=True)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    git(tmp_path, "init", "--initial-branch=main")
    (tmp_path / ".agents").mkdir()
    return tmp_path


def test_subdirectory_uses_checkout_settings(project: Path) -> None:
    path = project / ".agents/settings.json"
    path.write_text(json.dumps({"configuration": {"work-items": {"profile": "employer"}}}), encoding="utf-8")
    child = project / "src/package"
    child.mkdir(parents=True)
    assert configuration.load(child) == configuration.Project(project, "employer")


def test_nested_repository_does_not_inherit_parent_adoption(project: Path) -> None:
    (project / ".agents/plugins.json").write_text('{"plugins":["personal@tj-agents"]}', encoding="utf-8")
    child = project / "child"
    child.mkdir()
    git(child, "init", "--initial-branch=main")
    assert configuration.load(child) == configuration.Project(child)


def test_worktree_uses_its_own_configuration(project: Path, tmp_path: Path) -> None:
    (project / ".agents/plugins.json").write_text('{"plugins":["personal@tj-agents"]}', encoding="utf-8")
    git(
        project,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "--allow-empty",
        "-m",
        "base",
    )
    checkout = tmp_path / "worktree"
    git(project, "worktree", "add", "--detach", str(checkout))
    assert (checkout / ".git").is_file()
    assert configuration.load(checkout) == configuration.Project(checkout)
    (checkout / ".agents").mkdir()
    (checkout / ".agents/settings.json").write_text(
        '{"configuration":{"work-items":{"profile":"worktree-profile"}}}', encoding="utf-8"
    )
    assert configuration.load(checkout).profile == "worktree-profile"


@pytest.mark.parametrize(
    "content",
    [
        "[]",
        "{",
        '{"configuration":null}',
        '{"configuration":{"work-items":"employer"}}',
        '{"configuration":{"work-items":{"profile":null}}}',
        '{"configuration":{"work-items":{"profile":""}}}',
        '{"configuration":{"work-items":{"profile":{}}}}',
        '{"configuration":{"work-items":{"tracker":"github"}}}',
        '{"configuration":{"work-items":{"profile":"x","profile":"y"}}}',
        '{"configuration":{},"invalid":NaN}',
        '{"invalid":1e400}',
    ],
)
def test_malformed_configuration_is_not_ignored(project: Path, content: str) -> None:
    (project / ".agents/settings.json").write_text(content, encoding="utf-8")
    with pytest.raises(ConfigError, match=r"configuration|settings|profile|JSON"):
        configuration.load(project)


@pytest.mark.parametrize("content", ["[]", '{"plugins":"personal@tj-agents"}', '{"plugins":[null]}'])
def test_malformed_adoption_is_refused(project: Path, content: str) -> None:
    (project / ".agents/plugins.json").write_text(content, encoding="utf-8")
    with pytest.raises(ConfigError, match=r"configuration|plugins"):
        configuration.load(project)


def test_non_git_directory_does_not_read_adoption(tmp_path: Path) -> None:
    (tmp_path / ".agents").mkdir()
    (tmp_path / ".agents/plugins.json").write_text('{"plugins":["personal@tj-agents"]}', encoding="utf-8")
    assert configuration.load(tmp_path) == configuration.Project(None)
