"""The removed-paths guard: prints "ok ..." when nothing in the tree ROOT mentions a path the change
removed, otherwise "referenced [{path, at}, ...]", or "invalid ...".
  DELETED  JSON array of paths the change deleted or renamed away; when unset, read from git for MB..HEAD
  ROOT     the tree after the change
  HISTORY  JSON array of files whose mentions are a record of the past and are allowed
Besides each removed path, every parent directory that no longer exists is looked for, as "dir/" and as
"dir". A mention must not be preceded by a path character, so "x/a.json" is not "a.json".
"""
import json
import os
import re

from practice_ci import config
from practice_ci import git_objects as go

_BINARY_PROBE = 32768


def _terms(deleted, root):
    terms = set()
    for p in deleted:
        if not p:
            continue
        terms.add(p)
        d = os.path.dirname(p)
        while d not in ("", "/"):
            if not os.path.exists(os.path.join(root, d)):
                terms.update((d + "/", d))
            d = os.path.dirname(d)
    return sorted(terms, key=lambda t: (len(t), t), reverse=True)


def _files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d != ".git")
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            if not os.path.islink(full):
                yield full


def _hits(terms, root, history):
    patterns = [(t, re.compile(rb"(?<![A-Za-z0-9._/-])" + re.escape(os.fsencode(t)) + rb"(?![A-Za-z0-9_-])"))
                for t in terms if t]
    found = []
    for full in _files(root):
        rel = os.path.relpath(full, root).replace(os.sep, "/")
        if rel in history:
            continue
        try:
            with open(full, "rb") as f:
                data = f.read()
        except OSError:
            continue
        if b"\0" in data[:_BINARY_PROBE]:
            continue
        for t, rx in patterns:
            for match in rx.finditer(data):
                n = data.count(b"\n", 0, match.start()) + 1
                found.append({"path": t, "at": "%s:%d" % (rel, n)})
    found.sort(key=lambda h: h["at"])
    unique = {}
    for h in found:
        unique.setdefault(h["at"], h)
    return list(unique.values())


def run(env):
    try:
        history = env["HISTORY"]
        history = json.loads(history)
        if "DELETED" in env:
            deleted = json.loads(env["DELETED"])
        else:
            deleted = []
            for c in go.diff_changes(env["MB"], env["HEAD"], diff_filter="DR"):
                deleted.append(c.old_path if c.old_path is not None else c.path)
        assert isinstance(deleted, list) and isinstance(history, list)
    except (ValueError, KeyError, AssertionError):
        return "invalid DELETED and HISTORY must be JSON arrays"
    except go.GitError:
        return "invalid the change could not be read"
    root = env["ROOT"]
    terms = _terms(sorted(set(deleted)), root)
    hits = _hits(terms, root, set(history))[:config.get("git", "reportLimit")]
    if not hits:
        return "ok no removed path is mentioned"
    return "referenced " + json.dumps(hits, separators=(",", ":"), ensure_ascii=False)
