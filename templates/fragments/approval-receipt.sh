# main: prints one line, "ok approved by <login> at <head>", "missing ..." (no review approves the head) or
# "refused ..." (an approval that does not count, a moved head, or an unreadable answer). The verdict is
# an APPROVED review at the pull request's exact head by a maintainer or admin who is neither the author
# nor a bot (tooling/practice_ci/approvals.py); a label is only a trigger to run again, never the proof.
#   TOOLING  directory holding the practice_ci package
#   REPO     owner/name
#   NUMBER   the pull request number
#   KIND     what is being approved (one of approvals.kinds)
#   HEAD     the head this run judges; a pull request that has moved on is refused
#   GH_TOKEN token that can read pull requests
main() {
  # TOOLING is the trusted checkout, never the PR working directory. Isolated mode
  # ignores PYTHONPATH and user site/startup hooks; add only the trusted package root.
  (cd -- "$TOOLING" && python3 -I -c 'import os, runpy, sys; sys.path.insert(0, os.getcwd()); runpy.run_module("practice_ci.approvals", run_name="__main__")' --repo "$REPO" --pr "$NUMBER" --kind "$KIND" --head "$HEAD") || true
}
