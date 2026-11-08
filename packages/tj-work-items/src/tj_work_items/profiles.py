from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from tj_work_items.tracker import ConfigError, Repository

PROFILE_GROUP = "tj_work_items.profiles"
_SCP = re.compile(r"(?:[^@/]+@)?(?P<host>[^:/]+):(?P<path>[^\\]+)")


@dataclass(frozen=True)
class Profile:
    name: str
    tracker: str
    settings: Mapping[str, Any] = field(default_factory=dict)
    match: Mapping[str, str] = field(default_factory=dict)

    def matches(self, repository: Repository | None) -> bool:
        if not self.match or repository is None:
            return False
        host = self.match.get("remote_host")
        if host is not None and host.casefold() != repository.host.casefold():
            return False
        remote = self.match.get("remote")
        return remote is None or re.search(remote, repository.path, re.IGNORECASE) is not None


GITHUB_DEFAULT = Profile(name="github", tracker="github")


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
    name, tracker = value.get("name", source), value.get("tracker")
    settings, match = value.get("settings", {}), value.get("match", {})
    if not isinstance(name, str) or not isinstance(tracker, str) or not tracker:
        raise ConfigError(f"profile {source!r} needs a name and a tracker")
    if not isinstance(settings, Mapping) or not isinstance(match, Mapping):
        raise ConfigError(f"profile {source!r} settings and match must be mappings")
    return Profile(name=name, tracker=tracker, settings=dict(settings), match=dict(match))


def select(
    repository: Repository | None,
    requested: str | None = None,
    available: Callable[[], Iterable[Profile]] = installed_profiles,
) -> Profile:
    profiles = [*available(), GITHUB_DEFAULT]
    if requested is not None:
        for profile in profiles:
            if profile.name == requested:
                return profile
        names = ", ".join(profile.name for profile in profiles)
        raise ConfigError(f"no work-item profile named {requested!r}; installed: {names}")
    matching = [profile for profile in profiles if profile.matches(repository)]
    if len(matching) > 1:
        names = ", ".join(profile.name for profile in matching)
        raise ConfigError(f"several work-item profiles match this repository: {names}")
    if matching:
        return matching[0]
    if repository is not None and repository.host == "github.com":
        return GITHUB_DEFAULT
    raise ConfigError(
        "no work-item profile matches this repository; install its profile package "
        "with `uv tool install ... --with <profile>` or pass --profile"
    )
