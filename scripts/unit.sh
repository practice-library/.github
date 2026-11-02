#!/usr/bin/env bash
# Runs every unit case against the shell fragments the workflows embed, loaded straight from the
# fragments directory (selftest.libDir): there is no second copy of a library.
# A case is <unitDir>/<lib>/<name>.json = {"env": {...}, "expect": "<first word of main's output>"};
# it runs <libDir>/<lib>.sh's main with that environment. Each lib needs at least one case.
# A case may add "output": the whole line main must print, when the first word is not enough.
# A case may add "repo": {"base": {path: text}, "head": {path: text or null}, "message": text}: main then
# runs inside a throwaway git repository whose first commit holds base and whose second applies head
# (null deletes) with that message, and MB and HEAD are set to the two commits. "repo": {"config":
# {key: value}} sets git config in that repository first (a textconv driver, for instance). "author"
# names the author of the head commit (default unit). "merge": {"author": name, "message": text} makes the
# head commit on a side line and merges it into base with a merge commit by that author, which is HEAD;
# "merge": {"committer": name} gives the merge commit another committer.
# "committer" names the head commit's committer (default: the author). "failGit": text makes every git
# call whose arguments contain that text fail once the repository is built, to test a failed read.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
constants="$root/policy/constants.json"
unit_dir="$root/$(jq -er '.selftest.unitDir' "$constants")"
lib_dir="$root/$(jq -er '.selftest.libDir' "$constants")"
cd "$root"
# A case with a repository runs inside a throwaway directory, so the guards' runner is given by absolute path.
runner_env="$(jq -er '.git.runnerEnv' "$constants")"
export TOOLING="$root/tooling"
export "$runner_env=$root/$(jq -er '.tooling.launcher' "$constants")"

failed=0
total=0
# Usage: scripts/unit.sh [<library> ...]   (no argument: every library under the unit directory)
libs=()
if [ $# -gt 0 ]; then for n in "$@"; do libs+=("$lib_dir/$n.sh"); done; else libs=("$lib_dir"/*.sh); fi
for lib in "${libs[@]}"; do
  name="$(basename "$lib" .sh)"
  ls "$unit_dir/$name"/*.json > /dev/null 2>&1 || { echo "FAIL $name: no unit cases under $unit_dir/$name"; failed=$((failed + 1)); continue; }
done
cases=()
if [ $# -gt 0 ]; then
  for lib in "${libs[@]}"; do cases+=("$unit_dir/$(basename "$lib" .sh)"/*.json); done
else
  cases=("$unit_dir"/*/*.json)
fi
for case_path in "${cases[@]}"; do
  [ -f "$case_path" ] || continue
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
        committer="$author"; [ "$side" = head ] && committer="$(jq -r --arg a "$author" '.repo.committer // $a' "$case_path")"
        GIT_COMMITTER_NAME="$committer" GIT_COMMITTER_EMAIL=unit@example.invalid \
          git -C "$repo" -c user.name="$author" -c user.email=unit@example.invalid -c commit.gpgsign=false \
          commit -q --allow-empty -m "$message"
        if [ "$side" = base ]; then MB="$(git -C "$repo" rev-parse HEAD)"; else HEAD="$(git -C "$repo" rev-parse HEAD)"; fi
      done
      if jq -e '.repo | has("merge")' "$case_path" > /dev/null; then
        git -C "$repo" checkout -q --detach "$MB"
        merger="$(jq -r '.repo.merge.author // "unit"' "$case_path")"
        GIT_COMMITTER_NAME="$(jq -r --arg m "$merger" '.repo.merge.committer // $m' "$case_path")" GIT_COMMITTER_EMAIL=unit@example.invalid \
        git -C "$repo" -c user.name="$merger" -c user.email=unit@example.invalid \
          -c commit.gpgsign=false merge -q --no-ff -m "$(jq -r '.repo.merge.message // "Merge"' "$case_path")" "$HEAD"
        HEAD="$(git -C "$repo" rev-parse HEAD)"
      fi
      export MB HEAD
      cd "$repo"
      if jq -e '.repo | has("failGit")' "$case_path" > /dev/null; then
        mkdir "$repo.bin"
        trap 'rm -rf "$repo" "$repo.bin"' EXIT
        { echo '#!/usr/bin/env bash'
          printf 'case " $* " in *%q*) exit 128 ;; esac\n' "$(jq -r '.repo.failGit' "$case_path")"
          printf 'exec %q "$@"\n' "$(command -v git)"; } > "$repo.bin/git"
        chmod +x "$repo.bin/git"
        PATH="$repo.bin:$PATH"
      fi
    fi
    # shellcheck disable=SC1090 # the library is chosen by the case directory
    filled="$(jq -Rrs --slurpfile c "$constants" '
      gsub("@@(?<key>[A-Za-z0-9_.]+)@@";
        .key as $key | $c[0] | getpath($key | split(".")) // error("missing constant: " + $key) | tostring)
      ' "$lib")"
    source /dev/stdin <<<"$filled"
    main
  )" || got="error $?"
  output="$(jq -r '.output // empty' "$case_path")"
  if [ "${got%% *}" = "$want" ] && { [ -z "$output" ] || [ "$got" = "$output" ]; }; then
    echo "ok   $name/$(basename "$case_path" .json): $got"
  else
    echo "FAIL $name/$(basename "$case_path" .json): want $want, got: $got"
    failed=$((failed + 1))
  fi
done
echo "$total cases, $failed failed"
[ "$failed" -eq 0 ]
