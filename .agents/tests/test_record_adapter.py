import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


SCRIPTS = Path(__file__).resolve().parents[1] / "work-items/utility/manage/scripts"
sys.path.insert(0, str(SCRIPTS))
import github_tracker as github
import read_problem_record as reader
import records


CONFIG = {"schema_version": 1, "backend": "github", "repository": "owner/project", "issue_types": {}}
PROVIDER = {"schema_version": 1, "provider": "work-items:manage"}


class AdapterTests(unittest.TestCase):
    def facts(self, kind="bug"):
        return {name: kind if name == "kind" else "Observed " + name for name in records.skeleton(kind)}

    def api(self):
        return Mock(request=Mock(side_effect=[{"full_name": "owner/project", "has_issues": True}, []]))

    def test_another_provider_blocks_adoption_before_any_remote_call_or_local_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selected = root / ".problem-records.json"
            selected.write_text(json.dumps({"schema_version": 1, "provider": "work:track"}), encoding="utf-8")
            api = self.api()
            with self.assertRaisesRegex(records.ItemError, "another"):
                github.adopt(root, "owner/project", api)
            api.request.assert_not_called()
            self.assertFalse((root / github.CONFIG).exists())

    def test_both_selections_are_required_and_repeated_adoption_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(github, "source_repository", return_value="owner/project"):
            root = Path(directory)
            (root / github.CONFIG).write_text(json.dumps(CONFIG), encoding="utf-8")
            with self.assertRaisesRegex(records.ItemError, "finish adopt"):
                github.selection(root)
            for _ in range(2):
                result = github.adopt(root, "owner/project", self.api())
                self.assertEqual(PROVIDER, result["problem_provider"])
                self.assertEqual(CONFIG, github.selection(root))
            self.assertEqual(PROVIDER, json.loads((root / ".problem-records.json").read_text()))

    def test_failed_provider_write_rolls_back_only_new_tracker_selection(self):
        original_open = Path.open
        def opening(path, *args, **kwargs):
            if path.name == ".problem-records.json" and args and args[0] == "x":
                raise OSError("controlled provider write failure")
            return original_open(path, *args, **kwargs)
        with tempfile.TemporaryDirectory() as directory, patch.object(github, "source_repository", return_value="owner/project"), patch.object(Path, "open", opening):
            root = Path(directory)
            with self.assertRaisesRegex(OSError, "controlled"):
                github.adopt(root, "owner/project", self.api())
            self.assertFalse((root / github.CONFIG).exists())
            self.assertFalse((root / ".problem-records.json").exists())

    def test_reader_returns_only_current_canonical_open_problems(self):
        reference = "https://github.com/owner/project/issues/1"
        for kind in ("bug", "mistake", "debt", "task", "feature"):
            issue = {"number": 1, "html_url": reference, "state": "open", "title": "Observed problem", "body": github.body_for(self.facts(kind), "adapter-request")}
            api = Mock(request=Mock(return_value=issue))
            with self.subTest(kind=kind), patch.object(reader, "selection", return_value=CONFIG), patch.object(reader, "GitHub", return_value=api):
                if kind in {"bug", "mistake", "debt"}:
                    self.assertEqual({"record": reference, "kind": kind, "state": "open", "body": issue["body"]}, reader.read("source", reference))
                    issue["state"] = "closed"
                    with self.assertRaisesRegex(records.ItemError, "open"):
                        reader.read("source", reference)
                else:
                    with self.assertRaisesRegex(records.ItemError, "problem"):
                        reader.read("source", reference)
                for identity in ("owner/project#1", "https://github.com/foreign/project/issues/1"):
                    with self.assertRaises(records.ItemError):
                        reader.read("source", identity)

    def test_reader_rejects_manual_body_edits_with_stale_metadata(self):
        reference = "https://github.com/owner/project/issues/1"
        issue = {"number": 1, "html_url": reference, "state": "open", "title": "Observed problem",
                 "body": "Unverified manual edit\n" + github.body_for(self.facts(), "adapter-request")}
        api = Mock(request=Mock(return_value=issue))
        with patch.object(reader, "selection", return_value=CONFIG), patch.object(reader, "GitHub", return_value=api):
            with self.assertRaisesRegex(records.ItemError, "manually edited"):
                reader.read("source", reference)

    def test_problem_facts_and_disposition_have_deterministic_rendering(self):
        facts = self.facts()
        facts.update(observed="2026-10-16", source_owner="source owner", cause="unknown", state="deferred",
                     repair="existing goal", next_action="investigate", verification="not yet verified",
                     blocked_by="dependency", resolver="dependency owner", resume_condition="artifact available",
                     handoff_disposition={"record_id": "B014", "schema_version": 1})
        rendered = records.render(facts)
        self.assertEqual(rendered, records.render(copy.deepcopy(facts)))
        self.assertEqual(1, rendered.count("```agent-handoff-disposition"))
        self.assertIn("## Observable resume condition", rendered)
        facts["handoff_disposition"] = "not an object"
        with self.assertRaises(records.ItemError):
            records.validate(facts)


if __name__ == "__main__":
    unittest.main()
