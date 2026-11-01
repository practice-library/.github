# Generated from templates/selftest/lib/removed-refs.sh and policy/constants.json by scripts/render.sh. Do not edit.
# main: prints "ok ..." or "referenced [{path, at}, ...]" or "invalid ...". The guard is
# tooling/practice_ci/guards/removed_paths.py (inputs in its docstring): the removed paths (both paths of a
# rename, exact) are read from git for MB..HEAD when DELETED is unset.
# TODO: call scripts/practice-ci removed-paths once the core track adds the launcher.
main() {
  python3 -I "${PRACTICE_CI_RUNNER:-tooling/run_practice_ci.py}" removed-paths
}
