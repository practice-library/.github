"""Issue #61 (exact paths) and #70 (every byte of a commit message) for the guards that read git."""
import hashlib
import json
import os
import subprocess
import sys
import unittest

from .gitrepo import RepoCase  # first: it puts tooling on sys.path

from practice_ci import __main__, cli, config  # noqa: E402
from practice_ci import git_objects as go  # noqa: E402
from practice_ci import scan_records  # noqa: E402
from practice_ci.guards import denylist, release_note, removed_paths, size  # noqa: E402

SALT = "salt"
TERM = "forbiddenword"


def deny(*terms):
    h = [hashlib.sha256((SALT + ":" + t).encode()).hexdigest() for t in terms]
    return json.dumps({"salt": SALT, "sha256": h})


WATCH = json.dumps(["consumer/", "spec/"])
ODD_NAMES = ['consumer/q"uote.json', "consumer/tab\there.json", "consumer/new\nline.json", "consumer/café.json"]


class ChangesAreExact(RepoCase):
    def test_name_status_keeps_both_rename_paths_and_odd_names(self):
        mb, head = self.base_and_head({"a b/oldé.txt": "x\n" * 5}, {})
        self.git("mv", "a b/oldé.txt", 'new"q\t.txt')
        head = self.commit("move")
        (c,) = go.diff_changes(mb, head, cwd=self.repo)
        self.assertEqual((c.status, c.old_path, c.path), ("R", "a b/oldé.txt", 'new"q\t.txt'))
        self.assertEqual(c.paths, ("a b/oldé.txt", 'new"q\t.txt'))

    def test_blob_read_by_object_id(self):
        _, head = self.base_and_head({}, {"f.bin": "a\0b"})
        oid = go.blob_oid(head, "f.bin", cwd=self.repo)
        self.assertEqual(go.read_blob(oid, cwd=self.repo), b"a\0b")


class WatchedPrefix61(RepoCase):
    def test_release_note_catches_each_odd_name_under_a_watched_prefix(self):
        for name in ODD_NAMES:
            with self.subTest(name=name):
                self.setUp()
                mb, head = self.base_and_head({"CHANGELOG.md": "# c\n"}, {name: "x\n"})
                env = {"MB": mb, "HEAD": head, "WATCH": WATCH, "CHANGELOG": "CHANGELOG.md", "MARKER": "Release: none"}
                cwd = os.getcwd()
                os.chdir(self.repo)
                try:
                    self.assertTrue(release_note.run(env).startswith("missing "), release_note.run(env))
                finally:
                    os.chdir(cwd)

    def test_removed_paths_finds_a_mention_of_an_odd_deleted_name(self):
        name = 'spec/q"uoteé.json'
        mb, _ = self.base_and_head({name: "{}\n", "README.md": "see x\n"}, {})
        os.remove(os.path.join(self.repo, name))
        self.write("README.md", "see %s here\n" % name)
        head = self.commit("remove")
        cwd = os.getcwd()
        os.chdir(self.repo)
        try:
            out = removed_paths.run({"MB": mb, "HEAD": head, "ROOT": self.repo, "HISTORY": "[]"})
        finally:
            os.chdir(cwd)
        self.assertTrue(out.startswith("referenced "), out)

    def test_size_counts_a_newline_name(self):
        mb, head = self.base_and_head({"a.txt": "a\n"}, {"x\ny.txt": "1\n2\n3\n"})
        cwd = os.getcwd()
        os.chdir(self.repo)
        try:
            out = size.run({"MB": mb, "HEAD": head, "LIMIT": "10", "FIXTURES": "[]"})
        finally:
            os.chdir(cwd)
        self.assertEqual(out, "ok 3 non-fixture lines (limit 10)")

    def test_removed_paths_finds_literal_newline_name_and_reports_start_lines(self):
        name = "spec/new\nline.json"
        mb, _ = self.base_and_head({name: "{}\n", "spec/keep.json": "{}\n"}, {})
        os.remove(os.path.join(self.repo, name))
        self.write("README.md", "References:\n%s\nagain %s here\n" % (name, name))
        head = self.commit("remove")
        cwd = os.getcwd()
        os.chdir(self.repo)
        try:
            out = removed_paths.run({"MB": mb, "HEAD": head, "ROOT": self.repo, "HISTORY": "[]"})
        finally:
            os.chdir(cwd)
        self.assertTrue(out.startswith("referenced "), out)
        self.assertEqual(json.loads(out.removeprefix("referenced ")), [
            {"path": name, "at": "README.md:2"},
            {"path": name, "at": "README.md:4"},
        ])


class InRepo(RepoCase):
    def run_in_repo(self, fn, env):
        cwd = os.getcwd()
        os.chdir(self.repo)
        try:
            return fn(env)
        finally:
            os.chdir(cwd)

    def test_denylist_catches_a_term_in_an_odd_file_name_and_its_lines(self):
        for name in ODD_NAMES:
            with self.subTest(name=name):
                self.setUp()
                mb, head = self.base_and_head({"a.txt": "a\n"}, {name.replace("consumer/", "consumer/%s-" % TERM): "x\n"})
                out = self.run_in_repo(denylist.run, {"DENY": deny(TERM), "MB": mb, "HEAD": head})
                self.assertTrue(out.startswith("found 1 added path"), out)

    def test_denylist_reads_a_line_of_an_odd_file_name(self):
        mb, head = self.base_and_head({"a.txt": "a\n"}, {'consumer/q"ué.json': "%s\n" % TERM})
        out = self.run_in_repo(denylist.run, {"DENY": deny(TERM), "MB": mb, "HEAD": head})
        self.assertEqual(out, 'found 1 consumer/q"ué.json:1')


