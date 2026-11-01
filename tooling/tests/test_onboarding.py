import base64
import contextlib
import io
import json
import os
import tempfile
import unittest

from tooling.practice_ci import config, onboarding

PIN = "a" * 40
OTHER = "b" * 40
REPO = "practice-library/demo"
SELF = "practice-library/.github"


class FakeGh:
    """Answers reads from a table and records every write; a ruleset write is readable afterwards."""

    def __init__(self, tag_sha=PIN, files=None):
        self.writes = []
        self.reads = {
            f"repos/{SELF}/commits/{PIN}": {"sha": PIN},
            f"repos/{SELF}/commits/{config.get('release', 'tag')}": {"sha": tag_sha},
            f"repos/{REPO}/teams": [],
            f"repos/{REPO}/rulesets": [],
        }
        for path, text in (files or {}).items():
            branch = config.get("org", "defaultBranch")
            self.reads[f"repos/{REPO}/contents/{path}?ref={branch}"] = {
                "content": base64.b64encode(text.encode()).decode()}

    def read(self, endpoint):
        if endpoint in self.reads:
            return json.dumps(self.reads[endpoint])
        return None

    def write(self, method, endpoint, fields=(), body=None):
        self.writes.append((method, endpoint, tuple(fields), body))
        if endpoint.endswith("/rulesets") and body:
            name = json.loads(body)["name"]
            self.reads[f"repos/{REPO}/rulesets"] = [{"id": 7, "name": name}]
            self.reads[f"repos/{REPO}/rulesets/7"] = json.loads(body)


def run(argv, gh, root=onboarding.ROOT, ref=""):
    out, err = io.StringIO(), io.StringIO()
    env = {"PIN": PIN, "REF": ref}
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        status = onboarding.main(argv, env=env, gh=gh, root=root)
    return status, out.getvalue(), err.getvalue()


def make_root(consumer_files):
    """A scratch repository root: the real ruleset plus the given consumer files ({name: bytes})."""
    root = tempfile.mkdtemp()
    cdir = os.path.join(root, config.get("onboarding", "consumerDir"))
    os.makedirs(cdir)
    for name, data in consumer_files.items():
        with open(os.path.join(cdir, name), "wb") as f:
            f.write(data)
    rulesets = os.path.join(root, os.path.dirname(config.get("onboarding", "rulesetFile")))
    os.makedirs(rulesets)
    with open(os.path.join(onboarding.ROOT, config.get("onboarding", "rulesetFile")), "rb") as src:
        with open(os.path.join(root, config.get("onboarding", "rulesetFile")), "wb") as dst:
            dst.write(src.read())
    return root


class RenderFailureWritesNothing(unittest.TestCase):
    def test_unpinned_template_makes_zero_writes(self):
        root = make_root({"w.yml": b"jobs:\n  a:\n    uses: practice-library/.github/.github/workflows/gate.yml@main\n"})
        gh = FakeGh()
        status, _, err = run(["demo"], gh, root)
        self.assertEqual(status, 2)
        self.assertIn("not to PIN", err)
        self.assertEqual(gh.writes, [])

    def test_unreadable_template_makes_zero_writes(self):
        root = make_root({"w.yml": b"\xff\xfe not utf-8"})
        gh = FakeGh()
        status, _, err = run(["demo"], gh, root)
        self.assertEqual(status, 2)
        self.assertIn("cannot read the template", err)
        self.assertEqual(gh.writes, [])

    def test_bad_allowlist_makes_zero_writes(self):
        gh = FakeGh(files={config.get("automerge", "pathsFile"): "not json"})
        status, _, err = run(["demo"], gh)
        self.assertEqual(status, 2)
        self.assertEqual(gh.writes, [])

    def test_broken_ruleset_makes_zero_writes(self):
        root = make_root({})
        with open(os.path.join(root, config.get("onboarding", "rulesetFile")), "w") as f:
            f.write("{")
        gh = FakeGh()
        status, _, _ = run(["demo"], gh, root)
        self.assertEqual(status, 2)
        self.assertEqual(gh.writes, [])

    def test_bad_pin_makes_zero_writes(self):
        gh = FakeGh()
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = onboarding.main(["demo"], env={"PIN": OTHER}, gh=gh)
        self.assertEqual(status, 2)
        self.assertEqual(gh.writes, [])


