"""Exact-head approval receipts (#31, #74). Every REST response is mocked; nothing touches the network."""
import contextlib
import io
import json
import os
import subprocess
import tempfile
from pathlib import Path
import unittest

from tooling.practice_ci import approvals, config

CFG = config.get("approvals")
REPO = "example/repo"
NUMBER = 7
OLD = "a" * 40
HEAD = "b" * 40
AUTHOR = "contributor"
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def review(login, commit, state="APPROVED", body="", user_type="User"):
    return {"user": {"login": login, "type": user_type}, "state": state, "commit_id": commit, "body": body}


def publication_body(head=HEAD, statement=None):
    return "%s\n%s%s\n" % (statement or CFG["publicationStatement"], CFG["headPrefix"], head)


class FakeClient:
    """Answers the three REST paths approvals.check reads, and records what was asked."""

    def __init__(self, head, reviews, roles, author=AUTHOR):
        self.head, self.reviews, self.roles, self.author = head, reviews, roles, author
        self.paths = []

    def get(self, path):
        self.paths.append(path)
        if path == "repos/%s/pulls/%d" % (REPO, NUMBER):
            return {"head": {"sha": self.head}, "user": {"login": self.author}}
        prefix = "repos/%s/collaborators/" % REPO
        if path.startswith(prefix) and path.endswith("/permission"):
            login = path[len(prefix):-len("/permission")]
            return {"permission": "read", "role_name": self.roles.get(login, "read")}
        raise AssertionError("unexpected GET " + path)

    def get_all(self, path):
        self.paths.append(path)
        if path == "repos/%s/pulls/%d/reviews" % (REPO, NUMBER):
            return list(self.reviews)
        raise AssertionError("unexpected GET " + path)


def run(head, reviews, roles, kind="schema-loosening", expected=None):
    return approvals.check(FakeClient(head, reviews, roles), REPO, NUMBER, kind, CFG, expected)


class ExactHead(unittest.TestCase):
    def test_valid_review_at_head_passes(self):
        v = run(HEAD, [review("maintainer", HEAD)], {"maintainer": "maintain"})
        self.assertTrue(v.ok, str(v))
        self.assertIn(HEAD, v.message)

    def test_admin_passes(self):
        self.assertTrue(run(HEAD, [review("owner", HEAD)], {"owner": "admin"}).ok)

    def test_approval_at_old_head_is_rejected(self):
        v = run(HEAD, [review("maintainer", OLD)], {"maintainer": "maintain"})
        self.assertEqual(v.status, approvals.MISSING, str(v))
        self.assertIn("older head", v.message)

    def test_new_head_blocks_again(self):
        reviews = [review("maintainer", OLD)]
        roles = {"maintainer": "maintain"}
        self.assertTrue(run(OLD, reviews, roles).ok)
        self.assertFalse(run(HEAD, reviews, roles).ok)

    def test_stale_run_for_moved_head_is_refused(self):
        v = run(HEAD, [review("maintainer", HEAD)], {"maintainer": "maintain"}, expected=OLD)
        self.assertEqual(v.status, approvals.REFUSED, str(v))

    def test_later_changes_requested_revokes(self):
        reviews = [review("maintainer", HEAD), review("maintainer", HEAD, state="CHANGES_REQUESTED")]
        self.assertFalse(run(HEAD, reviews, {"maintainer": "maintain"}).ok)

    def test_dismissed_approval_does_not_count(self):
        reviews = [review("maintainer", HEAD, state="DISMISSED")]
        self.assertFalse(run(HEAD, reviews, {"maintainer": "maintain"}).ok)

    def test_later_comment_keeps_approval(self):
        reviews = [review("maintainer", HEAD), review("maintainer", HEAD, state="COMMENTED")]
        self.assertTrue(run(HEAD, reviews, {"maintainer": "maintain"}).ok)


