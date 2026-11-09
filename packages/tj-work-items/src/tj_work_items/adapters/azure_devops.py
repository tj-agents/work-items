from __future__ import annotations

import base64
import html
import json
import os
import shutil
import subprocess
from collections.abc import Callable, Mapping
from typing import Any, ClassVar
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlsplit
from urllib.request import Request, urlopen

from tj_work_items.adapters.github import Runner, gh, github_pull, pull_location, pull_request
from tj_work_items.refs import ItemRef
from tj_work_items.states import State
from tj_work_items.tracker import (
    ConfigError,
    Item,
    PullRequest,
    Repository,
    TrackerError,
    kind_for,
    parent_note,
)

AZURE_DEVOPS_RESOURCE = "499b84ac-1321-427f-aa17-267ca6975798"
PAT_VARIABLE = "AZURE_DEVOPS_EXT_PAT"
AZURE_PULL = "vstfs:///Git/PullRequestId/"
GITHUB_PULL = "vstfs:///GitHub/PullRequest/"
PULL_STATES = {"active": "open", "completed": "merged", "abandoned": "closed"}
CATEGORY_STATES = {
    "Proposed": State.TO_DO,
    "InProgress": State.IN_PROGRESS,
    "Resolved": State.IN_REVIEW,
    "Completed": State.DONE,
}
FIELDS = (
    "System.Id",
    "System.Title",
    "System.State",
    "System.WorkItemType",
    "System.AssignedTo",
    "System.TeamProject",
    "System.Description",
)


class HttpStatusError(TrackerError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


Send = Callable[[str, str, Any, str], Any]


def az_token(tenant: str | None) -> str:
    executable = shutil.which("az")
    if executable is None:
        raise ConfigError(f"Azure DevOps needs the Azure CLI `az` or {PAT_VARIABLE}")
    command = [executable, "account", "get-access-token", "--resource", AZURE_DEVOPS_RESOURCE]
    command += ["--tenant", tenant] if tenant else []
    command += ["--query", "accessToken", "-o", "tsv"]
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", timeout=60, check=False
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ConfigError(f"az failed to run: {error}") from error
    if result.returncode or not result.stdout.strip():
        raise ConfigError(f"az could not issue an Azure DevOps token: {result.stderr.strip()}")
    return result.stdout.strip()


def http_sender(authorization: Callable[[], str]) -> Send:
    def send(method: str, url: str, body: Any, content_type: str) -> Any:
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(url, data=data, method=method)
        request.add_header("Authorization", authorization())
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", content_type)
        try:
            with urlopen(request, timeout=60) as response:
                text = response.read().decode("utf-8")
        except HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:500]
            raise HttpStatusError(
                error.code, f"Azure DevOps {method} failed ({error.code}): {detail}"
            ) from error
        except URLError as error:
            raise TrackerError(f"Azure DevOps is unreachable: {error.reason}") from error
        return json.loads(text) if text else None

    return send


