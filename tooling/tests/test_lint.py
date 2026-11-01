"""The policy-literals lint: each rule finds its literal, and leaves placeholders, comments and prose."""

import shutil
import tempfile
import unittest
from pathlib import Path

from practice_ci import lint, policy

LABELS = ["schema-loosening-approved", "state:invalid", "kind:"]


def rules(found):
    return sorted(rule for rule, _, _ in found)


class Templates(unittest.TestCase):
    def check(self, text):
        d = Path(tempfile.mkdtemp())
        try:
            p = d / "w.yml"
            p.write_text(text, encoding="utf-8")
            return rules(lint.lint_template(p, "w.yml", LABELS))
        finally:
            shutil.rmtree(d)

    def test_placeholders_pass(self):
        self.assertEqual(self.check(
            "    runs-on: @@runner.image@@\n"
            "    timeout-minutes: @@runner.timeoutMinutes@@\n"
            "      - uses: @@actions.checkout.repo@@@@@actions.checkout.sha@@ # @@actions.checkout.version@@\n"
            "        python-version: @@tooling.pythonVersion@@\n"
            "    uses: ./.github/workflows/gate.yml\n"
            "    curl -fsSL --retry @@fetch.retries@@ \"$TOOL_URL\"\n"
            "    runs-on: ${{ matrix.os }}\n"), [])

    def test_hard_coded_timeout(self):
        self.assertEqual(self.check("    timeout-minutes: 20\n"), ["owned-key"])

    def test_hard_coded_runner_and_interpreter(self):
        self.assertEqual(self.check("    runs-on: ubuntu-24.04\n        python-version: '3.12.16'\n"),
                         ["owned-key", "owned-key"])

    def test_hard_coded_label(self):
        self.assertEqual(self.check('    gh api -f "labels[]=state:invalid"\n'), ["label"])
        self.assertEqual(self.check("    if: contains(labels, 'schema-loosening-approved')\n"), ["label"])

    def test_hard_coded_retry_count(self):
        self.assertEqual(self.check('    curl -fsSL --retry 3 "$U"\n'), ["retry"])
        self.assertEqual(self.check('    curl --retry-max-time=30 "$U"\n'), ["retry"])

    def test_hard_coded_tool_url(self):
        self.assertEqual(self.check("    TOOL_URL: https://example.com/tool.tar.gz\n"), ["download"])

    def test_hard_coded_pin(self):
        self.assertEqual(self.check("      - uses: actions/checkout@" + "0" * 40 + "\n"), ["pin", "pin"])

    def test_comments_are_prose(self):
        self.assertEqual(self.check("# the label state:invalid, https://example.com, timeout-minutes: 3\n"), [])


class Python(unittest.TestCase):
    def check(self, source, name="mod.py"):
        d = Path(tempfile.mkdtemp())
        try:
            p = d / name
            p.write_text(source, encoding="utf-8")
            return rules(lint.lint_python(p, name, "constants.json"))
        finally:
            shutil.rmtree(d)

    def test_designated_keywords_take_no_literal(self):
        self.assertEqual(self.check("run(x, timeout=30)\n"), ["policy-literal"])
        self.assertEqual(self.check("f(label='size-approved')\n"), ["policy-literal"])
        self.assertEqual(self.check("f(url=f'https://{h}')\n"), ["policy-literal"])
        self.assertEqual(self.check("p.add_argument('--n', default=3)\n"), ["policy-literal"])
        self.assertEqual(self.check("run(x, timeout=policy.value('a.b'), check=False)\n"), [])

    def test_only_the_accessor_names_the_constants_file(self):
        self.assertEqual(self.check("open('policy/constants.json')\n"), ["policy-file"])
        self.assertEqual(self.check("X = 'policy/constants.json'\n", "policy.py"), [])
        self.assertEqual(self.check('"""Reads policy/constants.json."""\n'), [])

    def test_the_accessor_takes_no_default(self):
        self.assertEqual(self.check("policy.value('a.b', 3)\n"), ["policy-default"])
        self.assertEqual(self.check("policy.value('a.b')\n"), [])


class Repository(unittest.TestCase):
    def test_this_checkout_is_clean(self):
        result = lint.run(policy.ROOT)
        self.assertEqual(result.status, "pass", result.message)


if __name__ == "__main__":
    unittest.main()
