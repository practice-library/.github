"""The spec fixtures, checked without the pinned validator binary (CI runs that; this runs the same
contract through the stdlib evaluator in minischema): examples pass, every counter-example fails for its
named reason (#39), and every guard mutant turns a fixture red (#63, #65)."""
import glob
import json
import os
import unittest

from tooling.practice_ci import guards, reasons
from tooling.tests.minischema import Validator

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SPECS = ("sources", "refresh-report", "ratchet")


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _spec(name, *parts):
    return os.path.join(ROOT, "spec", name, *parts)


def _validate(schema, path):
    return guards.FINDING if Validator(schema).errors(_load(path)) else guards.PASS


class SpecFixtures(unittest.TestCase):
    def test_examples_pass_and_counter_examples_fail(self):
        for name in SPECS:
            v = Validator(_load(_spec(name, "schema.json")))
            for f in glob.glob(_spec(name, "examples", "*.json")):
                self.assertEqual(v.errors(_load(f)), [], f)
            for f in glob.glob(_spec(name, "counter-examples", "*.json")):
                self.assertNotEqual(v.errors(_load(f)), [], f)

    def test_every_counter_example_fails_for_its_named_reason(self):
        for name in SPECS:
            v = Validator(_load(_spec(name, "schema.json")))
            table = reasons.load_reasons(_spec(name, "reasons.json"))
            files = {"counter-examples/" + os.path.basename(f): f
                     for f in glob.glob(_spec(name, "counter-examples", "*.json"))}
            self.assertEqual(reasons.check(table, files, lambda p: v.errors(_load(p))), [], name)

    def test_every_guard_mutant_is_caught(self):
        for name in SPECS:
            findings = guards.run(_load(_spec(name, "schema.json")), _spec(name, "guards.json"), _validate)
            self.assertEqual(findings, [], name)

    # -- #63: the robots state table --
    def _robots(self, status, verdict):
        rec = {"host": "docs.example.com", "fetchedAt": "2026-10-31T12:00:30Z", "verdict": verdict}
        if status is not None:
            rec["httpStatus"] = status
        return Validator(_load(_spec("refresh-report", "schema.json"))).errors(
            {"schemaVersion": 1, "graph": "vendors/example", "commit": "0" * 40,
             "run": {"id": 1, "url": "https://github.com/practice-library/graphs/actions/runs/1",
                     "startedAt": "2026-10-31T12:00:00Z", "finishedAt": "2026-10-31T12:03:00Z"},
             "requests": 1, "robots": [rec], "results": [],
             "aborted": {"reason": "x"}})

    def test_every_5xx_is_unreachable_and_never_allowed(self):
        for status in (500, 503, 599):
            self.assertNotEqual(self._robots(status, "allowed"), [], status)
            self.assertNotEqual(self._robots(status, "disallowed"), [], status)
            self.assertNotEqual(self._robots(status, "absent"), [], status)
            self.assertEqual(self._robots(status, "unreachable"), [], status)

    def test_state_table(self):
        table = {"allowed": (200, 299), "disallowed": (200, 299), "absent": (400, 499)}
        for verdict, (lo, hi) in table.items():
            self.assertEqual(self._robots(lo, verdict), [], verdict)
            self.assertEqual(self._robots(hi, verdict) if verdict != "absent" else self._robots(hi, verdict), [], verdict)
            self.assertNotEqual(self._robots(lo - 1, verdict), [], verdict)
            self.assertNotEqual(self._robots(hi + 1, verdict), [], verdict)
        for status in (429, 500, 599):
            self.assertEqual(self._robots(status, "unreachable"), [], status)
        for status in (200, 404, 499):
            self.assertNotEqual(self._robots(status, "unreachable"), [], status)
        self.assertEqual(self._robots(None, "unreachable"), [])

    # -- #65: sources closure --
    def test_sources_every_object_is_closed(self):
        v = Validator(_load(_spec("sources", "schema.json")))
        doc = _load(_spec("sources", "examples", "one-host.json"))
        places = [[], ["hosts", 0], ["hosts", 0, "robots"], ["hosts", 0, "terms"]]
        for place in places:
            probe = json.loads(json.dumps(doc))
            node = probe
            for k in place:
                node = node[k]
            node["unknownField"] = 1
            errors = v.errors(probe)
            self.assertTrue(any(e["keyword"] == "additionalProperties" for e in errors), place)


if __name__ == "__main__":
    unittest.main()
