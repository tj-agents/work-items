import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from test_github_tracker import CONFIG, FakeAPI, github, item, records, RequestJournal
import read_problem_record as reader


PROVIDER = {"schema_version": 1, "provider": "work-items:manage"}


class PrimarySelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tracker café ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.primary = self.base / "primary source"
        self.feature = self.base / "feature café"
        self.git("init", "-q", self.primary)
        self.git("-C", self.primary, "config", "remote.origin.url", "https://github.com/owner/project.git")
        (self.primary / "seed").write_text("fixture", encoding="utf-8")
        self.git("-C", self.primary, "add", "seed")
        self.git("-C", self.primary, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "commit", "-qm", "fixture")
        self.git("-C", self.primary, "worktree", "add", "-qb", "feature", self.feature)
        self.nested = self.feature / "nested directory"
        self.nested.mkdir()
        self.select(self.primary)

    def git(self, *args):
        return subprocess.run(["git", *map(str, args)], capture_output=True, text=True,
                              encoding="utf-8", check=True).stdout

    def select(self, root, config=CONFIG, provider=PROVIDER):
        (root / ".work-items.json").write_text(json.dumps(config), encoding="utf-8")
        (root / ".problem-records.json").write_text(json.dumps(provider), encoding="utf-8")

    def execute(self, api, root, command, **options):
        args = argparse.Namespace(command=command, root=str(root), reconcile_only=False, **options)
        with patch.object(github, "GitHub", return_value=api):
            return github.execute(args)

    def test_all_kinds_share_selection_receipts_and_lifecycle_across_worktrees(self):
        self.select(self.feature, {**CONFIG, "backend": "azure-devops"}, {"schema_version": 1, "provider": "work:track"})
        for kind in records.KINDS:
            with self.subTest(kind=kind):
                api = FakeAPI()
                facts = self.base / (kind + ".json")
                facts.write_text(json.dumps(item(kind)), encoding="utf-8")
                request = "primary-create-" + kind
                created = self.execute(api, self.primary, "create", input=str(facts), request_id=request)
                repeated = self.execute(api, self.nested, "create", input=str(facts), request_id=request)
                self.assertEqual(created["identity"], repeated["identity"])
                self.assertTrue(repeated["reconciled"])
                current = self.execute(api, self.feature, "read", item=created["identity"], body=True, comments=True)
                self.assertEqual(kind, current["kind"])
                facts.write_text(json.dumps({**item(kind), "title": "Updated " + kind}), encoding="utf-8")
                updated = self.execute(api, self.nested, "update", item=created["identity"], input=str(facts),
                                       expected_hash=current["body_hash"])
                self.assertEqual("Updated " + kind, updated["title"])
                if kind in {"bug", "mistake", "debt"}:
                    with patch.object(reader, "GitHub", return_value=api):
                        self.assertEqual(kind, reader.read(self.nested, created["url"])["kind"])
                evidence = self.base / "verification.txt"
                evidence.write_text("Observed fixture verification passed", encoding="utf-8")
                self.execute(api, self.feature, "note", item=created["identity"], text_file=str(evidence),
                             request_id="primary-note-" + kind)
                self.execute(api, self.nested, "link", item=created["identity"],
                             target="https://github.com/owner/project/pull/2", request_id="primary-link-" + kind)
                closed = self.execute(api, self.feature, "close", item=created["identity"], text_file=str(evidence),
                                      request_id="primary-close-" + kind)
                self.assertEqual("closed", closed["state"])
                retained = self.execute(api, self.primary, "list", kind=kind, state="all")
                self.assertEqual([created["identity"]], [value["identity"] for value in retained["items"]])
                self.assertEqual(1, len(api.issues))
                self.assertEqual(3, len(api.comments))
        self.assertEqual(RequestJournal(self.primary).root, RequestJournal(self.nested).root)
        primary_nested = self.primary / "nested source"
        primary_nested.mkdir()
        self.assertEqual(CONFIG, github.selection(primary_nested))

    def test_feature_declarations_cannot_replace_missing_invalid_or_foreign_primary_selection(self):
        self.select(self.feature)
        for filename in (".work-items.json", ".problem-records.json"):
            path = self.primary / filename
            original = path.read_text(encoding="utf-8")
            for replacement in (None, "invalid JSON"):
                with self.subTest(filename=filename, replacement=replacement):
                    if replacement is None:
                        path.unlink()
                    else:
                        path.write_text(replacement, encoding="utf-8")
                    with self.assertRaises(records.ItemError):
                        github.selection(self.nested)
                    path.write_text(original, encoding="utf-8")
        self.select(self.primary, provider={"schema_version": 1, "provider": "work:track"})
        api = Mock()
        with self.assertRaisesRegex(records.ItemError, "another"):
            github.adopt(self.feature, "owner/project", api)
        api.request.assert_not_called()

    def test_adoption_from_feature_writes_only_primary_and_uses_primary_lock(self):
        for filename in (".work-items.json", ".problem-records.json"):
            (self.primary / filename).unlink()
        self.select(self.feature, {**CONFIG, "backend": "azure-devops"}, {"schema_version": 1, "provider": "work:track"})
        before = {path.name: path.read_bytes() for path in self.feature.glob(".*.json")}
        api = Mock(request=Mock(side_effect=[{"full_name": "owner/project", "has_issues": True}, []]))
        result = github.adopt(self.nested, "owner/project", api)
        self.assertFalse(result["github_writes"])
        self.assertEqual(CONFIG, github.selection(self.primary))
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.feature.glob(".*.json")})
        self.assertTrue(all(call.args[0] == "GET" for call in api.request.call_args_list))

    def test_work_backend_and_azure_origin_fail_before_transport(self):
        self.select(self.feature)
        self.select(self.primary, {**CONFIG, "backend": "azure-devops"})
        api = FakeAPI()
        with self.assertRaisesRegex(records.ItemError, "explicitly selected GitHub"):
            self.execute(api, self.feature, "list", kind=None, state="all")
        self.select(self.primary)
        self.git("-C", self.primary, "config", "remote.origin.url", "https://dev.azure.com/work/project/_git/source")
        with self.assertRaisesRegex(records.ItemError, "source repository on github.com"):
            self.execute(api, self.nested, "list", kind=None, state="all")
        self.assertEqual([], api.calls)

    def test_invalid_inventory_missing_primary_and_unlisted_current_fail_closed(self):
        current = str(self.feature.resolve())
        absent = str(self.base / "absent primary")
        inventories = ["invalid\0\0", "worktree " + absent + "\0\0worktree " + current + "\0\0",
                       "worktree " + str(self.primary.resolve()) + "\0\0"]
        for inventory in inventories:
            with self.subTest(inventory=inventory), patch.object(github.subprocess, "run", side_effect=[
                    subprocess.CompletedProcess([], 0, stdout=current + "\n"),
                    subprocess.CompletedProcess([], 0, stdout=inventory)]):
                with self.assertRaises(records.ItemError):
                    github.source_primary(self.feature)
        with patch.object(github.subprocess, "run", side_effect=subprocess.TimeoutExpired("git", 15)):
            with self.assertRaisesRegex(records.ItemError, "source primary"):
                github.source_primary(self.feature)


if __name__ == "__main__":
    unittest.main()
