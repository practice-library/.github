#!/usr/bin/env bash
# Builds a leak-scan fixture as a throwaway git repository: a base commit (empty, or holding the
# case's base_files), then a "pull request" commit holding the case's files and, when the case asks
# for one, a planted secret. The secret is generated here at run time, so no file in this repository
# contains one. With plant.ignorefile, a further commit adds a .gitleaksignore entry for the secret.
# Usage: build.sh <fixture dir> <output dir>; prints dir=, range= and base= lines for GITHUB_OUTPUT.
set -euo pipefail
src="$1"
out="$2"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
constants="$root/policy/constants.json"
case_file="$src/$(jq -er '.selftest.caseFile' "$constants")"
author_name="$(jq -er '.selftest.author.name' "$constants")"
author_email="$(jq -er '.selftest.author.email' "$constants")"

rm -rf "$out"
mkdir -p "$out"
g() { git -C "$out" -c user.name="$author_name" -c user.email="$author_email" -c commit.gpgsign=false "$@"; }

write_files() {
  local key="$1" path
  while IFS= read -r path; do
    mkdir -p "$(dirname "$out/$path")"
    jq -r --arg k "$key" --arg p "$path" '.[$k][$p]' "$case_file" > "$out/$path"
  done < <(jq -r --arg k "$key" '(.[$k] // {}) | keys[]' "$case_file")
}

g init -q
write_files base_files
g add -A
g commit -q --allow-empty -m base
base="$(g rev-parse HEAD)"

write_files files

if jq -e '.plant' "$case_file" > /dev/null; then
  path="$(jq -er '.plant.path' "$case_file")"
  prefix="$(jq -er '.plant.prefix' "$case_file")"
  length="$(jq -er '.plant.length' "$case_file")"
  format="$(jq -er '.plant.format' "$case_file")"
  body="$(set +o pipefail; head -c 4096 /dev/urandom | LC_ALL=C tr -dc 'A-Za-z0-9' | head -c "$length")"
  [ "${#body}" -eq "$length" ] || { echo "could not generate $length random characters" >&2; exit 1; }
  mkdir -p "$(dirname "$out/$path")"
  # shellcheck disable=SC2059 # the format comes from the case file on purpose
  printf "$format\n" "$prefix$body" >> "$out/$path"
fi

g add -A
g commit -q -m "pull request"
head="$(g rev-parse HEAD)"

if jq -e '.plant.ignorefile == true' "$case_file" > /dev/null; then
  rule="$(jq -er '.plant.rule' "$case_file")"
  line="$(grep -n -F "$prefix$body" "$out/$path" | head -1 | cut -d: -f1)"
  printf '%s:%s:%s:%s\n' "$head" "$path" "$rule" "$line" > "$out/.gitleaksignore"
  g add -A
  g commit -q -m "ignore the finding"
  head="$(g rev-parse HEAD)"
fi

echo "dir=$out"
echo "range=$base..$head"
echo "base=$base"
