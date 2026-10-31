#!/usr/bin/env bash
# Runs the denylist step of the guard workflow, as callers get it, on throwaway repositories that hold a
# simulated maintainer merge made in the browser (authored by the maintainer, committed by GitHub) and
# the cases around it. The step's own script is taken from the workflow file, so a change to its glue
# (events, the base-commit list, which rows are judged, the exemption) is caught here before it can turn
# main red. The rendered file is what callers run; with no argument the canary first runs
# scripts/render.sh --check, so the copy it exercises is exactly the render of
# templates/.github/workflows/guard.yml and the fragments it includes.
# One scenario uses this repository's own list and the author of the merge commit that first turned
# main red (MAINTAINER_MERGE), read from history; the name is never printed.
# The canary term is made up and salted afresh; no output names a term or a name.
# Usage: scripts/denylist-canary.sh [guard.yml]   (a file argument skips the render check)
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIST=.github/denylist.json
MAINTAINER_MERGE=3267684c2fbf40a655a64942437e806423cce9fb
if [ $# -eq 0 ]; then
  bash "$root/scripts/render.sh" --check > /dev/null \
    || { echo "FAIL the rendered workflows are not the render of templates/ (scripts/render.sh --check)"; exit 1; }
fi
workflow="${1:-$root/.github/workflows/guard.yml}"

# The run block of the step named denylist, without its indentation.
step="$(awk '
  /^      - name: / { in_step = ($0 == "      - name: denylist"); next }
  in_step && /^        run: \|$/ { in_run = 1; next }
  in_run && $0 != "" && match($0, /^ */) && RLENGTH < 10 { exit }
  in_run { sub(/^          /, ""); print }' "$workflow")"
[ -n "$step" ] || { echo "FAIL no denylist step in $workflow"; exit 1; }
# The step must get the event from GitHub; the scenarios below set EVENT themselves.
awk '
  /^      - name: / { in_step = ($0 == "      - name: denylist"); next }
  in_step && /^        run: / { exit 1 }
  in_step && $0 == "          EVENT: ${{ github.event_name }}" { found = 1; exit 0 }
  END { exit !found }' "$workflow" || { echo "FAIL the denylist step does not set EVENT from github.event_name"; exit 1; }

salt="canary-$RANDOM-$RANDOM-$$"
hash() { printf '%s' "$salt:$1" | python3 -I -c 'import hashlib, sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())'; }
term="$(hash zebracorn)"
plain="{\"salt\":\"$salt\",\"sha256\":[\"$term\"]}"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
# The maintainer's name is three words holding the term; its exemption comes from the hash tool itself.
maintainer="Zebracorn Account Name"
printf '%s\n' "$plain" > "$work/list.json"
allow="$(printf '%s\n' "$maintainer" | bash "$root/scripts/denylist-hash.sh" --names "$work/list.json")" \
  || { echo "FAIL scripts/denylist-hash.sh --names did not hash a three-word name"; exit 1; }
exempt="{\"salt\":\"$salt\",\"sha256\":[\"$term\"],\"allowAuthorNames\":[\"$allow\"]}"
failed=0

# scenario <name> <want 0|1> <event> <list or "" for none on base> <author> <message> <added line> <merge author or "">
# Optional, set for one call: HEAD_LIST (the list the head commit writes), FILE (the file the head commit
# adds, default notes.md), MERGE_COMMITTER (default GitHub), MERGE_MESSAGE.
scenario() {
  local name="$1" want="$2" event="$3" list="$4" author="$5" message="$6" line="$7" merger="$8" repo got out
  repo="$(mktemp -d "$work/r.XXXXXX")"
  git -C "$repo" init -q
  mkdir -p "$repo/.github"
  if [ -n "$list" ]; then printf '%s\n' "$list" > "$repo/$LIST"; fi
  printf 'Base.\n' > "$repo/README.md"
  git -C "$repo" add -A
  git -C "$repo" -c user.name=base -c user.email=base@example.invalid -c commit.gpgsign=false commit -q -m base
  local base; base="$(git -C "$repo" rev-parse HEAD)"
  printf '%s\n' "$line" > "$repo/${FILE:-notes.md}"
  if [ -n "${HEAD_LIST:-}" ]; then printf '%s\n' "$HEAD_LIST" > "$repo/$LIST"; fi
  git -C "$repo" add -A
  git -C "$repo" -c user.name="$author" -c user.email=a@example.invalid -c commit.gpgsign=false commit -q -m "$message"
  local head; head="$(git -C "$repo" rev-parse HEAD)"
  if [ -n "$merger" ]; then
    git -C "$repo" checkout -q --detach "$base"
    GIT_AUTHOR_NAME="$merger" GIT_AUTHOR_EMAIL=m@example.invalid \
      GIT_COMMITTER_NAME="${MERGE_COMMITTER:-GitHub}" GIT_COMMITTER_EMAIL=noreply@example.invalid \
      git -C "$repo" -c commit.gpgsign=false merge -q --no-ff \
      -m "${MERGE_MESSAGE:-Merge pull request #1 from example/notes}" "$head"
    head="$(git -C "$repo" rev-parse HEAD)"
  fi
  got=0
  out="$(cd "$repo" && NONE=false BASE="$base" MB="$base" HEAD="$head" LIST="$LIST" EVENT="$event" bash -c "$step" 2>&1)" || got=$?
  [ "$got" -eq 0 ] || got=1
  if [ "$got" = "$want" ]; then
    echo "ok   $name: ${out##*$'\n'}"
  else
    echo "FAIL $name: want exit $want, got $got: ${out##*$'\n'}"
    failed=$((failed + 1))
  fi
}

scenario push-maintainer-merge 0 push "$plain" "Contributor" "Add notes" "Clean notes." "$maintainer"
scenario push-maintainer-merge-exempt 0 push "$exempt" "Contributor" "Add notes" "Clean notes." "$maintainer"
scenario pull-request-maintainer-commit-exempt 0 pull_request "$exempt" "$maintainer" "Add notes" "Clean notes." ""
scenario push-maintainer-commit-exempt 0 push "$exempt" "$maintainer" "Add notes" "Clean notes." ""
scenario pull-request-maintainer-commit 1 pull_request "$plain" "$maintainer" "Add notes" "Clean notes." ""
scenario push-denied-author 1 push "$plain" "$maintainer" "Add notes" "Clean notes." ""
scenario exempt-author-other-name 1 pull_request "$exempt" "Zebracorn" "Add notes" "Clean notes." ""
scenario exempt-author-name-in-message 1 pull_request "$exempt" "$maintainer" "$maintainer" "Clean notes." ""
scenario exempt-author-name-in-line 1 pull_request "$exempt" "$maintainer" "Add notes" "$maintainer" ""
scenario push-merge-term-in-line 1 push "$exempt" "Contributor" "Add notes" "Zebracorn" "$maintainer"
# A merge commit pushed directly is judged by its message and committer.
MERGE_MESSAGE="Merge notes from Zebracorn" scenario push-merge-term-in-message 1 push "$exempt" "Contributor" "Add notes" "Clean notes." "$maintainer"
MERGE_COMMITTER="Zebracorn" scenario push-merge-denied-committer 1 push "$exempt" "Contributor" "Add notes" "Clean notes." "Contributor"
# The list is read from the base commit: a change cannot exempt its own author.
HEAD_LIST="$exempt" scenario head-adds-own-exemption 1 pull_request "$plain" "$maintainer" "Add notes" "Clean notes." ""
HEAD_LIST="$exempt" scenario head-adds-own-exemption-push 1 push "$plain" "$maintainer" "Add notes" "Clean notes." ""
# With no list on the base, the change that adds the first list is checked with it.
HEAD_LIST="$plain" scenario first-list-clean 0 pull_request "" "Contributor" "Add notes" "Clean notes." ""
HEAD_LIST="$plain" scenario first-list-term-in-line 1 pull_request "" "Contributor" "Add notes" "Zebracorn" ""
# A file whose name looks like a name row is still content.
FILE="author 0123456789abcdef0123456789abcdef01234567" scenario file-named-like-author-row 1 pull_request "$exempt" "$maintainer" "Add notes" "$maintainer" ""
FILE="committer 0123456789abcdef0123456789abcdef01234567" scenario file-named-like-committer-row 1 pull_request "$exempt" "$maintainer" "Add notes" "$maintainer" ""

# This repository's own list and the maintainer who merged in the browser: a non-merge commit by them on
# push is green, and only because of the exemption (without it, the same commit is red).
real="$(git -C "$root" log -1 --format=%an "$MAINTAINER_MERGE" 2> /dev/null)" \
  || { echo "FAIL cannot read $MAINTAINER_MERGE from history (the checkout needs fetch-depth 0)"; exit 1; }
own="$(jq -c . "$root/$LIST")" || { echo "FAIL cannot read $LIST"; exit 1; }
jq -e '.allowAuthorNames | length > 0' <<< "$own" > /dev/null || { echo "FAIL $LIST has no allowAuthorNames"; failed=$((failed + 1)); }
scenario registered-maintainer-push-commit 0 push "$own" "$real" "Add notes" "Clean notes." ""
scenario registered-maintainer-push-merge 0 push "$own" "Contributor" "Add notes" "Clean notes." "$real"
scenario registered-maintainer-unexempt 1 push "$(jq -c 'del(.allowAuthorNames)' <<< "$own")" "$real" "Add notes" "Clean notes." ""
echo "$failed failed"
[ "$failed" -eq 0 ]
