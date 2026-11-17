from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from tj_work_items import adapters, configuration, profiles
from tj_work_items.refs import ItemRef, is_bare, parse_ref
from tj_work_items.states import State
from tj_work_items.tracker import ConfigError, Tracker, TrackerError, TrackerType

EXIT_USAGE = 2
EXIT_TRACKER = 3


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="tj item", description="Work items in the active profile's tracker")
    root.add_argument("--profile", help="profile name; creation still follows the project's policy")
    root.add_argument("--cwd", type=Path, default=Path.cwd(), help="repository directory")
    actions = root.add_subparsers(dest="action", required=True)
    reference = actions.add_parser("reference", help="normalize an address without contacting its tracker")
    reference.add_argument("ref")
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
    create = actions.add_parser("create", help="create a work item")
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
    actions.add_parser("profile", help="show the profile and tracker selected for this repository")
    return root


def run(arguments: argparse.Namespace) -> Any:
    explicit = getattr(arguments, "ref", None)
    ref = parse_ref(explicit, None) if explicit is not None and not is_bare(explicit) else None
    if arguments.action == "reference" and ref is not None:
        return ref.to_json()
    project = configuration.load(arguments.cwd)
    repository = profiles.repository_at(project.root or arguments.cwd)
    # Policy must be checked before loading or constructing any tracker adapter.
    if arguments.action == "create":
        profile = profiles.select(
            repository,
            arguments.profile,
            configured=project.profile,
            adopted=project.plugins,
            for_creation=True,
        )
    else:
        profile = None
    trackers = adapters.available()
    if ref is not None and ref.provider == "url":
        ref = parse_ref(f"{ref.scope}:{ref.id}", None, [kind.parse_url for kind in trackers.values()])
    if ref is not None and ref.provider not in trackers:
        raise ConfigError(f"no tracker adapter named {ref.provider!r}; use reference to link this address")
    instances: dict[str, Tracker] = {}

    def tracker_for(selected: profiles.Profile) -> Tracker:
        if selected.name not in instances:
            kind = trackers.get(selected.tracker)
            if kind is None:
                raise ConfigError(f"no tracker adapter named {selected.tracker!r}; install its adapter")
            instances[selected.name] = kind(selected.settings, repository)
        return instances[selected.name]

    if profile is None:
        profile = profiles.select(
            repository,
            arguments.profile,
            configured=project.profile,
            adopted=project.plugins,
            provider=None if ref is None else ref.provider,
            scope=None if ref is None else ref.scope,
            scope_for=None if ref is None else lambda selected: tracker_for(selected).default_scope(),
        )
    tracker = tracker_for(profile)
    if arguments.action == "profile":
        return {
            "profile": profile.name,
            "tracker": profile.tracker,
            "scope": tracker.default_scope(),
            "creation": profile.creation.value,
        }
    if arguments.action == "mine":
        return [item.to_json() for item in tracker.list_mine()]
    if arguments.action == "create":
        return _create(tracker, trackers, arguments)
    default = tracker.default_scope()
    ref = ref or parse_ref(
        arguments.ref,
        None if default is None else (tracker.provider, default),
        [kind.parse_url for kind in trackers.values()],
    )
    if arguments.action == "reference":
        return ref.to_json()
    target = _tracker_for(ref, tracker, profile.name)
    actions: dict[str, Callable[[], Any]] = {
        "resolve": lambda: target.resolve(ref).to_json(body=arguments.body),
        "progress": lambda: target.transition(ref, State.parse(arguments.state)).to_json(),
        "comment": lambda: _comment(target, ref, arguments),
        "link": lambda: _link(target, ref, arguments.url),
        "prs": lambda: _prs(target, ref),
    }
    return actions[arguments.action]()


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
