"""The size guard: prints "ok <n> non-fixture lines (limit <L>)", "over <n> non-fixture lines, more than
<L>: split the pull request", or "invalid ...".
  NUMSTAT   output of git diff --numstat -M: "<added><TAB><deleted><TAB><path>", a rename written as
            "<old> => <new>" or "<dir>/{<old> => <new>}/<rest>"; a binary file shows "-" and counts 0.
            When unset, read from git for MB..HEAD with -z, so a path is exact (quotes, tabs, newlines),
            and each file git calls binary is recounted from its diff taken with --text.
  FIXTURES  JSON array of fixture entries. An entry starting and ending in / is a directory from the root
            ("/rulesets/"); any other entry ending in / is a directory anywhere in the path
            ("examples/"); an entry with no / is a file name anywhere ("INDEX.md"); any other entry is one
            exact path from the root, a leading / allowed. The entry "/" alone is refused.
  LIMIT     the most non-fixture lines that pass, a whole number
A changed line counts once, as an added line; a renamed file counts by its new path, once.
"""
import json
import re

from practice_ci import git_objects as go

_NUMSTAT_LINE = re.compile(r"([0-9]+|-)")


def newpath(path):
    """The new path of a numstat path written with rename arrows."""
    if re.search(r"\{.* => .*\}", path):
        return re.sub(r"\{([^{}]*) => ([^{}]*)\}", lambda m: m.group(2), path, count=1).replace("//", "/")
    if " => " in path:
        return re.sub(r"^.* => ", "", path)
    return path


def is_fixture(path, fixtures):
    for e in fixtures:
        if e.startswith("/") and e.endswith("/"):
            hit = path.startswith(e[1:])
        elif e.endswith("/"):
            hit = ("/" + path).find("/" + e) >= 0
        elif "/" in e:
            hit = path == e.removeprefix("/")
        else:
            hit = path.split("/")[-1] == e
        if hit:
            return True
    return False


def _parse_numstat_text(text):
    rows = []
    for line in text.split("\n"):
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 3 or not _NUMSTAT_LINE.fullmatch(parts[0]):
            raise ValueError("bad numstat line")
        rows.append((0 if parts[0] == "-" else int(parts[0]), newpath("\t".join(parts[2:]))))
    return rows


def _read_numstat(mb, head):
    raw = go.git("diff", "--numstat", "-z", "-M", "--no-ext-diff", "--no-textconv", mb, head)
    tokens = raw.split(b"\0")
    if tokens and tokens[-1] == b"":
        tokens.pop()
    rows, i = [], 0
    while i < len(tokens):
        added, _, rest = tokens[i].partition(b"\t")
        _deleted, _, path = rest.partition(b"\t")
        i += 1
        if not path:  # a rename: the old path, then the new one, follow
            if i + 2 > len(tokens):
                raise go.GitError("numstat output ends inside a rename")
            path = tokens[i + 1]
            i += 2
        path = go.decode_path(path)
        if added == b"-":
            out = go.git("--literal-pathspecs", "diff", "--text", "--no-textconv", "--no-ext-diff", "--no-color",
                         "--unified=0", mb, head, "--", path)
            count, in_hunk = 0, False
            for line in out.split(b"\n"):
                if line.startswith(b"@@"):
                    in_hunk = True
                elif in_hunk and line.startswith(b"+"):
                    count += 1
            rows.append((count, path))
        else:
            rows.append((int(added), path))
    return rows


def run(env):
    limit = env.get("LIMIT", "")
    if not re.fullmatch(r"[0-9]+", limit):
        return "invalid LIMIT must be a whole number"
    try:
        fixtures = json.loads(env.get("FIXTURES", "null"))
        assert isinstance(fixtures, list) and all(isinstance(f, str) and f and f != "/" for f in fixtures)
    except (ValueError, AssertionError):
        return 'invalid FIXTURES must be a JSON array of non-empty strings, not "/"'
    try:
        if "NUMSTAT" in env:
            rows = _parse_numstat_text(env["NUMSTAT"])
        else:
            rows = _read_numstat(env["MB"], env["HEAD"])
    except ValueError:
        return "invalid NUMSTAT is not git diff --numstat output"
    except (go.GitError, KeyError):
        return "invalid the diff could not be read"
    n = sum(added for added, path in rows if not is_fixture(path, fixtures))
    if n <= int(limit):
        return "ok %d non-fixture lines (limit %s)" % (n, limit)
    return "over %d non-fixture lines, more than %s: split the pull request" % (n, limit)
