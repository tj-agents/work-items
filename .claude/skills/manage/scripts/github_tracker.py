import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlparse

from records import ItemError, KINDS, read_input, render


REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
REQUEST = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{7,127}")
MARKER = re.compile(r"\n<!-- work-item:v1 (.+) -->\n?\Z")
COMMENT = re.compile(r"\n<!-- work-item-comment:v1 (.+) -->\n?\Z")
CONFIG = ".work-items.json"


class APIError(ItemError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def json_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class GitHub:
    def __init__(self, timeout=60):
        self.timeout = timeout

    def request(self, method, endpoint, payload=None, paginate=False):
        command = ["gh", "api", "--hostname", "github.com", "--method", method,
                   "-H", "Accept: application/vnd.github+json", "-H", "X-GitHub-Api-Version: 2026-03-10", endpoint]
        if payload is not None:
            command.extend(["--input", "-"])
        if paginate:
            command.extend(["--paginate", "--slurp"])
        env = {**os.environ, "GH_PROMPT_DISABLED": "1"}
        env.pop("GH_DEBUG", None)
        try:
            result = subprocess.run(command, input=json_text(payload) if payload is not None else None,
                                    capture_output=True, text=True, encoding="utf-8", timeout=self.timeout,
                                    env=env, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise APIError("GitHub transport unavailable; a write outcome may be uncertain") from error
        if result.returncode:
            status = re.search(r"HTTP (\d{3})", result.stderr)
            code = int(status.group(1)) if status else None
            raise APIError(f"GitHub {method} failed (HTTP {code or 'unknown'}); verify gh authentication and access", code)
        try:
            data = json.loads(result.stdout)
            if paginate:
                if not isinstance(data, list) or any(not isinstance(page, list) for page in data):
                    raise ValueError("invalid paginated response")
                return [item for page in data for item in page]
            return data
        except (ValueError, TypeError) as error:
            raise APIError("GitHub returned an invalid response; a write outcome may be uncertain") from error


def source_repository(root):
    result = subprocess.run(["git", "-C", str(root), "config", "--get", "remote.origin.url"],
                            capture_output=True, text=True, encoding="utf-8", timeout=15, check=False)
    remote = result.stdout.strip()
    if remote.startswith("git@github.com:"):
        repo = remote[len("git@github.com:"):]
    else:
        parsed = urlparse(remote)
        if parsed.scheme != "https" or parsed.netloc != "github.com" or parsed.query or parsed.fragment:
            raise ItemError("origin must identify a source repository on github.com")
        repo = parsed.path.lstrip("/")
    repo = repo.removesuffix(".git")
    if result.returncode or not REPOSITORY.fullmatch(repo):
        raise ItemError("origin must identify owner/repository on github.com")
    return repo


def selection(root, require_provider=True):
    path = Path(root).resolve() / CONFIG
    if path.is_symlink():
        raise ItemError("tracker configuration must be a regular repository file")
    try:
        config = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise ItemError("explicit .work-items.json selection is required; run adopt for the intended repository") from error
    if not isinstance(config, dict) or set(config) != {"schema_version", "backend", "repository", "issue_types"}:
        raise ItemError("invalid tracker selection shape")
    if type(config["schema_version"]) is not int or config["schema_version"] != 1 or config["backend"] != "github":
        raise ItemError("this utility requires an explicitly selected GitHub backend")
    repo = source_repository(root)
    if not isinstance(config["repository"], str) or config["repository"].casefold() != repo.casefold():
        raise ItemError("selected repository does not match origin")
    types = config["issue_types"]
    if not isinstance(types, dict) or set(types) - set(KINDS) or any(not isinstance(v, str) or not v.strip() for v in types.values()):
        raise ItemError("invalid issue type mapping")
    if require_provider:
        provider_path = Path(root).resolve() / ".problem-records.json"
        try:
            provider = json.loads(provider_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as error:
            raise ItemError("explicit Core provider selection is required; finish adopt before tracker operations") from error
        if provider_path.is_symlink() or not isinstance(provider, dict) or set(provider) != {"schema_version", "provider"} or type(provider["schema_version"]) is not int or provider != {"schema_version": 1, "provider": "work-items:manage"}:
            raise ItemError("Core problem-record provider differs; reconcile before tracker operations")
    return config


def request_id(value):
    if not REQUEST.fullmatch(value):
        raise ItemError("request-id must contain 8–128 letters, digits, underscores or hyphens")
    return value


def issue_number(value, repository):
    prefix = f"https://github.com/{repository}/issues/"
    identity = repository + "#"
    number = value[len(prefix):] if value.startswith(prefix) else value[len(identity):] if value.startswith(identity) else ""
    if not number.isascii() or not number.isdecimal() or int(number) <= 0:
        raise ItemError("item must be a full issue URL or repository#number matching the selected repository")
    return int(number)


def metadata(body):
    if not isinstance(body, str):
        raise ItemError("managed issue body must be text")
    match = MARKER.search(body)
    if not match:
        raise ItemError("issue is not managed by work-items")
    try:
        value = json.loads(match.group(1))
        if not isinstance(value, dict) or set(value) != {"request_id", "kind", "creation_hash", "render_hash"}:
            raise ValueError("metadata shape")
        if value["kind"] not in KINDS or not isinstance(value["request_id"], str):
            raise ValueError("metadata kind/request")
        request_id(value["request_id"])
        if any(not isinstance(value[k], str) or not re.fullmatch(r"[a-f0-9]{64}", value[k]) for k in ("creation_hash", "render_hash")):
            raise ValueError("metadata digest")
        return value, body[:match.start()]
    except (ValueError, TypeError) as error:
        raise ItemError("invalid managed issue metadata") from error


def body_for(item, request, existing=None):
    text = render(item).rstrip("\n")
    info = {"request_id": request, "kind": item["kind"],
            "creation_hash": existing["creation_hash"] if existing else digest(json_text(item)), "render_hash": digest(text)}
    body = text + "\n<!-- work-item:v1 " + json_text(info) + " -->\n"
    if len(body) > 65536:
        raise ItemError("rendered issue body exceeds 65536 characters")
    return body


class Tracker:
    def __init__(self, config, api=None, journal=None):
        self.config = config
        self.repo = config["repository"]
        self.api = api or GitHub()
        self.journal = journal
        self.endpoint = "repos/" + self.repo + "/issues"

    def all(self):
        return [issue for issue in self.api.request("GET", self.endpoint + "?state=all&per_page=100", paginate=True)
                if "pull_request" not in issue]

    def get(self, number):
        issue = self.api.request("GET", self.endpoint + f"/{number}")
        if not isinstance(issue, dict) or issue.get("number") != number or "pull_request" in issue:
            raise ItemError("target is not the expected issue")
        metadata(issue.get("body"))
        return issue

    def compact(self, issue):
        if not isinstance(issue, dict) or type(issue.get("number")) is not int or issue["number"] <= 0:
            raise ItemError("invalid issue response identity")
        if issue.get("html_url") != f"https://github.com/{self.repo}/issues/{issue['number']}" or issue.get("state") not in ("open", "closed") or not isinstance(issue.get("title"), str):
            raise ItemError("invalid issue response fields")
        info, _ = metadata(issue.get("body"))
        return {"identity": f"{self.repo}#{issue['number']}", "url": issue["html_url"], "state": issue["state"],
                "title": issue["title"], "kind": info["kind"], "body_hash": digest(issue["body"])}

    def find_request(self, request, item):
        found = []
        for issue in self.all():
            try:
                info, _ = metadata(issue.get("body"))
            except ItemError:
                continue
            if info["request_id"] == request:
                if info["creation_hash"] != digest(json_text(item)):
                    raise ItemError("request-id already exists with different creation facts")
                found.append(issue)
        if len(found) > 1:
            raise ItemError("request-id has multiple issues; reconcile their ownership before continuing")
        return found[0] if found else None

    def create(self, item, request, reconcile_only=False):
        request_id(request)
        body = body_for(item, request)
        key = self.repo + ":create:" + request
        fingerprint = digest(json_text(item))
        receipt = self.journal.read(key, fingerprint) if self.journal else None
        existing = self.find_request(request, item)
        if existing is None and receipt and receipt["resource_id"]:
            existing = self.get(receipt["resource_id"])
            info, _ = metadata(existing["body"])
            if info["request_id"] != request or info["creation_hash"] != fingerprint:
                raise ItemError("returned issue no longer matches its request receipt")
        if existing:
            if self.journal:
                self.journal.complete(key, fingerprint, existing["number"])
            return {**self.compact(existing), "reconciled": True}
        if receipt or reconcile_only:
            raise ItemError("request outcome remains uncertain; reconcile without another POST")
        payload = {"title": item["title"], "body": body}
        issue_type = self.config["issue_types"].get(item["kind"])
        if issue_type:
            available = self.api.request("GET", "repos/" + self.repo + "/issue-types")
            if issue_type not in [entry["name"] for entry in available]:
                raise ItemError("configured issue type is unavailable; reconcile repository selection")
            payload["type"] = issue_type
        if self.journal:
            self.journal.reserve(key, fingerprint)
        try:
            issue = self.api.request("POST", self.endpoint, payload)
            result = self.compact(issue)
            if self.journal:
                self.journal.complete(key, fingerprint, issue["number"])
        except (APIError, ItemError, KeyError, TypeError):
            existing = self.find_request(request, item)
            if existing:
                if self.journal:
                    self.journal.complete(key, fingerprint, existing["number"])
                return {**self.compact(existing), "reconciled": True}
            raise ItemError("create outcome uncertain or rejected; retain request-id and reconcile before retrying")
        return {**result, "reconciled": False}

    def update(self, number, item, expected_hash):
        issue = self.get(number)
        info, old_text = metadata(issue["body"])
        if digest(issue["body"]) != expected_hash or digest(old_text) != info["render_hash"]:
            raise ItemError("issue changed; read and reconcile current content before updating")
        if item["kind"] != info["kind"]:
            raise ItemError("update cannot change the work-item kind")
        payload = {"title": item["title"], "body": body_for(item, info["request_id"], info)}
        try:
            return self.compact(self.api.request("PATCH", self.endpoint + f"/{number}", payload))
        except APIError as error:
            raise ItemError("update outcome uncertain; read the issue before another update") from error

    def comment(self, number, text, request, operation="note"):
        request_id(request)
        if not isinstance(text, str) or not text.strip():
            raise ItemError("comment/verification text must be nonempty")
        info = {"request_id": request, "operation": operation, "content_hash": digest(text)}
        body = text + "\n<!-- work-item-comment:v1 " + json_text(info) + " -->\n"
        if len(body) > 65536:
            raise ItemError("comment exceeds 65536 characters")
        endpoint = self.endpoint + f"/{number}/comments"
        key = self.repo + f":comment:{number}:" + request
        fingerprint = digest(json_text(info))
        receipt = self.journal.read(key, fingerprint) if self.journal else None
        def reconcile():
            found = []
            for comment in self.api.request("GET", endpoint + "?per_page=100", paginate=True):
                match = COMMENT.search(comment.get("body") or "")
                if not match:
                    continue
                try:
                    previous = json.loads(match.group(1))
                except ValueError:
                    continue
                if isinstance(previous, dict) and previous.get("request_id") == request:
                    if previous != info or digest(comment["body"][:match.start()]) != info["content_hash"]:
                        raise ItemError("comment request-id exists with different facts")
                    found.append(comment)
            if len(found) > 1:
                raise ItemError("comment request-id has duplicates; reconcile before continuing")
            if not found and receipt and receipt["resource_id"]:
                comment = self.api.request("GET", "repos/" + self.repo + "/issues/comments/" + str(receipt["resource_id"]))
                if comment.get("body") != body:
                    raise ItemError("comment changed since its request receipt")
                found.append(comment)
            return found[0] if found else None
        existing = reconcile()
        if existing:
            if self.journal:
                self.journal.complete(key, fingerprint, existing["id"])
            return existing
        if receipt:
            raise ItemError("comment outcome remains uncertain; reconcile without another POST")
        if self.journal:
            self.journal.reserve(key, fingerprint)
        try:
            comment = self.api.request("POST", endpoint, {"body": body})
            if self.journal:
                self.journal.complete(key, fingerprint, comment["id"])
            return comment
        except APIError:
            existing = reconcile()
            if existing:
                return existing
            raise ItemError("comment outcome uncertain or rejected; retain request-id and reconcile before retrying")


def adopt(root, repository, api):
    root = Path(root).resolve()
    provider_path = root / ".problem-records.json"
    provider = {"schema_version": 1, "provider": "work-items:manage"}
    if provider_path.is_symlink():
        raise ItemError("problem-record provider selection must be a regular repository file")
    if provider_path.exists():
        try:
            existing_provider = json.loads(provider_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as error:
            raise ItemError("existing problem-record provider is unreadable; reconcile before adoption") from error
        if not isinstance(existing_provider, dict) or type(existing_provider.get("schema_version")) is not int or existing_provider != provider:
            raise ItemError("another problem-record provider is selected; reconcile before adoption")
    if not REPOSITORY.fullmatch(repository) or source_repository(root).casefold() != repository.casefold():
        raise ItemError("adoption repository must match the source origin")
    repo = api.request("GET", "repos/" + repository)
    if not repo.get("has_issues") or repo.get("archived") or repo.get("full_name", "").casefold() != repository.casefold():
        raise ItemError("source repository must have issues enabled and be writable")
    try:
        types = api.request("GET", "repos/" + repository + "/issue-types")
    except APIError as error:
        if error.status != 404:
            raise
        types = []
    available = {entry["name"] for entry in types}
    mapping = {kind: name for kind, name in {"feature": "Feature", "task": "Task", "bug": "Bug", "mistake": "Task", "debt": "Task"}.items() if name in available}
    config = {"schema_version": 1, "backend": "github", "repository": repo["full_name"], "issue_types": mapping}
    path = Path(root).resolve() / CONFIG
    if path.exists():
        existing = selection(root, require_provider=False)
        if existing != config:
            raise ItemError("existing tracker selection differs; reconcile it explicitly before adoption")
    created = []
    provider_existed = provider_path.exists()
    tracker_existed = path.exists()
    try:
        for target, value, existed in ((path, config, tracker_existed), (provider_path, provider, provider_existed)):
            if not existed:
                with target.open("x", encoding="utf-8", newline="\n") as handle:
                    created.append(target)
                    handle.write(json.dumps(value, indent=2) + "\n")
        selection(root)
    except (OSError, ItemError):
        for target in reversed(created):
            target.unlink()
        raise
    return {"selected": config, "problem_provider": provider, "type_support": "native" if mapping else "body-kind", "github_writes": False}


def add_commands(commands):
    command = commands.add_parser("adopt")
    command.add_argument("--root", default=".")
    command.add_argument("--repository", required=True)
    for name in ("create", "read", "list", "update", "note", "link", "close"):
        command = commands.add_parser(name)
        command.add_argument("--root", default=".")
        if name in ("create", "update"):
            command.add_argument("--input", required=True)
        if name not in ("create", "list"):
            command.add_argument("--item", required=True)
        if name in ("create", "note", "link", "close"):
            command.add_argument("--request-id", required=True)
        if name == "create":
            command.add_argument("--reconcile-only", action="store_true")
        if name == "update":
            command.add_argument("--expected-hash", required=True)
        if name == "list":
            command.add_argument("--kind", choices=KINDS)
            command.add_argument("--state", choices=("open", "closed", "all"), default="open")
        if name == "read":
            command.add_argument("--body", action="store_true")
            command.add_argument("--comments", action="store_true")
        if name in ("note", "close"):
            command.add_argument("--text-file", required=True)
        if name == "link":
            command.add_argument("--target", required=True)


def execute(args):
    api = GitHub()
    if args.command == "adopt":
        return adopt(args.root, args.repository, api)
    from request_journal import RequestJournal
    tracker = Tracker(selection(args.root), api, RequestJournal(args.root))
    if args.command == "create":
        return tracker.create(read_input(args.input), args.request_id, args.reconcile_only)
    if args.command == "list":
        result = []
        for issue in tracker.all():
            try:
                item = tracker.compact(issue)
            except ItemError:
                continue
            if (not args.kind or item["kind"] == args.kind) and (args.state == "all" or item["state"] == args.state):
                result.append(item)
        return {"repository": tracker.repo, "items": result}
    number = issue_number(args.item, tracker.repo)
    issue = tracker.get(number)
    if args.command == "read":
        result = tracker.compact(issue)
        if args.body:
            result["body"] = issue["body"]
        if args.comments:
            result["comments"] = api.request("GET", tracker.endpoint + f"/{number}/comments?per_page=100", paginate=True)
        return result
    if args.command == "update":
        return tracker.update(number, read_input(args.input), args.expected_hash)
    if args.command == "close" and issue["state"] == "closed":
        return {**tracker.compact(issue), "already_closed": True}
    text = "Linked work: " + args.target if args.command == "link" else Path(args.text_file).read_text(encoding="utf-8-sig")
    if args.command == "link" and not re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/(issues|pull)/[1-9][0-9]*", args.target):
        raise ItemError("link target must be a GitHub issue or pull request URL")
    comment = tracker.comment(number, text, args.request_id, args.command)
    if args.command == "close":
        try:
            return tracker.compact(api.request("PATCH", tracker.endpoint + f"/{number}", {"state": "closed", "state_reason": "completed"}))
        except APIError as error:
            raise ItemError("close outcome uncertain; read state before retrying with the same request-id") from error
    return {"identity": f"{tracker.repo}#{number}", "comment_url": comment["html_url"]}
