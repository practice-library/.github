"""templates/.github/workflows/plugin-matrix.yml: the wiring the gateway helpers rely on (#41)."""
import importlib
import os
import re
import unittest

from tooling.practice_ci import config

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TEMPLATE = os.path.join(ROOT, "templates", ".github", "workflows", config.get("pluginGateway", "workflow"))
# Actions this template needs that policy has no pin for yet; the integration render adds them.
UNPINNED = ("actions.uploadArtifact.", "actions.downloadArtifact.")


def text():
    with open(TEMPLATE, encoding="utf-8") as f:
        return f.read()


def job(name):
    body = text().split("\njobs:\n", 1)[1]
    match = re.search(r"(?ms)^  %s:\n(.*?)(?=^  [a-z]+:\n|\Z)" % re.escape(name), body)
    assert match, name
    return match.group(1)


class Template(unittest.TestCase):
    def test_three_jobs_plan_unit_merge(self):
        body = text().split("\njobs:\n", 1)[1]
        self.assertEqual(re.findall(r"(?m)^  ([a-z]+):\n", body), ["plan", "unit", "merge"])

    def test_merge_runs_even_when_a_unit_fails_but_not_without_a_plan(self):
        merge = job("merge")
        self.assertIn("needs: [plan, unit]", merge)
        self.assertIn("if: always() && needs.plan.result == 'success'", merge)

    def test_unit_matrix_width_and_units_come_from_the_plan(self):
        unit = job("unit")
        self.assertIn("max-parallel: ${{ fromJSON(needs.plan.outputs.max-parallel) }}", unit)
        self.assertIn("unit: ${{ fromJSON(needs.plan.outputs.units) }}", unit)
        self.assertIn("fail-fast: false", unit)
        self.assertIn("needs.plan.outputs.has-units == 'true'", unit)

    def test_partials_are_uploaded_even_after_a_failure(self):
        self.assertRegex(job("unit"), r"if: always\(\)\n\s+with:\n\s+name: @@pluginGateway\.artifacts\.partialPrefix@@")

    def test_defaults_are_policy_placeholders_not_literals(self):
        for name in ("time-seconds", "output-bytes", "max-parallel", "retry-attempts", "retry-wait-seconds"):
            with self.subTest(name):
                self.assertRegex(text(), r"(?m)^      %s:\n(?:.*\n)*?        default: @@pluginGateway\." % re.escape(name))

    def test_every_placeholder_resolves_in_policy_except_the_unpinned_actions(self):
        keys = set(re.findall(r"@@([A-Za-z0-9_.]+)@@", text()))
        self.assertTrue(keys)
        for key in sorted(keys):
            if key.startswith(UNPINNED):
                continue
            with self.subTest(key):
                config.get(*key.split("."))

    def test_the_module_the_workflow_runs_exists_with_a_main(self):
        module = importlib.import_module(config.get("pluginGateway", "module"))
        self.assertTrue(callable(module.main))


if __name__ == "__main__":
    unittest.main()
