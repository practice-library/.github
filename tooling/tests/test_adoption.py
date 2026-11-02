"""Exercise the adoption example through the real template renderer, without writing outputs."""
import json
from pathlib import Path
import re
import subprocess
import unittest

from tooling.practice_ci import config, onboarding


class AdoptionExample(unittest.TestCase):
    def render(self, policy):
        root = Path(onboarding.ROOT)
        templates = root / config.get("render", "templatesDir")
        fragments = root / config.get("render", "fragmentsDir")
        all_templates = {str(p.relative_to(templates)): p.read_text()
                         for p in templates.rglob("*") if p.is_file()}
        result = subprocess.run([
            "jq", "-nr", "--argjson", "c", json.dumps([policy]),
            "--argjson", "frags", json.dumps({p.name: p.read_text() for p in fragments.iterdir() if p.is_file()}),
            "--argjson", "all", json.dumps(all_templates),
            "--arg", "t", all_templates["README.md"],
            "-f", str(root / "scripts" / "render.jq"),
        ], capture_output=True, text=True, check=True)
        return result.stdout.split("```yaml\n", 1)[1].split("```", 1)[0]

    def test_example_runs_every_mandatory_job_and_gate_needs_follow_policy(self):
        policy = config.load()
        # Reordering also proves needs is rendered from policy, rather than copied.
        for mandatory in (policy["gate"]["mandatoryJobs"], list(reversed(policy["gate"]["mandatoryJobs"]))):
            policy["gate"]["mandatoryJobs"] = mandatory
            example = self.render(policy).split("jobs:\n", 1)[1]
            jobs = dict(re.findall(r"(?m)^  ([\w-]+):\n((?:^    .*\n|^\n)*)", example))
            gate = jobs[config.get("gate", "callerJob")]
            needs = json.loads(re.search(r"needs: (\[.*\])", gate).group(1))
            self.assertEqual(needs, mandatory)
            self.assertEqual(set(jobs), set(mandatory) | {config.get("gate", "callerJob")})
            for job in mandatory:
                body = jobs[job]
                workflow = (config.get("guards", "workflow") if job in config.get("guards", "ids")
                            else next(c["workflow"] for c in config.get("checks") if c["id"] == job))
                reference = f"{config.get('org', 'name')}/{config.get('org', 'repo')}/.github/workflows/{workflow}@<sha>"
                self.assertIn(f"uses: {reference}", body)
                if job in config.get("guards", "ids"):
                    self.assertIn(f"guard: {job}", body)
                    self.assertIn("pull-requests: read", body)
            self.assertIn("if: always()", gate)
            self.assertIn("needs: ${{ toJSON(needs) }}", gate)
