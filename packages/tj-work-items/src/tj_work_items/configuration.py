from __future__ import annotations

import json
import math
import re
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

from tj_work_items.tracker import ConfigError


@dataclass(frozen=True, slots=True)
class Project:
    root: Path | None
    profile: str | None = None
    plugins: tuple[str, ...] = ()


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ConfigError(f"duplicate configuration key {key!r}")
        value[key] = item
    return value


def _constant(value: str) -> object:
    raise ConfigError(f"invalid JSON constant {value!r}")


def _float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ConfigError("configuration contains a non-finite number")
    return parsed


def _redirected(path: Path) -> bool:
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return path.is_symlink() or bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _read(path: Path) -> dict[str, object]:
    try:
        path.lstat()
    except FileNotFoundError:
        return {}
    if _redirected(path) or not path.is_file():
        raise ConfigError(f"configuration must be a regular file: {path}")
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_object,
            parse_constant=_constant,
            parse_float=_float,
        )
    except (OSError, UnicodeError, ValueError, RecursionError) as error:
        raise ConfigError(f"could not read configuration {path}: {error}") from error
    if not isinstance(value, dict):
        raise ConfigError(f"configuration must be an object: {path}")
    return value


def load(cwd: Path) -> Project:
    """Read only the current Git checkout's declarations, including from subdirectories."""
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ConfigError(f"could not locate the project: {error}") from error
    if result.returncode:
        return Project(None)
    root = Path(result.stdout.strip()).resolve()
    agents = root / ".agents"
    try:
        agents.lstat()
    except FileNotFoundError:
        return Project(root)
    if _redirected(agents) or not agents.is_dir():
        raise ConfigError(f"configuration directory must not be redirected: {agents}")
    settings = _read(agents / "settings.json")
    namespaces = settings.get("configuration", {})
    if not isinstance(namespaces, dict):
        raise ConfigError("settings configuration must be an object")
    for name, namespace in namespaces.items():
        if not re.fullmatch(r"[a-z][a-z0-9-]*", name) or not isinstance(namespace, dict):
            raise ConfigError(f"invalid settings namespace {name!r}; expected an object")
    items = namespaces.get("work-items", {})
    if set(items) - {"profile"}:
        raise ConfigError("configuration.work-items only accepts profile")
    profile = items.get("profile")
    if "profile" in items and (not isinstance(profile, str) or not profile.strip()):
        raise ConfigError("configuration.work-items.profile must be a nonempty profile name")
    declaration = _read(agents / "plugins.json")
    plugins = declaration.get("plugins", [])
    if not isinstance(plugins, list) or not all(
        isinstance(plugin, str) and re.fullmatch(r"[a-z][a-z0-9-]*@[a-z][a-z0-9-]*", plugin)
        for plugin in plugins
    ):
        raise ConfigError("plugins.json plugins must be a list of plugin@marketplace names")
    return Project(root, profile, tuple(plugins))
