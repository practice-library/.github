"""A throwaway git repository for the tests."""
import os
import subprocess
import sys
import tempfile
import unittest

# The tests run as tooling.tests.* (discover -t .), the modules import as practice_ci.*.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class RepoCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = self._tmp.name
        self.git("init", "-q")
        self.git("config", "user.name", "unit")
        self.git("config", "user.email", "unit@example.invalid")
        self.git("config", "commit.gpgsign", "false")

    def git(self, *args, input=None):
        done = subprocess.run(["git", *args], cwd=self.repo, input=input, stdout=subprocess.PIPE, check=True)
        return done.stdout.decode("utf-8", "surrogateescape").strip()

    def write(self, path, text):
        full = os.path.join(self.repo, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(text)

    def commit(self, message="change"):
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD")

    def base_and_head(self, base_files, head_files, message="change"):
        for p, t in base_files.items():
            self.write(p, t)
        mb = self.commit("base")
        for p, t in head_files.items():
            self.write(p, t)
        return mb, self.commit(message)
