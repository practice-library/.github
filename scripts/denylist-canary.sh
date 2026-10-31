#!/usr/bin/env bash
# Runs the denylist step of the rendered guard workflow, as callers get it, on throwaway repositories that
# hold a simulated maintainer merge made in the browser (authored by the maintainer, committed by GitHub)
# and the cases around it. The step's own script is taken from the workflow file, so a change to its glue
# (events, which commits are judged, the exemption) is caught here before it can turn main red.
# The canary term is made up and salted afresh; no output names a term.
# Usage: scripts/denylist-canary.sh [guard.yml]   (default .github/workflows/guard.yml)
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workflow="${1:-$root/.github/workflows/guard.yml}"
LIST=.github/denylist.json

# The run block of the step named denylist, without its indentation.
step="$(awk '
  /^      - name: / { in_step = ($0 == "      - name: denylist"); next }
  in_step && /^        run: \|$/ { in_run = 1; next }
  in_run && $0 != "" && match($0, /^ */) && RLENGTH < 10 { exit }
  in_run { sub(/^          /, ""); print }' "$workflow")"
[ -n "$step" ] || { echo "no denylist step in $workflow"; exit 1; }
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
exempt="{\"salt\":\"$salt\",\"sha256\":[\"$term\"],\"allowAuthorNames\":[\"$term\"]}"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
failed=0

# scenario <name> <want 0|1> <event> <list> <author> <message> <added line> <merge author or "">
scenario() {
  local name="$1" want="$2" event="$3" list="$4" author="$5" message="$6" line="$7" merger="$8" repo got
  repo="$(mktemp -d "$work/r.XXXXXX")"
  git -C "$repo" init -q
  mkdir -p "$repo/.github"
  printf '%s\n' "$list" > "$repo/$LIST"
  printf 'Base.\n' > "$repo/README.md"
  git -C "$repo" add -A
  git -C "$repo" -c user.name=base -c user.email=base@example.invalid -c commit.gpgsign=false commit -q -m base
  local base; base="$(git -C "$repo" rev-parse HEAD)"
  printf '%s\n' "$line" > "$repo/notes.md"
  git -C "$repo" add -A
  git -C "$repo" -c user.name="$author" -c user.email=a@example.invalid -c commit.gpgsign=false commit -q -m "$message"
  local head; head="$(git -C "$repo" rev-parse HEAD)"
  if [ -n "$merger" ]; then
    git -C "$repo" checkout -q --detach "$base"
    GIT_AUTHOR_NAME="$merger" GIT_AUTHOR_EMAIL=m@example.invalid GIT_COMMITTER_NAME=GitHub GIT_COMMITTER_EMAIL=noreply@example.invalid \
      git -C "$repo" -c commit.gpgsign=false merge -q --no-ff -m "Merge pull request #1 from example/notes" "$head"
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

scenario push-maintainer-merge 0 push "$plain" "Contributor" "Add notes" "Clean notes." "Zebracorn"
scenario push-maintainer-merge-exempt 0 push "$exempt" "Contributor" "Add notes" "Clean notes." "Zebracorn"
scenario pull-request-maintainer-commit-exempt 0 pull_request "$exempt" "Zebracorn" "Add notes" "Clean notes." ""
scenario push-maintainer-commit-exempt 0 push "$exempt" "Zebracorn" "Add notes" "Clean notes." ""
scenario pull-request-maintainer-commit 1 pull_request "$plain" "Zebracorn" "Add notes" "Clean notes." ""
scenario push-denied-author 1 push "$plain" "Zebracorn" "Add notes" "Clean notes." ""
scenario exempt-author-term-in-message 1 pull_request "$exempt" "Zebracorn" "Zebracorn" "Clean notes." ""
scenario exempt-author-term-in-line 1 pull_request "$exempt" "Zebracorn" "Add notes" "Zebracorn" ""
scenario push-merge-term-in-line 1 push "$exempt" "Contributor" "Add notes" "Zebracorn" "Zebracorn"
echo "$failed failed"
[ "$failed" -eq 0 ]
