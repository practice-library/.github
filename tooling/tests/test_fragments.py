"""Fragments run from the production source, and their verdicts map through a closed vocabulary."""

import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from practice_ci import fragments, policy
from practice_ci.result import ERROR, FAIL, PASS

FRAGMENTS = policy.path("render.fragmentsDir")
# A verdict a fragment prints: echo "<token> ..." / echo '<token> ...' / print("<token> ..."). A bare
# print("word") is a helper's output inside an embedded program, not a verdict.
_PRINTED = re.compile(r"""(?:echo|print\()\s*["']([a-z]+) """)


class Vocabulary(unittest.TestCase):
    def test_every_fragment_is_declared_and_every_declaration_has_a_fragment(self):
        on_disk = {p.stem for p in FRAGMENTS.glob("*.sh")}
        self.assertEqual(on_disk - set(fragments.VOCABULARY) - fragments.NOT_RUN_HERE, set())
        self.assertEqual(set(fragments.VOCABULARY) - on_disk, set())

    def test_every_printed_verdict_is_declared(self):
        for name, vocabulary in fragments.VOCABULARY.items():
            text = fragments.source(name).read_text(encoding="utf-8")
            printed = set(_PRINTED.findall(text))
            self.assertLessEqual(printed, set(vocabulary), name)

    def test_unknown_token_is_an_error(self):
        r = fragments.judge("gate-required", "okay the needs are exactly the file")
        self.assertEqual((r.status, r.reason), (ERROR, "gate-required.unknown-verdict"))

    def test_empty_output_is_an_error(self):
        self.assertEqual(fragments.judge("pin-check", "").status, ERROR)

    def test_token_maps_to_status_and_reason(self):
        r = fragments.judge("schema-loosening", 'loose ["a/b"]')
        self.assertEqual((r.status, r.reason, r.detail), (FAIL, "schema-loosening.loose", '["a/b"]'))
        r = fragments.judge("schema-loosening", "skip not a schema")
        self.assertEqual((r.status, r.reason), (PASS, "schema-loosening.skip"))

    def test_json_output(self):
        r = fragments.judge("schema-mutate", '{"type":"object"}')
        self.assertEqual((r.status, r.reason, r.detail), (PASS, "schema-mutate.json", '{"type":"object"}'))
        self.assertEqual(fragments.judge("schema-mutate", "invalid no such place").status, FAIL)
        self.assertEqual(fragments.judge("schema-mutate", "{broken").status, ERROR)


class Run(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_runs_the_production_fragment_in_the_given_root(self):
        env = {"PATH": "/usr/bin:/bin", "RCS": "0 0", "FINDING": "2"}
        r = fragments.run("each-result", self.root, env)
        self.assertEqual((r.status, r.reason, r.detail), (PASS, "each-result.pass", "0"))

    def test_a_fragment_that_exits_non_zero_is_an_error(self):
        fake = self.root / "fake.sh"
        fake.write_text("main() { echo ok fine; return 3; }\n")
        with mock.patch.object(fragments, "source", lambda name: fake):
            r = fragments.run("pin-check", self.root, {"PATH": "/usr/bin:/bin"})
        self.assertEqual((r.status, r.reason), (ERROR, "pin-check.exit"))

    def test_an_undeclared_fragment_is_an_error(self):
        self.assertEqual(fragments.run("nope", self.root, {}).status, ERROR)


if __name__ == "__main__":
    unittest.main()
