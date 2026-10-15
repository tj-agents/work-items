import argparse
import json
import re
from pathlib import Path
import sys


TEMPLATES = Path(__file__).resolve().parents[1] / "templates"
KINDS = ("feature", "task", "bug", "mistake", "debt")


class ItemError(ValueError):
    pass


def schema_for(kind):
    if kind not in KINDS:
        raise ItemError("kind must be one of: " + ", ".join(KINDS))
    return json.loads((TEMPLATES / f"{kind}.schema.json").read_text(encoding="utf-8"))


def check_value(value, spec, path):
    expected = spec["type"]
    if expected == "string":
        if not isinstance(value, str) or not value.strip():
            raise ItemError(f"{path} must be a nonempty string")
        if len(value) > spec.get("maxLength", 65536):
            raise ItemError(f"{path} is too long")
        if not re.search(spec.get("pattern", r"\S"), value):
            raise ItemError(f"{path} does not match its contract")
        if "enum" in spec and value not in spec["enum"]:
            raise ItemError(f"{path} must be one of {spec['enum']}")
        if "const" in spec and value != spec["const"]:
            raise ItemError(f"{path} must equal {spec['const']}")
    elif expected == "array":
        if not isinstance(value, list):
            raise ItemError(f"{path} must be an array")
        for index, item in enumerate(value):
            check_value(item, spec["items"], f"{path}[{index}]")
    else:
        raise ItemError(f"unsupported contract type: {expected}")


def validate(item):
    if not isinstance(item, dict):
        raise ItemError("input must be a JSON object")
    spec = schema_for(item.get("kind"))
    unknown = set(item) - spec["properties"].keys()
    if unknown:
        raise ItemError("unknown fields: " + ", ".join(sorted(unknown)))
    missing = [name for name in spec["required"] if name not in item]
    if missing:
        raise ItemError("missing fields: " + ", ".join(missing))
    for name, value in item.items():
        check_value(value, spec["properties"][name], name)
    if "\n" in item["title"] or "\r" in item["title"]:
        raise ItemError("title must be one line")
    return item


def skeleton(kind):
    spec = schema_for(kind)
    return {name: kind if name == "kind" else "" for name in spec["required"]}


def render(item):
    validate(item)
    spec = schema_for(item["kind"])
    lines = [item["summary"].strip()]
    for name, rule in spec["properties"].items():
        if "title" in rule:
            lines.extend(["", "## " + rule["title"], "", item[name].strip()])
    metadata = [f"Kind: {item['kind']}"]
    for name in ("priority", "owner"):
        if name in item:
            metadata.append(f"{name.capitalize()}: {item[name]}")
    lines.extend(["", "## Tracking", "", *metadata])
    for name, heading in (("links", "Links"), ("legacy_ids", "Legacy identities")):
        if item.get(name):
            lines.extend(["", "## " + heading, "", *["- " + value for value in item[name]]])
    return "\n".join(lines) + "\n"


def read_input(path):
    try:
        raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8-sig")
        return validate(json.loads(raw))
    except (OSError, json.JSONDecodeError) as error:
        raise ItemError(str(error)) from error


def parser():
    result = argparse.ArgumentParser(description="Deterministic, explicitly selected work-item tools")
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("schema", "template"):
        command = commands.add_parser(name)
        command.add_argument("--kind", choices=KINDS, required=True)
    for name in ("validate", "preview"):
        command = commands.add_parser(name)
        command.add_argument("--input", required=True, help="UTF-8 JSON path, or - for stdin")
    return result


def run(arguments):
    if arguments.command == "schema":
        return schema_for(arguments.kind)
    if arguments.command == "template":
        return skeleton(arguments.kind)
    item = read_input(arguments.input)
    if arguments.command == "validate":
        return {"valid": True, "kind": item["kind"]}
    return {"title": item["title"], "body": render(item)}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    try:
        output = run(parser().parse_args())
        print(json.dumps(output, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (ItemError, OSError, UnicodeError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
