# main: prints "ok ..." or "referenced [{path, at}, ...]" or "invalid ...". The guard is
# tooling/practice_ci/guards/removed_paths.py (inputs in its docstring): the removed paths (both paths of a
# rename, exact) are read from git for MB..HEAD when DELETED is unset.
# @@git.runnerEnv@@ is the launcher (scripts/practice-ci) of the checkout that holds the tooling.
main() {
  python3 -I "${@@git.runnerEnv@@:-@@tooling.launcher@@}" removed-paths
}
