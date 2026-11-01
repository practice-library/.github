"""Expected-reason assertions (#39), the local guards runner (#35), and the shared check profile."""
import copy
import glob
import json
import os
import subprocess
import unittest

from tooling.practice_ci import config, guards, reasons

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def basic(*pairs):
    """A validator's structured output in the standard format, one error per (keywordLocation, instanceLocation)."""
    return json.dumps({"valid": False, "errors": [{"keywordLocation": k, "instanceLocation": i, "error": "x"} for k, i in pairs]})


class ParseErrors(unittest.TestCase):
    def test_keyword_is_the_last_segment_of_the_keyword_location(self):
        got = reasons.parse_errors(basic(("/allOf/0/then/properties/verdict/const", "/robots/0/verdict")))
        self.assertEqual(got, [{"keyword": "const", "instanceLocation": "/robots/0/verdict"}])

    def test_unreadable_output_fails_closed(self):
        for bad in ("not json", "{}", '{"errors": [{"keywordLocation": "/a"}]}', '{"errors": [{"instanceLocation": ""}]}'):
            with self.assertRaises(reasons.ReasonError):
                reasons.parse_errors(bad)


class Holds(unittest.TestCase):
    def test_keyword_and_location_must_hold_on_the_same_error(self):
        errors = reasons.parse_errors(basic(("/properties/a/type", "/a"), ("/properties/b/const", "/b")))
        self.assertTrue(reasons.holds(errors, {"keyword": "type", "instanceLocation": "/a"}))
        self.assertFalse(reasons.holds(errors, {"keyword": "type", "instanceLocation": "/b"}))
        self.assertFalse(reasons.holds(errors, {"keyword": "const", "instanceLocation": "/a"}))

    def test_location_may_be_below_the_named_one(self):
        errors = reasons.parse_errors(basic(("/additionalProperties", "/hosts/0/extra")))
        self.assertTrue(reasons.holds(errors, {"keyword": "additionalProperties", "instanceLocation": "/hosts/0"}))
        self.assertFalse(reasons.holds(errors, {"keyword": "additionalProperties", "instanceLocation": "/hosts/1"}))
        self.assertFalse(reasons.holds(errors, {"keyword": "additionalProperties", "instanceLocation": "/hosts/0/ext"}))

    def test_root_location_covers_everything(self):
        errors = reasons.parse_errors(basic(("/required", "")))
        self.assertTrue(reasons.holds(errors, {"keyword": "required", "instanceLocation": ""}))


class Check(unittest.TestCase):
    REASONS = {"counter-examples/a.json": {"keyword": "const", "instanceLocation": "/v"}}

    def test_a_counter_example_failing_for_another_reason_is_a_finding(self):
        run = lambda p: reasons.parse_errors(basic(("/properties/w/type", "/w")))
        findings = reasons.check(self.REASONS, {"counter-examples/a.json": "a"}, run)
        self.assertEqual(len(findings), 1)
        self.assertIn("expected const at /v", findings[0])

    def test_passing_validation_is_a_finding(self):
        self.assertEqual(len(reasons.check(self.REASONS, {"counter-examples/a.json": "a"}, lambda p: [])), 1)

    def test_matching_reason_is_clean(self):
        run = lambda p: reasons.parse_errors(basic(("/properties/v/const", "/v")))
        self.assertEqual(reasons.check(self.REASONS, {"counter-examples/a.json": "a"}, run), [])

    def test_counter_example_without_a_reason_and_stale_reason_are_findings(self):
        findings = reasons.check(self.REASONS, {"counter-examples/b.json": "b"}, lambda p: [])
        self.assertEqual(sorted(f.split(":")[0] for f in findings), ["counter-examples/a.json", "counter-examples/b.json"])

    def test_reasons_file_shape(self):
        for spec in ("sources", "refresh-report", "ratchet"):
            table = reasons.load_reasons(os.path.join(ROOT, "spec", spec, config.get("reasons", "file")))
            files = glob.glob(os.path.join(ROOT, "spec", spec, "counter-examples", "*.json"))
            self.assertEqual(len(table), len(files), spec)


