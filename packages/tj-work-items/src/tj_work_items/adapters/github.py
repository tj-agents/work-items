from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable, Mapping
from typing import Any, ClassVar
from urllib.parse import urlsplit

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

Runner = Callable[[list[str], str | None], str]

KIND_LABELS = ("bug", "mistake", "debt", "feature", "task", "story")
STATUS_NAMES: dict[State, tuple[str, ...]] = {
    State.TO_DO: ("Todo", "To Do", "Backlog", "Ready"),
    State.IN_PROGRESS: ("In Progress",),
    State.BLOCKED: ("Blocked",),
    State.IN_REVIEW: ("In Review", "Review"),
    State.DONE: ("Done",),
}

ISSUE_FIELDS = (
    "id number title url state body issueType{name} labels(first:20){nodes{name}} "
    "assignees(first:20){nodes{login}} "
    "repository{nameWithOwner} projectItems(first:20){nodes{id project{id title} "
    "status:fieldValueByName(name:$field){... on ProjectV2ItemFieldSingleSelectValue{name}}}}"
)
ISSUE = (
    "query($owner:String!,$name:String!,$number:Int!,$field:String!){"
    "repository(owner:$owner,name:$name){issue(number:$number){" + ISSUE_FIELDS + "}}}"
)
SEARCH = (
    "query($query:String!,$field:String!){search(query:$query,type:ISSUE,first:100){"
    "nodes{... on Issue{" + ISSUE_FIELDS + "}}}}"
)
FIELD = (
    "query($project:ID!,$field:String!){node(id:$project){... on ProjectV2{"
    "field(name:$field){... on ProjectV2SingleSelectField{id options{id name}}}}}}"
)
REPOSITORY_PROJECTS = (
    "query($owner:String!,$name:String!){repository(owner:$owner,name:$name){"
    "projectsV2(first:20){nodes{id title closed}}}}"
)
ADD_CARD = (
    "mutation($project:ID!,$content:ID!){addProjectV2ItemById("
    "input:{projectId:$project,contentId:$content}){item{id}}}"
)
PULL_FIELDS = "url state title body headRefName"
CLOSING_PRS = (
    "query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name){issue(number:$number){"
    "closedByPullRequestsReferences(first:50,includeClosedPrs:true){nodes{" + PULL_FIELDS + "}}}}}"
)
PULL = (
    "query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name){"
    "pullRequest(number:$number){" + PULL_FIELDS + "}}}"
)
SET_STATUS = (
    "mutation($project:ID!,$item:ID!,$field:ID!,$option:String!){"
    "updateProjectV2ItemFieldValue(input:{projectId:$project,itemId:$item,fieldId:$field,"
    "value:{singleSelectOptionId:$option}}){projectV2Item{id}}}"
)


