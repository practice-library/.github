"""scripts/mutants.sh counts a mutant as killed only on a behavioural failure (issue 71).

Each test builds a throwaway repository holding the real runner scripts and one tiny library or step.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from tooling.tests import ROOT, TOOLING
from practice_ci import config

LIB = "main() { jq -nr '\"ok\"'; }\n"
STEP = "steps:\n  - name: demo\n    run: |\n      set -euo pipefail\n      [ \"$A\" = \"1\" ]\n"
STEP_TEST = """import subprocess, sys, unittest
sys.path.insert(0, %r)
from practice_ci import check_steps


class Demo(unittest.TestCase):
    def run_step(self, a):
        with open("step.yml", encoding="utf-8") as f:
            script = check_steps.block_named(f.read(), "demo")
        return subprocess.run(["bash"], input=script, text=True, env={"A": a, "PATH": "/usr/bin:/bin"}, check=False).returncode

    def test_a_decides(self):
        self.assertEqual(self.run_step("1"), 0)
        self.assertNotEqual(self.run_step("2"), 0)
"""


def write(base, rel, body):
    path = os.path.join(base, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body if isinstance(body, str) else json.dumps(body))


class MutantsRunnerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.box = self.tmp.name
        os.makedirs(os.path.join(self.box, "scripts"))
        for script in ("mutants.sh", "unit.sh"):
            shutil.copy(os.path.join(ROOT, "scripts", script), os.path.join(self.box, "scripts", script))
        os.symlink(os.path.join(ROOT, config.get("tooling", "launcher")), os.path.join(self.box, config.get("tooling", "launcher")))
        constants = config.load()
        constants["selftest"].update({"unitDir": "unit", "libDir": "lib", "mutantsDir": "selftest/mutants"})
        write(self.box, "policy/constants.json", constants)

    def run_runner(self, *names):
        done = subprocess.run(["bash", "scripts/mutants.sh", *names], cwd=self.box, capture_output=True, text=True, check=False)
        return done.returncode, done.stdout + done.stderr

    def lib(self, mutants):
        write(self.box, "lib/demo.sh", LIB)
        write(self.box, "unit/demo/a.json", {"env": {}, "expect": "ok"})
        write(self.box, "selftest/mutants/demo.json", mutants)

    def step(self, mutants):
        write(self.box, "step.yml", STEP)
        write(self.box, "demo_step_test.py", STEP_TEST % TOOLING)
        write(self.box, "selftest/mutants/step-demo.json", {"target": "step.yml", "tests": ["demo_step_test"], "mutants": mutants})

    def test_a_behaviour_change_is_caught(self):
        self.lib([{"name": "flip", "find": "\"ok\"", "replace": "\"no\""}])
        rc, out = self.run_runner("demo")
        self.assertEqual(rc, 0, out)
        self.assertIn("caught demo/flip by demo/a", out)

    def test_a_jq_program_that_no_longer_compiles_is_not_a_kill(self):
        self.lib([{"name": "jq-broken", "find": "'\"ok\"'", "replace": "'\"ok\" |'"}])
        rc, out = self.run_runner("demo")
        self.assertNotEqual(rc, 0, out)
        self.assertIn("FAIL demo/jq-broken", out)
        self.assertNotIn("caught demo/jq-broken", out)

    def test_a_shell_syntax_error_is_not_a_kill(self):
        self.lib([{"name": "sh-broken", "find": "; }", "replace": ";"}])
        rc, out = self.run_runner("demo")
        self.assertNotEqual(rc, 0, out)
        self.assertIn("FAIL demo/sh-broken", out)

    def test_a_survivor_and_a_stale_mutant_fail(self):
        self.lib([{"name": "same", "find": "-nr", "replace": "-n -r"}, {"name": "gone", "find": "absent", "replace": "x"}])
        rc, out = self.run_runner("demo")
        self.assertNotEqual(rc, 0, out)
        self.assertIn("FAIL demo/same: survived", out)
        self.assertIn("FAIL demo/gone: the find text is not in", out)
        self.assertIn("2 mutants, 2 not caught", out)

    def test_a_target_that_fails_unmutated_is_an_error_not_a_pile_of_kills(self):
        self.lib([{"name": "flip", "find": "\"ok\"", "replace": "\"no\""}])
        write(self.box, "unit/demo/a.json", {"env": {}, "expect": "never"})
        rc, out = self.run_runner("demo")
        self.assertNotEqual(rc, 0, out)
        self.assertIn("already fails its tests unmutated", out)
        self.assertNotIn("caught demo/", out)

    def test_the_library_is_restored_after_every_run(self):
        self.lib([{"name": "flip", "find": "\"ok\"", "replace": "\"no\""}, {"name": "jq-broken", "find": "'\"ok\"'", "replace": "'\"ok\" |'"}])
        self.run_runner("demo")
        with open(os.path.join(self.box, "lib", "demo.sh"), encoding="utf-8") as f:
            self.assertEqual(f.read(), LIB)

    def test_a_step_behaviour_change_is_caught_and_a_step_syntax_error_is_not(self):
        self.step([
            {"name": "flip", "find": "[ \"$A\" = \"1\" ]", "replace": "[ \"$A\" != \"1\" ]"},
            {"name": "broken", "find": "[ \"$A\" = \"1\" ]", "replace": "[ \"$A\" = \"1\" ] ) "},
            {"name": "comment", "find": "set -euo pipefail", "replace": "set -euo pipefail  # same"},
        ])
        rc, out = self.run_runner("step-demo")
        self.assertNotEqual(rc, 0, out)
        self.assertIn("caught step-demo/flip by test_a_decides", out)
        self.assertIn("FAIL step-demo/broken: the mutated step.yml does not parse", out)
        self.assertIn("FAIL step-demo/comment: survived", out)
        self.assertIn("3 mutants, 2 not caught", out)


if __name__ == "__main__":
    unittest.main()