class WhoMayApprove(unittest.TestCase):
    def test_author_is_rejected(self):
        v = run(HEAD, [review(AUTHOR, HEAD)], {AUTHOR: "admin"})
        self.assertEqual(v.status, approvals.REFUSED, str(v))
        self.assertIn("author", v.message)

    def test_bot_by_type_is_rejected(self):
        v = run(HEAD, [review("helper", HEAD, user_type="Bot")], {"helper": "admin"})
        self.assertEqual(v.status, approvals.REFUSED, str(v))

    def test_bot_by_login_is_rejected(self):
        login = "helper" + CFG["botSuffix"]
        v = run(HEAD, [review(login, HEAD)], {login: "admin"})
        self.assertEqual(v.status, approvals.REFUSED, str(v))

    def test_write_role_is_rejected(self):
        v = run(HEAD, [review("writer", HEAD)], {"writer": "write"})
        self.assertEqual(v.status, approvals.REFUSED, str(v))
        self.assertIn("role write", v.message)

    def test_unauthorized_reviewer_is_rejected(self):
        self.assertFalse(run(HEAD, [review("stranger", HEAD)], {}).ok)

    def test_permission_is_read_over_rest(self):
        client = FakeClient(HEAD, [review("maintainer", HEAD)], {"maintainer": "maintain"})
        approvals.check(client, REPO, NUMBER, "size", CFG)
        self.assertIn("repos/%s/collaborators/maintainer/permission" % REPO, client.paths)

    def test_one_good_approval_among_bad_passes(self):
        reviews = [review(AUTHOR, HEAD), review("writer", HEAD), review("maintainer", HEAD)]
        self.assertTrue(run(HEAD, reviews, {"writer": "write", "maintainer": "maintain"}).ok)


class Labels(unittest.TestCase):
    def test_labels_never_authorize(self):
        # A label alone (no review) is not an approval; the module never reads labels at all.
        client = FakeClient(HEAD, [], {})
        v = approvals.check(client, REPO, NUMBER, "schema-loosening", CFG)
        self.assertEqual(v.status, approvals.MISSING)
        self.assertFalse(any("labels" in p or "events" in p for p in client.paths))

    def test_unknown_kind_is_refused(self):
        self.assertEqual(run(HEAD, [review("maintainer", HEAD)], {"maintainer": "maintain"}, kind="nope").status,
                         approvals.REFUSED)


class Publication(unittest.TestCase):
    KIND = CFG["publicationKind"]
    ROLES = {"maintainer": "maintain"}

    def test_valid_publication_passes(self):
        self.assertTrue(run(HEAD, [review("maintainer", HEAD, body=publication_body())], self.ROLES, self.KIND).ok)

    def test_missing_publication_line_is_rejected(self):
        body = "%s%s\n" % (CFG["headPrefix"], HEAD)
        v = run(HEAD, [review("maintainer", HEAD, body=body)], self.ROLES, self.KIND)
        self.assertEqual(v.status, approvals.REFUSED, str(v))
        self.assertIn("statement", v.message)

    def test_missing_head_line_is_rejected(self):
        body = CFG["publicationStatement"] + "\n"
        self.assertFalse(run(HEAD, [review("maintainer", HEAD, body=body)], self.ROLES, self.KIND).ok)

    def test_head_line_naming_another_commit_is_rejected(self):
        body = publication_body(head=OLD)
        self.assertFalse(run(HEAD, [review("maintainer", HEAD, body=body)], self.ROLES, self.KIND).ok)

    def test_statement_inside_other_text_is_rejected(self):
        body = "Not yet: %s\n%s%s\n" % (CFG["publicationStatement"], CFG["headPrefix"], HEAD)
        self.assertFalse(run(HEAD, [review("maintainer", HEAD, body=body)], self.ROLES, self.KIND).ok)

    def test_plain_approval_is_not_a_publication_approval(self):
        self.assertFalse(run(HEAD, [review("maintainer", HEAD)], self.ROLES, self.KIND).ok)