class Guards(unittest.TestCase):
    DOC = {"properties": {"a": {"minimum": 1}}, "list": [1, 2]}

    def test_local_script_can_execute_the_guards_package(self):
        result = subprocess.run(
            ["bash", os.path.join(ROOT, "scripts", "guards.sh"),
             "unused-validator", "unused-schema", "unused-guards", "--help"],
            cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--validator", result.stdout)

    def test_set_delete_true(self):
        self.assertEqual(guards.apply_mutant(self.DOC, {"pointer": "/properties/a/minimum", "set": 0})["properties"]["a"]["minimum"], 0)
        self.assertNotIn("minimum", guards.apply_mutant(self.DOC, {"pointer": "/properties/a/minimum", "mutation": "delete"})["properties"]["a"])
        self.assertIs(guards.apply_mutant(self.DOC, {"pointer": "/properties/a", "mutation": "true"})["properties"]["a"], True)
        self.assertEqual(guards.apply_mutant(self.DOC, {"pointer": "/list/1", "mutation": "delete"})["list"], [1])

    def test_the_input_is_not_changed(self):
        before = copy.deepcopy(self.DOC)
        guards.apply_mutant(self.DOC, {"pointer": "/properties/a", "mutation": "delete"})
        self.assertEqual(self.DOC, before)

    def test_a_mutant_that_names_nothing_is_an_error(self):
        for m in ({"pointer": "/nope", "set": 1}, {"pointer": "/list/2", "set": 1}, {"pointer": "/list/01", "set": 1},
                  {"pointer": "properties", "set": 1}, {"pointer": "/a~2b", "set": 1},
                  {"pointer": "/properties", "set": 1, "mutation": "delete"}, {"pointer": "/properties", "mutation": "bogus"},
                  {"pointer": "/properties"}, {"pointer": ""}, "x"):
            with self.assertRaises(guards.MutantError, msg=m):
                guards.apply_mutant(self.DOC, m)

    def test_tilde_escapes(self):
        doc = {"a/b": {"c~d": 1}}
        self.assertEqual(guards.apply_mutant(doc, {"pointer": "/a~1b/c~0d", "set": 2}), {"a/b": {"c~d": 2}})

    def test_a_surviving_mutant_is_reported(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            for d, name, doc in (("ex", "ok.json", 1), ("bad", "no.json", 0)):
                os.makedirs(os.path.join(tmp, d))
                with open(os.path.join(tmp, d, name), "w") as f:
                    json.dump(doc, f)
            gp = os.path.join(tmp, "guards.json")
            with open(gp, "w") as f:
                json.dump({"examples": "ex", "counter-examples": "bad",
                           "mutants": [{"pointer": "/minimum", "set": 0}, {"pointer": "/unused", "set": 0}, {"pointer": "/gone", "set": 0}]}, f)
            schema = {"minimum": 1, "unused": 5}

            def validate(s, path):
                with open(path) as f:
                    v = json.load(f)
                return guards.PASS if v >= s.get("minimum", 0) else guards.FINDING
            findings = guards.run(schema, gp, validate)
            self.assertEqual(len(findings), 2)
            self.assertTrue(any(f.startswith("survived") and "/unused" in f for f in findings))
            self.assertTrue(any("no such place" in f for f in findings))


class CheckProfile(unittest.TestCase):
    def test_every_spec_check_json_is_the_shared_profile(self):
        profile = config.get("profiles", "specCheck")
        for spec in ("sources", "refresh-report", "ratchet"):
            with open(os.path.join(ROOT, "spec", spec, "check.json"), encoding="utf-8") as f:
                self.assertEqual(json.load(f), profile, spec)
            with open(os.path.join(ROOT, "templates", "spec", spec, "check.json"), encoding="utf-8") as f:
                self.assertEqual(f.read().strip(), "@@json:profiles.specCheck@@", spec)


if __name__ == "__main__":
    unittest.main()