class Nul70(RepoCase):
    def nul_commit(self, message):
        """A commit made by hand, since git refuses to write a NUL into a message."""
        tree = self.git("rev-parse", "HEAD^{tree}")
        parent = self.git("rev-parse", "HEAD")
        ident = b"unit <unit@example.invalid> 1700000000 +0000"
        body = (b"tree " + tree.encode() + b"\nparent " + parent.encode() + b"\nauthor " + ident
                + b"\ncommitter " + ident + b"\n\n" + message)
        oid = self.git("hash-object", "-t", "commit", "-w", "--literally", "--stdin", input=body)
        self.git("update-ref", "refs/heads/nul", oid)
        return oid

    def test_text_after_a_nul_is_scanned(self):
        self.write("a.txt", "a\n")
        mb = self.commit("base")
        head = self.nul_commit(b"subject\n\nfine\0 " + TERM.encode() + b"\n")
        out = self.run_in_repo(denylist.run, {"DENY": deny(TERM), "MB": mb, "HEAD": head})
        self.assertEqual(out, "found 1 commit " + head)

    def test_a_marker_line_after_a_nul_is_not_a_line(self):
        self.write("spec/x.json", "{}\n")
        mb = self.commit("base")
        self.write("spec/x.json", "{ }\n")
        self.git("add", "-A")
        tree = self.git("write-tree")
        ident = b"unit <unit@example.invalid> 1700000000 +0000"
        body = (b"tree " + tree.encode() + b"\nparent " + mb.encode() + b"\nauthor " + ident
                + b"\ncommitter " + ident + b"\n\nx\0\nRelease: none\n")
        head = self.git("hash-object", "-t", "commit", "-w", "--literally", "--stdin", input=body)
        env = {"MB": mb, "HEAD": head, "WATCH": WATCH, "CHANGELOG": "CHANGELOG.md", "MARKER": "Release: none"}
        out = self.run_in_repo(release_note.run, env)
        self.assertTrue(out.startswith("ok a commit message says"), out)

    def run_in_repo(self, fn, env):
        cwd = os.getcwd()
        os.chdir(self.repo)
        try:
            return fn(env)
        finally:
            os.chdir(cwd)


class RecordKind(RepoCase):
    def test_a_message_line_that_looks_like_a_row_cannot_hide_a_term(self):
        self.write("a.txt", "a\n")
        mb = self.commit("base")
        self.write("a.txt", "b\n")
        head = self.commit("subject\n\n::guard-commit::\n%s\n::guard-commit:: %s" % (TERM, TERM))
        records = scan_records.collect(mb, head, cwd=self.repo)
        messages = [r for r in records if r.kind == scan_records.MESSAGE]
        self.assertTrue(any(r.payload == "::guard-commit::" for r in messages))
        self.assertTrue(all(r.commit == head for r in messages))
        out = self.in_repo(denylist.run, {"DENY": deny(TERM), "MB": mb, "HEAD": head})
        self.assertEqual(out, "found 2 commit %s" % head)

    def test_a_payload_never_changes_its_kind(self):
        rec = scan_records.ScanRecord(scan_records.MESSAGE, commit="c" * 40, line=1, payload="author " + "a" * 40)
        self.assertEqual(rec.kind, scan_records.MESSAGE)
        self.assertEqual(rec.where(), "commit " + "c" * 40)

    def in_repo(self, fn, env):
        cwd = os.getcwd()
        os.chdir(self.repo)
        try:
            return fn(env)
        finally:
            os.chdir(cwd)


class Launcher(unittest.TestCase):
    def test_launcher_runs_every_guard_isolated_and_prints_one_plain_line(self):
        launcher = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), config.get("tooling", "launcher"))
        done = subprocess.run([sys.executable, "-I", launcher, "denylist"], env={"DENY": ""}, stdout=subprocess.PIPE, cwd="/")
        self.assertTrue(done.stdout.startswith(b"unguarded "), done.stdout)
        self.assertEqual(done.stdout.count(b"\n"), 1)
        self.assertEqual(done.returncode, 0)

    def test_every_guard_is_a_launcher_command(self):
        self.assertEqual(set(cli.GUARDS), {"denylist", "removed-paths", "release-note", "size"})
        self.assertTrue(set(cli.GUARDS) <= set(__main__.commands()))

    def test_no_script_or_template_names_the_removed_runner(self):
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.assertFalse(os.path.exists(os.path.join(root, "tooling", "run_practice_ci.py")))
        for top in ("templates", "scripts", "policy"):
            for where, _, names in os.walk(os.path.join(root, top)):
                for name in names:
                    with open(os.path.join(where, name), encoding="utf-8", errors="ignore") as f:
                        text = f.read()
                    with self.subTest(file=os.path.join(where, name)):
                        self.assertNotIn("run_practice_ci", text)
                        self.assertNotIn("runnerScript", text)
                        self.assertNotIn("core track adds the launcher", text)


if __name__ == "__main__":
    unittest.main()
