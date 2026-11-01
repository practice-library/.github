"""The launcher loads only the package beside it, whatever the caller's tree or environment holds."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from practice_ci import policy

LAUNCHER = policy.path("tooling.launcher")
LAUNCH_PY = LAUNCHER.parent / "launch.py"


class Launcher(unittest.TestCase):
    def setUp(self):
        self.scratch = Path(tempfile.mkdtemp())
        self.marker = self.scratch / "poisoned"
        poison = "open(%r, 'w').write('imported')\n" % str(self.marker)
        # A caller tree that tries to replace the package and a standard module.
        (self.scratch / "practice_ci").mkdir()
        (self.scratch / "practice_ci" / "__init__.py").write_text(poison)
        (self.scratch / "practice_ci" / "cli.py").write_text(poison)
        (self.scratch / "json.py").write_text(poison)
        (self.scratch / "argparse.py").write_text(poison)

    def tearDown(self):
        shutil.rmtree(self.scratch, ignore_errors=True)

    def run_launcher(self, *args, env_extra=None, command=None):
        env = dict(os.environ)
        env.update({"PYTHONPATH": str(self.scratch), "PYTHONSTARTUP": str(self.scratch / "json.py"),
                    "PYTHONHOME": os.environ.get("PYTHONHOME", "")})
        if not env["PYTHONHOME"]:
            del env["PYTHONHOME"]
        env.update(env_extra or {})
        return subprocess.run(command or [str(LAUNCHER), *args], cwd=self.scratch, env=env,
                              capture_output=True, text=True, check=False)

    def test_caller_modules_are_never_imported(self):
        proc = self.run_launcher("version")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn(str(policy.ROOT), proc.stdout)
        self.assertFalse(self.marker.exists(), "a module from the caller's tree or PYTHONPATH was imported")

    def test_version_names_the_interpreter(self):
        proc = self.run_launcher("version")
        self.assertRegex(proc.stdout, r"python \d+\.\d+\.\d+ ")

    def test_bootstrap_refuses_a_run_without_isolation(self):
        proc = self.run_launcher(command=[sys.executable, str(LAUNCH_PY), "version"])
        self.assertEqual(proc.returncode, 2)
        self.assertIn("-I", proc.stderr)
        self.assertFalse(self.marker.exists())

    def test_policy_python_is_enforced_when_asked(self):
        proc = self.run_launcher("version", "--require-policy-python")
        wanted = policy.value("tooling.pythonVersion")
        if proc.stdout.find("python %s " % wanted) >= 0:
            self.assertEqual(proc.returncode, 0, proc.stdout)
        else:
            self.assertEqual(proc.returncode, 2, proc.stdout)
            self.assertIn("bootstrap.python-version", proc.stdout)


if __name__ == "__main__":
    unittest.main()
