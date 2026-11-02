import os
import tempfile
import unittest

from tooling.tests import ROOT
from practice_ci import config, lint_literals

RULES = config.get("tooling", "lint")


def py(source):
    return lint_literals.lint_python(source, "m.py", RULES)


def text(source):
    return lint_literals.lint_text(source, "w.yml", RULES)


class PythonMutationTest(unittest.TestCase):
    """Each hard-coded policy value must fail; the same value read from config must pass."""

    def test_hard_coded_timeout_fails(self):
        self.assertTrue(py("subprocess.run(cmd, timeout=30)"))
        self.assertTrue(py("subprocess.run(cmd, timeout=1)"))
        self.assertFalse(py("subprocess.run(cmd, timeout=config.get('x', 'timeout'))"))

    def test_hard_coded_label_fails(self):
        self.assertTrue(py("add(label='size-approved')"))
        self.assertTrue(py("add(labels=['size-approved'])"))
        self.assertTrue(py("if label == 'size-approved': pass"))
        self.assertFalse(py("add(label=config.get('guards', 'sizeLabel'))"))
        self.assertFalse(py("add(labels=[config.get('guards', 'sizeLabel')])"))

    def test_hard_coded_retry_fails(self):
        self.assertTrue(py("fetch(url_value, retries=3)"))
        self.assertTrue(py("fetch(url_value, retries=0)"))
        self.assertTrue(py("if retries > 3: pass"))
        self.assertFalse(py("fetch(url_value, retries=config.get('runner', 'fetchRetries'))"))

    def test_hard_coded_url_fails(self):
        self.assertTrue(py("urlopen('https://example.invalid/x')"))
        self.assertTrue(py("BASE = 'https://example.invalid/x'"))
        self.assertTrue(py("fetch(url='https://example.invalid/x')"))
        self.assertFalse(py("urlopen(config.get('tools', 'x', 'url'))"))

    def test_compare_with_policy_name_and_len(self):
        self.assertTrue(py("if len(size) > 600: pass"))
        self.assertTrue(py("if 600 < size: pass"))
        self.assertFalse(py("if size > config.get('guards', 'sizeLimit'): pass"))

    def test_small_numbers_none_and_docstrings_are_not_policy(self):
        self.assertFalse(py("if count > 0: pass"))
        self.assertFalse(py("run(cmd, timeout=None)"))
        self.assertFalse(py('"""See https://example.invalid for background."""\n'))

    def test_unrelated_literals_pass(self):
        self.assertFalse(py("print('hello'); x = 41 + 1"))


class TemplateMutationTest(unittest.TestCase):
    def test_hard_coded_cap_fails(self):
        self.assertTrue(text('gh api --limit 500'))
        self.assertTrue(text('LIMIT=500'))
        self.assertFalse(text('LIMIT=@@guards.sizeLimit@@'))
        self.assertFalse(text('gh api --limit "$LIMIT"'))

    def test_hard_coded_timeout_fails(self):
        self.assertTrue(text("    timeout-minutes: 20\n"))
        self.assertTrue(text("    run: curl --max-time 30 x\n"))
        self.assertFalse(text("    timeout-minutes: @@runner.timeoutMinutes@@\n"))

    def test_hard_coded_label_fails(self):
        self.assertTrue(text("    run: gh pr create --label size-approved\n"))
        self.assertTrue(text('    run: jq \'select(.label.name == "size-approved")\'\n'))
        self.assertTrue(text("    run: jq \".[] | select(.label.name == \\\"size-approved\\\")\"\n"))
        self.assertFalse(text('    run: gh pr create --label "$LABEL"\n'))
        self.assertFalse(text('    run: gh pr create --label @@guards.sizeLabel@@\n'))
        self.assertFalse(text("    run: jq \".[] | select(.label.name == \\\"$LABEL\\\")\"\n"))

    def test_hard_coded_retry_fails(self):
        self.assertTrue(text('    run: curl -fsSL --retry 3 "$URL"\n'))
        self.assertFalse(text('    run: curl -fsSL --retry @@runner.fetchRetries@@ "$URL"\n'))

    def test_hard_coded_url_fails(self):
        self.assertTrue(text('    run: curl -fsSL https://example.invalid/x\n'))
        self.assertFalse(text('    run: curl -fsSL "$TOOL_URL"\n'))
        self.assertFalse(text("    # see https://example.invalid for the background\n"))

    def test_hard_coded_pin_fails(self):
        self.assertTrue(text("      - uses: actions/checkout@v4\n"))
        self.assertFalse(text("      - uses: @@actions.checkout.repo@@@@@actions.checkout.sha@@ # @@actions.checkout.version@@\n"))
        self.assertFalse(text("    uses: ./.github/workflows/guard.yml\n"))


class TreeTest(unittest.TestCase):
    def test_this_repository_is_clean(self):
        findings, scanned = lint_literals.lint_tree(ROOT, RULES)
        self.assertEqual(findings, [])
        self.assertGreater(scanned, 10)

    def test_a_planted_file_in_each_root_fails_and_tests_are_skipped(self):
        with tempfile.TemporaryDirectory() as root:
            def put(rel, body):
                path = os.path.join(root, rel)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(body)
            put("tooling/practice_ci/bad.py", "run(cmd, timeout=30)\n")
            put("tooling/tests/skipped.py", "run(cmd, timeout=30)\n")
            put("templates/.github/workflows/bad.yml", "    timeout-minutes: 20\n")
            put("templates/fragments/bad.sh", "curl --retry 3 x\n")
            findings, _ = lint_literals.lint_tree(root, RULES)
            self.assertEqual(sorted(f.split(":")[0] for f in findings), [
                "templates/.github/workflows/bad.yml", "templates/fragments/bad.sh", "tooling/practice_ci/bad.py"])

    def test_run_reports_the_findings(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "tooling"))
            os.makedirs(os.path.join(root, "templates", ".github", "workflows"))
            os.makedirs(os.path.join(root, "templates", "fragments"))
            with open(os.path.join(root, "tooling", "bad.py"), "w", encoding="utf-8") as f:
                f.write("urlopen('https://example.invalid/x')\n")
            res = lint_literals.run([root])
            self.assertFalse(res.ok)
            self.assertEqual(res.exit_code(), config.get("tooling", "exitCodes")["fail"])


if __name__ == "__main__":
    unittest.main()
