import argparse
import json
import sys

from github_tracker import GitHub, Tracker, issue_number, selection
from records import ItemError


def read(root, reference):
    tracker = Tracker(selection(root), GitHub(timeout=10))
    number = issue_number(reference, tracker.repo)
    if reference != f"https://github.com/{tracker.repo}/issues/{number}":
        raise ItemError("problem records require the canonical GitHub issue URL")
    issue = tracker.get(number)
    compact = tracker.compact(issue)
    if compact["kind"] not in {"bug", "mistake", "debt"} or compact["state"] != "open":
        raise ItemError("admission requires an open problem record")
    return {"record": compact["url"], "kind": compact["kind"], "state": compact["state"], "body": issue["body"]}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Read one current canonical problem record for Core admission")
    parser.add_argument("--root", required=True)
    parser.add_argument("--record", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(read(args.root, args.record), ensure_ascii=False, separators=(",", ":")))
        return 0
    except (ItemError, OSError, UnicodeError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
