"""The denylist scan: prints "ok ...", "found <n> <where>...", "unguarded ..." or "invalid ...".

The term itself is never printed.
  DENY       JSON {"salt": "<text>", "sha256": ["<hex>", ...], "allowAuthorNames": ["<hex>", ...]}: each
             sha256 entry is 64 lower-case hex characters, sha256(salt + ":" + term), where a term is one
             word or two adjacent words, lower case, words joined by one space; empty when the repository
             has no list. The optional allowAuthorNames entries are sha256(salt + ":" + name) of whole
             names, written the same way: an author or committer name that is one of them is not judged.
             Messages, added lines and added paths are judged whatever the name.
             The optional exemptPaths is a list of {"glob": <path glob>, "terms": [<hex>, ...]}: an added
             line of a file whose path matches a glob is not found for the sha256 entries in terms, or
             for any entry when terms is absent. It applies to added lines only. A glob is relative to
             the root: * and ? stay inside one path segment, a segment that is exactly ** spans any number
             of segments, and the first segment holds no wildcard. Each line an exemption lets through is
             printed with its glob (the first reportLimit, after the count).
  EVENT      the GitHub event; push leaves the author name of merge commits out (a merge made in the
             browser is authored by whoever pressed merge). Its message and committer are judged.
  TEXT_FILE  rows "<where><TAB><text>"; when unset, the change MB..HEAD is collected from git.
A text is cut into words of [a-z0-9]; each word, each two adjacent words, and those two written together
are checked.
"""
import hashlib
import json
import re

from practice_ci import config, git_objects, scan_records
from practice_ci.scan_records import NAME_KINDS, LINE

_DIGEST = re.compile(r"[0-9a-f]{64}")
_GLOB = re.compile(r"[A-Za-z0-9._*?-]+(/[A-Za-z0-9._*?-]+)*")
_INVALID_LIST = ('invalid the denylist must be {"salt": text, "sha256": [64 lower-case hex, ...], '
                 '"allowAuthorNames": [64 lower-case hex, ...]}')
_INVALID_EXEMPT = ('invalid exemptPaths must be [{"glob": path glob whose first segment has no wildcard, '
                   '"terms": [hex, ...]}]')


class Invalid(Exception):
    """The denylist cannot be used; the message is the result line."""


def _glob_re(g):
    segs = g.split("/")
    out = ""
    for i, seg in enumerate(segs):
        last = i == len(segs) - 1
        if seg == "**":
            out += ".+" if last else "(?:[^/]+/)*"
            continue
        out += "".join("[^/]*" if c == "*" else "[^/]" if c == "?" else re.escape(c) for c in seg)
        if not last:
            out += "/"
    return re.compile(out)


def _all_digests(items):
    return isinstance(items, list) and all(isinstance(h, str) and _DIGEST.fullmatch(h) for h in items)


def parse_deny(text):
    """(salt, hashes, allowed names, exemptions) from the DENY JSON, or Invalid."""
    try:
        deny = json.loads(text)
        salt, terms, allow = deny["salt"], deny["sha256"], deny.get("allowAuthorNames", [])
        assert isinstance(salt, str) and salt and _all_digests(terms) and _all_digests(allow)
    except Exception:
        raise Invalid(_INVALID_LIST)
    exempt = []
    try:
        rules = deny.get("exemptPaths", [])
        assert isinstance(rules, list)
        for r in rules:
            assert isinstance(r, dict) and set(r) <= {"glob", "terms"}
            g = r["glob"]
            assert isinstance(g, str) and _GLOB.fullmatch(g)
            segs = g.split("/")
            assert not re.search(r"[*?]", segs[0]) and ".." not in segs and "." not in segs
            assert all(s == "**" or "**" not in s for s in segs)
            t = r.get("terms")
            assert t is None or (t and _all_digests(t))
            exempt.append((g, _glob_re(g), None if t is None else set(t)))
    except Exception:
        raise Invalid(_INVALID_EXEMPT)
    return salt, set(terms), set(allow), exempt


def judge(records, salt, hashes, allow, exempt):
    """The result line for these records. Only a record's kind decides how it is judged."""
    limit = config.get("git", "reportLimit")
    if not hashes:
        return "unguarded the denylist has no entries"

    def h(term):
        return hashlib.sha256((salt + ":" + term).encode()).hexdigest()

    found, let_through = [], []
    for rec in records:
        words = re.findall(r"[a-z0-9]+", rec.payload.lower())
        if rec.kind in NAME_KINDS and h(" ".join(words)) in allow:
            continue
        terms = set(words)
        for a, b in zip(words, words[1:]):
            terms.add(a + " " + b)
            terms.add(a + b)
        hit = {h(t) for t in terms} & hashes
        if not hit:
            continue
        where = rec.where()
        if rec.kind == LINE:
            for g, rx, t in exempt:
                if rx.fullmatch(rec.path) and (t is None or hit <= t):
                    let_through.append("%s (%s)" % (where, g))
                    break
            else:
                found.append(where)
        else:
            found.append(where)
    note = ""
    if let_through:
        note = "; exempt %d: %s" % (len(let_through), ", ".join(let_through[:limit]))
    if found:
        seen = list(dict.fromkeys(found))
        return "found %d %s%s" % (len(found), ", ".join(seen[:limit]), note)
    return "ok no denied term in the change" + note


def run(env):
    deny = env.get("DENY", "")
    if not deny:
        return "unguarded no denylist: add one (scripts/denylist-hash.sh)"
    try:
        if env.get("TEXT_FILE"):
            records = scan_records.read_rows(env["TEXT_FILE"])
        else:
            records = scan_records.collect(env["MB"], env["HEAD"], skip_merge_authors=env.get("EVENT") == "push")
    except (git_objects.GitError, KeyError, OSError):
        return "invalid the change could not be read"
    try:
        return judge(records, *parse_deny(deny))
    except Invalid as e:
        return str(e)
