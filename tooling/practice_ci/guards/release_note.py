"""The release-note guard: prints "ok ...", "missing ..." or "invalid ...".

Ok when the change touches no watched path, or adds a line with text to the changelog (a whitespace-only
edit does not count), or a commit message holds the marker line.
  CHANGED    JSON array of changed paths, old and new; when unset, read from git for MB..HEAD, with both
             paths of a rename
  WATCH      JSON array of watched paths; an entry ending in / covers everything under it
  CHANGELOG  the changelog path       MARKER  the line that says no release is needed
  MESSAGES   the change's commit messages; when unset, read from the commit objects of MB..HEAD, every
             byte of them
  CHANGELOG_ADDED  how many lines the change adds to the changelog that hold a non-space character; when
             unset, counted from git: added lines after the first hunk header (so a line that starts with
             ++ counts), minus lines the same change removes (so a moved line counts nothing), with
             whitespace changes ignored.
"""
import json
import re
from collections import Counter

from practice_ci import git_objects as go

_TRAILING_SPACE = " \t\r\f\v"


def changelog_added(mb, head, changelog):
    out = go.git("--literal-pathspecs", "diff", "-w", "--ignore-blank-lines", "--no-ext-diff", "--no-textconv",
                 "--text", "--no-color", "--unified=0", mb, head, "--", changelog)
    lines = out.split(b"\n")
    first = next((i for i, l in enumerate(lines) if l.startswith(b"@@")), None)
    if first is None:
        return 0
    added = [l[1:] for l in lines[first:] if l.startswith(b"+")]
    removed = Counter(l[1:] for l in lines[first:] if l.startswith(b"-"))
    kept = 0
    for l in added:
        if removed[l] > 0:
            removed[l] -= 1
        else:
            kept += 1
    return kept


def _watched(changed, watch):
    return sorted({f for f in changed
                   if any(f.startswith(p) if p.endswith("/") else f == p for p in watch)})


def _json_list(text):
    value = json.loads(text)
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ValueError("not a list of strings")
    return value


def run(env):
    mb, head = env.get("MB", ""), env.get("HEAD", "")
    changelog = env.get("CHANGELOG", "")
    try:
        if "CHANGELOG_ADDED" not in env:
            if not (mb and head):
                return "invalid CHANGELOG_ADDED is unset and there is no MB..HEAD to count from"
            try:
                env = dict(env, CHANGELOG_ADDED=str(changelog_added(mb, head, changelog)))
            except go.GitError:
                return "invalid the changelog diff could not be read"
        if not re.fullmatch(r"[0-9]+", env["CHANGELOG_ADDED"]):
            return "invalid CHANGELOG_ADDED must be a count"
        added = int(env["CHANGELOG_ADDED"])
        try:
            watch = _json_list(env["WATCH"])
            if "CHANGED" in env:
                changed = _json_list(env["CHANGED"])
            else:
                changed = [p for c in go.diff_changes(mb, head) for p in c.paths]
        except (ValueError, KeyError):
            return "invalid CHANGED and WATCH must be JSON arrays"
        touched = _watched(changed, watch)
        if not touched:
            return "ok no watched path changed"
        if added > 0 and changelog in changed:
            return "ok %s has %d added lines" % (changelog, added)
        if "MESSAGES" in env:
            lines = env["MESSAGES"].split("\n")
        else:
            lines = [l for c in go.read_commits(mb, head) for l in c.message_lines()]
        marker = env["MARKER"]
        if any(l.rstrip(_TRAILING_SPACE) == marker for l in lines):
            return "ok a commit message says: " + marker
        return ('missing %s changed, but neither %s nor a "%s" line in a commit message'
                % (json.dumps(touched, separators=(",", ":"), ensure_ascii=False), changelog, marker))
    except go.GitError:
        return "invalid the change could not be read"
