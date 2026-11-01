"""The shell inside workflow steps, run for real: the self-checkout fragment and the guard's range step."""
import os
import re
import subprocess
import tempfile
import unittest

from tooling.tests import ROOT
from practice_ci import check_steps, config

FRAGMENT = os.path.join(ROOT, "templates", "fragments", "self-checkout.yml")
GUARD = os.path.join(ROOT, "templates", ".github", "workflows", "guard.yml")
NAME_VERIFY_INPUTS = "The called workflow must say which tooling it is"
NAME_VERIFY_HEAD = "The tooling is at exactly that commit"
NAME_RANGE = "The change to check"
SHA = "0123456789abcdef0123456789abcdef01234567"


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def fill(script):
    return re.sub(r"@@([A-Za-z0-9_.]+)@@", lambda m: str(config.get(*m.group(1).split("."))), script)


def bash(script, env=None, cwd=None):
    full = {"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "/"), **(env or {})}
    return subprocess.run(["bash"], input=fill(script), capture_output=True, text=True, env=full, cwd=cwd, check=False)


def git(cwd, *args):
    done = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false", *args],
        cwd=cwd, capture_output=True, text=True, check=True)
    return done.stdout.strip()


class SelfCheckoutFragmentTest(unittest.TestCase):
    def setUp(self):
        self.text = read(FRAGMENT)

    def test_inputs_must_be_present_and_the_sha_40_hex(self):
        script = check_steps.block_named(self.text, NAME_VERIFY_INPUTS)
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out")
            open(out, "w").close()
            ok = bash(script, {"WORKFLOW_REPOSITORY": "o/r", "WORKFLOW_SHA": SHA, "GITHUB_OUTPUT": out})
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertEqual(read(out), "sha=%s\n" % SHA)
            for repo, sha in (("", SHA), ("o/r", ""), ("o/r", SHA[:39]), ("o/r", SHA + "0"), ("o/r", SHA.upper()), ("o/r", "main"), ("o/r", SHA[:39] + "\n")):
                with self.subTest(repo=repo, sha=sha):
                    open(out, "w").close()
                    self.assertNotEqual(bash(script, {"WORKFLOW_REPOSITORY": repo, "WORKFLOW_SHA": sha, "GITHUB_OUTPUT": out}).returncode, 0)
                    self.assertEqual(read(out), "", "a refused commit must not be published")

    def test_head_of_the_checkout_must_be_the_workflow_sha(self):
        script = check_steps.block_named(self.text, NAME_VERIFY_HEAD)
        with tempfile.TemporaryDirectory() as workspace:
            tooling = os.path.join(workspace, config.get("selfCheckout", "dir"))
            os.makedirs(tooling)
            git(tooling, "init", "-q")
            git(tooling, "commit", "-q", "--allow-empty", "-m", "one")
            head = git(tooling, "rev-parse", "HEAD")
            self.assertEqual(bash(script, {"WORKFLOW_SHA": head, "GITHUB_WORKSPACE": workspace}).returncode, 0)
            self.assertNotEqual(bash(script, {"WORKFLOW_SHA": SHA, "GITHUB_WORKSPACE": workspace}).returncode, 0)
            self.assertNotEqual(bash(script, {"WORKFLOW_SHA": "", "GITHUB_WORKSPACE": workspace}).returncode, 0)
            self.assertNotEqual(bash(script, {"WORKFLOW_SHA": head[:7], "GITHUB_WORKSPACE": workspace}).returncode, 0)

    def test_the_commit_is_chosen_once_and_the_same_one_is_checked_out_and_verified(self):
        # A repository running its own reusable workflow (a local call, from its pull request) has the
        # caller's commit as job.workflow_sha, the merge commit; checking out any other ref and comparing
        # with this one failed in CI. The chosen ref is pinned here, and checkout and verification both use it.
        text = fill(self.text)
        chosen = "${{ job.workflow_repository == github.repository && github.sha || job.workflow_sha }}"
        output = "${{ steps.tooling-ref.outputs.sha }}"
        self.assertEqual(text.count(chosen), 1)
        self.assertEqual(text.count("WORKFLOW_SHA: " + chosen), 1)
        self.assertIn("ref: " + output, text)
        self.assertEqual(text.count("WORKFLOW_SHA: " + output), 1)
        self.assertNotIn("ref: ${{ job.workflow_sha }}", text)
        self.assertIn("id: tooling-ref", text)

    def test_checkout_is_a_sibling_of_the_caller_and_keeps_no_credentials(self):
        text = fill(self.text)
        self.assertIn("repository: ${{ job.workflow_repository }}", text)
        self.assertEqual(text.count("persist-credentials: false"), 2)
        self.assertIn("path: " + config.get("selfCheckout", "dir"), text)
        self.assertIn("path: " + config.get("selfCheckout", "callerDir"), text)
        self.assertNotEqual(config.get("selfCheckout", "dir"), config.get("selfCheckout", "callerDir"))
        pin = config.get("actions", "checkout")
        self.assertEqual(text.count("uses: %s@%s # %s" % (pin["repo"], pin["sha"], pin["version"])), 2)

    def test_the_guard_has_the_include_point_after_its_own_checkout(self):
        guard = read(GUARD)
        include = guard.index("#@include self-checkout.yml")
        self.assertGreater(include, guard.index("persist-credentials: false"))
        self.assertLess(include, guard.index("- name: " + NAME_RANGE))

    def test_guard_uses_the_workflow_checkout_for_approvals_and_git_guards(self):
        guard = read(GUARD)
        self.assertEqual(guard.count("TOOLING: ${{ github.workspace }}/@@selfCheckout.dir@@/tooling"), 3)
        self.assertIn("@@git.runnerEnv@@: ${{ github.workspace }}/@@selfCheckout.dir@@/@@tooling.launcher@@", guard)
        self.assertNotIn("ref: @@release.tag@@", guard)

    def test_every_step_shell_parses(self):
        self.assertEqual(check_steps.parse_errors(self.text, "fragment"), [])
        self.assertEqual(check_steps.parse_errors(read(GUARD), "guard"), [])


