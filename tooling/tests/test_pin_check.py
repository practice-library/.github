"""Runs templates/fragments/pin-check.sh with a stand-in for yq that reads JSON (JSON is YAML), so the
test needs no download. The unit cases under selftest/unit/pin-check run the same fragment with the real yq."""
import os
import stat
import subprocess
import tempfile
import unittest

from tooling.practice_ci import config

FRAGMENT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                        "templates", "fragments", "pin-check.sh")
ORG = "practice-library"
PINNED = "c" * 40
GOOD = f"{ORG}/.github/.github/workflows/gate.yml@{PINNED}"
BAD = f"{ORG}/.github/.github/workflows/gate.yml@main"

YQ_STUB = r'''#!/usr/bin/env python3
import json, sys
expr, path = sys.argv[2], sys.argv[3]
try:
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    out, n = [], 0
    def add(v):
        global n
        if v is not None or 'has("uses")' in expr:
            n += 1
            out.append({"line": n, "v": v})
    if ".runs.steps" in expr:
        for s in doc["runs"].get("steps") or []:
            if "uses" in s: add(s["uses"])
    else:
        for job in (doc.get("jobs") or {}).values():
            if "uses" in job: add(job["uses"])
            for s in job.get("steps") or []:
                if "uses" in s: add(s["uses"])
    print(json.dumps(out))
except Exception:
    sys.exit(1)
'''


def workflow(*uses):
    return '{"jobs": {"j": {"steps": [' + ",".join('{"uses": %s}' % u for u in uses) + "]}}}"


def action(*uses):
    return '{"runs": {"steps": [' + ",".join('{"uses": %s}' % u for u in uses) + "]}}"


def q(s):
    return '"%s"' % s


