from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any, assert_never

from tj_work_items import adapters, profiles
from tj_work_items.refs import ItemRef, parse_ref
from tj_work_items.states import State
from tj_work_items.tracker import ConfigError, Tracker, TrackerError, TrackerType

EXIT_USAGE = 2
EXIT_TRACKER = 3


class Action(StrEnum):
    RESOLVE = "resolve"
    MINE = "mine"
    PROGRESS = "progress"
    COMMENT = "comment"
    LINK = "link"
    PRS = "prs"
    CREATE = "create"
    PROFILE = "profile"


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="tj item", description="Work items in the active profile's tracker")
    root.add_argument("--profile", help="profile name; default: matched from the repository origin")
    root.add_argument("--cwd", type=Path, default=Path.cwd(), help="repository directory")
    actions = root.add_subparsers(dest="action", required=True)
    resolve = actions.add_parser(Action.RESOLVE.value, help="show one work item")
    resolve.set_defaults(action=Action.RESOLVE)
    resolve.add_argument("ref")
    resolve.add_argument("--body", action="store_true", help="include the description")
    mine = actions.add_parser(Action.MINE.value, help="list open work items assigned to you")
    mine.set_defaults(action=Action.MINE)
    progress = actions.add_parser(Action.PROGRESS.value, help="move a work item to a canonical state")
    progress.set_defaults(action=Action.PROGRESS)
    progress.add_argument("ref")
    progress.add_argument("--state", required=True, help=", ".join(state.value for state in State))
    comment = actions.add_parser(Action.COMMENT.value, help="comment on a work item")
    comment.set_defaults(action=Action.COMMENT)
    comment.add_argument("ref")
    text = comment.add_mutually_exclusive_group(required=True)
    text.add_argument("--body")
    text.add_argument("--body-file", type=Path)
    link = actions.add_parser(Action.LINK.value, help="link an artifact such as a pull request")
    link.set_defaults(action=Action.LINK)
    link.add_argument("ref")
    link.add_argument("url")
    prs = actions.add_parser(Action.PRS.value, help="list the pull requests linked to a work item")
    prs.set_defaults(action=Action.PRS)
    prs.add_argument("ref")
    create = actions.add_parser(Action.CREATE.value, help="create a work item")
    create.set_defaults(action=Action.CREATE)
    create.add_argument("--title", required=True)
    create.add_argument("--body", default="")
    create.add_argument("--parent", help="ref to link the new item under")
    create.add_argument(
        "--field",
        action="append",
        default=[],
        type=_field,
        metavar="NAME=VALUE",
        help="a create field the profile declares, such as attribution=TechPlatform",
    )
    profile = actions.add_parser(
        Action.PROFILE.value, help="show the profile and tracker selected for this repository"
    )
    profile.set_defaults(action=Action.PROFILE)
    return root


def run(arguments: argparse.Namespace) -> Any:
    repository = profiles.repository_at(arguments.cwd)
    profile = profiles.select(repository, arguments.profile)
    trackers = adapters.available()
    tracker: Tracker = adapters.tracker_type(profile.tracker)(profile.settings, repository)
    action: Action = arguments.action
    match action:
        case Action.PROFILE:
            return {"profile": profile.name, "tracker": profile.tracker, "scope": tracker.default_scope()}
        case Action.MINE:
            return [item.to_json() for item in tracker.list_mine()]
        case Action.CREATE:
            return _create(tracker, trackers, arguments)
        case Action.RESOLVE | Action.PROGRESS | Action.COMMENT | Action.LINK | Action.PRS:
            return _run_item_action(action, tracker, trackers, profile.name, arguments)
        case unexpected:
            assert_never(unexpected)


def _run_item_action(
    action: Action,
    tracker: Tracker,
    trackers: Mapping[str, TrackerType],
    profile: str,
    arguments: argparse.Namespace,
) -> Any:
    default = tracker.default_scope()
    ref = parse_ref(
        arguments.ref,
        None if default is None else (tracker.provider, default),
        [kind.parse_url for kind in trackers.values()],
    )
    target = _tracker_for(ref, tracker, profile)
    actions: Mapping[Action, Callable[[], Any]] = {
        Action.RESOLVE: lambda: target.resolve(ref).to_json(body=arguments.body),
        Action.PROGRESS: lambda: target.transition(ref, State.parse(arguments.state)).to_json(),
        Action.COMMENT: lambda: _comment(target, ref, arguments),
        Action.LINK: lambda: _link(target, ref, arguments.url),
        Action.PRS: lambda: _prs(target, ref),
    }
    return actions[action]()


def _create(
    tracker: Tracker, trackers: Mapping[str, TrackerType], arguments: argparse.Namespace
) -> dict[str, Any]:
    default = tracker.default_scope()
    parent: ItemRef | None = None
    if arguments.parent is not None:
        parent = parse_ref(
            arguments.parent,
            None if default is None else (tracker.provider, default),
            [kind.parse_url for kind in trackers.values()],
        )
    return tracker.create(arguments.title, arguments.body, parent, dict(arguments.field)).to_json()


def _field(value: str) -> tuple[str, str]:
    name, separator, field_value = value.partition("=")
    if not separator or not name or not field_value:
        raise argparse.ArgumentTypeError(f"expected NAME=VALUE, got {value!r}")
    return name, field_value


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
