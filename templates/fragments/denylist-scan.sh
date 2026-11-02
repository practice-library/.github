# main: prints "ok ...", "found <n> <where>...", "unguarded ..." or "invalid ..."; the term itself is
# never printed. The scan is tooling/practice_ci/guards/denylist.py, which reads git as bytes (names,
# quoted paths and commit messages with a NUL are exact) and judges typed records.
# Inputs: DENY (JSON, see the module), EVENT, TEXT_FILE (rows "<where><TAB><text>") or MB and HEAD.
# @@git.runnerEnv@@ is the launcher (scripts/practice-ci) of the checkout that holds the tooling.
main() {
  python3 -I "${@@git.runnerEnv@@:-@@tooling.launcher@@}" denylist
}
