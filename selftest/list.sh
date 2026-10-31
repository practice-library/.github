#!/usr/bin/env bash
# Prints one GITHUB_OUTPUT line per check: <check>=<JSON array of that check's fixtures>.
# Usage: list.sh <fixtures dir> <case file name>
set -euo pipefail
dir="$1"
case_file="$2"

all="$(
  for d in "$dir"/*/; do
    name="$(basename "$d")"
    jq -c --arg n "$name" '
      if (.check | type) != "string" then error($n + ": check is missing")
      elif (.expect != "pass" and .expect != "fail") then error($n + ": expect must be pass or fail")
      else {fixture: $n} + (del(.files, .plant)) end' "$d/$case_file"
  done | jq -sc '.'
)"

[ "$(jq 'length' <<<"$all")" -gt 0 ] || { echo "no fixtures under $dir" >&2; exit 1; }

jq -r 'group_by(.check)[] | "\(.[0].check)=\(map(del(.check)) | tojson)"' <<<"$all"