class AzureDevOpsTracker:
    provider: ClassVar[str] = "azure-devops"

    def __init__(
        self,
        settings: Mapping[str, Any],
        repository: Repository | None,
        send: Send | None = None,
        run: Runner = gh,
    ) -> None:
        del repository
        organization, project = settings.get("organization"), settings.get("project")
        if not isinstance(organization, str) or not isinstance(project, str):
            raise ConfigError("an azure-devops profile needs `organization` and `project` settings")
        self.organization, self.project = organization, project
        self.area_path = settings.get("area_path")
        self.states: Mapping[str, Any] = settings.get("states", {})
        self.kinds = dict(settings.get("kinds", {}))
        work_item_type = settings.get("work_item_type")
        self.work_item_type = work_item_type if isinstance(work_item_type, str) else None
        self.send = send or http_sender(self._authorization(settings.get("tenant")))
        self._type_states: dict[tuple[str, str], list[dict[str, str]]] = {}
        self.run = run

    @staticmethod
    def parse_url(url: str) -> ItemRef | None:
        parts = urlsplit(url)
        segments = parts.path.strip("/").split("/")
        host = (parts.hostname or "").casefold()
        if host == "dev.azure.com" and segments:
            organization, rest = segments[0], segments[1:]
        elif host.endswith(".visualstudio.com"):
            organization, rest = host.removesuffix(".visualstudio.com"), segments
        else:
            return None
        if "_workitems" not in rest:
            return None
        tail = rest[rest.index("_workitems") + 1 :]
        if len(tail) != 2 or tail[0] != "edit" or not tail[1].isdigit():
            return None
        return ItemRef("azure-devops", f"dev.azure.com/{organization}".casefold(), tail[1])

    def default_scope(self) -> str | None:
        return f"dev.azure.com/{self.organization}".casefold()

    def resolve(self, ref: ItemRef) -> Item:
        return self._item(self._work_item(ref))

    def create(self, title: str, body: str, parent: ItemRef | None) -> Item:
        if self.work_item_type is None:
            raise ConfigError("an azure-devops profile needs a `work_item_type` setting to create work items")
        description = body
        if parent is not None and parent.provider != self.provider:
            description = parent_note(body, parent)
        patch = [
            {"op": "add", "path": "/fields/System.Title", "value": title},
            {"op": "add", "path": "/fields/System.Description", "value": description},
        ]
        url = (
            f"https://dev.azure.com/{self.organization}/{quote(self.project)}"
            f"/_apis/wit/workitems/${quote(self.work_item_type)}?api-version=7.1"
        )
        created = self.send("POST", url, patch, "application/json-patch+json")
        ref = ItemRef(self.provider, self.default_scope() or "", str(created["id"]))
        item = self.transition(ref, State.TO_DO)
        if parent is not None and parent.provider == self.provider:
            self._link_parent(ref, parent)
        return item

    def list_mine(self) -> list[Item]:
        clauses = ["[System.TeamProject] = @project", "[System.AssignedTo] = @Me"]
        if isinstance(self.area_path, str):
            clauses.append(f"[System.AreaPath] UNDER '{self.area_path.replace("'", "''")}'")
        query = "SELECT [System.Id] FROM WorkItems WHERE " + " AND ".join(clauses)
        query += " ORDER BY [System.ChangedDate] DESC"
        found = self.send("POST", self._project_url("wiql", "$top=200"), {"query": query}, "application/json")
        ids = [entry["id"] for entry in found.get("workItems", [])]
        if not ids:
            return []
        batch = self.send(
            "POST",
            self._project_url("workitemsbatch"),
            {"ids": ids, "fields": list(FIELDS)},
            "application/json",
        )
        items = [self._item(raw) for raw in batch.get("value", [])]
        return [item for item in items if item.state is not State.DONE and item.native_state != "Removed"]

    def transition(self, ref: ItemRef, state: State) -> Item:
        raw = self._work_item(ref)
        fields = raw["fields"]
        work_type, current = fields["System.WorkItemType"], fields["System.State"]
        target = self._native(fields["System.TeamProject"], work_type, state)
        if current != target:
            try:
                self._set_state(ref, raw["rev"], target)
            except HttpStatusError as error:
                if error.status != 400:
                    raise
                if self._work_item(ref)["fields"]["System.State"] == target:
                    return self.resolve(ref)
                for step in self._walk(fields["System.TeamProject"], work_type, current, target, error):
                    self._set_state(ref, self._work_item(ref)["rev"], step)
        item = self.resolve(ref)
        if item.native_state != target:
            raise TrackerError(f"Azure DevOps did not record {target!r} for {ref}")
        return item

    def comment(self, ref: ItemRef, text: str) -> None:
        project = self._work_item(ref)["fields"]["System.TeamProject"]
        body = {"text": html.escape(text).replace("\n", "<br>")}
        url = self._url(project, f"workItems/{ref.id}/comments", "api-version=7.1-preview.4")
        self.send("POST", url, body, "application/json")

    def link_artifact(self, ref: ItemRef, url: str) -> None:
        raw = self._work_item(ref)
        if any(relation.get("url") == url for relation in raw.get("relations") or []):
            return
        patch = [
            {"op": "test", "path": "/rev", "value": raw["rev"]},
            {"op": "add", "path": "/relations/-", "value": {"rel": "Hyperlink", "url": url}},
        ]
        self.send("PATCH", self._item_url(ref), patch, "application/json-patch+json")

    def _link_parent(self, ref: ItemRef, parent: ItemRef) -> None:
        organization = self._organization(parent)
        raw = self._work_item(ref)
        patch = [
            {"op": "test", "path": "/rev", "value": raw["rev"]},
            {
                "op": "add",
                "path": "/relations/-",
                "value": {
                    "rel": "System.LinkTypes.Hierarchy-Reverse",
                    "url": f"https://dev.azure.com/{organization}/_apis/wit/workItems/{parent.id}",
                },
            },
        ]
        self.send("PATCH", self._item_url(ref), patch, "application/json-patch+json")

    def linked_prs(self, ref: ItemRef) -> list[PullRequest]:
        raw = self._work_item(ref)
        project = raw["fields"]["System.TeamProject"]
        found: dict[str, PullRequest] = {}
        for relation in raw.get("relations") or []:
            url = str(relation.get("url", ""))
            location = pull_location(url) if relation.get("rel") == "Hyperlink" else None
            pull: PullRequest | None
            if url.startswith(AZURE_PULL):
                pull = self._azure_pull(unquote(url.removeprefix(AZURE_PULL)))
            elif url.startswith(GITHUB_PULL):
                pull = self._github_artifact(project, unquote(url.removeprefix(GITHUB_PULL)), ref.id)
            elif location is not None:
                node = github_pull(self.run, *location)
                pull = None if node is None else pull_request(node)
            else:
                continue
            if pull is not None:
                found.setdefault(pull.url, pull)
        return list(found.values())

    def _azure_pull(self, artifact: str) -> PullRequest:
        project, repository, number = artifact.split("/")
        url = (
            f"https://dev.azure.com/{self.organization}/{project}/_apis/git/repositories/{repository}"
            f"/pullrequests/{number}?api-version=7.1"
        )
        pull = self.send("GET", url, None, "application/json")
        return PullRequest(
            url=f"{pull['repository']['webUrl']}/pullrequest/{number}",
            state=PULL_STATES.get(pull["status"], pull["status"]),
            head=pull["sourceRefName"].removeprefix("refs/heads/"),
            title=pull.get("title", ""),
        )

    def _github_artifact(self, project: str, artifact: str, item: str) -> PullRequest | None:
        connection, number = artifact.split("/")
        url = (
            f"https://dev.azure.com/{self.organization}/{quote(project)}/_apis/githubconnections/{connection}"
            "/repos?api-version=7.1-preview.1"
        )
        repositories = self.send("GET", url, None, "application/json")
        candidates = []
        for entry in repositories.get("value", []):
            location = pull_location(f"{entry['gitHubRepositoryUrl'].rstrip('/')}/pull/{number}")
            node = None if location is None else github_pull(self.run, *location)
            if node is not None:
                candidates.append(node)
        if len(candidates) > 1:
            candidates = [node for node in candidates if f"AB#{item}" in (node.get("body") or "")]
        return pull_request(candidates[0]) if len(candidates) == 1 else None

    def _authorization(self, tenant: Any) -> Callable[[], str]:
        cached: list[str] = []

        def authorization() -> str:
            if not cached:
                pat = os.environ.get(PAT_VARIABLE)
                if pat:
                    cached.append("Basic " + base64.b64encode(f":{pat}".encode()).decode())
                else:
                    cached.append("Bearer " + az_token(tenant if isinstance(tenant, str) else None))
            return cached[0]

        return authorization

    def _work_item(self, ref: ItemRef) -> dict[str, Any]:
        raw = self.send("GET", self._item_url(ref, "$expand=relations"), None, "application/json")
        if not isinstance(raw, dict) or not isinstance(raw.get("fields"), dict):
            raise TrackerError(f"Azure DevOps returned no work item for {ref}")
        return raw

    def _item(self, raw: Mapping[str, Any]) -> Item:
        fields = raw["fields"]
        project, work_type = fields["System.TeamProject"], fields["System.WorkItemType"]
        native = fields["System.State"]
        assigned = fields.get("System.AssignedTo")
        assignee = assigned.get("uniqueName") if isinstance(assigned, dict) else assigned
        identifier = str(raw.get("id") or fields["System.Id"])
        return Item(
            ref=ItemRef(self.provider, self.default_scope() or "", identifier),
            title=fields.get("System.Title", ""),
            url=(f"https://dev.azure.com/{self.organization}/{quote(project)}/_workitems/edit/{identifier}"),
            native_state=native,
            state=self._canonical(project, work_type, native),
            kind=kind_for(work_type, self.kinds),
            assignees=(assignee,) if assignee else (),
            body=fields.get("System.Description") or "",
        )

    def _mapping(self, work_type: str) -> dict[State, str]:
        generic = {key: value for key, value in self.states.items() if isinstance(value, str)}
        specific = self.states.get(work_type)
        merged = {**generic, **(specific if isinstance(specific, Mapping) else {})}
        return {State.parse(key): str(value) for key, value in merged.items()}

    def _ordered_states(self, project: str, work_type: str) -> list[dict[str, str]]:
        key = (project, work_type)
        if key not in self._type_states:
            url = self._url(project, f"workitemtypes/{quote(work_type)}/states")
            self._type_states[key] = list(self.send("GET", url, None, "application/json")["value"])
        return self._type_states[key]

    def _native(self, project: str, work_type: str, state: State) -> str:
        mapped = self._mapping(work_type)
        if state in mapped:
            return mapped[state]
        ordered = self._ordered_states(project, work_type)
        for entry in ordered:
            if entry["name"].casefold() == state.value.casefold():
                return entry["name"]
        for entry in ordered:
            if CATEGORY_STATES.get(entry.get("category", "")) is state:
                return entry["name"]
        names = ", ".join(entry["name"] for entry in ordered)
        raise TrackerError(
            f"{work_type} has no state for {state.value} (states: {names}); "
            "map it with the profile's `states` setting"
        )

    def _canonical(self, project: str, work_type: str, native: str) -> State | None:
        for state, name in self._mapping(work_type).items():
            if name.casefold() == native.casefold():
                return state
        for entry in self._ordered_states(project, work_type):
            if entry["name"] == native:
                return CATEGORY_STATES.get(entry.get("category", ""))
        return None

    def _walk(
        self, project: str, work_type: str, current: str, target: str, error: TrackerError
    ) -> list[str]:
        names = [entry["name"] for entry in self._ordered_states(project, work_type)]
        if current in names and target in names and names.index(current) < names.index(target):
            return names[names.index(current) + 1 : names.index(target) + 1]
        raise TrackerError(f"no stepwise path from {current!r} to {target!r} for {work_type}: {error}")

    def _set_state(self, ref: ItemRef, revision: int, state: str) -> None:
        patch = [
            {"op": "test", "path": "/rev", "value": revision},
            {"op": "add", "path": "/fields/System.State", "value": state},
        ]
        self.send("PATCH", self._item_url(ref), patch, "application/json-patch+json")

    def _organization(self, ref: ItemRef) -> str:
        if ref.provider != self.provider or ref.scope.casefold() != self.default_scope():
            raise ConfigError(f"{ref} is outside this profile's organization {self.organization!r}")
        if not ref.id.isdigit():
            raise ConfigError(f"{ref} has a non-numeric work item id")
        return self.organization

    def _item_url(self, ref: ItemRef, query: str = "") -> str:
        organization = self._organization(ref)
        suffix = f"&{query}" if query else ""
        return f"https://dev.azure.com/{organization}/_apis/wit/workitems/{ref.id}?api-version=7.1{suffix}"

    def _project_url(self, path: str, query: str = "") -> str:
        return self._url(self.project, path, query)

    def _url(self, project: str, path: str, query: str = "") -> str:
        version = query if "api-version" in query else "&".join(filter(None, ["api-version=7.1", query]))
        return f"https://dev.azure.com/{self.organization}/{quote(project)}/_apis/wit/{path}?{version}"
