from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from tj_work_items import adapters, profiles
from tj_work_items.refs import ItemRef, parse_ref
from tj_work_items.states import State
from tj_work_items.tracker import ConfigError, Tracker, TrackerError

EXIT_USAGE = 2
EXIT_TRACKER = 3


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="tj item", description="Work items in the active profile's tracker")
    root.add_argument("--profile", help="profile name; default: matched from the repository origin")
    root.add_argument("--cwd", type=Path, default=Path.cwd(), help="repository directory")
    actions = root.add_subparsers(dest="action", required=True)
    resolve = actions.add_parser("resolve", help="show one work item")
    resolve.add_argument("ref")
    resolve.add_argument("--body", action="store_true", help="include the description")
    actions.add_parser("mine", help="list open work items assigned to you")
    progress = actions.add_parser("progress", help="move a work item to a canonical state")
    progress.add_argument("ref")
    progress.add_argument("--state", required=True, help=", ".join(state.value for state in State))
    comment = actions.add_parser("comment", help="comment on a work item")
    comment.add_argument("ref")
    text = comment.add_mutually_exclusive_group(required=True)
    text.add_argument("--body")
    text.add_argument("--body-file", type=Path)
    link = actions.add_parser("link", help="link an artifact such as a pull request")
    link.add_argument("ref")
    link.add_argument("url")
    prs = actions.add_parser("prs", help="list the pull requests linked to a work item")
    prs.add_argument("ref")
    actions.add_parser("profile", help="show the profile and tracker selected for this repository")
    return root


def run(arguments: argparse.Namespace) -> Any:
    repository = profiles.repository_at(arguments.cwd)
    profile = profiles.select(repository, arguments.profile)
    trackers = adapters.available()
    tracker: Tracker = adapters.tracker_type(profile.tracker)(profile.settings, repository)
    if arguments.action == "profile":
        return {"profile": profile.name, "tracker": profile.tracker, "scope": tracker.default_scope()}
    if arguments.action == "mine":
        return [item.to_json() for item in tracker.list_mine()]
    default = tracker.default_scope()
    ref = parse_ref(
        arguments.ref,
        None if default is None else (tracker.provider, default),
        [kind.parse_url for kind in trackers.values()],
    )
    target = _tracker_for(ref, tracker, profile.name)
    actions: dict[str, Callable[[], Any]] = {
        "resolve": lambda: target.resolve(ref).to_json(body=arguments.body),
        "progress": lambda: target.transition(ref, State.parse(arguments.state)).to_json(),
        "comment": lambda: _comment(target, ref, arguments),
        "link": lambda: _link(target, ref, arguments.url),
        "prs": lambda: _prs(target, ref),
    }
    return actions[arguments.action]()


def _tracker_for(ref: ItemRef, tracker: Tracker, profile: str) -> Tracker:
    if ref.provider != tracker.provider:
        raise ConfigError(
            f"{ref} belongs to {ref.provider}, but profile {profile!r} uses {tracker.provider}; "
            "pass --profile for that tracker"
        )
    return tracker


def _comment(tracker: Tracker, ref: ItemRef, arguments: argparse.Namespace) -> dict[str, str]:
    text = arguments.body if arguments.body is not None else arguments.body_file.read_text("utf-8")
    if not text.strip():
        raise ConfigError("comment text is empty")
    tracker.comment(ref, text)
    return {"ref": str(ref), "commented": "true"}


def _prs(tracker: Tracker, ref: ItemRef) -> dict[str, Any]:
    pulls = tracker.linked_prs(ref)
    return {
        "ref": str(ref),
        "prs": [pull.to_json() for pull in pulls],
        "all_merged": bool(pulls) and all(pull.state == "merged" for pull in pulls),
    }


def _link(tracker: Tracker, ref: ItemRef, url: str) -> dict[str, str]:
    tracker.link_artifact(ref, url)
    return {"ref": str(ref), "linked": url}


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        result = run(arguments)
    except (ConfigError, ValueError, OSError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return EXIT_USAGE
    except TrackerError as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return EXIT_TRACKER
    except (KeyError, TypeError) as error:
        print(json.dumps({"error": f"unexpected tracker response: {error!r}"}), file=sys.stderr)
        return EXIT_TRACKER
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
