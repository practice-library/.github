"""Typed scan records: what the denylist judges, each with a kind set by where it was read from.

A record is {kind, path, commit, line, payload}. The kind comes from the reader that made the record
(an added line, an added path, a name, a message line); it is never inferred from the payload text, so
no line of a message or a file can pose as another kind of record.
"""
import re
from dataclasses import dataclass

from practice_ci import git_objects as go

LINE, PATH, AUTHOR, COMMITTER, MESSAGE, TEXT = "line", "path", "author", "committer", "message", "text"
NAME_KINDS = (AUTHOR, COMMITTER)


@dataclass(frozen=True)
class ScanRecord:
    kind: str
    path: str = ""
    commit: str = ""
    line: int = 0
    payload: str = ""

    def where(self):
        """The place to report: never the payload, which may hold the denied term."""
        if self.kind == LINE:
            return "%s:%d" % (self.path, self.line)
        if self.kind == PATH:
            return "added path %d" % self.line
        if self.kind in NAME_KINDS:
            return "%s %s" % (self.kind, self.commit)
        if self.kind == MESSAGE:
            return "commit %s" % self.commit
        return self.path


def collect(base, head, *, skip_merge_authors=False, cwd=None):
    """Every added line, added path, commit message line, author name and committer name of
    base..head. Any failed read raises GitError, so an unreadable change is never judged clean."""
    records = []
    for a in go.added_lines(base, head, cwd=cwd):
        records.append(ScanRecord(LINE, path=a.path, line=a.line, payload=go.decode_text(a.payload)))
    added = [c for c in go.diff_changes(base, head, cwd=cwd) if c.status in "ARC"]
    for n, c in enumerate(added, 1):
        records.append(ScanRecord(PATH, path=c.path, line=n, payload=c.path))
    commits = go.read_commits(base, head, cwd=cwd)
    for c in commits:
        if not (skip_merge_authors and c.is_merge):
            records.append(ScanRecord(AUTHOR, commit=c.sha, payload=c.author))
    for c in commits:
        records.append(ScanRecord(COMMITTER, commit=c.sha, payload=c.committer))
    for c in commits:
        for n, text in enumerate(c.message_lines(), 1):
            records.append(ScanRecord(MESSAGE, commit=c.sha, line=n, payload=text))
    return records


_NAME_ROW = re.compile(r"(author|committer) ([0-9a-f]{40}|[0-9a-f]{64})")
_PATH_ROW = re.compile(r"added path ([0-9]+)")
_MESSAGE_ROW = re.compile(r"commit ([0-9a-f]{40}|[0-9a-f]{64})")
_LINE_ROW = re.compile(r"(.+):([0-9]+)")


def read_rows(text_file):
    """Records from a file of "<where><TAB><text>" rows (a producer outside git, such as an issue body).
    Rows are split on "\\n" only: a lone "\\r" in a text must not start a row whose where the text chose.
    The kind is read from the where column, which the producer wrote, never from the text."""
    records = []
    with open(text_file, encoding="utf-8", errors="replace", newline="\n") as f:
        for row in f:
            where, _, text = row.rstrip("\n").partition("\t")
            if m := _NAME_ROW.fullmatch(where):
                records.append(ScanRecord(m.group(1), commit=m.group(2), payload=text))
            elif m := _PATH_ROW.fullmatch(where):
                records.append(ScanRecord(PATH, line=int(m.group(1)), payload=text))
            elif m := _MESSAGE_ROW.fullmatch(where):
                records.append(ScanRecord(MESSAGE, commit=m.group(1), payload=text))
            elif m := _LINE_ROW.fullmatch(where):
                records.append(ScanRecord(LINE, path=m.group(1), line=int(m.group(2)), payload=text))
            else:
                records.append(ScanRecord(TEXT, path=where, payload=text))
    return records
