# Generated from templates/selftest/lib/denylist-scan.sh and policy/constants.json by scripts/render.sh. Do not edit.
# main: prints "ok ...", "found <n> <where>...", "unguarded ..." or "invalid ..."; the term itself is
# never printed. The scan is tooling/practice_ci/guards/denylist.py, which reads git as bytes (names,
# quoted paths and commit messages with a NUL are exact) and judges typed records.
# Inputs: DENY (JSON, see the module), EVENT, TEXT_FILE (rows "<where><TAB><text>") or MB and HEAD.
# TODO: call scripts/practice-ci denylist once the core track adds the launcher.
main() {
  python3 -I "${PRACTICE_CI_RUNNER:-tooling/run_practice_ci.py}" denylist
}