class Apply(unittest.TestCase):
    def test_label_comes_from_policy_and_files_carry_pin_and_tag(self):
        tag = config.get("release", "tag")
        gh = FakeGh()
        status, out, _ = run(["demo"], gh)
        self.assertEqual(status, 0)
        labels = [w for w in gh.writes if w[1] == f"repos/{REPO}/labels"]
        self.assertEqual(len(labels), 1)
        cfg = config.get("onboarding", "label")
        self.assertEqual(labels[0][2], (
            ("-f", f"name={config.get('guards', 'loosenLabel')}"),
            ("-f", f"color={cfg['color']}"),
            ("-f", f"description={cfg['description']}")))
        self.assertIn(f"@{PIN} # {tag}", out)
        self.assertNotIn(config.get("onboarding", "pinPlaceholder"), out)
        self.assertNotIn(config.get("onboarding", "refPlaceholder"), out)
        self.assertNotIn(config.get("onboarding", "generatedHeaderPrefix"), out)

    def test_tag_elsewhere_writes_no_label_after_the_pin(self):
        gh = FakeGh(tag_sha=OTHER)
        status, out, _ = run(["demo"], gh)
        self.assertEqual(status, 0)
        self.assertIn("writing no label after the pin", out)
        self.assertIn(f"@{PIN}\n", out)
        self.assertNotIn(f"@{PIN} #", out)

    def test_explicit_ref_is_validated_and_used(self):
        status, _, err = run(["demo"], FakeGh(), ref="bad ref")
        self.assertEqual(status, 2)
        status, out, _ = run(["demo"], FakeGh(), ref="v9.9.9")
        self.assertEqual(status, 0)
        self.assertIn(f"@{PIN} # v9.9.9", out)

    def test_dry_run_writes_nothing(self):
        gh = FakeGh()
        status, out, _ = run(["--dry-run", "demo"], gh)
        self.assertEqual(status, 0)
        self.assertEqual(gh.writes, [])
        self.assertIn("+ api -X POST", out)

    def test_existing_label_is_not_created_again(self):
        gh = FakeGh()
        gh.reads[f"repos/{REPO}/labels/{config.get('guards', 'loosenLabel')}"] = {"name": "x"}
        run(["demo"], gh)
        self.assertEqual([w for w in gh.writes if w[1].endswith("/labels")], [])

    def test_merge_settings_follow_policy(self):
        gh = FakeGh()
        run(["demo"], gh)
        patches = [[v for _, v in w[2]] for w in gh.writes if w[0] == "PATCH" and ("-F", "allow_auto_merge=true") in w[2]]
        self.assertEqual(len(patches), 1)
        fields = {v.split("=")[0]: v.split("=")[1] for v in patches[0]}
        self.assertEqual(fields["allow_merge_commit"], "true")
        self.assertEqual(fields["allow_squash_merge"], "true")
        self.assertEqual(fields["allow_rebase_merge"], "false")


class RepoName(unittest.TestCase):
    def test_accepts_name_and_owner_name(self):
        self.assertEqual(onboarding.parse_repo("demo"), REPO)
        self.assertEqual(onboarding.parse_repo(REPO), REPO)

    def test_refuses_other_owner_extra_segments_and_dots(self):
        for bad in ("other/demo", "practice-library/a/b", "..", ".", "a b", ""):
            with self.assertRaises(onboarding.OnboardError, msg=bad):
                onboarding.parse_repo(bad)


if __name__ == "__main__":
    unittest.main()
