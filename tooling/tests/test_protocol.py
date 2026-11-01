import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from practice_ci import config, protocol  # noqa: E402

ROOT = config._ROOT
UNIT = os.path.join(ROOT, config.get("selftest", "unitDir"), "message-extract")
FENCE = config.get("protocol", "fenceOpen")


def body(block, before="Some text.\n\n", after=""):
    return (before + FENCE + "\n" + block + "\n```\n" + after).encode("utf-8")


class ExtractCases(unittest.TestCase):
    """Every selftest unit case for the message-extract library, run through the Python reader."""

    def test_unit_cases(self):
        names = sorted(n for n in os.listdir(UNIT) if n.endswith(".json"))
        self.assertTrue(names)
        for name in names:
            with open(os.path.join(UNIT, name), encoding="utf-8") as f:
                case = json.load(f)
            got = protocol.extract_file(os.path.join(ROOT, case["env"]["BODY_FILE"]))
            with self.subTest(name):
                self.assertEqual(got.split(" ", 1)[0], case["expect"], got)
                if "output" in case:
                    self.assertEqual(got, case["output"])


class Grammar(unittest.TestCase):
    def test_plain_message_is_ok(self):
        self.assertEqual(protocol.extract(body('{"a":1}')), 'ok {"a":1}')

    def test_html_comment_outside_fence_is_refused(self):
        hidden = b"<!--\n" + FENCE.encode() + b'\n{"a":1}\n```\n-->\n' + body('{"a":2}')
        self.assertTrue(protocol.extract(hidden).startswith("invalid "))

    def test_inline_html_comment_is_refused(self):
        self.assertTrue(protocol.extract(body('{"a":1}', before="text <!-- x --> more\n")).startswith("invalid "))

    def test_html_block_outside_fence_is_refused(self):
        self.assertTrue(protocol.extract(body('{"a":1}', before="<details>\n")).startswith("invalid "))
        self.assertTrue(protocol.extract(body('{"a":1}', after="<div hidden>x</div>\n")).startswith("invalid "))

    def test_html_inside_another_fence_is_text(self):
        quoted = "~~~\n<!-- an example -->\n~~~\n"
        self.assertEqual(protocol.extract(body('{"a":1}', before=quoted)), 'ok {"a":1}')

    def test_html_comment_inside_json_block_cannot_make_a_message(self):
        self.assertTrue(protocol.extract(body("<!-- x -->{}")).startswith("invalid "))

    def test_indented_or_longer_fence_is_refused(self):
        for opener in (" " + FENCE, "`" + FENCE, "~~~json"):
            raw = ("%s\n{}\n```\n" % opener).encode()
            self.assertTrue(protocol.extract(raw).startswith("invalid "), opener)


class Unsafe(unittest.TestCase):
    def test_decoded_unsafe_values_are_refused(self):
        cases = {
            "control": '{"a":"x\\u0001y"}',
            "tab": '{"a":"x\\ty"}',
            "format": '{"a":"x\\u200by"}',
            "bidi": '{"a":"x\\u202ey"}',
            "line separator": '{"a":"x\\u2028y"}',
            "paragraph separator": '{"a":"x\\u2029y"}',
            "lone high surrogate": '{"a":"x\\ud800y"}',
            "lone low surrogate": '{"a":"\\udc00"}',
            "in a key": '{"a\\u200b":"y"}',
            "nested": '{"a":{"b":[1,{"c":"\\u0085"}]}}',
        }
        for name, block in cases.items():
            with self.subTest(name):
                self.assertTrue(protocol.extract(body(block)).startswith("invalid "), name)

    def test_paired_surrogates_and_plain_text_are_safe(self):
        self.assertTrue(protocol.extract(body('{"a":"\\ud83d\\ude00 ok é"}')).startswith("ok "))

    def test_needs_must_be_single_line(self):
        for needs in ("a\\nb", "a\\r", "a\\u2028b", "a\\u000bb"):
            block = '{"data":{"needs":["%s"]}}' % needs
            got = protocol.extract(body(block))
            with self.subTest(needs):
                self.assertEqual(got, "invalid a needs entry spans more than one line")

    def test_duplicate_key_at_any_depth(self):
        self.assertEqual(protocol.extract(body('{"a":{"b":1,"b":2}}')), "invalid a key is given twice in the block")
        self.assertEqual(protocol.extract(body('{"a\\u0062":1,"ab":2}')), "invalid a key is given twice in the block")

    def test_nan_is_refused(self):
        self.assertTrue(protocol.extract(body('{"a":NaN}')).startswith("invalid "))


