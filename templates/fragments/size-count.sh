# main: prints "ok <n> non-fixture lines (limit <L>)", "over <n> non-fixture lines, more than <L>: split the
# pull request" or "invalid ...". The guard is tooling/practice_ci/guards/size.py (inputs in its
# docstring): when NUMSTAT is unset the counts are read from git for MB..HEAD with exact paths.
# @@git.runnerEnv@@ is the launcher (scripts/practice-ci) of the checkout that holds the tooling.
main() {
  python3 -I "${@@git.runnerEnv@@:-@@tooling.launcher@@}" size
}
