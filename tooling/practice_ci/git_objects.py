"""Byte-safe access to git for the guards.

Every read goes through ``git()``, which returns bytes and raises GitError when git fails, so a change
that cannot be read is never judged clean. Paths are read from ``-z`` output (or C-unquoted from a diff
header) and kept exactly: quotes, tabs, newlines and non-ASCII bytes survive. A path that is not UTF-8
is decoded with surrogateescape so it round-trips.
"""
import re
import subprocess
from dataclasses import dataclass


class GitError(Exception):
    """A git read failed, or its output is not what git writes."""


def git(*args, cwd=None):
    try:
        done = subprocess.run(["git", *args], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as e:
        raise GitError("git cannot run: %s" % e)
    if done.returncode != 0:
        raise GitError("git %s failed with exit %d" % (args[0] if args else "", done.returncode))
    return done.stdout


def decode_path(raw):
    return raw.decode("utf-8", "surrogateescape")


def decode_text(raw):
    return raw.decode("utf-8", "replace")


# ---- changed paths ---------------------------------------------------------------------------------

@dataclass(frozen=True)
class Change:
    """One entry of ``git diff --name-status -z``. A rename or copy keeps both paths."""
    status: str
    path: str
    old_path: str | None = None
    score: int | None = None

    @property
    def paths(self):
        return (self.path,) if self.old_path is None else (self.old_path, self.path)


_STATUS = re.compile(rb"([ACDMRTUX])([0-9]*)")


def parse_name_status(raw):
    """Parse ``--name-status -z`` output into Change records."""
    tokens = raw.split(b"\0")
    if tokens and tokens[-1] == b"":
        tokens.pop()
    changes = []
    i = 0
    while i < len(tokens):
        m = _STATUS.fullmatch(tokens[i])
        if not m:
            raise GitError("unexpected name-status entry")
        letter = m.group(1).decode()
        score = int(m.group(2)) if m.group(2) else None
        width = 2 if letter in "RC" else 1
        if i + 1 + width > len(tokens):
            raise GitError("name-status output ends inside an entry")
        paths = [decode_path(t) for t in tokens[i + 1:i + 1 + width]]
        if width == 2:
            changes.append(Change(letter, paths[1], paths[0], score))
        else:
            changes.append(Change(letter, paths[0], None, score))
        i += 1 + width
    return changes


def diff_changes(base, head, *, renames=True, diff_filter=None, pathspecs=(), cwd=None):
    args = ["--literal-pathspecs", "diff", "--name-status", "-z", "--no-ext-diff",
            "-M" if renames else "--no-renames"]
    if diff_filter:
        args.append("--diff-filter=" + diff_filter)
    args += [base, head]
    if pathspecs:
        args += ["--", *pathspecs]
    return parse_name_status(git(*args, cwd=cwd))


# ---- objects by id ---------------------------------------------------------------------------------

def blob_oid(rev, path, *, cwd=None):
    """The object id of the blob at ``path`` in ``rev``; GitError when there is none."""
    out = git("rev-parse", "--verify", "--quiet", "%s:%s" % (rev, path), cwd=cwd)
    return out.decode("ascii").strip()


def read_blob(oid, *, cwd=None):
    return git("cat-file", "blob", oid, cwd=cwd)


def commits_in_range(base, head, *, cwd=None):
    out = git("rev-list", "%s..%s" % (base, head), cwd=cwd)
    return [s.decode("ascii") for s in out.split(b"\n") if s]


# ---- commits ---------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Commit:
    sha: str
    parents: tuple
    author: str
    committer: str
    message: bytes

    @property
    def is_merge(self):
        return len(self.parents) > 1

    def message_lines(self):
        """The message split on newline only, every byte kept: text after a NUL is still a line's text."""
        return [decode_text(line) for line in self.message.split(b"\n")]


_IDENT = re.compile(rb"(?:(.*) )?<[^<>]*> [0-9]+ [+-][0-9]{4}")


def parse_commit(sha, raw):
    """Parse a commit object (``git cat-file commit``). The message starts after the first blank line,
    so no byte of it can pose as a header; a malformed object is rejected."""
    head, sep, message = raw.partition(b"\n\n")
    if not sep:
        raise GitError("commit %s has no message separator" % sha)
    parents, idents, encoding = [], {}, "utf-8"
    for line in head.split(b"\n"):
        if line.startswith(b" "):
            continue  # continuation of a multi-line header (a signature)
        key, _, value = line.partition(b" ")
        if key == b"parent":
            parents.append(value.decode("ascii", "replace"))
        elif key == b"encoding":
            encoding = value.decode("ascii", "replace")
        elif key in (b"author", b"committer"):
            if key in idents:
                raise GitError("commit %s has two %s headers" % (sha, key.decode()))
            m = _IDENT.fullmatch(value)
            if not m:
                raise GitError("commit %s has an unreadable %s header" % (sha, key.decode()))
            idents[key] = m.group(1) or b""
    if b"author" not in idents or b"committer" not in idents:
        raise GitError("commit %s lacks an author or a committer" % sha)

    def name(raw_name):
        try:
            return raw_name.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            return decode_text(raw_name)

    return Commit(sha, tuple(parents), name(idents[b"author"]), name(idents[b"committer"]), message)


def read_commit(sha, *, cwd=None):
    return parse_commit(sha, git("cat-file", "commit", sha, cwd=cwd))


def read_commits(base, head, *, cwd=None):
    return [read_commit(s, cwd=cwd) for s in commits_in_range(base, head, cwd=cwd)]


# ---- added lines -----------------------------------------------------------------------------------

@dataclass(frozen=True)
class AddedLine:
    path: str
    line: int
    payload: bytes


_C_ESCAPES = {b"a": 7, b"b": 8, b"f": 12, b"n": 10, b"r": 13, b"t": 9, b"v": 11, b"\\": 92, b'"': 34}
_C_PART = re.compile(rb'\\([0-7]{3}|.)|([^\\"]+)', re.S)


def unquote_diff_path(raw):
    """The path of a ``+++ `` header: C-quoted by git when it holds a quote, tab, newline, backslash
    or (by default) a non-ASCII byte; otherwise bare, with one trailing tab when it holds a space."""
    if not raw.startswith(b'"'):
        return decode_path(raw[:-1] if raw.endswith(b"\t") else raw)
    out = bytearray()
    pos = 1
    while True:
        if pos >= len(raw):
            raise GitError("a quoted diff path is not closed")
        if raw[pos:pos + 1] == b'"':
            return decode_path(bytes(out))
        m = _C_PART.match(raw, pos)
        if not m:
            raise GitError("a quoted diff path cannot be read")
        esc, plain = m.group(1), m.group(2)
        if plain is not None:
            out += plain
        elif len(esc) == 3 and esc[:1] in b"01234567":
            out.append(int(esc, 8) & 0xFF)
        elif esc in _C_ESCAPES:
            out.append(_C_ESCAPES[esc])
        else:
            raise GitError("a quoted diff path holds an unknown escape")
        pos = m.end()


_HUNK = re.compile(rb"\+([0-9]+)")


def added_lines(base, head, *, cwd=None):
    """Every line the change adds, with its path and line number in the head, as bytes.

    The diff is taken with --no-renames (a moved file's every line is read at its new path), --text and
    --no-textconv (no .gitattributes can hide a line). A ``+++ `` line is a file header only between
    ``diff --git`` and the first ``@@``; inside a hunk it is an added line starting with ``++``."""
    out = git("diff", "--text", "--no-textconv", "--no-ext-diff", "--no-color", "--no-prefix",
              "--no-renames", "--unified=0", base, head, cwd=cwd)
    path, lineno, in_header = None, 0, False
    found = []
    for line in out.split(b"\n"):
        if line.startswith(b"diff --git "):
            in_header, path = True, None
        elif in_header and line.startswith(b"+++ "):
            path = unquote_diff_path(line[4:])
        elif line.startswith(b"@@"):
            m = _HUNK.search(line)
            if not m:
                raise GitError("a hunk header has no new line number")
            in_header, lineno = False, int(m.group(1))
        elif not in_header and line.startswith(b"+"):
            if path is None:
                raise GitError("an added line has no file header")
            found.append(AddedLine(path, lineno, line[1:]))
            lineno += 1
    return found
