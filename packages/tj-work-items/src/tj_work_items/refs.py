from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from urllib.parse import quote, unquote, urlsplit

_QUALIFIED = re.compile(r"(?P<provider>[a-z][a-z0-9-]*):(?P<scope>\S+):(?P<id>[^\s:]+)")
_NETWORK_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://")
_BARE = re.compile(r"(?:AB#|#)?(?P<id>[A-Za-z0-9][A-Za-z0-9_-]*)")


@dataclass(frozen=True)
class ItemRef:
    provider: str
    scope: str
    id: str

    def __str__(self) -> str:
        return f"{self.provider}:{self.scope}:{self.id}"

    def to_json(self) -> dict[str, str]:
        return {"ref": str(self), "provider": self.provider, "scope": self.scope, "native_id": self.id}


UrlParser = Callable[[str], ItemRef | None]


def is_bare(text: str) -> bool:
    return _BARE.fullmatch(text.strip()) is not None


def github_url(url: str) -> ItemRef | None:
    parts = urlsplit(url)
    segments = parts.path.strip("/").split("/")
    if parts.hostname != "github.com" or len(segments) != 4:
        return None
    owner, name, kind, number = segments
    if kind != "issues" or not number.isascii() or not number.isdigit():
        return None
    return ItemRef("github", f"github.com/{owner}/{name}".casefold(), number)


def azure_devops_url(url: str) -> ItemRef | None:
    parts = urlsplit(url)
    segments = parts.path.strip("/").split("/")
    host = (parts.hostname or "").casefold()
    if host == "dev.azure.com" and segments:
        organization, rest = segments[0], segments[1:]
    elif host.endswith(".visualstudio.com"):
        organization, rest = host.removesuffix(".visualstudio.com"), segments
    else:
        return None
    if not organization or "_workitems" not in rest:
        return None
    tail = rest[rest.index("_workitems") + 1 :]
    if len(tail) != 2 or tail[0] != "edit" or not tail[1].isascii() or not tail[1].isdigit():
        return None
    return ItemRef("azure-devops", f"dev.azure.com/{organization}".casefold(), tail[1])


def _url(value: str) -> ItemRef:
    if any(character.isspace() or ord(character) < 32 for character in value) or "\\" in value:
        raise ValueError("work-item URL must not contain whitespace, controls or backslashes")
    parts = urlsplit(value)
    if not parts.scheme or not value.partition(":")[2]:
        raise ValueError("work-item URL must be absolute")
    authority = parts.netloc
    if authority or parts.scheme in {"http", "https"}:
        host = parts.hostname
        if not host or any(character in host for character in "%/?#"):
            raise ValueError("work-item URL needs a valid host")
        host = f"[{host}]" if ":" in host else host.encode("idna").decode("ascii")
        port = parts.port
        authority = host
        if port is not None and (parts.scheme, port) not in {("http", 80), ("https", 443)}:
            authority += f":{port}"
        if "@" in parts.netloc:
            authority = f"{parts.netloc.rsplit('@', 1)[0]}@{authority}"
    path = parts.path
    if authority:
        segments: list[str] = []
        for segment in (path or "/").split("/"):
            decoded = unquote(segment)
            if decoded == "..":
                if len(segments) > 1:
                    segments.pop()
            elif decoded != ".":
                segments.append(segment)
        if unquote(path.rsplit("/", 1)[-1]) in {".", ".."}:
            segments.append("")
        path = "/".join(segments) or "/"
    path = quote(path, safe="/%:@!$&'()*+,;=-._~")
    remainder = f"//{authority}{path}" if authority else path
    if "?" in value.split("#", 1)[0]:
        remainder += "?" + quote(parts.query, safe="/%?:@!$&'()*+,;=-._~")
    if "#" in value:
        remainder += "#" + quote(parts.fragment, safe="/%?:@!$&'()*+,;=-._~")
    return ItemRef("url", parts.scheme, remainder)


def parse_ref(
    text: str,
    default: tuple[str, str] | None,
    url_parsers: Iterable[UrlParser] = (),
) -> ItemRef:
    value = text.strip()
    wrapped = value.removeprefix("url:")
    if value.startswith("url:") and _NETWORK_URL.match(wrapped):
        try:
            _url(wrapped)
        except ValueError:
            # An invalid URL can still be an explicit provider:scope:id triple.
            pass
        else:
            scheme, _, remainder = wrapped.partition(":")
            return ItemRef("url", scheme, remainder)
    qualified = _QUALIFIED.fullmatch(value)
    if qualified and not _NETWORK_URL.match(value):
        return ItemRef(qualified["provider"], qualified["scope"], qualified["id"])
    bare = _BARE.fullmatch(value)
    if bare:
        if default is None:
            raise ValueError(f"{value!r} needs a repository profile; pass a URL or provider:scope:id")
        return ItemRef(default[0], default[1], bare["id"])
    if ":" in value:
        if value.startswith("url:"):
            raise ValueError("URL reference needs a scope and native ID")
        opaque = _url(value)
        normalized = f"{opaque.scope}:{opaque.id}"
        for parse_url in (github_url, azure_devops_url, *url_parsers):
            ref = parse_url(normalized)
            if ref is not None:
                return ref
        return opaque
    raise ValueError(f"unrecognised work-item reference {value!r}; use 461, #461, a URL or provider:scope:id")
