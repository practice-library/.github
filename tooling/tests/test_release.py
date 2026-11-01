import os
import tempfile
import unittest

from tooling.practice_ci import config, release

LOG = "# Changelog\n\nintro\n\n## Unreleased\n\n## v3.0.0\n\n- x\n\n## v2.6.0\n"


class Check(unittest.TestCase):
    def test_agreeing_tag_passes(self):
        self.assertEqual(release.check("v3.0.0", LOG, "v3.0.0"), [])

    def test_unreleased_is_not_a_version(self):
        self.assertEqual(release.top_version(LOG), "v3.0.0")

    def test_tag_differs_from_changelog(self):
        errors = release.check("v3.1.0", LOG, "v3.1.0")
        self.assertEqual(len(errors), 1)
        self.assertIn("v3.0.0", errors[0])

    def test_stale_policy_tag_is_refused(self):
        errors = release.check("v3.0.0", LOG, "v2.0.0")
        self.assertEqual(len(errors), 1)
        self.assertIn("release.tag", errors[0])

    def test_no_version_heading(self):
        self.assertEqual(len(release.check("v3.0.0", "# Changelog\n\n## Unreleased\n", "v3.0.0")), 1)


class ThisRepository(unittest.TestCase):
    def test_policy_tag_is_the_top_changelog_version(self):
        with open(os.path.join(release.ROOT, config.get("guards", "changelog")), encoding="utf-8") as f:
            top = release.top_version(f.read())
        self.assertEqual(config.get("release", "tag"), top)

    def test_historical_v2_4_0_note_is_recorded(self):
        with open(os.path.join(release.ROOT, config.get("guards", "changelog")), encoding="utf-8") as f:
            text = f.read()
        section = text.split("## v2.4.0", 1)[1].split("\n## ", 1)[0]
        self.assertIn("No tag was moved", section)

    def test_main_exit_status(self):
        root = tempfile.mkdtemp()
        with open(os.path.join(root, config.get("guards", "changelog")), "w", encoding="utf-8") as f:
            f.write(LOG)
        self.assertEqual(release.main(["v3.0.0"], root=root), 0)
        self.assertEqual(release.main(["v3.0.1"], root=root), 1)
        self.assertEqual(release.main([], root=root), 2)


if __name__ == "__main__":
    unittest.main()
