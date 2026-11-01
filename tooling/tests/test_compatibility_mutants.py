"""Every rule of the classifier is covered: for each mutant in mutants/compatibility.json ({"name", "find",
"replace"}), a copy of the package with the mutation applied must turn a case or a rule test red. A mutant
whose find text is not in the source is stale; one that does not compile proves nothing; one that survives
means a rule no test needs."""
import json
import os
import py_compile
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TESTS = ("tooling.tests.test_compatibility_cases", "tooling.tests.test_compatibility_rules")
TARGET = os.path.join("tooling", "practice_ci", "compatibility.py")


def _mutants():
    with open(os.path.join(ROOT, "tooling", "tests", "mutants", "compatibility.json"), encoding="utf-8") as f:
        return json.load(f)


class Mutants(unittest.TestCase):
    def test_every_mutant_is_caught(self):
        problems = []
        with tempfile.TemporaryDirectory() as tmp:
            for part in ("tooling", "policy"):
                shutil.copytree(os.path.join(ROOT, part), os.path.join(tmp, part),
                                ignore=shutil.ignore_patterns("__pycache__", "mutants"))
            os.symlink(os.path.join(ROOT, "selftest"), os.path.join(tmp, "selftest"))
            target = os.path.join(tmp, TARGET)
            with open(target, encoding="utf-8") as f:
                original = f.read()
            names = [m["name"] for m in _mutants()]
            self.assertEqual(len(names), len(set(names)), "duplicate mutant names")
            for m in _mutants():
                if original.count(m["find"]) < 1:
                    problems.append("%s: stale, the find text is not in the source" % m["name"])
                    continue
                with open(target, "w", encoding="utf-8") as f:
                    f.write(original.replace(m["find"], m["replace"], 1))
                try:
                    py_compile.compile(target, doraise=True, cfile=os.path.join(tmp, "check.pyc"))
                except py_compile.PyCompileError:
                    problems.append("%s: the mutated module does not compile, so it proves nothing" % m["name"])
                    continue
                run = subprocess.run([sys.executable, "-B", "-m", "unittest", *TESTS], cwd=tmp,
                                     capture_output=True, text=True)
                if run.returncode == 0:
                    problems.append("%s: survived, no case turned red" % m["name"])
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
