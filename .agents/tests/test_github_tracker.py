import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / ".agents/work-items/utility/manage/scripts"
sys.path.insert(0, str(SCRIPTS))
import github_tracker as github
import records


CONFIG = {"schema_version": 1, "backend": "github", "repository": "owner/project", "issue_types": {}}


def item(kind="bug"):
    result = records.skeleton(kind)
    return {key: value if key == "kind" else "Observed " + key for key, value in result.items()}


class FakeAPI:
    def __init__(self):
        self.issues = []
        self.comments = []
        self.calls = []
        self.fail_after_create = False
        self.fail_before_create = False
        self.fail_after_comment = False

    def request(self, method, endpoint, payload=None, paginate=False):
        self.calls.append((method, endpoint, copy.deepcopy(payload)))
        base = "repos/owner/project/issues"
        if method == "GET" and endpoint == base + "?state=all&per_page=100":
            return copy.deepcopy(self.issues)
        if method == "GET" and endpoint == "repos/owner/project/issue-types":
            return [{"name": name} for name in ("Task", "Feature", "Bug")]
        if endpoint.startswith(base + "/1/comments"):
            if method == "GET":
                return copy.deepcopy(self.comments)
            value = {"body": payload["body"], "html_url": "https://github.com/owner/project/issues/1#issuecomment-1"}
            self.comments.append(value)
            if self.fail_after_comment:
                raise github.APIError("lost response")
            return copy.deepcopy(value)
        if method == "POST" and endpoint == base:
            if self.fail_before_create:
                raise github.APIError("rejected", 403)
            value = {"number": len(self.issues) + 1, "state": "open", "html_url": f"https://github.com/owner/project/issues/{len(self.issues) + 1}", **payload}
            self.issues.append(value)
            if self.fail_after_create:
                raise github.APIError("lost response")
            return copy.deepcopy(value)
        if endpoint == base + "/1":
            if method == "PATCH":
                self.issues[0].update(payload)
            return copy.deepcopy(self.issues[0])
        raise AssertionError((method, endpoint, payload))


