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
# A stand-in for gh: it prints the label events the scenario sets in GH_EVENTS, as the step's --jq would.
mkdir -p "$work/bin"
printf '#!/bin/sh\nprintf "%%s\\n" "${GH_EVENTS:-}"\n' > "$work/bin/gh"
chmod +x "$work/bin/gh"
# The maintainer's name is three words holding the term; its exemption comes from the hash tool itself.
maintainer="Zebracorn Account Name"
printf '%s\n' "$plain" > "$work/list.json"
allow="$(printf '%s\n' "$maintainer" | bash "$root/scripts/denylist-hash.sh" --names "$work/list.json")" \
  || { echo "FAIL scripts/denylist-hash.sh --names did not hash a three-word name"; exit 1; }
exempt="{\"salt\":\"$salt\",\"sha256\":[\"$term\"],\"allowAuthorNames\":[\"$allow\"]}"
failed=0

# scenario <name> <want 0|1> <event> <list or "" for none on base> <author> <message> <added line> <merge author or "">
# Optional, set for one call: HEAD_LIST (the list the head commit writes), FILE (the file the head commit
# adds, default notes.md), MERGE_COMMITTER (default GitHub), MERGE_MESSAGE, and for the exemption label
# NUMBER (a pull request number; empty means not a pull request), LABELS (JSON, default []) and
# GH_EVENTS (the label events, "<login><TAB><type>" lines). MOVE_FROM puts the line in that file on the
# base and has the head commit move it to FILE (git mv) instead of adding the line. BASE_AFTER_LIST writes
# that list on the base line after the head branched (DELETE_LIST=1 has the head commit delete the list), so BASE moves on while MB stays where it branched.
scenario() {
  local name="$1" want="$2" event="$3" list="$4" author="$5" message="$6" line="$7" merger="$8" repo got out
  repo="$(mktemp -d "$work/r.XXXXXX")"
  git -C "$repo" init -q
  mkdir -p "$repo/.github"
  if [ -n "$list" ]; then printf '%s\n' "$list" > "$repo/$LIST"; fi
  printf 'Base.\n' > "$repo/README.md"
  if [ -n "${MOVE_FROM:-}" ]; then mkdir -p "$(dirname "$repo/$MOVE_FROM")"; printf '%s\n' "$line" > "$repo/$MOVE_FROM"; fi
  git -C "$repo" add -A
  git -C "$repo" -c user.name=base -c user.email=base@example.invalid -c commit.gpgsign=false commit -q -m base
  local base; base="$(git -C "$repo" rev-parse HEAD)"
  mkdir -p "$(dirname "$repo/${FILE:-notes.md}")"
  if [ -n "${MOVE_FROM:-}" ]; then git -C "$repo" mv "$MOVE_FROM" "${FILE:-notes.md}"
  else printf '%s\n' "$line" > "$repo/${FILE:-notes.md}"; fi
  if [ -n "${HEAD_LIST:-}" ]; then printf '%s\n' "$HEAD_LIST" > "$repo/$LIST"; fi
  if [ -n "${DELETE_LIST:-}" ]; then git -C "$repo" rm -q "$LIST"; fi
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
  local tip="$base"
  if [ -n "${BASE_AFTER_LIST:-}" ]; then
    git -C "$repo" checkout -q --detach "$base"
    printf '%s\n' "$BASE_AFTER_LIST" > "$repo/$LIST"
    git -C "$repo" add -A
    git -C "$repo" -c user.name=base -c user.email=base@example.invalid -c commit.gpgsign=false commit -q -m "base moves on"
    tip="$(git -C "$repo" rev-parse HEAD)"
  fi
  got=0
  out="$(cd "$repo" && NONE=false BASE="$tip" MB="$base" HEAD="$head" LIST="$LIST" EVENT="$event" \
    LABEL=schema-loosening-approved LABELS="${LABELS:-[]}" AUTHOR=contributor NUMBER="${NUMBER:-}" \
    REPO=example/repo GH_TOKEN=unused GH_EVENTS="${GH_EVENTS:-}" PATH="$work/bin:$PATH" bash -c "$step" 2>&1)" || got=$?
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

# Path exemptions: a listed term in a quoted data tree passes; the same term anywhere else does not.
tree="{\"salt\":\"$salt\",\"sha256\":[\"$term\"],\"exemptPaths\":[{\"glob\":\"vendors/*/graph/nodes/**\"}]}"
FILE=vendors/acme/graph/nodes/a.json scenario exempt-term-in-tree 0 pull_request "$tree" "Contributor" "Add a node" "Zebracorn quoted." ""
FILE=docs/a.md scenario exempt-term-outside-tree 1 pull_request "$tree" "Contributor" "Add notes" "Zebracorn quoted." ""
FILE=vendors/zebracorn/graph/nodes/a.json scenario exempt-term-in-path 1 pull_request "$tree" "Contributor" "Add a node" "Clean." ""
FILE=vendors/acme/graph/nodes/a.json scenario exempt-term-in-message 1 pull_request "$tree" "Contributor" "Quote Zebracorn" "Clean." ""
# A file moved out of the tree is read whole at its new path, so the quoted term is found there.
MOVE_FROM=vendors/acme/graph/nodes/a.json FILE=docs/a.md scenario exempt-renamed-out 1 pull_request "$tree" "Contributor" "Move a node" "Zebracorn quoted." ""
MOVE_FROM=vendors/acme/graph/nodes/a.json FILE=vendors/beta/graph/nodes/a.json scenario exempt-renamed-within 0 pull_request "$tree" "Contributor" "Move a node" "Zebracorn quoted." ""
# A carriage return inside a line cannot forge a row that names the exempt tree.
FILE=docs/a.md scenario exempt-cr-forged-row 1 pull_request "$tree" "Contributor" "Add notes" "$(printf 'Harmless.\rvendors/acme/graph/nodes/a.json:1\tZebracorn here.')" ""
# An exemption never applies to the change that adds it: not to a list on the base, nor to a first list.
HEAD_LIST="$tree" FILE=vendors/acme/graph/nodes/a.json scenario exempt-added-by-change 1 pull_request "$plain" "Contributor" "Add a node" "Zebracorn quoted." ""
HEAD_LIST="$tree" FILE=vendors/acme/graph/nodes/a.json scenario exempt-in-first-list 1 pull_request "" "Contributor" "Add a node" "Zebracorn quoted." ""
# Adding or widening an exemption needs the label from someone other than the author and not a bot.
HEAD_LIST="$tree" NUMBER=1 scenario exempt-widened-no-label 1 pull_request "$plain" "Contributor" "Add an exemption" "Clean." ""
HEAD_LIST="$tree" NUMBER=1 LABELS='["schema-loosening-approved"]' GH_EVENTS="maintainer	User" scenario exempt-widened-labelled 0 pull_request "$plain" "Contributor" "Add an exemption" "Clean." ""
HEAD_LIST="$tree" NUMBER=1 LABELS='["schema-loosening-approved"]' GH_EVENTS="contributor	User" scenario exempt-widened-self-labelled 1 pull_request "$plain" "Contributor" "Add an exemption" "Clean." ""
HEAD_LIST="$tree" NUMBER=1 LABELS='["schema-loosening-approved"]' GH_EVENTS="helper[bot]	Bot" scenario exempt-widened-bot-labelled 1 pull_request "$plain" "Contributor" "Add an exemption" "Clean." ""
HEAD_LIST="$tree" scenario exempt-widened-push 0 push "$plain" "Contributor" "Add an exemption" "Clean." ""
HEAD_LIST="$plain" NUMBER=1 scenario exempt-removed 0 pull_request "$tree" "Contributor" "Drop the exemption" "Clean." ""
HEAD_LIST="{" NUMBER=1 scenario exempt-head-list-unreadable 1 pull_request "$tree" "Contributor" "Break the list" "Clean." ""
# Widening is judged against the base as it is now: an exemption the base dropped after the change branched
# would come back with the merge, so it needs the label like any added entry.
BASE_AFTER_LIST="$plain" NUMBER=1 scenario exempt-base-dropped-since 1 pull_request "$tree" "Contributor" "Add notes" "Clean." ""
two="{\"salt\":\"$salt\",\"sha256\":[\"$term\"],\"exemptPaths\":[{\"glob\":\"docs/a.md\"},{\"glob\":\"vendors/*/graph/nodes/**\"}]}"
moved="{\"salt\":\"$salt\",\"sha256\":[\"$term\"],\"exemptPaths\":[{\"glob\":\"vendors/*/graph/nodes/**\"},{\"glob\":\"docs/a.md\"}]}"
left="{\"salt\":\"$salt\",\"sha256\":[\"$term\"],\"exemptPaths\":[{\"glob\":\"docs/a.md\"}]}"
HEAD_LIST="$moved" BASE_AFTER_LIST="$left" NUMBER=1 scenario exempt-moved-then-dropped-on-base 1 pull_request "$two" "Contributor" "Reorder" "Clean." ""
HEAD_LIST="{" scenario exempt-head-list-unreadable-push 1 push "$tree" "Contributor" "Break the list" "Clean." ""

# The list a change writes is the one the next change is judged with: it must be digests only and not empty.
HEAD_LIST="{\"salt\":\"$salt\",\"sha256\":[\"$term\",\"bogus\"]}" scenario head-list-not-digests 1 pull_request "$plain" "Contributor" "Edit the list" "Clean." ""
HEAD_LIST="{\"salt\":\"$salt\",\"sha256\":[]}" scenario head-list-emptied 1 pull_request "$plain" "Contributor" "Empty the list" "Clean." ""
DELETE_LIST=1 scenario head-list-deleted 1 pull_request "$plain" "Contributor" "Delete the list" "Clean." ""
DELETE_LIST=1 BASE_AFTER_LIST="$tree" scenario head-list-deleted-base-moved 1 pull_request "$plain" "Contributor" "Delete the list" "Clean." ""
BASE_AFTER_LIST="$plain" scenario base-gained-list-after-branch 0 pull_request "" "Contributor" "Add notes" "Clean." ""
HEAD_LIST="{\"salt\":\"$salt\",\"sha256\":[\"$term\",\"$(hash quokka)\"]}" scenario head-list-grows 0 pull_request "$plain" "Contributor" "Add an entry" "Clean." ""
# The hash tool refuses a list that is not digests, so its output is never appended to a broken list.
# A digest with a final newline is one too: jq's $ matches before it, so the tool anchors with \z.
for bad in "not-a-digest|\"sha256\":[\"bogus\"]" "digest-newline|\"sha256\":[\"$term\\n\"]" \
           "name-newline|\"sha256\":[],\"allowAuthorNames\":[\"$term\\n\"]" "name-null|\"sha256\":[],\"allowAuthorNames\":null"; do
  printf '%s\n' "{\"salt\":\"$salt\",${bad#*|}}" > "$work/bad.json"
  if printf 'zebracorn\n' | bash "$root/scripts/denylist-hash.sh" "$work/bad.json" > /dev/null 2>&1; then
    echo "FAIL denylist-hash.sh accepted a list that is not digests: ${bad%%|*}"; failed=$((failed + 1))
  else echo "ok   denylist-hash.sh refuses a list that is not digests: ${bad%%|*}"; fi
done

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