def gh(arguments: list[str], payload: str | None) -> str:
    executable = shutil.which("gh")
    if executable is None:
        raise TrackerError("the GitHub CLI `gh` is not on PATH")
    try:
        result = subprocess.run(
            [executable, *arguments],
            input=payload,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise TrackerError(f"gh failed to run: {error}") from error
    if result.returncode:
        command = " ".join(arguments[:4])
        raise TrackerError(f"gh {command} failed: {result.stderr.strip() or result.stdout}")
    return result.stdout


def pull_location(url: str) -> tuple[str, str, int] | None:
    parts = urlsplit(url)
    segments = parts.path.strip("/").split("/")
    if (
        parts.hostname != "github.com"
        or len(segments) != 4
        or segments[2] != "pull"
        or not segments[3].isdigit()
    ):
        return None
    return segments[0], segments[1], int(segments[3])


def graphql(run: Runner, document: str, **variables: Any) -> dict[str, Any]:
    response = json.loads(
        run(["api", "graphql", "--input", "-"], json.dumps({"query": document, "variables": variables}))
    )
    if response.get("errors") or not isinstance(response.get("data"), dict):
        raise TrackerError(f"GitHub GraphQL failed: {response.get('errors')}")
    return dict(response["data"])


def pull_request(node: Mapping[str, Any]) -> PullRequest:
    return PullRequest(
        url=node["url"], state=node["state"].lower(), head=node["headRefName"], title=node["title"]
    )


def github_pull(run: Runner, owner: str, name: str, number: int) -> Mapping[str, Any] | None:
    found = (graphql(run, PULL, owner=owner, name=name, number=number).get("repository") or {}).get(
        "pullRequest"
    )
    return found if isinstance(found, Mapping) else None


class GitHubTracker:
    provider: ClassVar[str] = "github"

    def __init__(self, settings: Mapping[str, Any], repository: Repository | None, run: Runner = gh) -> None:
        self.repository = repository
        self.status_field = str(settings.get("status_field", "Status"))
        self.states = {State.parse(key): str(value) for key, value in settings.get("states", {}).items()}
        self.kinds = dict(settings.get("kinds", {}))
        self.run = run

    @staticmethod
    def parse_url(url: str) -> ItemRef | None:
        parts = urlsplit(url)
        segments = parts.path.strip("/").split("/")
        if parts.hostname != "github.com" or len(segments) != 4:
            return None
        owner, name, kind, number = segments
        if kind != "issues" or not number.isdigit():
            return None
        return ItemRef("github", f"github.com/{owner}/{name}".casefold(), number)

    def default_scope(self) -> str | None:
        if self.repository is None or self.repository.host != "github.com":
            return None
        return f"github.com/{self.repository.path}".casefold()

    def resolve(self, ref: ItemRef) -> Item:
        return self._item(self._issue(ref))

    def create(self, title: str, body: str, parent: ItemRef | None, fields: Mapping[str, str]) -> Item:
        if fields:
            raise ConfigError(f"a GitHub issue takes no create fields: {', '.join(sorted(fields))}")
        scope = self.default_scope()
        if scope is None or self.repository is None:
            raise ConfigError("creating a GitHub issue needs a github.com repository scope")
        owner, name = self.repository.path.split("/", 1)
        payload_body = body
        if parent is not None and parent.provider != self.provider:
            payload_body = parent_note(body, parent)
        created = self._rest_json(
            "POST", f"repos/{owner}/{name}/issues", {"title": title, "body": payload_body}
        )
        ref = ItemRef(self.provider, scope, str(created["number"]))
        if parent is not None and parent.provider == self.provider:
            self._add_sub_issue(parent, int(created["id"]))
        return self.transition(ref, State.TO_DO)

    def list_mine(self) -> list[Item]:
        scope = self.default_scope()
        if scope is None:
            raise ConfigError("listing your GitHub issues needs a github.com repository")
        query = f"repo:{scope.removeprefix('github.com/')} is:issue is:open assignee:@me"
        data = self._graphql(SEARCH, query=query, field=self.status_field)
        return [self._item(node) for node in data["search"]["nodes"] if node]

    def transition(self, ref: ItemRef, state: State) -> Item:
        issue = self._issue(ref)
        cards = issue["projectItems"]["nodes"] or self._place(ref, issue["id"])
        for card in cards:
            project = card["project"]
            field = self._graphql(FIELD, project=project["id"], field=self.status_field)["node"]["field"]
            if not field:
                raise TrackerError(f"project {project['title']!r} has no {self.status_field!r} field")
            option = self._option(field["options"], state, project["title"])
            self._graphql(
                SET_STATUS, project=project["id"], item=card["id"], field=field["id"], option=option
            )
        closed = issue["state"] == "CLOSED"
        if state is State.DONE and not closed:
            self._rest("PATCH", self._issue_path(ref), {"state": "closed", "state_reason": "completed"})
        elif state is not State.DONE and closed:
            self._rest("PATCH", self._issue_path(ref), {"state": "open"})
        item = self.resolve(ref)
        if item.state is not state:
            raise TrackerError(f"GitHub did not record {state.value} for {ref}")
        return item

    def _place(self, ref: ItemRef, issue: str) -> list[dict[str, Any]]:
        owner, name = self._owner_name(ref)
        found = self._graphql(REPOSITORY_PROJECTS, owner=owner, name=name)["repository"]["projectsV2"][
            "nodes"
        ]
        projects = [project for project in found if not project["closed"]]
        if not projects:
            raise TrackerError(
                f"{owner}/{name} has no linked GitHub Project to place {ref} on; link one to the repository"
            )
        cards = []
        for project in projects:
            added = self._graphql(ADD_CARD, project=project["id"], content=issue)
            cards.append({"id": added["addProjectV2ItemById"]["item"]["id"], "project": project})
        return cards

    def comment(self, ref: ItemRef, text: str) -> None:
        self._rest("POST", self._issue_path(ref) + "/comments", {"body": text})

    def link_artifact(self, ref: ItemRef, url: str) -> None:
        comments = json.loads(self.run(["api", self._issue_path(ref) + "/comments?per_page=100"], None))
        if any(url in comment.get("body", "") for comment in comments):
            return
        self.comment(ref, f"Linked: {url}")

    def linked_prs(self, ref: ItemRef) -> list[PullRequest]:
        owner, name = self._owner_name(ref)
        issue = self._graphql(CLOSING_PRS, owner=owner, name=name, number=int(ref.id))["repository"]["issue"]
        found = {node["url"]: pull_request(node) for node in issue["closedByPullRequestsReferences"]["nodes"]}
        comments = json.loads(self.run(["api", self._issue_path(ref) + "/comments?per_page=100"], None))
        for comment in comments:
            text = comment.get("body", "")
            location = (
                pull_location(text.removeprefix("Linked: ").strip()) if text.startswith("Linked: ") else None
            )
            if location is not None:
                node = github_pull(self.run, *location)
                if node is not None:
                    found.setdefault(node["url"], pull_request(node))
        return list(found.values())

    def _issue(self, ref: ItemRef) -> dict[str, Any]:
        owner, name = self._owner_name(ref)
        data = self._graphql(ISSUE, owner=owner, name=name, number=int(ref.id), field=self.status_field)
        issue = (data.get("repository") or {}).get("issue")
        if not issue:
            raise TrackerError(f"GitHub issue {ref} was not found")
        return dict(issue)

    def _item(self, issue: Mapping[str, Any]) -> Item:
        statuses = [card["status"]["name"] for card in issue["projectItems"]["nodes"] if card.get("status")]
        if statuses:
            state = self._canonical(statuses[0])
        else:
            state = State.DONE if issue["state"] == "CLOSED" else State.TO_DO
        repository = issue["repository"]["nameWithOwner"]
        return Item(
            ref=ItemRef("github", f"github.com/{repository}".casefold(), str(issue["number"])),
            title=issue["title"],
            url=issue["url"],
            native_state=statuses[0] if statuses else issue["state"].lower(),
            state=state,
            kind=self._kind(issue),
            assignees=tuple(node["login"] for node in issue["assignees"]["nodes"]),
            body=issue.get("body") or "",
        )

    def _kind(self, issue: Mapping[str, Any]) -> str | None:
        labels: list[str] = [
            label["name"].casefold() for label in (issue.get("labels") or {}).get("nodes", [])
        ]
        for label in labels:
            if label in KIND_LABELS:
                return label
        return kind_for((issue.get("issueType") or {}).get("name"), self.kinds)

    def _names(self, state: State) -> tuple[str, ...]:
        return (self.states[state],) if state in self.states else STATUS_NAMES[state]

    def _canonical(self, status: str) -> State | None:
        for state in State:
            if status.casefold() in {name.casefold() for name in self._names(state)}:
                return state
        return None

    def _option(self, options: list[dict[str, str]], state: State, project: str) -> str:
        for name in self._names(state):
            for option in options:
                if option["name"].casefold() == name.casefold():
                    return option["id"]
        available = ", ".join(option["name"] for option in options)
        raise TrackerError(
            f"project {project!r} has no {self.status_field} option for {state.value}; "
            f"available: {available}; map it with the profile's `states` setting"
        )

    def _owner_name(self, ref: ItemRef) -> tuple[str, str]:
        if ref.provider != self.provider:
            raise ConfigError(f"{ref} is not a GitHub reference")
        segments = ref.scope.split("/")
        if len(segments) != 3 or segments[0] != "github.com" or not ref.id.isdigit():
            raise ConfigError(f"{ref} is not github:github.com/<owner>/<repo>:<number>")
        return segments[1], segments[2]

    def _issue_path(self, ref: ItemRef) -> str:
        owner, name = self._owner_name(ref)
        return f"repos/{owner}/{name}/issues/{ref.id}"

    def _add_sub_issue(self, parent: ItemRef, sub_issue_id: int) -> None:
        owner, name = self._owner_name(parent)
        self._rest(
            "POST", f"repos/{owner}/{name}/issues/{parent.id}/sub_issues", {"sub_issue_id": sub_issue_id}
        )

    def _graphql(self, document: str, /, **variables: Any) -> dict[str, Any]:
        return graphql(self.run, document, **variables)

    def _rest(self, method: str, path: str, body: Mapping[str, Any]) -> None:
        self._rest_json(method, path, body)

    def _rest_json(self, method: str, path: str, body: Mapping[str, Any]) -> dict[str, Any]:
        return dict(json.loads(self.run(["api", "-X", method, path, "--input", "-"], json.dumps(body))))
