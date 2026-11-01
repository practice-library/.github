"""Reads files out of commits in the caller's repository. A file that is not there is None; a file that
is there but cannot be read raises, so a failed read never looks like an absent file."""

import subprocess
from pathlib import Path


class GitReadError(RuntimeError):
    """A git object that exists could not be read."""


def blob(root: Path, rev: str, path: str) -> str | None:
    """The text of path at rev as a shell command substitution reads it: without trailing newlines and
    without NUL bytes, so the value can be handed to a fragment in its environment."""
    spec = rev + ":" + path
    probe = subprocess.run(["git", "cat-file", "-e", spec], cwd=root, capture_output=True, check=False)
    if probe.returncode != 0:
        return None
    read = subprocess.run(["git", "cat-file", "blob", spec], cwd=root, capture_output=True, check=False)
    if read.returncode != 0:
        raise GitReadError("cannot read " + spec)
    return read.stdout.replace(b"\0", b"").decode("utf-8", "surrogateescape").rstrip("\n")
