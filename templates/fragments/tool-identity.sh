# main: judges the identity of the workflow that defines the running job, before anything is checked
# out with it. Prints "ok <repository>@<sha>" when both are usable, otherwise "invalid <why>". Nothing
# is defaulted: actions/checkout reads an empty repository as the caller and an empty ref as the default
# branch, so an empty or malformed identity must stop the job here instead of selecting other code.
#   WORKFLOW_REPOSITORY  job.workflow_repository: owner/name
#   WORKFLOW_SHA         job.workflow_sha: the full commit, 40 lower-case hex characters
main() {
  local repo="${WORKFLOW_REPOSITORY:-}" sha="${WORKFLOW_SHA:-}"
  if [ -z "$repo" ]; then echo "invalid job.workflow_repository is empty (this needs GitHub.com)"; return 0; fi
  if ! [[ "$repo" =~ ^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$ ]] || [[ "$repo" == */. ]] || [[ "$repo" == */.. ]]; then
    echo "invalid job.workflow_repository is not owner/name"; return 0
  fi
  if [ -z "$sha" ]; then echo "invalid job.workflow_sha is empty (this needs GitHub.com)"; return 0; fi
  if ! [[ "$sha" =~ ^[0-9a-f]{40}$ ]]; then echo "invalid job.workflow_sha is not 40 lower-case hex characters"; return 0; fi
  echo "ok $repo@$sha"
}
