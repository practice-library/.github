"""spec/sources: the optional terms.note (#50).

The schema validator itself runs in CI (schema-check over examples/ and counter-examples/); these tests
hold what that run cannot: the schema's bound equals the one in policy, and each case file is the case
its name says, so a renamed or emptied file cannot pass for a case it no longer is.
"""
import glob
import json
import os
import unittest

from tooling.practice_ci import config

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SOURCES = os.path.join(ROOT, os.path.dirname(config.get("spec", "sourcesSchemaPath")))


def load(*parts):
    with open(os.path.join(SOURCES, *parts), encoding="utf-8") as f:
        return json.load(f)


def notes(directory):
    """(file name, note) for every host terms in a case directory that carries a note."""
    found = []
    for path in sorted(glob.glob(os.path.join(SOURCES, directory, "*.json"))):
        with open(path, encoding="utf-8") as f:
            document = json.load(f)
        for host in document["hosts"]:
            if "note" in host.get("terms", {}):
                found.append((os.path.basename(path), host["terms"]["note"]))
    return found


class TermsNoteSchema(unittest.TestCase):
    def setUp(self):
        schema = load(os.path.basename(config.get("spec", "sourcesSchemaPath")))
        self.terms = schema["$defs"]["host"]["properties"]["terms"]

    def test_note_is_declared_and_optional(self):
        self.assertIn("note", self.terms["properties"])
        self.assertNotIn("note", self.terms["required"])

    def test_note_is_a_non_empty_bounded_string(self):
        note = self.terms["properties"]["note"]
        self.assertEqual(note["type"], "string")
        self.assertEqual(note["minLength"], 1)
        self.assertEqual(note["maxLength"], config.get("spec", "termsNoteMaxLength"))

    def test_unknown_terms_fields_stay_refused(self):
        self.assertIs(self.terms["additionalProperties"], False)


class TermsNoteCases(unittest.TestCase):
    def test_accepted_cases_are_within_bounds(self):
        accepted = notes("examples")
        self.assertGreaterEqual(len(accepted), 3)
        longest = config.get("spec", "termsNoteMaxLength")
        for name, note in accepted:
            self.assertIsInstance(note, str, name)
            self.assertTrue(1 <= len(note) <= longest, name)
        lengths = {len(note) for _, note in accepted}
        self.assertIn(1, lengths)
        self.assertIn(longest, lengths)

    def test_refused_cases_each_break_one_rule(self):
        longest = config.get("spec", "termsNoteMaxLength")
        refused = dict(notes("counter-examples"))
        self.assertEqual(refused["terms-note-empty.json"], "")
        self.assertEqual(len(refused["terms-note-over-cap.json"]), longest + 1)
        self.assertNotIsInstance(refused["terms-note-not-a-string.json"], str)

    def test_unknown_field_case_has_no_note(self):
        terms = load("counter-examples", "terms-unknown-field.json")["hosts"][0]["terms"]
        self.assertNotIn("note", terms)
        self.assertEqual(set(terms) - {"url", "checkedAt", "quote"}, {"notes"})


if __name__ == "__main__":
    unittest.main()
