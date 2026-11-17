from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any, assert_never
from urllib.parse import urlsplit

from tj_work_items.tracker import ConfigError, Repository

PROFILE_GROUP = "tj_work_items.profiles"
_SCP = re.compile(r"(?:[^@/]+@)?(?P<host>[^:/]+):(?P<path>[^\\]+)")


class CreationPolicy(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class Profile:
    name: str
    tracker: str
    settings: Mapping[str, Any] = field(default_factory=dict)
    match: Mapping[str, str] = field(default_factory=dict)
    creation: CreationPolicy = CreationPolicy.DENY

    def __post_init__(self) -> None:
        if not isinstance(self.creation, CreationPolicy):
            raise ConfigError("profile creation must be a CreationPolicy")

    def require_creation(self) -> None:
        match self.creation:
            case CreationPolicy.ALLOW:
                return
            case CreationPolicy.DENY:
                raise ConfigError(
                    f"profile {self.name!r} denies work-item creation; use an existing reference "
                    f"or follow {self.name}:create-work-item and its approval workflow"
                )
            case _:
                assert_never(self.creation)

    def matches(self, repository: Repository | None) -> bool:
        if not self.match or repository is None:
            return False
        host = self.match.get("remote_host")
        if host is not None and host.casefold() != repository.host.casefold():
            return False
        remote = self.match.get("remote")
        return remote is None or re.search(remote, repository.path, re.IGNORECASE) is not None


PERSONAL = Profile(name="personal", tracker="github", creation=CreationPolicy.ALLOW)


def parse_remote(url: str) -> Repository | None:
    text = url.strip()
    if "://" in text:
        parts = urlsplit(text)
        host, path = parts.hostname or "", parts.path
    else:
        scp = _SCP.fullmatch(text)
        if scp is None:
            return None
        host, path = scp["host"], scp["path"]
    path = path.strip("/").removesuffix(".git")
    if not host or not path:
        return None
    return Repository(host=host.casefold(), path=path)


def repository_at(cwd: Path) -> Repository | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_remote(result.stdout) if result.returncode == 0 else None


def installed_profiles() -> list[Profile]:
    profiles = []
    for entry in entry_points(group=PROFILE_GROUP):
        value = entry.load()
        profiles.append(profile_from(value() if callable(value) else value, entry.name))
    return profiles


def profile_from(value: object, source: str) -> Profile:
    if not isinstance(value, Mapping):
        raise ConfigError(f"profile {source!r} is not a mapping")
    if set(value) - {"name", "tracker", "settings", "match", "creation"}:
        raise ConfigError(f"profile {source!r} has unknown properties")
    name, tracker = value.get("name", source), value.get("tracker")
    settings, match = value.get("settings", {}), value.get("match", {})
    if not isinstance(name, str) or not name.strip() or not isinstance(tracker, str) or not tracker.strip():
        raise ConfigError(f"profile {source!r} needs a name and a tracker")
    if not isinstance(settings, Mapping) or not isinstance(match, Mapping):
        raise ConfigError(f"profile {source!r} settings and match must be mappings")
    if not all(isinstance(key, str) for key in settings):
        raise ConfigError(f"profile {source!r} settings keys must be strings")
    if set(match) - {"remote_host", "remote"} or not all(
        isinstance(item, str) and item.strip() for item in match.values()
    ):
        raise ConfigError(f"profile {source!r} has invalid match rules")
    try:
        re.compile(match.get("remote", ""))
    except re.error as error:
        raise ConfigError(f"profile {source!r} has an invalid remote pattern: {error}") from error
    try:
        creation = CreationPolicy(value.get("creation", "deny"))
    except (TypeError, ValueError) as error:
        raise ConfigError(f"profile {source!r} creation must be allow or deny") from error
    return Profile(name=name, tracker=tracker, settings=dict(settings), match=dict(match), creation=creation)


def select(
    repository: Repository | None,
    requested: str | None = None,
    available: Callable[[], Iterable[Profile]] | None = None,
    *,
    configured: str | None = None,
    adopted: Iterable[str] = (),
    for_creation: bool = False,
    provider: str | None = None,
    scope: str | None = None,
    scope_for: Callable[[Profile], str | None] | None = None,
) -> Profile:
    profiles = list((available or installed_profiles)())
    names = [profile.name for profile in profiles]
    if len(set(names)) != len(names) or "personal" in names:
        raise ConfigError("duplicate or reserved work-item profile name")
    plugins = set(adopted)
    matching = [
        profile
        for profile in profiles
        if profile.matches(repository) or f"{profile.name}@tj-agents" in plugins
    ]
    personal = "personal@tj-agents" in plugins and "work@tj-agents" not in plugins
    if personal:
        profiles.append(PERSONAL)

    def named(name: str) -> Profile:
        for candidate in profiles:
            if candidate.name == name:
                return candidate
        raise ConfigError(f"no work-item profile named {name!r}; install the project's profile package")

    project = named(configured) if configured is not None else None
    if project is None and len(matching) > 1:
        names_text = ", ".join(profile.name for profile in matching)
        raise ConfigError(f"several work-item profiles match this repository: {names_text}")
    if project is None:
        project = matching[0] if matching else PERSONAL if personal else None
    if "work@tj-agents" in plugins and project is None and (provider is None or for_creation):
        raise ConfigError("no work-item profile matches this work project; install or configure its profile")
    selected = named(requested) if requested is not None else project
    if provider is not None and requested is None and not for_creation:
        candidates = [profile for profile in profiles if profile.tracker == provider]
        scoped = (
            [] if scope_for is None else [profile for profile in candidates if scope_for(profile) == scope]
        )
        if len(scoped) > 1:
            raise ConfigError(f"several work-item profiles match reference scope {scope!r}; pass --profile")
        if scoped:
            selected = scoped[0]
        elif selected is not None and selected.tracker == provider:
            pass
        elif len(candidates) == 1:
            selected = candidates[0]
        elif not candidates:
            # An explicit address selects its adapter, but confers no creation authority.
            selected = Profile(name=provider, tracker=provider)
        else:
            raise ConfigError(
                f"no unique work-item profile for tracker {provider!r}; configure it or pass --profile"
            )
    if selected is None or (for_creation and project is None):
        raise ConfigError(
            "no work-item profile matches this repository; configure configuration.work-items.profile "
            "in .agents/settings.json or install its profile package; use an existing reference. "
            "--profile cannot supply missing project creation authority"
        )
    if provider is not None and selected.tracker != provider:
        raise ConfigError(
            f"reference belongs to {provider}, but profile {selected.name!r} uses {selected.tracker}; "
            "pass --profile"
        )
    governing_profiles = [*matching, *([] if project is None else [project])]
    if for_creation:
        for governing in governing_profiles:
            governing.require_creation()
        selected.require_creation()
    if any(governing.creation is CreationPolicy.DENY for governing in governing_profiles):
        return replace(selected, creation=CreationPolicy.DENY)
    return selected
