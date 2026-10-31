#!/usr/bin/env bash
# Runs every unit case against the rendered shell libraries the workflows embed.
# A case is <unitDir>/<lib>/<name>.json = {"env": {...}, "expect": "<first word of main's output>"};
# it runs <libDir>/<lib>.sh's main with that environment. Each lib needs at least one case.
# A case may add "repo": {"base": {path: text}, "head": {path: text or null}, "message": text}: main then
# runs inside a throwaway git repository whose first commit holds base and whose second applies head
# (null deletes) with that message, and MB and HEAD are set to the two commits. "repo": {"config":
# {key: value}} sets git config in that repository first (a textconv driver, for instance). "author"
# names the author of the head commit (default unit). "merge": {"author": name, "message": text} makes the
# head commit on a side line and merges it into base with a merge commit by that author, which is HEAD.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
constants="$root/policy/constants.json"
unit_dir="$root/$(jq -er '.selftest.unitDir' "$constants")"
lib_dir="$root/$(jq -er '.selftest.libDir' "$constants")"
cd "$root"

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
    if jq -e 'has("repo")' "$case_path" > /dev/null; then
      repo="$(mktemp -d)"
      trap 'rm -rf "$repo"' EXIT
      git -C "$repo" init -q
      while IFS= read -r -d '' key; do
        git -C "$repo" config "$key" "$(jq -j --arg k "$key" '.repo.config[$k]' "$case_path")"
      done < <(jq -j '.repo.config // {} | keys[] | . + "\u0000"' "$case_path")
      for side in base head; do
        while IFS= read -r -d '' path; do
          mkdir -p "$(dirname "$repo/$path")"
          if jq -e --arg s "$side" --arg p "$path" '.repo[$s][$p] == null' "$case_path" > /dev/null; then
            rm -f "$repo/$path"
          else
            jq -j --arg s "$side" --arg p "$path" '.repo[$s][$p]' "$case_path" > "$repo/$path"
          fi
        done < <(jq -j --arg s "$side" '.repo[$s] // {} | keys[] | . + "\u0000"' "$case_path")
        git -C "$repo" add -A
        message="$side"; [ "$side" = head ] && message="$(jq -r '.repo.message // "head"' "$case_path")"
        author=unit; [ "$side" = head ] && author="$(jq -r '.repo.author // "unit"' "$case_path")"
        git -C "$repo" -c user.name="$author" -c user.email=unit@example.invalid -c commit.gpgsign=false \
          commit -q --allow-empty -m "$message"
        if [ "$side" = base ]; then MB="$(git -C "$repo" rev-parse HEAD)"; else HEAD="$(git -C "$repo" rev-parse HEAD)"; fi
      done
      if jq -e '.repo | has("merge")' "$case_path" > /dev/null; then
        git -C "$repo" checkout -q --detach "$MB"
        git -C "$repo" -c user.name="$(jq -r '.repo.merge.author // "unit"' "$case_path")" -c user.email=unit@example.invalid \
          -c commit.gpgsign=false merge -q --no-ff -m "$(jq -r '.repo.merge.message // "Merge"' "$case_path")" "$HEAD"
        HEAD="$(git -C "$repo" rev-parse HEAD)"
      fi
      export MB HEAD
      cd "$repo"
    fi
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
