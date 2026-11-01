"""The mutation runner: a kill needs a wrong verdict; parse failures and errors are invalid mutants."""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from practice_ci import mutants


class Outcome(unittest.TestCase):
    def test_unit_wrong_verdict_kills_but_error_does_not(self):
        out = "ok   a/x: ok\nFAIL a/y: want ok, got: found 1\nFAIL a/z: want ok, got: error 1\n2 failed"
        self.assertEqual(mutants.outcome("unit:a", 1, out), (["a/y"], ["a/z"]))

    def test_unit_only_errors(self):
        out = "FAIL a/z: want ok, got: error 2\n"
        self.assertEqual(mutants.outcome("unit:a", 1, out), ([], ["a/z"]))

    def test_canary(self):
        out = "ok   p\nFAIL q: want exit 1, got 0: ok\nERROR r: exit 2: crash\n"
        self.assertEqual(mutants.outcome("canary", 1, out), (["q"], ["r"]))

    def test_lint(self):
        self.assertEqual(mutants.outcome("lint", 1, "FAIL label w.yml:3: x\n")[0], ["FAIL label w.yml:3: x"])
        self.assertEqual(mutants.outcome("lint", 2, "Traceback"), ([], ["lint exit 2"]))

    def test_unittest(self):
        out = "FAIL: test_a (tests.t.A.test_a)\nERROR: test_b (tests.t.A.test_b)\n"
        self.assertEqual(mutants.outcome("unittest:t*.py", 1, out), (["test_a"], ["test_b"]))

    def test_a_crash_with_nothing_parsed_is_an_error(self):
        self.assertEqual(mutants.outcome("canary", 2, "boom"), ([], ["canary exit 2"]))


class Parse(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.d)

    def problem(self, name, original, mutated):
        p = self.d / name
        p.write_text(mutated)
        return mutants.parse_problem(p, original, mutated)

    def test_python_that_does_not_compile(self):
        self.assertIsNotNone(self.problem("m.py", "x = 1\n", "x = = 1\n"))
        self.assertIsNone(self.problem("m.py", "x = 1\n", "x = 2\n"))

    def test_bash_that_does_not_parse(self):
        self.assertIsNotNone(self.problem("m.sh", "main() { :; }\n", "main() { if; }\n"))

    def test_embedded_jq_that_does_not_compile(self):
        good = "main() { jq -en --arg l \"$L\" '$l | length > 0'; }\n"
        bad = "main() { jq -en --arg l \"$L\" '$l | length > (0'; }\n"
        self.assertIsNotNone(self.problem("m.sh", good, bad))
        self.assertIsNone(self.problem("m.sh", good, good.replace("> 0", ">= 0")))

    def test_embedded_python_that_does_not_compile(self):
        good = "main() { python3 -I -c 'print(1)'; }\n"
        bad = "main() { python3 -I -c 'print(1'; }\n"
        self.assertIsNotNone(self.problem("m.sh", good, bad))


class Isolation(unittest.TestCase):
    def test_a_mutant_is_written_only_to_the_copy_and_restored(self):
        copy = Path(tempfile.mkdtemp())
        try:
            (copy / "t.py").write_text("x = 1\n")
            m = mutants.Mutant("n", "t.py", "x = 1", "x = 2")
            seen = []
            with mock.patch.object(mutants, "run_suite",
                                   lambda s, c, o: (seen.append((c / "t.py").read_text()), (1, "FAIL q: want exit 1, got 0"))[1]):
                caught, line = mutants._one(m, "f/n", "canary", copy, Path("/nonexistent.invalid"))
            self.assertTrue(caught, line)
            self.assertEqual(seen, ["x = 2\n"])
            self.assertEqual((copy / "t.py").read_text(), "x = 1\n")
        finally:
            shutil.rmtree(copy)

    def test_a_stale_mutant_fails(self):
        copy = Path(tempfile.mkdtemp())
        try:
            (copy / "t.py").write_text("x = 1\n")
            caught, line = mutants._one(mutants.Mutant("n", "t.py", "y", "z"), "f/n", "canary", copy, copy)
            self.assertFalse(caught)
            self.assertIn("stale", line)
        finally:
            shutil.rmtree(copy)


if __name__ == "__main__":
    unittest.main()