class Timestamps(unittest.TestCase):
    """spec/protocol/message.schema.json: time and expires are real UTC calendar times."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "templates", "spec", "protocol", "message.schema.json"), encoding="utf-8") as f:
            schema = json.load(f)
        import re
        cls.time = re.compile(schema["properties"]["time"]["pattern"])
        cls.expires = re.compile(schema["properties"]["data"]["properties"]["expires"]["pattern"])

    def test_calendar_valid(self):
        for stamp in ("2026-10-31T12:00:00Z", "2028-02-29T23:59:59Z", "2000-02-29T00:00:00Z", "2026-12-31T00:00:00Z"):
            with self.subTest(stamp):
                self.assertTrue(self.time.search(stamp) and self.expires.search(stamp))

    def test_calendar_invalid(self):
        for stamp in ("2026-02-31T12:00:00Z", "2026-02-29T12:00:00Z", "1900-02-29T12:00:00Z", "2026-04-31T12:00:00Z",
                      "2026-13-01T12:00:00Z", "2026-00-10T12:00:00Z", "2026-01-00T12:00:00Z",
                      "2026-10-31T25:00:00Z", "2026-10-31T24:00:00Z", "2026-10-31T12:60:00Z", "2026-10-31T12:00:60Z"):
            with self.subTest(stamp):
                self.assertFalse(self.time.search(stamp), stamp)
                self.assertFalse(self.expires.search(stamp), stamp)

    def test_counter_examples_on_disk_hold_the_invalid_stamps(self):
        wanted = {"2026-02-31T12:00:00Z", "2026-10-31T25:00:00Z"}
        held = set()
        directory = os.path.join(ROOT, "spec", "protocol", "counter-examples")
        for name in os.listdir(directory):
            with open(os.path.join(directory, name), encoding="utf-8") as f:
                message = json.load(f)
            held.update(v for v in (message.get("time"), message.get("data", {}).get("expires")) if v)
        self.assertTrue(wanted <= held, wanted - held)


class Trust(unittest.TestCase):
    """#56: acceptance is bound to the body's digest; a foreign edit is not rehabilitated by a relabel."""

    AUTHOR, OTHER = "owner-login", "someone-else"

    def event(self, comments, action, actor, text):
        return protocol.decide(action, actor, self.AUTHOR, protocol.digest(text), protocol.parse_verdict(comments))

    def verdict_comment(self, status, text):
        return {"user": {"login": config.get("protocol", "verdictAuthor")}, "body": protocol.render_verdict(status, protocol.digest(text))}

    def test_create_foreign_edit_trusted_relabel_is_invalid(self):
        original, tampered = b"original body", b"tampered body"
        comments = []
        what, status, _ = self.event(comments, "opened", self.AUTHOR, original)
        self.assertEqual((what, status), (protocol.JUDGE, None))
        comments = [self.verdict_comment(protocol.ACCEPTED, original)]
        what, status, _ = self.event(comments, "edited", self.OTHER, tampered)
        self.assertEqual((what, status), (protocol.KEEP_INVALID, protocol.TAINTED))
        comments = [self.verdict_comment(protocol.ACCEPTED, original), self.verdict_comment(protocol.TAINTED, tampered)]
        what, status, _ = self.event(comments, "labeled", self.AUTHOR, tampered)
        self.assertEqual(what, protocol.KEEP_INVALID)

    def test_relabel_after_foreign_edit_is_invalid_even_without_a_taint_record(self):
        comments = [self.verdict_comment(protocol.ACCEPTED, b"original body")]
        what, status, _ = self.event(comments, "labeled", self.AUTHOR, b"tampered body")
        self.assertEqual((what, status), (protocol.KEEP_INVALID, protocol.TAINTED))

    def test_unlabeled_create_foreign_edit_relabel_without_verdict_is_invalid(self):
        comments = []
        original, tampered = b"original body", b"foreign revision"
        self.assertEqual(self.event(comments, "opened", self.AUTHOR, original)[0], protocol.JUDGE)
        # No kind label: the opened run stores no verdict. The foreign edit's
        # run has not recorded taint when the relabel run reads the new body.
        for action in ("labeled", "retitled"):
            with self.subTest(action=action):
                what, status, reason = self.event(comments, action, self.AUTHOR, tampered)
                self.assertEqual((what, status), (protocol.KEEP_INVALID, protocol.TAINTED))
                self.assertTrue(reason)
                comments = [self.verdict_comment(status, tampered)]
                self.assertEqual(self.event(comments, action, self.AUTHOR, tampered)[0], protocol.KEEP_INVALID)
                self.assertEqual(self.event(comments, "edited", self.AUTHOR, tampered)[0], protocol.JUDGE)
                comments = []

    def test_author_edit_resubmits(self):
        comments = [self.verdict_comment(protocol.TAINTED, b"tampered")]
        what, _, _ = self.event(comments, "edited", self.AUTHOR, b"fixed by author")
        self.assertEqual(what, protocol.JUDGE)

    def test_relabel_of_unchanged_accepted_body_is_judged(self):
        comments = [self.verdict_comment(protocol.ACCEPTED, b"same")]
        what, _, _ = self.event(comments, "labeled", self.AUTHOR, b"same")
        self.assertEqual(what, protocol.JUDGE)

    def test_forged_verdict_by_another_login_is_ignored(self):
        forged = {"user": {"login": self.OTHER}, "body": protocol.render_verdict(protocol.ACCEPTED, protocol.digest(b"x"))}
        self.assertIsNone(protocol.parse_verdict([forged]))

    def test_latest_verdict_wins(self):
        comments = [self.verdict_comment(protocol.ACCEPTED, b"a"), self.verdict_comment(protocol.TAINTED, b"b")]
        self.assertEqual(protocol.parse_verdict(comments)["status"], protocol.TAINTED)


