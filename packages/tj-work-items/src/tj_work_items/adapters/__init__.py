from __future__ import annotations

from importlib.metadata import entry_points
from typing import cast

from tj_work_items.adapters.azure_devops import AzureDevOpsTracker
from tj_work_items.adapters.github import GitHubTracker
from tj_work_items.tracker import ConfigError, TrackerType

TRACKER_GROUP = "tj_work_items.trackers"


def available() -> dict[str, TrackerType]:
    found: dict[str, TrackerType] = {
        GitHubTracker.provider: GitHubTracker,
        AzureDevOpsTracker.provider: AzureDevOpsTracker,
    }
    for entry in entry_points(group=TRACKER_GROUP):
        found[entry.name] = cast(TrackerType, entry.load())
    return found


def tracker_type(name: str) -> TrackerType:
    trackers = available()
    if name not in trackers:
        names = ", ".join(sorted(trackers))
        raise ConfigError(f"no tracker adapter named {name!r}; installed: {names}")
    return trackers[name]
