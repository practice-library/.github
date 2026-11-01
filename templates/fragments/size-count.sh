# main: prints "ok <n> non-fixture lines (limit <L>)", "over <n> non-fixture lines, more than <L>: split the
# pull request" or "invalid ...". The guard is tooling/practice_ci/guards/size.py (inputs in its
# docstring): when NUMSTAT is unset the counts are read from git for MB..HEAD with exact paths.
# TODO: call scripts/practice-ci size once the core track adds the launcher.
main() {
  python3 -I "${@@git.runnerEnv@@:-@@git.runnerScript@@}" size
}
