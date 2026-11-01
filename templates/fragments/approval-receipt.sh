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
  PYTHONPATH="$TOOLING" python3 -m practice_ci.approvals --repo "$REPO" --pr "$NUMBER" --kind "$KIND" --head "$HEAD" || true
}
