#!/usr/bin/env bash
# Runs every unit case against the rendered shell libraries the workflows embed.
# A case is <unitDir>/<lib>/<name>.json = {"env": {...}, "expect": "<first word of main's output>"};
# it runs <libDir>/<lib>.sh's main with that environment. Each lib needs at least one case.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
constants="$root/policy/constants.json"
unit_dir="$root/$(jq -er '.selftest.unitDir' "$constants")"
lib_dir="$root/$(jq -er '.selftest.libDir' "$constants")"

failed=0
total=0
for lib in "$lib_dir"/*.sh; do
  name="$(basename "$lib" .sh)"
  ls "$unit_dir/$name"/*.json > /dev/null 2>&1 || { echo "FAIL $name: no unit cases under $unit_dir/$name"; failed=$((failed + 1)); continue; }
done
for case_path in "$unit_dir"/*/*.json; do
  name="$(basename "$(dirname "$case_path")")"
  lib="$lib_dir/$name.sh"
  total=$((total + 1))
  [ -f "$lib" ] || { echo "FAIL $name/$(basename "$case_path"): no library $lib"; failed=$((failed + 1)); continue; }
  want="$(jq -er '.expect' "$case_path")"
  got="$(
    while IFS= read -r -d '' kv; do export "${kv?}"; done < <(jq -j '.env | to_entries[] | "\(.key)=\(.value | if type == "string" then . else tojson end)\u0000"' "$case_path")
    # shellcheck disable=SC1090 # the library is chosen by the case directory
    source "$lib"
    main
  )" || got="error $?"
  if [ "${got%% *}" = "$want" ]; then
    echo "ok   $name/$(basename "$case_path" .json): $got"
  else
    echo "FAIL $name/$(basename "$case_path" .json): want $want, got: $got"
    failed=$((failed + 1))
  fi
done
echo "$total cases, $failed failed"
[ "$failed" -eq 0 ]