class Fragment(unittest.TestCase):
    """templates/fragments/message-extract.sh is a thin caller of the Python reader."""

    def run_main(self, body_path):
        import subprocess
        import tempfile
        with open(os.path.join(ROOT, "templates", "fragments", "message-extract.sh"), encoding="utf-8") as f:
            text = f.read().replace("@@protocol.toolingDir@@", config.get("protocol", "toolingDir"))
        with tempfile.TemporaryDirectory() as tmp:
            lib = os.path.join(tmp, "lib.sh")
            with open(lib, "w", encoding="utf-8") as f:
                f.write(text)
            env = dict(os.environ, BODY_FILE=body_path)
            env.pop("PRACTICE_CI_TOOLING", None)
            done = subprocess.run(["bash", "-c", 'source "$1"; main', "bash", lib], cwd=ROOT, env=env,
                                  capture_output=True, text=True, check=True)
        return done.stdout.strip()

    def test_every_unit_case_through_the_fragment(self):
        for name in sorted(n for n in os.listdir(UNIT) if n.endswith(".json")):
            with open(os.path.join(UNIT, name), encoding="utf-8") as f:
                case = json.load(f)
            got = self.run_main(os.path.join(ROOT, case["env"]["BODY_FILE"]))
            with self.subTest(name):
                self.assertEqual(got.split(" ", 1)[0], case["expect"], got)
                if "output" in case:
                    self.assertEqual(got, case["output"])

    def test_fragment_holds_no_rules_of_its_own(self):
        with open(os.path.join(ROOT, "templates", "fragments", "message-extract.sh"), encoding="utf-8") as f:
            self.assertNotIn("jq", f.read())


class WorkflowSequence(unittest.TestCase):
    """The workflow's decide step, run as it runs it: authorized create, unauthorized edit, trusted relabel."""

    def cli(self, *args):
        import subprocess
        code = ("import sys; sys.path.insert(0, sys.argv[1]); from practice_ci import protocol; "
                "sys.exit(protocol.main(sys.argv[2:]))")
        return subprocess.run([sys.executable, "-I", "-c", code, os.path.join(ROOT, "tooling"), *args],
                              capture_output=True, text=True, check=True).stdout.strip()

    def test_create_foreign_edit_relabel_is_invalid(self):
        import tempfile
        author, other = "owner-login", "someone-else"
        original = os.path.join(tempfile.mkdtemp(), "original.md")
        with open(original, "wb") as f:
            f.write(body('{"a":1}'))
        tampered = os.path.join(os.path.dirname(original), "tampered.md")
        with open(tampered, "wb") as f:
            f.write(body('{"a":2}'))
        comments = os.path.join(os.path.dirname(original), "comments.json")

        def run(action, actor, path):
            return json.loads(self.cli("decide", action, actor, author, self.cli("digest", path), comments))

        def store(status, path):
            line = self.cli("verdict", status, self.cli("digest", path))
            with open(comments, "w", encoding="utf-8") as f:
                json.dump([{"id": 7, "user": {"login": config.get("protocol", "verdictAuthor")}, "body": line}], f)

        with open(comments, "w", encoding="utf-8") as f:
            f.write("[]")
        self.assertEqual(run("opened", author, original)["what"], "judge")
        store("accepted", original)
        edited = run("edited", other, tampered)
        self.assertEqual((edited["what"], edited["status"]), ("invalid", "tainted"))
        store("tainted", tampered)
        relabeled = run("labeled", author, tampered)
        self.assertEqual(relabeled["what"], "invalid")
        self.assertEqual(self.cli("verdict-id", comments), "7")
        self.assertEqual(run("edited", author, tampered)["what"], "judge")


if __name__ == "__main__":
    unittest.main()
