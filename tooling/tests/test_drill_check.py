"""tooling/practice_ci/drill_check.py against spec/drill-report/ (#36)."""
import contextlib
import copy
import glob
import io
import json
import os
import tempfile
import unittest

from tooling.practice_ci import drill_check

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SPEC = os.path.join(ROOT, "spec", "drill-report")

# Each semantic counter-example is schema-valid and breaks exactly one rule: the finding it must produce.
EXPECTED = {
    "mttd-off-by-one-ms": "mttdMs: is 7501",
    "mttd-ignores-sub-millisecond": "mttdMs: is 7500",
    "mttd-ignores-leap-day": "mttdMs: is 2000",
    "detected-before-injected": "detectedAt: precedes injectedAt",
    "scaled-wrong": "scaledMttdMs: is 37000",
    "scaled-rounded-up": "scaledMttdMs: is 16667",
    "within-true-over-objective": "withinObjective: is true",
    "within-false-under-objective": "withinObjective: is false",
    "within-false-at-objective": "withinObjective: is false",
    "notified-false-with-both-present": "notified: is false",
    "notified-before-detected": "notifiedAt: precedes detectedAt",
}


def load(directory, name):
    with open(os.path.join(SPEC, directory, name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def names(directory):
    return sorted(os.path.basename(p)[: -len(".json")] for p in glob.glob(os.path.join(SPEC, directory, "*.json")))


class Examples(unittest.TestCase):
    def test_every_example_is_consistent(self):
        self.assertGreaterEqual(len(names("examples")), 6)
        for name in names("examples"):
            with self.subTest(name):
                self.assertEqual(drill_check.check(load("examples", name)), [])

    def test_the_four_cases_the_issue_asks_for_exist(self):
        for name in ("within-objective", "over-objective", "detected-not-notified"):
            self.assertIn(name, names("examples"))
        self.assertIn("mttd-off-by-one-ms", names("semantic-counter-examples"))
        self.assertIn("missing-injected-at", names("counter-examples"))

    def test_over_objective_and_detection_only_read_as_such(self):
        self.assertFalse(load("examples", "over-objective")["withinObjective"])
        detection_only = load("examples", "detected-not-notified")
        self.assertFalse(detection_only["notified"])
        self.assertNotIn("notifiedAt", detection_only)


class SemanticCounterExamples(unittest.TestCase):
    def test_every_file_has_an_expected_finding_and_back(self):
        self.assertEqual(names("semantic-counter-examples"), sorted(EXPECTED))

    def test_each_is_refused_for_its_one_reason(self):
        for name, fragment in EXPECTED.items():
            with self.subTest(name):
                findings = drill_check.check(load("semantic-counter-examples", name))
                self.assertEqual(len(findings), 1, findings)
                self.assertIn(fragment, findings[0])


class Time(unittest.TestCase):
    def test_leap_day_is_a_day(self):
        before = drill_check.parse_time("2028-02-28T00:00:00Z")
        after = drill_check.parse_time("2028-03-01T00:00:00Z")
        self.assertEqual(after - before, 2 * 86400 * drill_check.NS_PER_SECOND)

    def test_fraction_is_exact_to_the_nanosecond(self):
        base = drill_check.parse_time("2026-10-31T12:00:00Z")
        self.assertEqual(drill_check.parse_time("2026-10-31T12:00:00.5Z") - base, 500_000_000)
        self.assertEqual(drill_check.parse_time("2026-10-31T12:00:00.000000001Z") - base, 1)

    def test_not_an_instant_is_refused(self):
        for text in ("2026-02-30T12:00:00Z", "2026-10-31T12:00:00+00:00", "2026-10-31T24:00:00Z", "yesterday", 7, None):
            with self.subTest(text):
                with self.assertRaises(ValueError):
                    drill_check.parse_time(text)


class Robustness(unittest.TestCase):
    def setUp(self):
        self.report = load("examples", "within-objective")

    def test_not_an_object(self):
        self.assertEqual(drill_check.check([]), ["report is not an object"])

    def test_missing_injected_at_is_a_finding_not_a_crash(self):
        report = copy.deepcopy(self.report)
        del report["injectedAt"]
        self.assertIn("injectedAt: missing", drill_check.check(report))

    def test_wrong_types_are_findings_not_crashes(self):
        report = copy.deepcopy(self.report)
        report.update(mttdMs="7500", withinObjective="true", notified=1, detectedAt="garbage")
        findings = drill_check.check(report)
        self.assertTrue(any(f.startswith("mttdMs:") for f in findings))
        self.assertTrue(any(f.startswith("detectedAt:") for f in findings))
        self.assertTrue(any(f.startswith("withinObjective:") for f in findings))
        self.assertTrue(any(f.startswith("notified:") for f in findings))

    def test_a_bool_is_not_an_integer(self):
        report = copy.deepcopy(self.report)
        report["threshold"] = True
        self.assertIn("threshold: missing or not an integer", drill_check.check(report))

    def test_zero_probe_interval_does_not_divide_by_zero(self):
        report = copy.deepcopy(self.report)
        report["probeIntervalMs"] = 0
        drill_check.check(report)


class Cli(unittest.TestCase):
    def run_main(self, *paths):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = drill_check.main(list(paths))
        return status, out.getvalue(), err.getvalue()

    def test_consistent_reports_exit_zero(self):
        status, out, _ = self.run_main(os.path.join(SPEC, "examples", "within-objective.json"))
        self.assertEqual(status, drill_check.EXIT_OK)
        self.assertIn("ok ", out)

    def test_a_finding_exits_one_and_names_the_file(self):
        path = os.path.join(SPEC, "semantic-counter-examples", "mttd-off-by-one-ms.json")
        status, out, _ = self.run_main(path)
        self.assertEqual(status, drill_check.EXIT_FINDINGS)
        self.assertIn(path + ": mttdMs", out)

    def test_one_bad_report_among_good_ones_still_fails(self):
        good = os.path.join(SPEC, "examples", "within-objective.json")
        bad = os.path.join(SPEC, "semantic-counter-examples", "scaled-wrong.json")
        self.assertEqual(self.run_main(good, bad, good)[0], drill_check.EXIT_FINDINGS)

    def test_usage_and_unreadable_exit_two(self):
        self.assertEqual(self.run_main()[0], drill_check.EXIT_USAGE)
        with tempfile.TemporaryDirectory() as tmp:
            broken = os.path.join(tmp, "broken.json")
            with open(broken, "w", encoding="utf-8") as f:
                f.write("{")
            self.assertEqual(self.run_main(broken)[0], drill_check.EXIT_USAGE)
            self.assertEqual(self.run_main(os.path.join(tmp, "absent.json"))[0], drill_check.EXIT_USAGE)


if __name__ == "__main__":
    unittest.main()
