"""Release consistency: the tag about to be cut, the top version heading of the changelog and
policy release.tag must be one and the same.

Usage: python3 -m practice_ci.release <tag>
"""
import os
import re
import sys

from . import config

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def top_version(changelog_text):
    """The first version heading of the changelog (a heading such as "Unreleased" is not one), or None."""
    heading = re.compile(config.get("release", "changelogHeadingPattern"))
    for line in changelog_text.splitlines():
        found = heading.match(line)
        if found:
            return found.group(1)
    return None


def check(tag, changelog_text, policy_tag):
    """The ways the three disagree, as a list of messages (empty when they agree)."""
    errors = []
    top = top_version(changelog_text)
    if top is None:
        errors.append("the changelog has no version heading")
    elif top != tag:
        errors.append(f"the top changelog version is {top}, not the intended tag {tag}")
    if policy_tag != tag:
        errors.append(f"release.tag in policy/constants.json is {policy_tag}, not the intended tag {tag}")
    return errors


def main(argv=None, root=ROOT):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("usage: python3 -m practice_ci.release <tag>", file=sys.stderr)
        return 2
    with open(os.path.join(root, config.get("guards", "changelog")), encoding="utf-8") as f:
        errors = check(argv[0], f.read(), config.get("release", "tag"))
    for error in errors:
        print(f"error: {error}")
    if not errors:
        print(f"ok: {argv[0]} is the top changelog version and release.tag")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