class GuardRangeStepTest(unittest.TestCase):
    def setUp(self):
        self.script = check_steps.block_named(read(GUARD), NAME_RANGE)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = os.path.join(self.tmp.name, "repo")
        os.makedirs(self.repo)
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "a")
        self.a = git(self.repo, "rev-parse", "HEAD")
        git(self.repo, "checkout", "-q", "-b", "side")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "b")
        self.b = git(self.repo, "rev-parse", "HEAD")
        git(self.repo, "checkout", "-q", "main")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "c")
        self.c = git(self.repo, "rev-parse", "HEAD")
        self.out = os.path.join(self.tmp.name, "out")

    def step(self, **env):
        base = {"GUARD": "denylist", "GUARDS": '["denylist","size"]', "EVENT": "pull_request", "PR_BASE": "", "PR_HEAD": "",
                "PUSH_BEFORE": "", "PUSH_AFTER": "", "GITHUB_OUTPUT": self.out}
        done = bash(self.script, {**base, **env}, cwd=self.repo)
        outputs = {}
        if os.path.exists(self.out):
            outputs = dict(line.split("=", 1) for line in read(self.out).splitlines())
            os.remove(self.out)
        return done, outputs

    def test_unknown_guard_fails(self):
        done, _ = self.step(GUARD="nope")
        self.assertNotEqual(done.returncode, 0)

    def test_pull_request_range_is_from_the_merge_base(self):
        done, out = self.step(PR_BASE=self.c, PR_HEAD=self.b)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(out, {"none": "false", "base": self.c, "mb": self.a, "head": self.b})

    def test_push_range_and_no_range(self):
        done, out = self.step(EVENT="push", PUSH_BEFORE=self.a, PUSH_AFTER=self.c)
        self.assertEqual((done.returncode, out), (0, {"none": "false", "base": self.a, "mb": self.a, "head": self.c}))
        for before in ("", "0" * 40):
            with self.subTest(before=before):
                done, out = self.step(EVENT="push", PUSH_BEFORE=before, PUSH_AFTER=self.c)
                self.assertEqual((done.returncode, out), (0, {"none": "true"}))

    def test_other_events_have_no_range(self):
        done, out = self.step(EVENT="workflow_dispatch")
        self.assertEqual((done.returncode, out), (0, {"none": "true"}))


if __name__ == "__main__":
    unittest.main()
