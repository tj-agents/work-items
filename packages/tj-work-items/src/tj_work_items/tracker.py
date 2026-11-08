from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar, Protocol

from tj_work_items.refs import ItemRef
from tj_work_items.states import State


class ConfigError(Exception):
    pass


class TrackerError(Exception):
    pass


@dataclass(frozen=True)
class Repository:
    host: str
    path: str


@dataclass(frozen=True)
class Item:
    ref: ItemRef
    title: str
    url: str
    native_state: str
    state: State | None
    kind: str | None
    assignees: tuple[str, ...] = ()
    body: str = field(default="", repr=False)

    def to_json(self, *, body: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {
            "ref": str(self.ref),
            "title": self.title,
            "url": self.url,
            "state": None if self.state is None else self.state.value,
            "native_state": self.native_state,
            "kind": self.kind,
            "assignees": list(self.assignees),
        }
        if body:
            result["body"] = self.body
        return result


@dataclass(frozen=True)
class PullRequest:
    url: str
    state: str
    head: str
    title: str = ""

    def to_json(self) -> dict[str, str]:
        return {"url": self.url, "state": self.state, "head": self.head, "title": self.title}


class Tracker(Protocol):
    provider: ClassVar[str]

    @staticmethod
    def parse_url(url: str) -> ItemRef | None: ...

    def default_scope(self) -> str | None: ...

    def resolve(self, ref: ItemRef) -> Item: ...

    def list_mine(self) -> list[Item]: ...

    def transition(self, ref: ItemRef, state: State) -> Item: ...

    def comment(self, ref: ItemRef, text: str) -> None: ...

    def link_artifact(self, ref: ItemRef, url: str) -> None: ...

    def linked_prs(self, ref: ItemRef) -> list[PullRequest]: ...


class TrackerType(Protocol):
    @property
    def provider(self) -> str: ...

    @staticmethod
    def parse_url(url: str) -> ItemRef | None: ...

    def __call__(self, settings: Mapping[str, Any], repository: Repository | None) -> Tracker: ...


def kind_for(native: str | None, kinds: Mapping[str, str]) -> str | None:
    if not native:
        return None
    for name, kind in kinds.items():
        if name.casefold() == native.casefold():
            return kind
    return native.casefold()