class TrackerTests(unittest.TestCase):
    def setUp(self):
        self.api = FakeAPI()
        self.tracker = github.Tracker(CONFIG, self.api)

    def test_create_retries_reconcile_the_original_issue(self):
        first = self.tracker.create(item(), "request-0001")
        second = self.tracker.create(item(), "request-0001")
        self.assertEqual(first["identity"], second["identity"])
        self.assertTrue(second["reconciled"])
        self.assertEqual(1, len(self.api.issues))
        self.assertEqual(1, sum(method == "POST" for method, _, _ in self.api.calls))

    def test_lost_create_response_is_reconciled_without_reposting(self):
        self.api.fail_after_create = True
        self.assertTrue(self.tracker.create(item(), "request-0001")["reconciled"])
        self.assertEqual(1, len(self.api.issues))

    def test_rejected_create_does_not_retry_post(self):
        self.api.fail_before_create = True
        with self.assertRaisesRegex(records.ItemError, "uncertain or rejected"):
            self.tracker.create(item(), "request-0001")
        self.assertEqual(1, sum(method == "POST" for method, _, _ in self.api.calls))

    def test_collision_and_duplicates_remain_visible(self):
        self.tracker.create(item(), "request-0001")
        with self.assertRaisesRegex(records.ItemError, "different creation facts"):
            self.tracker.create({**item(), "title": "Different"}, "request-0001")
        self.api.issues.append(copy.deepcopy(self.api.issues[0]))
        with self.assertRaisesRegex(records.ItemError, "multiple issues"):
            self.tracker.create(item(), "request-0001")

    def test_native_type_mapping_is_verified_before_submission(self):
        tracker = github.Tracker({**CONFIG, "issue_types": {"feature": "Feature"}}, self.api)
        tracker.create(item("feature"), "request-0001")
        self.assertEqual("Feature", self.api.issues[0]["type"])
        tracker = github.Tracker({**CONFIG, "issue_types": {"bug": "Missing"}}, self.api)
        with self.assertRaisesRegex(records.ItemError, "unavailable"):
            tracker.create(item(), "request-0002")
        self.assertEqual(1, len(self.api.issues))

    def test_update_refuses_stale_hash_and_manual_body_edits(self):
        created = self.tracker.create(item(), "request-0001")
        updated = {**item(), "evidence": "New evidence"}
        with self.assertRaisesRegex(records.ItemError, "changed"):
            self.tracker.update(1, updated, "stale")
        self.tracker.update(1, updated, created["body_hash"])
        self.assertIn("New evidence", self.api.issues[0]["body"])
        info, text = github.metadata(self.api.issues[0]["body"])
        self.api.issues[0]["body"] = "Manual text\n" + self.api.issues[0]["body"]
        with self.assertRaisesRegex(records.ItemError, "changed"):
            self.tracker.update(1, updated, github.digest(self.api.issues[0]["body"]))

    def test_update_preserves_creation_identity_and_rejects_kind_changes(self):
        created = self.tracker.create(item(), "request-0001")
        updated = {**item(), "title": "Updated"}
        self.tracker.update(1, updated, created["body_hash"])
        self.assertTrue(self.tracker.create(item(), "request-0001")["reconciled"])
        current = self.tracker.compact(self.api.issues[0])
        with self.assertRaisesRegex(records.ItemError, "cannot change"):
            self.tracker.update(1, item("task"), current["body_hash"])

    def test_uncertain_comment_reconciles_and_changed_comment_refuses_retry(self):
        self.tracker.create(item(), "request-0001")
        self.api.fail_after_comment = True
        first = self.tracker.comment(1, "Actual verification", "comment-0001", "close")
        second = self.tracker.comment(1, "Actual verification", "comment-0001", "close")
        self.assertEqual(first, second)
        self.assertEqual(1, len(self.api.comments))
        self.api.comments[0]["body"] = "Changed\n" + self.api.comments[0]["body"]
        with self.assertRaisesRegex(records.ItemError, "different facts"):
            self.tracker.comment(1, "Actual verification", "comment-0001", "close")

    def test_pull_requests_and_oversized_bodies_cannot_be_mutated(self):
        self.tracker.create(item(), "request-0001")
        self.api.issues[0]["pull_request"] = {}
        self.assertEqual([], self.tracker.all())
        with self.assertRaisesRegex(records.ItemError, "expected issue"):
            self.tracker.get(1)
        with self.assertRaisesRegex(records.ItemError, "exceeds"):
            self.tracker.create({**item(), "evidence": "a" * 65536}, "request-0002")
        with self.assertRaises(records.ItemError):
            self.tracker.comment(1, " ", "comment-0001")

    def test_issue_identity_never_crosses_selected_repository(self):
        for value in ("owner/project#1", "https://github.com/owner/project/issues/1"):
            self.assertEqual(1, github.issue_number(value, "owner/project"))
        for value in ("1", "other/project#1", "owner/project#0", "owner/project#١", "https://github.com/owner/project/pull/1"):
            with self.assertRaises(records.ItemError):
                github.issue_number(value, "owner/project")


class SelectionTests(unittest.TestCase):
    def test_no_selection_different_origin_and_work_backend_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(records.ItemError, "explicit"):
                github.selection(root)
            path = root / github.CONFIG
            path.write_text(json.dumps(CONFIG), encoding="utf-8")
            with patch.object(github, "source_repository", return_value="other/project"):
                with self.assertRaisesRegex(records.ItemError, "does not match"):
                    github.selection(root)
            path.write_text(json.dumps({**CONFIG, "backend": "azure-devops"}), encoding="utf-8")
            with self.assertRaisesRegex(records.ItemError, "explicitly selected GitHub"):
                github.selection(root)

    def test_gh_transport_uses_argument_arrays_and_flattens_all_pages(self):
        response = subprocess.CompletedProcess([], 0, stdout='[[{"number":1}],[{"number":2}]]', stderr="")
        with patch.object(github.subprocess, "run", return_value=response) as run:
            result = github.GitHub().request("GET", "repos/owner/project/issues", paginate=True)
            self.assertEqual([1, 2], [v["number"] for v in result])
            args, kwargs = run.call_args
            self.assertIn("--slurp", args[0])
            self.assertNotIn("shell", kwargs)
            self.assertEqual("utf-8", kwargs["encoding"])


if __name__ == "__main__":
    unittest.main()
