from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import ClassVar, override

import pytest
from tj_work_items import adapters, cli, configuration, profiles
from tj_work_items.adapters.azure_devops import AzureDevOpsTracker
from tj_work_items.adapters.github import GitHubTracker
from tj_work_items.refs import ItemRef
from tj_work_items.states import State
from tj_work_items.tracker import Item, PullRequest

WORK = profiles.Profile(
    name="infonetica",
    tracker="azure-devops",
    settings={"organization": "infonetica", "project": "CRIS"},
    match={"remote_host": "github.com", "remote": "^Infonetica/"},
)


def forbidden(*args: object, **kwargs: object) -> None:
    pytest.fail("unexpected adapter or project access")


@pytest.fixture
def repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    subprocess.run(["git", "init", "--initial-branch=main", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "remote",
            "add",
            "origin",
            "git@github.com:Infonetica/cris-preaward-app.git",
        ],
        check=True,
        capture_output=True,
    )
    monkeypatch.setattr(profiles, "installed_profiles", lambda: [WORK])
    return tmp_path


@pytest.mark.parametrize("installed", [True, False])
def test_employer_create_never_loads_an_adapter_or_calls_gh(
    repository: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    installed: bool,
) -> None:
    monkeypatch.setattr(profiles, "installed_profiles", lambda: [WORK] if installed else [])
    monkeypatch.setattr(adapters, "available", forbidden)
    monkeypatch.setattr(GitHubTracker, "create", forbidden)
    code = cli.main(["--cwd", str(repository), "create", "--title", "No side effects"])
    assert code == cli.EXIT_USAGE
    error = json.loads(capsys.readouterr().err)["error"]
    assert "existing reference" in error
    if installed:
        assert "infonetica:create-work-item" in error


