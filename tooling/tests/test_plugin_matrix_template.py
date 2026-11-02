"""templates/.github/workflows/plugin-matrix.yml: the wiring the gateway helpers rely on (#41)."""
import importlib
import os
import re
import unittest

from tooling.practice_ci import config

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATE = os.path.join(ROOT, "templates", ".github", "workflows", config.get("pluginGateway", "workflow"))


def text():
    with open(TEMPLATE, encoding="utf-8") as f:
        return f.read()


def job(name):
    body = text().split("\njobs:\n", 1)[1]
    match = re.search(r"(?ms)^  %s:\n(.*?)(?=^  [a-z]+:\n|\Z)" % re.escape(name), body)
    assert match, name
    return match.group(1)


class Template(unittest.TestCase):
    def test_one_job_runs_plan_units_and_merge(self):
        body = text().split("\njobs:\n", 1)[1]
        self.assertEqual(re.findall(r"(?m)^  ([a-z]+):\n", body), ["run"])
        self.assertIn("python3 -m @@pluginGateway.module@@ run", job("run"))

    def test_the_report_is_the_workflow_output(self):
        self.assertIn("value: ${{ jobs.run.outputs.report }}", text())
        self.assertIn("report: ${{ steps.run.outputs.report }}", job("run"))

    def test_no_artifact_actions_are_used(self):
        self.assertNotIn("artifact", text().lower())

    def test_the_gateway_helpers_are_checked_out_at_the_tooling_ref(self):
        self.assertIn("ref: ${{ inputs.tooling-ref }}", job("run"))

    def test_defaults_are_policy_placeholders_not_literals(self):
        for name in ("time-seconds", "output-bytes", "max-parallel", "retry-attempts", "retry-wait-seconds"):
            with self.subTest(name):
                self.assertRegex(text(), r"(?m)^      %s:\n(?:.*\n)*?        default: @@pluginGateway\." % re.escape(name))

    def test_every_placeholder_resolves_in_policy(self):
        keys = set(re.findall(r"@@([A-Za-z0-9_.]+)@@", text()))
        self.assertTrue(keys)
        for key in sorted(keys):
            with self.subTest(key):
                config.get(*key.split("."))

    def test_the_module_the_workflow_runs_exists_with_a_main(self):
        module = importlib.import_module(config.get("pluginGateway", "module"))
        self.assertTrue(callable(module.main))


if __name__ == "__main__":
    unittest.main()