class FakeResponse:
    def __init__(self, payload, link=""):
        self.payload, self.headers = payload, {"Link": link} if link else {}

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Rest(unittest.TestCase):
    def test_pagination_follows_next_link(self):
        pages = {}
        first = "%s/repos/%s/pulls/%d/reviews?per_page=%d" % (CFG["apiUrl"], REPO, NUMBER, CFG["perPage"])
        second = first + "&page=2"
        pages[first] = FakeResponse([review("a", HEAD)], '<%s>; rel="next", <%s>; rel="last"' % (second, second))
        pages[second] = FakeResponse([review("b", HEAD)])
        seen = []

        def opener(req, timeout):
            seen.append((req.full_url, req.get_header("Authorization"), timeout))
            return pages[req.full_url]

        client = approvals.RestClient("t0ken", CFG, opener=opener)
        got = client.get_all("repos/%s/pulls/%d/reviews" % (REPO, NUMBER))
        self.assertEqual([r["user"]["login"] for r in got], ["a", "b"])
        self.assertEqual([s[0] for s in seen], [first, second])
        self.assertTrue(all(s[1] == "Bearer t0ken" and s[2] == CFG["timeoutSeconds"] for s in seen))

    def test_rest_only_never_graphql(self):
        with open(approvals.__file__, encoding="utf-8") as f:
            self.assertNotIn("graphql", f.read().lower())

    def test_cli_prints_verdict_and_exit_code(self):
        client = FakeClient(HEAD, [review("maintainer", HEAD)], {"maintainer": "maintain"})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = approvals.main(["--repo", REPO, "--pr", str(NUMBER), "--kind", "size", "--head", HEAD], client=client)
        self.assertEqual(code, 0)
        self.assertTrue(out.getvalue().startswith("ok approved by maintainer"))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = approvals.main(["--repo", REPO, "--pr", str(NUMBER), "--kind", "size", "--head", OLD], client=client)
        self.assertEqual(code, 1)
        self.assertTrue(out.getvalue().startswith("refused "))


class Templates(unittest.TestCase):
    """The guard no longer treats who added a label as the authorization."""

    def read(self, *parts):
        with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
            return f.read()

    def test_guard_uses_approval_receipts_not_label_events(self):
        guard = self.read("templates", ".github", "workflows", "guard.yml")
        self.assertNotIn("label-approval.sh", guard)
        self.assertNotIn("issues/$NUMBER/events", guard)
        self.assertEqual(guard.count("#@include approval-receipt.sh"), 3)

    def test_pr_python_package_and_startup_hooks_cannot_authorize(self):
        with tempfile.TemporaryDirectory() as directory:
            pr = Path(directory)
            package = pr / "practice_ci"
            package.mkdir()
            (package / "__init__.py").write_text("")
            (package / "approvals.py").write_text('print("ok attacker package")')
            (pr / "sitecustomize.py").write_text('print("ok attacker startup")')
            env = dict(os.environ, TOOLING=os.path.join(ROOT, "tooling"),
                       REPO=REPO, NUMBER=str(NUMBER), KIND=CFG["sizeKind"],
                       HEAD=HEAD, PYTHONPATH=directory)
            env.pop("GH_TOKEN", None)  # Real CLI refuses locally, without a network call.
            result = subprocess.run(
                ["bash", "-c", self.read("templates", "fragments", "approval-receipt.sh") + "\nmain"],
                cwd=directory, env=env, text=True, capture_output=True, check=True)
            self.assertTrue(result.stdout.startswith("refused "), result)
            self.assertNotIn("attacker", result.stdout)

    def test_review_event_compares_the_pull_request_range(self):
        guard = self.read("templates", ".github", "workflows", "guard.yml")
        script = guard.split('          base=""; head=""', 1)[1].split("\n      - name: denylist", 1)[0]
        script = 'base=""; head=""' + "\n".join(line[10:] for line in script.splitlines())
        with tempfile.TemporaryDirectory() as directory:
            output = os.path.join(directory, "output")
            env = dict(os.environ, EVENT="pull_request_review", PR_BASE=OLD,
                       PR_HEAD=HEAD, GITHUB_OUTPUT=output)
            subprocess.run(["bash", "-ec", 'git() { echo "$2"; }\n' + script],
                           env=env, text=True, capture_output=True, check=True)
            self.assertEqual(Path(output).read_text().splitlines(),
                             ["none=false", "base=" + OLD, "mb=" + OLD, "head=" + HEAD])

    def test_guard_approval_kinds_come_from_policy(self):
        guard = self.read("templates", ".github", "workflows", "guard.yml")
        self.assertEqual(guard.count("export KIND='@@approvals.schemaLooseningKind@@'"), 2)
        self.assertEqual(guard.count("export KIND='@@approvals.sizeKind@@'"), 1)
        for key in ("schemaLooseningKind", "sizeKind"):
            self.assertIn(CFG[key], CFG["kinds"])

    def test_gate_does_not_use_label_approval(self):
        self.assertNotIn("label-approval.sh", self.read("templates", ".github", "workflows", "gate.yml"))


if __name__ == "__main__":
    unittest.main()
