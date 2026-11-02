# main: prints "ok ...", "missing ..." or "invalid ...". The guard is
# tooling/practice_ci/guards/release_note.py (inputs in its docstring): the changed paths (both paths of
# a rename, exact) and the commit messages (every byte) are read from git for MB..HEAD when CHANGED and
# MESSAGES are unset.
# @@git.runnerEnv@@ is the launcher (scripts/practice-ci) of the checkout that holds the tooling.
main() {
  python3 -I "${@@git.runnerEnv@@:-@@tooling.launcher@@}" release-note
}
