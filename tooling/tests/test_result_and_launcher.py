import json
import os
import subprocess
import tempfile
import unittest

from tooling.tests import ROOT
from practice_ci import config, result

LAUNCHER = os.path.join(ROOT, config.get("tooling", "launcher"))


def launch(*args, cwd=None, env=None):
    return subprocess.run(["python3", "-I", LAUNCHER, *args], capture_output=True, text=True, cwd=cwd, env=env, check=False)


class ResultTest(unittest.TestCase):
    def test_json_shape(self):
        res = result.failed("c", ["why"], ["e"])
        self.assertEqual(list(json.loads(res.to_json())), ["ok", "check", "reasons", "evidence"])
        self.assertEqual(json.loads(res.to_json()), {"ok": False, "check": "c", "reasons": ["why"], "evidence": ["e"]})

    def test_exit_codes_come_from_config(self):
        codes = config.get("tooling", "exitCodes")
        self.assertEqual(result.passed("c").exit_code(), codes["pass"])
        self.assertEqual(result.failed("c", ["x"]).exit_code(), codes["fail"])
        self.assertEqual(result.error("c", "x").exit_code(), codes["error"])
        self.assertEqual(len(set(codes.values())), 3)

    def test_an_error_is_not_in_the_json(self):
        self.assertNotIn("errored", result.error("c", "x").to_dict())


class LauncherTest(unittest.TestCase):
    def test_invalid_python_input_still_returns_one_json_error(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "tooling"))
            with open(os.path.join(root, "tooling", "bad.py"), "w", encoding="utf-8") as f:
                f.write("if\n")
            done = launch("lint-literals", root)
            self.assertEqual(done.returncode, config.get("tooling", "exitCodes")["error"])
            self.assertFalse(json.loads(done.stdout)["ok"])
            self.assertEqual(done.stderr, "")

    def test_runs_a_command_and_prints_one_json_result(self):
        done = launch("lint-literals")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertTrue(json.loads(done.stdout)["ok"])

    def test_unknown_command_and_no_command_are_errors(self):
        for args in (("nope",), ()):
            done = launch(*args)
            self.assertEqual(done.returncode, config.get("tooling", "exitCodes")["error"])
            self.assertFalse(json.loads(done.stdout)["ok"])

    def test_a_command_name_cannot_reach_the_private_modules(self):
        self.assertEqual(launch("config").returncode, config.get("tooling", "exitCodes")["error"])

    def test_never_imports_code_from_the_caller(self):
        with tempfile.TemporaryDirectory() as caller:
            for module in ("json.py", "re.py"):
                with open(os.path.join(caller, module), "w", encoding="utf-8") as f:
                    f.write("raise SystemExit(99)\n")
            env = dict(os.environ, PYTHONPATH=caller)
            done = launch("lint-literals", cwd=caller, env=env)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)


if __name__ == "__main__":
    unittest.main()
