import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".agents/work-items/utility/manage/scripts/work_item.py"
SPEC = importlib.util.spec_from_file_location("work_item", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def example(kind="bug"):
    item = module.skeleton(kind)
    return {key: value if key == "kind" else f"Observed {key}: café" for key, value in item.items()}


class WorkItemTests(unittest.TestCase):
    def test_every_kind_requires_real_facts_and_renders_its_sections(self):
        for kind in module.KINDS:
            with self.subTest(kind=kind):
                with self.assertRaises(module.ItemError):
                    module.validate(module.skeleton(kind))
                item = example(kind)
                self.assertEqual(module.validate(item), item)
                first = module.render(item)
                self.assertEqual(first, module.render(dict(reversed(list(item.items())))))
                for rule in module.schema_for(kind)["properties"].values():
                    if "title" in rule:
                        self.assertIn("## " + rule["title"], first)

    def test_invalid_values_are_rejected(self):
        for patch in ({"evidence": " "}, {"kind": "unknown"}, {"kind": []},
                      {"priority": "urgent"}, {"owner": None}, {"links": "url"},
                      {"links": [None]}, {"title": "a\nb"}, {"title": "a" * 257},
                      {"extra": "ignored?"}):
            with self.subTest(patch=patch), self.assertRaises(module.ItemError):
                module.validate({**example(), **patch})
        with self.assertRaises(module.ItemError):
            module.validate([])
        with self.assertRaises(module.ItemError):
            module.validate({"kind": "bug", "title": "Bug"})

    def test_unknown_cause_is_valid_and_no_priority_is_invented(self):
        item = {**example("mistake"), "cause": "Unknown; investigation required"}
        self.assertNotIn("Priority:", module.render(item))
        self.assertIn("Unknown; investigation required", module.render(item))

    def test_legacy_ids_and_links_survive_preview(self):
        item = {**example(), "legacy_ids": ["BUGS.md#B013"], "links": ["https://example.test/evidence"]}
        body = module.render(item)
        self.assertIn("BUGS.md#B013", body)
        self.assertIn("https://example.test/evidence", body)

    def test_cli_validates_and_previews_from_stdin_without_git_or_github(self):
        for command in ("validate", "preview"):
            result = subprocess.run([sys.executable, "-B", str(SCRIPT), command, "--input", "-"],
                                    input=json.dumps(example()), text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIsInstance(json.loads(result.stdout), dict)
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), "validate", "--input", "-"],
                                input="broken json", text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("error", json.loads(result.stderr))


if __name__ == "__main__":
    unittest.main()
