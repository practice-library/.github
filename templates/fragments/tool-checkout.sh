# main: judges the tooling checkout before anything in it runs. Prints "ok <sha>" when the repository in
# TOOLING is at exactly WORKFLOW_SHA and holds the launcher; "mismatch ..." when HEAD is another commit;
# "bootstrap ..." when that commit has no launcher (a commit from before the tooling existed: pin a
# release that ships it, nothing is fetched from elsewhere); "invalid ..." when TOOLING is no repository.
#   TOOLING       the directory the workflow's own commit was checked out into
#   WORKFLOW_SHA  job.workflow_sha
#   LAUNCHER      the launcher's path inside TOOLING
main() {
  local head
  if ! head="$(git -C "${TOOLING:-}" rev-parse --verify --quiet HEAD^{commit} 2>/dev/null)"; then
    echo "invalid ${TOOLING:-(unset)} is not a checked-out repository"; return 0
  fi
  if [ "$head" != "${WORKFLOW_SHA:-}" ]; then
    echo "mismatch the tooling checkout is at $head, not job.workflow_sha ${WORKFLOW_SHA:-(unset)}"; return 0
  fi
  if [ -z "${LAUNCHER:-}" ] || [ ! -f "$TOOLING/$LAUNCHER" ]; then
    echo "bootstrap $head has no ${LAUNCHER:-launcher}: this commit predates the tooling, so pin a release that ships it"; return 0
  fi
  echo "ok $head"
}