def test_explicit_allow_cannot_bypass_project_policy_before_adapter_loading(
    repository: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    allow = profiles.Profile("custom", "custom", creation=profiles.CreationPolicy.ALLOW)
    monkeypatch.setattr(profiles, "installed_profiles", lambda: [WORK, allow])
    monkeypatch.setattr(adapters, "available", forbidden)
    assert cli.main(["--cwd", str(repository), "--profile", "custom", "create", "--title", "x"]) == 2
    assert "infonetica:create-work-item" in capsys.readouterr().err


@pytest.mark.parametrize(
    "parent", ["7", "github:github.com/tj-agents/agent:231", "https://tracker.example/42"]
)
def test_explicit_allow_cannot_supply_missing_project_creation_authority(
    repository: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    parent: str,
) -> None:
    allow = profiles.Profile("other", "github", creation=profiles.CreationPolicy.ALLOW)
    monkeypatch.setattr(profiles, "installed_profiles", lambda: [allow])
    monkeypatch.setattr(adapters, "available", forbidden)
    assert (
        cli.main(
            [
                "--cwd",
                str(repository),
                "--profile",
                "other",
                "create",
                "--title",
                "x",
                "--parent",
                parent,
            ]
        )
        == 2
    )
    assert "existing reference" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "https://tracker.example:8443/items/42?q=x#c",
            ItemRef("url", "https", "//tracker.example:8443/items/42?q=x#c"),
        ),
        ("url:https://tracker.example/items/42", ItemRef("url", "https", "//tracker.example/items/42")),
        (
            "https://github.com/TJ-Agents/Agent/issues/231",
            ItemRef("github", "github.com/tj-agents/agent", "231"),
        ),
        (
            "https://dev.azure.com/Infonetica/_workitems/edit/42",
            ItemRef("azure-devops", "dev.azure.com/infonetica", "42"),
        ),
        (
            "https://infonetica.visualstudio.com/CRIS/_workitems/edit/42",
            ItemRef("azure-devops", "dev.azure.com/infonetica", "42"),
        ),
        ("jira:tracker.example:ABC-1", ItemRef("jira", "tracker.example", "ABC-1")),
        ("jira:https://tracker.example:APP-12", ItemRef("jira", "https://tracker.example", "APP-12")),
        ("url:invalid_scope:APP-12", ItemRef("url", "invalid_scope", "APP-12")),
    ],
)
def test_fully_qualified_reference_needs_no_profile_registry_or_network(
    raw: str,
    expected: ItemRef,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(adapters, "available", forbidden)
    monkeypatch.setattr(configuration, "load", forbidden)
    monkeypatch.setattr(profiles, "installed_profiles", forbidden)
    assert cli.main(["reference", raw]) == 0
    assert json.loads(capsys.readouterr().out) == expected.to_json()


@pytest.mark.parametrize("raw", ["42", "#42", "AB#42"])
def test_bare_reference_uses_employer_scope(
    repository: Path,
    raw: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["--cwd", str(repository), "reference", raw]) == 0
    assert (
        json.loads(capsys.readouterr().out)
        == ItemRef("azure-devops", "dev.azure.com/infonetica", "42").to_json()
    )


def test_missing_profile_does_not_infer_bare_reference_from_git_origin(
    repository: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(profiles, "installed_profiles", list)
    assert cli.main(["--cwd", str(repository), "reference", "42"]) == 2
    assert "no work-item profile matches" in capsys.readouterr().err


def test_profile_exposes_default_deny(
    repository: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["--cwd", str(repository), "profile"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "profile": "infonetica",
        "tracker": "azure-devops",
        "scope": "dev.azure.com/infonetica",
        "creation": "deny",
    }


def test_explicit_azure_reference_uses_its_installed_profile_outside_a_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(profiles, "installed_profiles", lambda: [WORK])
    item = Item(
        ItemRef("azure-devops", "dev.azure.com/infonetica", "42"), "Existing", "", "New", State.TO_DO, None
    )
    monkeypatch.setattr(AzureDevOpsTracker, "resolve", lambda self, ref: item if ref == item.ref else None)
    assert (
        cli.main(["--cwd", str(tmp_path), "resolve", "https://dev.azure.com/infonetica/_workitems/edit/42"])
        == 0
    )
    assert json.loads(capsys.readouterr().out)["ref"] == str(item.ref)


def test_unknown_url_mutation_requires_an_adapter(
    repository: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        cli.main(["--cwd", str(repository), "comment", "https://tracker.example/42", "--body", "text"]) == 2
    )
    assert "no tracker adapter" in capsys.readouterr().err


class CustomTracker(GitHubTracker):
    provider: ClassVar[str] = "custom"

    @staticmethod
    def parse_url(url: str) -> ItemRef | None:
        prefix = "https://tracker.example/items/"
        return (
            ItemRef("custom", "tracker.example/team", url.removeprefix(prefix))
            if url.startswith(prefix)
            else None
        )

    @override
    def default_scope(self) -> str:
        return "tracker.example/team"

    def create(self, title: str, body: str, parent: ItemRef | None, fields: Mapping[str, str]) -> Item:
        assert body == "Details"
        assert parent == ItemRef("custom", "tracker.example/team", "7")
        assert fields == {"priority": "high"}
        return Item(ItemRef(self.provider, self.default_scope(), "8"), title, "", "New", State.TO_DO, None)

    @override
    def resolve(self, ref: ItemRef) -> Item:
        assert ref.provider == self.provider
        return Item(ref, "Existing", "", "New", State.TO_DO, None)


def test_new_registered_adapter_and_allow_profile_use_the_same_create_caller(
    repository: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    profile = profiles.profile_from({"tracker": "custom", "creation": "allow"}, "custom")
    monkeypatch.setattr(profiles, "installed_profiles", lambda: [profile])
    monkeypatch.setattr(adapters, "available", lambda: {"custom": CustomTracker})
    (repository / ".agents").mkdir()
    (repository / ".agents/settings.json").write_text(
        '{"configuration":{"work-items":{"profile":"custom"}}}', encoding="utf-8"
    )
    assert (
        cli.main(
            [
                "--cwd",
                str(repository),
                "--profile",
                "custom",
                "create",
                "--title",
                "New",
                "--body",
                "Details",
                "--parent",
                "7",
                "--field",
                "priority=high",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["ref"] == "custom:tracker.example/team:8"


@pytest.mark.parametrize("raw", ["https://tracker.example/items/8", "url:https://tracker.example/items/8"])
def test_custom_url_operation_uses_registered_parser_and_matching_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    raw: str,
) -> None:
    monkeypatch.setattr(profiles, "installed_profiles", lambda: [profiles.Profile("custom", "custom")])
    monkeypatch.setattr(adapters, "available", lambda: {"custom": CustomTracker})
    assert cli.main(["--cwd", str(tmp_path), "resolve", raw]) == 0
    assert json.loads(capsys.readouterr().out)["ref"] == "custom:tracker.example/team:8"


def test_registered_url_provider_receives_its_explicit_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(CustomTracker, "provider", "url")
    monkeypatch.setattr(profiles, "installed_profiles", lambda: [profiles.Profile("url-provider", "url")])
    monkeypatch.setattr(adapters, "available", lambda: {"url": CustomTracker})
    assert cli.main(["--cwd", str(tmp_path), "resolve", "url:invalid_scope:APP-12"]) == 0
    assert json.loads(capsys.readouterr().out)["ref"] == "url:invalid_scope:APP-12"


def test_adopted_personal_checkout_can_create(
    repository: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "remote",
            "set-url",
            "origin",
            "https://github.com/tj-agents/agent.git",
        ],
        check=True,
        capture_output=True,
    )
    (repository / ".agents").mkdir()
    (repository / ".agents/plugins.json").write_text('{"plugins":["personal@tj-agents"]}', encoding="utf-8")
    monkeypatch.setattr(profiles, "installed_profiles", list)
    created: list[str] = []

    def create(
        tracker: GitHubTracker,
        title: str,
        body: str,
        parent: ItemRef | None,
        fields: Mapping[str, str],
    ) -> Item:
        created.append(title)
        return Item(
            ItemRef(tracker.provider, tracker.default_scope() or "", "231"),
            title,
            "",
            "Todo",
            State.TO_DO,
            None,
        )

    monkeypatch.setattr(GitHubTracker, "create", create)
    assert cli.main(["--cwd", str(repository), "create", "--title", "Authorized"]) == 0
    assert created == ["Authorized"]
    assert json.loads(capsys.readouterr().out)["ref"] == "github:github.com/tj-agents/agent:231"


def test_profile_override_reports_effective_project_denial(
    repository: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    allow = profiles.Profile("custom", "custom", creation=profiles.CreationPolicy.ALLOW)
    monkeypatch.setattr(profiles, "installed_profiles", lambda: [WORK, allow])
    monkeypatch.setattr(adapters, "available", lambda: {"custom": CustomTracker})
    assert cli.main(["--cwd", str(repository), "--profile", "custom", "profile"]) == 0
    assert json.loads(capsys.readouterr().out)["creation"] == "deny"


def test_explicit_ref_selects_profile_by_scope_in_an_unrelated_checkout(
    repository: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    other = profiles.Profile(
        "other", "azure-devops", settings={"organization": "other", "project": "Product"}
    )
    monkeypatch.setattr(profiles, "installed_profiles", lambda: [WORK, other])
    expected = ItemRef("azure-devops", "dev.azure.com/other", "42")

    def resolve(tracker: AzureDevOpsTracker, ref: ItemRef) -> Item:
        assert tracker.organization == "other"
        assert ref == expected
        return Item(ref, "Existing", "", "New", State.TO_DO, None)

    monkeypatch.setattr(AzureDevOpsTracker, "resolve", resolve)
    assert cli.main(["--cwd", str(repository), "resolve", str(expected)]) == 0
    assert json.loads(capsys.readouterr().out)["ref"] == str(expected)


@pytest.mark.parametrize("outside_project", [True, False])
@pytest.mark.parametrize("installed", [True, False])
def test_explicit_github_prs_selects_its_adapter_without_creation_authority(
    repository: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    outside_project: bool,
    installed: bool,
) -> None:
    cwd = repository.parent if outside_project else repository
    monkeypatch.setattr(profiles, "installed_profiles", lambda: [WORK] if installed else [])
    expected = ItemRef("github", "github.com/tj-agents/agent", "231")
    seen: list[ItemRef] = []

    def linked_prs(tracker: GitHubTracker, ref: ItemRef) -> list[PullRequest]:
        assert tracker.provider == "github"
        seen.append(ref)
        return [PullRequest("https://github.com/tj-agents/agent/pull/232", "merged", "test")]

    monkeypatch.setattr(GitHubTracker, "linked_prs", linked_prs)
    monkeypatch.setattr(GitHubTracker, "create", forbidden)
    assert cli.main(["--cwd", str(cwd), "prs", str(expected)]) == 0
    assert seen == [expected]
    assert json.loads(capsys.readouterr().out)["all_merged"] is True


def test_explicit_adapter_resolution_does_not_enable_subsequent_create(
    repository: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(profiles, "installed_profiles", list)
    monkeypatch.setattr(GitHubTracker, "linked_prs", lambda tracker, ref: [])
    assert cli.main(["--cwd", str(repository), "prs", "github:github.com/tj-agents/agent:231"]) == 0
    capsys.readouterr()
    monkeypatch.setattr(adapters, "available", forbidden)
    assert cli.main(["--cwd", str(repository), "create", "--title", "Denied"]) == 2
    assert "existing reference" in capsys.readouterr().err


def test_explicit_refs_in_work_adoption_need_no_profile_but_bare_refs_and_create_do(
    repository: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (repository / ".agents").mkdir()
    (repository / ".agents/plugins.json").write_text(
        '{"plugins":["work@tj-agents","infonetica@tj-agents"]}', encoding="utf-8"
    )
    monkeypatch.setattr(profiles, "installed_profiles", list)
    expected = ItemRef("github", "github.com/tj-agents/agent", "231")
    seen: list[ItemRef] = []

    def linked_prs(tracker: GitHubTracker, ref: ItemRef) -> list[PullRequest]:
        assert tracker.provider == expected.provider
        seen.append(ref)
        return []

    monkeypatch.setattr(GitHubTracker, "linked_prs", linked_prs)
    assert cli.main(["--cwd", str(repository), "prs", str(expected)]) == 0
    assert seen == [expected]
    assert json.loads(capsys.readouterr().out)["ref"] == str(expected)
    assert cli.main(["--cwd", str(repository), "reference", "231"]) == 2
    assert "no work-item profile matches this work project" in capsys.readouterr().err
    monkeypatch.setattr(adapters, "available", forbidden)
    assert cli.main(["--cwd", str(repository), "create", "--title", "Denied"]) == 2
    assert "no work-item profile matches this work project" in capsys.readouterr().err