class PinCheck(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.bin = tempfile.mkdtemp()
        self.yq = os.path.join(self.bin, "yq")
        with open(self.yq, "w") as f:
            f.write(YQ_STUB)
        os.chmod(self.yq, os.stat(self.yq).st_mode | stat.S_IXUSR)
        with open(FRAGMENT, encoding="utf-8") as f:
            text = f.read().replace("@@pinCheck.maxLocalDepth@@", str(config.get("pinCheck", "maxLocalDepth")))
        self.lib = os.path.join(self.bin, "lib.sh")
        with open(self.lib, "w") as f:
            f.write(text)

    def put(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)

    def main(self):
        env = dict(os.environ, ROOT=self.root, ORG=ORG, YQ=self.yq)
        done = subprocess.run(["bash", "-c", 'source "$1"; main', "x", self.lib], env=env,
                              capture_output=True, text=True)
        return done.stdout.strip()

    def test_plain_pinned_workflow_is_ok(self):
        self.put(".github/workflows/a.yml", workflow(q(GOOD)))
        self.assertTrue(self.main().startswith("ok"))

    def test_local_composite_action_is_followed(self):
        self.put(".github/workflows/a.yml", workflow(q("./.github/actions/x")))
        self.put(".github/actions/x/action.yml", action(q(BAD)))
        self.assertEqual(self.main(), 'unpinned [".github/actions/x/action.yml:1 main"]')

    def test_local_composite_action_yaml_extension_and_pinned(self):
        self.put(".github/workflows/a.yml", workflow(q("./.github/actions/x")))
        self.put(".github/actions/x/action.yaml", action(q(GOOD)))
        self.assertTrue(self.main().startswith("ok"))

    def test_nested_local_actions_are_followed(self):
        self.put(".github/workflows/a.yml", workflow(q("./a")))
        self.put("a/action.yml", action(q("./b")))
        self.put("b/action.yml", action(q(BAD)))
        self.assertEqual(self.main(), 'unpinned ["b/action.yml:1 main"]')

    def test_cycle_terminates(self):
        self.put(".github/workflows/a.yml", workflow(q("./a")))
        self.put("a/action.yml", action(q("./a")))
        self.assertTrue(self.main().startswith("ok"))

    def test_depth_limit_refuses(self):
        depth = config.get("pinCheck", "maxLocalDepth")
        self.put(".github/workflows/a.yml", workflow(q("./d0")))
        for i in range(depth + 2):
            self.put(f"d{i}/action.yml", action(q(f"./d{i + 1}")))
        self.assertTrue(self.main().startswith("invalid"), self.main())

    def test_local_reusable_workflow_file_is_followed(self):
        self.put(".github/workflows/a.yml", '{"jobs": {"j": {"uses": "./other/w.yml"}}}')
        self.put("other/w.yml", workflow(q(BAD)))
        self.assertEqual(self.main(), 'unpinned ["other/w.yml:1 main"]')

    def test_non_string_uses_is_refused(self):
        self.put(".github/workflows/a.yml", workflow("5"))
        self.assertEqual(self.main(), "invalid .github/workflows/a.yml:1 uses is not a string")

    def test_non_string_uses_in_local_action_is_refused(self):
        self.put(".github/workflows/a.yml", workflow(q("./x")))
        self.put("x/action.yml", action('{"a": 1}'))
        self.assertEqual(self.main(), "invalid x/action.yml:1 uses is not a string")

    def test_null_workflow_step_uses_is_refused(self):
        self.put(".github/workflows/a.yml", workflow("null"))
        self.assertEqual(self.main(), "invalid .github/workflows/a.yml:1 uses is not a string")

    def test_null_workflow_job_uses_is_refused(self):
        self.put(".github/workflows/a.yml", '{"jobs": {"j": {"uses": null}}}')
        self.assertEqual(self.main(), "invalid .github/workflows/a.yml:1 uses is not a string")

    def test_null_composite_uses_is_refused(self):
        self.put(".github/workflows/a.yml", workflow(q("./x")))
        self.put("x/action.yml", action("null"))
        self.assertEqual(self.main(), "invalid x/action.yml:1 uses is not a string")

    def test_absent_uses_is_allowed_in_workflows_and_actions(self):
        self.put(".github/workflows/a.yml", '{"jobs": {"j": {"steps": [{"run": "true"}, {"uses": "./x"}]}}}')
        self.put("x/action.yml", '{"runs": {"steps": [{"run": "true"}]}}')
        self.assertTrue(self.main().startswith("ok"))

    def test_unparseable_local_action_is_refused(self):
        self.put(".github/workflows/a.yml", workflow(q("./x")))
        self.put("x/action.yml", "{ not parseable")
        self.assertEqual(self.main(), "invalid x/action.yml is not YAML")

    def test_unparseable_workflow_is_refused(self):
        self.put(".github/workflows/a.yml", "{ not parseable")
        self.assertEqual(self.main(), "invalid .github/workflows/a.yml is not YAML")

    def test_local_path_leaving_the_repository_is_refused(self):
        self.put(".github/workflows/a.yml", workflow(q("./../outside")))
        self.assertTrue(self.main().startswith("invalid"))

    def test_local_action_directory_symlink_escape_is_refused(self):
        with tempfile.TemporaryDirectory() as outside:
            with open(os.path.join(outside, "action.yml"), "w") as f:
                f.write(action(q(GOOD)))
            os.symlink(outside, os.path.join(self.root, "linked-action"))
            self.put(".github/workflows/a.yml", workflow(q("./linked-action")))
            self.assertIn("leaves the repository", self.main())

    def test_local_action_metadata_symlink_escape_is_refused(self):
        for name in ("action.yml", "action.yaml"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as outside:
                target = os.path.join(outside, name)
                with open(target, "w") as f:
                    f.write(action(q(GOOD)))
                self.put("local/keep", "")
                link = os.path.join(self.root, "local", name)
                os.symlink(target, link)
                self.put(".github/workflows/a.yml", workflow(q("./local")))
                self.assertIn("leaves the repository", self.main())
                os.unlink(link)

    def test_local_symlink_within_repository_is_followed(self):
        self.put("actual/action.yml", action(q(BAD)))
        os.symlink("actual", os.path.join(self.root, "linked-action"))
        self.put(".github/workflows/a.yml", workflow(q("./linked-action")))
        self.assertEqual(self.main(), 'unpinned ["actual/action.yml:1 main"]')

    def test_missing_local_action_is_refused(self):
        self.put(".github/workflows/a.yml", workflow(q("./nothing")))
        self.assertTrue(self.main().startswith("invalid"))
        self.put("empty/keep", "")
        self.put(".github/workflows/a.yml", workflow(q("./empty")))
        self.assertIn("has no action.yml", self.main())


if __name__ == "__main__":
    unittest.main()
