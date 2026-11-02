"""scripts/discover.sh on this repository: every check has JSON targets and fixtures, and no template is a target."""
import json
import os
import shutil
import subprocess
import unittest

from tooling.tests import ROOT
from practice_ci import config


@unittest.skipUnless(shutil.which("jq") and shutil.which("git"), "needs jq and git")
class DiscoverTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.done = subprocess.run(["bash", os.path.join(ROOT, config.get("self", "discoverScript"))], cwd=ROOT,
                                  capture_output=True, text=True, check=False)
        cls.outputs = dict(line.split("=", 1) for line in cls.done.stdout.splitlines())

    def test_it_succeeds_and_prints_only_json_outputs(self):
        self.assertEqual(self.done.returncode, 0, self.done.stderr)
        for name, value in self.outputs.items():
            with self.subTest(output=name):
                self.assertIsInstance(json.loads(value), list)

    def test_every_check_has_targets_and_fixtures(self):
        for row in config.get("checks"):
            with self.subTest(check=row["id"]):
                self.assertTrue(json.loads(self.outputs["targets-" + row["id"]]))
                self.assertTrue(json.loads(self.outputs["fixtures-" + row["id"]]))

    def test_no_template_is_a_target(self):
        # templates/spec/*/check.json is "@@json:...@@", not JSON: matching it made jq fail in CI.
        templates = config.get("render", "templatesDir") + "/"
        for row in config.get("checks"):
            for target in json.loads(self.outputs["targets-" + row["id"]]):
                with self.subTest(check=row["id"], target=target["target"]):
                    self.assertFalse(target["target"].startswith(templates))


if __name__ == "__main__":
    unittest.main()
