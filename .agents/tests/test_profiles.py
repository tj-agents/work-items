from __future__ import annotations

from dataclasses import replace

import pytest
from tj_work_items.profiles import CreationPolicy, Profile, profile_from, select
from tj_work_items.tracker import ConfigError, Repository

EMPLOYER = Profile(
    tracker="azure-devops",
)


def test_existing_profile_without_creation_defaults_to_deny() -> None:
    assert loaded.creation is CreationPolicy.DENY


@pytest.mark.parametrize("value", [None, True, "approved", {}, 1])
def test_invalid_creation_policy_is_rejected(value: object) -> None:
    with pytest.raises(ConfigError, match="creation"):
        profile_from({"tracker": "custom", "creation": value}, "custom")


@pytest.mark.parametrize(
    "value",
    [
        {"tracker": "custom", "unexpected": True},
        {"tracker": "custom", "match": {"unexpected": "yes"}},
        {"tracker": "custom", "match": {"remote": "["}},
        {"tracker": "custom", "match": {"remote": True}},
    ],
)
def test_malformed_profile_is_rejected(value: object) -> None:
    with pytest.raises(ConfigError, match="profile"):
        profile_from(value, "custom")


@pytest.mark.parametrize("installed", [True, False])
    with pytest.raises(ConfigError, match=r"existing reference|profile matches"):
        select(REPOSITORY, available=lambda: [EMPLOYER] if installed else [], for_creation=True)


def test_personal_override_cannot_bypass_matched_creation_policy() -> None:
        select(
            REPOSITORY,
            "personal",
            available=lambda: [EMPLOYER],
            adopted=["personal@tj-agents"],
            for_creation=True,
        )


def test_configured_allow_cannot_bypass_matched_creation_policy() -> None:
    permissive = Profile("custom", "custom", creation=CreationPolicy.ALLOW)
        select(REPOSITORY, configured="custom", available=lambda: [EMPLOYER, permissive], for_creation=True)


def test_requested_allow_cannot_bypass_adopted_creation_policy() -> None:
    permissive = Profile("custom", "custom", creation=CreationPolicy.ALLOW)
        select(
            None,
            "custom",
            available=lambda: [EMPLOYER, permissive],
            adopted=["company@tj-agents"],
            for_creation=True,
        )


def test_missing_work_profile_never_uses_personal_adoption() -> None:
    with pytest.raises(ConfigError, match="work project"):
        select(REPOSITORY, available=list, adopted=["work@tj-agents", "personal@tj-agents"])


def test_missing_configured_profile_never_uses_an_override() -> None:
    permissive = Profile("custom", "custom", creation=CreationPolicy.ALLOW)
    with pytest.raises(ConfigError, match="missing"):
        select(REPOSITORY, "custom", available=lambda: [permissive], configured="missing", for_creation=True)


def test_personal_requires_explicit_adoption() -> None:
    with pytest.raises(ConfigError, match="no work-item profile named"):
        select(REPOSITORY, "personal", available=list, for_creation=True)


def test_profile_configuration_disambiguates_matching_profiles() -> None:
    other = replace(EMPLOYER, name="other")


def test_duplicate_installed_profile_names_are_refused() -> None:
    with pytest.raises(ConfigError, match="duplicate"):
        select(REPOSITORY, available=lambda: [EMPLOYER, EMPLOYER])
