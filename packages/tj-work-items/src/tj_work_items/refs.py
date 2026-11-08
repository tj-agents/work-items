from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass

_QUALIFIED = re.compile(r"(?P<provider>[a-z][a-z0-9-]*):(?P<scope>[^\s:]+):(?P<id>[^\s:/]+)")
_BARE = re.compile(r"(?:AB#|#)?(?P<id>[A-Za-z0-9][A-Za-z0-9_-]*)")


@dataclass(frozen=True)
class ItemRef:
    provider: str
    scope: str
    id: str

    def __str__(self) -> str:
        return f"{self.provider}:{self.scope}:{self.id}"


UrlParser = Callable[[str], ItemRef | None]


def parse_ref(
    text: str,
    default: tuple[str, str] | None,
    url_parsers: Iterable[UrlParser],
) -> ItemRef:
    value = text.strip()
    if "://" in value:
        for parse_url in url_parsers:
            ref = parse_url(value)
            if ref is not None:
                return ref
        raise ValueError(f"no installed tracker adapter recognises the URL {value!r}")
    qualified = _QUALIFIED.fullmatch(value)
    if qualified:
        return ItemRef(qualified["provider"], qualified["scope"], qualified["id"])
    bare = _BARE.fullmatch(value)
    if bare:
        if default is None:
            raise ValueError(f"{value!r} needs a repository profile; pass a URL or provider:scope:id")
        return ItemRef(default[0], default[1], bare["id"])
    raise ValueError(f"unrecognised work-item reference {value!r}; use 461, #461, a URL or provider:scope:id")
