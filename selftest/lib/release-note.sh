# Generated from templates/selftest/lib/release-note.sh and policy/constants.json by scripts/render.sh. Do not edit.
# main: prints "ok ...", "missing ..." or "invalid ...". The guard is
# tooling/practice_ci/guards/release_note.py (inputs in its docstring): the changed paths (both paths of
# a rename, exact) and the commit messages (every byte) are read from git for MB..HEAD when CHANGED and
# MESSAGES are unset.
# TODO: call scripts/practice-ci release-note once the core track adds the launcher.
main() {
  python3 -I "${PRACTICE_CI_RUNNER:-tooling/run_practice_ci.py}" release-note
}
