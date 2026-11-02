"""Every shell unit case of the schema-loosening guard (selftest/unit/schema-loosening) must give the same
line through the Python classifier: the port changes no verdict and no path."""
import glob
import json
import os
import unittest

from tooling.practice_ci import compatibility

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CASES = sorted(glob.glob(os.path.join(ROOT, "selftest", "unit", "schema-loosening", "*.json")))


def _abs(p):
    return os.path.join(ROOT, p) if p else p


class UnitCases(unittest.TestCase):
    def test_there_are_cases(self):
        self.assertGreater(len(CASES), 100)

    def test_every_case(self):
        failures = []
        for path in CASES:
            with open(path, encoding="utf-8") as f:
                case = json.load(f)
            env = case["env"]
            got = compatibility.judge_files(_abs(env.get("OLD_FILE", "")), _abs(env.get("NEW_FILE", "")),
                                            env.get("TIGHTEN"), env.get("FILE_PATH", ""))
            want = case["expect"]
            output = case.get("output")
            if got.split(" ")[0] != want or (output is not None and got != output):
                failures.append("%s: want %s %s, got %s" % (os.path.basename(path), want, output or "", got))
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
