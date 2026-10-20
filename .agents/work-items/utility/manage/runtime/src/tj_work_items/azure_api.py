from __future__ import annotations

import base64
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class APIError(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class Response(Protocol):
    def read(self) -> bytes: ...

    def close(self) -> None: ...


class Opener(Protocol):
    def open(self, request: Request, timeout: float = ...) -> Response: ...


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self,
        request: Request,
        fp: object,
        code: int,
        message: str,
        headers: object,
        new_url: str,
    ) -> Request | None:
        return None


@dataclass(frozen=True)
class Client:
    config: Mapping[str, object]
    token: str = field(repr=False)
    opener: Opener | Callable[[Request, float], Response] | None = None
    timeout: float = 15.0
    authentication: str = "pat"
    api_area: str = "wit"
    team: str | None = None

    def __post_init__(self) -> None:
        organization = self.config.get("organization")
        project = self.config.get("project")
        if not isinstance(organization, str) or not re.fullmatch(
            r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?", organization
        ):
            raise APIError("Azure DevOps organization is invalid")
        if (
            not isinstance(project, str)
            or not project.strip()
            or project != project.strip()
            or project in {".", ".."}
            or any(character in project for character in "/\\?#")
            or any(ord(character) < 32 for character in project)
        ):
            raise APIError("Azure DevOps project is invalid")
        if not isinstance(self.token, str) or not self.token:
            raise APIError("Azure DevOps credentials are unavailable")
        if self.authentication not in {"pat", "bearer"}:
            raise APIError("Azure DevOps authentication must be pat or bearer")
        if self.api_area not in {"wit", "work"}:
            raise APIError("Azure DevOps API area must be wit or work")
        if self.api_area == "wit" and self.team is not None:
            raise APIError("Azure DevOps WIT requests do not accept a team")
        if self.api_area == "work" and (
            not isinstance(self.team, str)
            or not self.team.strip()
            or self.team != self.team.strip()
            or self.team in {".", ".."}
            or any(character in self.team for character in "/\\?#")
            or any(ord(character) < 32 for character in self.team)
        ):
            raise APIError("Azure DevOps work requests require a valid team")
        object.__setattr__(
            self,
            "config",
            {"organization": organization, "project": project},
        )

    @property
    def organization(self) -> str:
        organization = self.config["organization"]
        assert isinstance(organization, str)
        return organization

    @property
    def project(self) -> str:
        project = self.config["project"]
        assert isinstance(project, str)
        return project

    @property
    def base_url(self) -> str:
        if self.api_area == "work":
            assert isinstance(self.team, str)
            return (
                f"https://dev.azure.com/{self.organization}/"
                f"{quote(self.project, safe='')}/{quote(self.team, safe='')}/_apis/work"
            )
        return (
            f"https://dev.azure.com/{self.organization}/"
            f"{quote(self.project, safe='')}/_apis/wit"
        )

    def request(
        self,
        method: str,
        suffix: str,
        payload: Mapping[str, object] | Sequence[Mapping[str, object]] | None = None,
        content_type: str = "application/json",
    ) -> object:
        url = self._url(suffix)
        encoded_payload = None
        authorization = (
            "Basic " + base64.b64encode(f"work-items:{self.token}".encode()).decode()
            if self.authentication == "pat"
            else "Bearer " + self.token
        )
        headers = {
            "Accept": "application/json",
            "Authorization": authorization,
            "User-Agent": "tj-agents-work-items/1",
        }
        if payload is not None:
            encoded_payload = json.dumps(
                payload, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
            headers["Content-Type"] = content_type
        request = Request(url, data=encoded_payload, headers=headers, method=method)
        try:
            response = self._open(request)
            try:
                body = response.read()
            finally:
                response.close()
        except HTTPError as error:
            raise APIError(
                f"Azure DevOps {method} failed (HTTP {error.code})", error.code
            ) from error
        except (OSError, URLError, TimeoutError) as error:
            raise APIError(
                "Azure DevOps transport is unavailable; "
                "a write outcome may be uncertain"
            ) from error
        if not body:
            return None
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise APIError(
                "Azure DevOps returned an invalid response; "
                "a write outcome may be uncertain"
            ) from error

    def _open(self, request: Request) -> Response:
        if self.opener is None:
            return cast(
                Response, build_opener(NoRedirect()).open(request, timeout=self.timeout)
            )
        if callable(self.opener):
            return self.opener(request, self.timeout)
        return self.opener.open(request, timeout=self.timeout)

    def _url(self, suffix: str) -> str:
        parsed = urlsplit(suffix)
        if (
            not suffix
            or parsed.scheme
            or parsed.netloc
            or parsed.fragment
            or parsed.path.startswith("/")
            or "\\" in parsed.path
            or "\\" in unquote(parsed.path)
            or ".." in unquote(parsed.path).split("/")
        ):
            raise APIError("Azure DevOps endpoint is invalid")
        query = parse_qsl(parsed.query, keep_blank_values=True)
        query.append(("api-version", "7.1"))
        return urlunsplit(
            (
                "https",
                "dev.azure.com",
                urlsplit(self.base_url).path + "/" + parsed.path,
                urlencode(query),
                "",
            )
        )
