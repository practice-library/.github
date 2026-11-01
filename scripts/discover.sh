#!/usr/bin/env bash
# For every row of `checks` in policy/constants.json, prints two GITHUB_OUTPUT lines:
#   targets-<check>=  what the check runs on: one entry per <dir>/<targetFile> found in the repository
#                     (its inputs, with paths made relative to the repository root), or a single
#                     repository-wide entry when the row has no targetFile;
#   fixtures-<check>= the self-test fixtures that exercise it.
# Fails when a check has no target or no fixture, or a fixture names a check that does not exist.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
constants="$root/policy/constants.json"
fixtures_dir="$(jq -er '.selftest.fixturesDir' "$constants")"
case_file="$(jq -er '.selftest.caseFile' "$constants")"
cd "$root"
lib="$root/$(jq -er '.render.fragmentsDir' "$constants")/discover-targets.sh"

cases="$(
  for d in "$fixtures_dir"/*/; do
    name="$(basename "$d")"
    jq -c --arg n "$name" '
      if (.check | type) != "string" then error($n + ": check is missing")
      elif (.expect == "error" and .check == "schema-check") then {fixture: $n} + del(.files, .base_files, .plant)
      elif (.expect != "pass" and .expect != "fail") then error($n + ": expect must be pass or fail (or error, for a schema-check setup error)")
      else {fixture: $n} + del(.files, .base_files, .plant) end' "$d/$case_file"
  done | jq -sc '.'
)"

unknown="$(jq -c --slurpfile c "$constants" '[.[].check] - [$c[0].checks[].id] | unique' <<<"$cases")"
[ "$unknown" = "[]" ] || { echo "fixtures name checks that do not exist: $unknown" >&2; exit 1; }

while IFS= read -r row; do
  id="$(jq -r '.id' <<<"$row")"
  result="$(ROW="$row" EXCLUDE="^$fixtures_dir/" bash -c 'source "$1"; main' _ "$lib")"
  [ "${result%% *}" = ok ] || { echo "$id: ${result#* }" >&2; exit 1; }
  targets="${result#ok }"
  [ "$(jq 'length' <<<"$targets")" -gt 0 ] || { echo "$id: no targets" >&2; exit 1; }
  fixtures="$(jq -c --arg id "$id" 'map(select(.check == $id) | del(.check))' <<<"$cases")"
  [ "$(jq 'length' <<<"$fixtures")" -gt 0 ] || { echo "$id: no self-test fixture" >&2; exit 1; }
  echo "targets-$id=$targets"
  echo "fixtures-$id=$fixtures"
done < <(jq -c '.checks[]' "$constants")
