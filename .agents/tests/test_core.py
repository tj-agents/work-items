from __future__ import annotations

import pytest
from tj_work_items.adapters.azure_devops import AzureDevOpsTracker
from tj_work_items.adapters.github import GitHubTracker
from tj_work_items.profiles import GITHUB_DEFAULT, Profile, parse_remote, select
from tj_work_items.refs import ItemRef, parse_ref
from tj_work_items.states import State
from tj_work_items.tracker import ConfigError, Repository

PARSERS = [GitHubTracker.parse_url, AzureDevOpsTracker.parse_url]
DEFAULT = ("github", "github.com/tj-agents/core")
WORK = Profile(
    name="employer",
    tracker="azure-devops",
    settings={"organization": "contoso", "project": "Product"},
    match={"remote_host": "github.com", "remote": r"^contoso/"},
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("461", "github:github.com/tj-agents/core:461"),
        ("#461", "github:github.com/tj-agents/core:461"),
        ("https://github.com/TJ-Agents/Agent/issues/76", "github:github.com/tj-agents/agent:76"),
        (
            "https://dev.azure.com/Contoso/My%20Project/_workitems/edit/12",
            "azure-devops:dev.azure.com/contoso:12",
        ),
        (
            "https://contoso.visualstudio.com/Product/_workitems/edit/9",
            "azure-devops:dev.azure.com/contoso:9",
        ),
        (
            "https://contoso.visualstudio.com/_workitems/edit/27737",
            "azure-devops:dev.azure.com/contoso:27737",
        ),
        ("https://dev.azure.com/contoso/_workitems/edit/5", "azure-devops:dev.azure.com/contoso:5"),
        ("AB#27737", "github:github.com/tj-agents/core:27737"),
        ("jira:acme.atlassian.net:ABC-12", "jira:acme.atlassian.net:ABC-12"),
    ],
)
def test_refs_accept_numbers_urls_and_qualified_forms(text: str, expected: str) -> None:
    assert str(parse_ref(text, DEFAULT, PARSERS)) == expected


def test_bare_ref_without_profile_scope_is_refused() -> None:
    with pytest.raises(ValueError, match="needs a repository profile"):
        parse_ref("461", None, PARSERS)


def test_unknown_url_is_refused() -> None:
    with pytest.raises(ValueError, match="no installed tracker adapter"):
        parse_ref("https://example.com/browse/ABC-1", DEFAULT, PARSERS)


@pytest.mark.parametrize("text", ["In Review", "in-review", "IN_REVIEW", "inreview"])
def test_states_parse_loosely(text: str) -> None:
    assert State.parse(text) is State.IN_REVIEW


def test_unknown_state_lists_the_canonical_states() -> None:
    with pytest.raises(ValueError, match="In Progress"):
        State.parse("Doing")


@pytest.mark.parametrize(
    "remote",
    [
        "https://github.com/contoso/app.git",
        "git@github.com:contoso/app.git",
        "ssh://git@github.com/contoso/app",
    ],
)
def test_remotes_parse_to_host_and_path(remote: str) -> None:
    assert parse_remote(remote) == Repository("github.com", "contoso/app")


def test_profile_matched_by_origin_beats_the_github_default() -> None:
    assert select(Repository("github.com", "contoso/app"), available=lambda: [WORK]) is WORK


def test_unmatched_github_origin_uses_the_github_default() -> None:
    assert select(Repository("github.com", "tj-agents/core"), available=lambda: [WORK]) is GITHUB_DEFAULT


def test_unmatched_non_github_origin_is_refused() -> None:
    with pytest.raises(ConfigError, match="no work-item profile matches"):
        select(Repository("gitlab.com", "acme/app"), available=lambda: [WORK])


def test_requested_profile_wins_over_origin() -> None:
    assert select(Repository("github.com", "tj-agents/core"), "employer", available=lambda: [WORK]) is WORK


def test_ambiguous_profiles_are_refused() -> None:
    twin = Profile(name="twin", tracker="azure-devops", match=WORK.match)
    with pytest.raises(ConfigError, match="several"):
        select(Repository("github.com", "contoso/app"), available=lambda: [WORK, twin])


def test_item_ref_round_trips_its_text_form() -> None:
    ref = ItemRef("azure-devops", "dev.azure.com/contoso", "7")
    assert parse_ref(str(ref), None, PARSERS) == ref


def test_pull_request_urls_are_not_work_items() -> None:
    with pytest.raises(ValueError, match="no installed tracker adapter"):
        parse_ref("https://github.com/acme/widget/pull/461", DEFAULT, PARSERS)
