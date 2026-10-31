#!/usr/bin/env bash
# Builds a leak-scan fixture as a throwaway git repository: an empty base commit, then one
# "pull request" commit holding the case's files and, when the case asks for one, a planted secret.
# The secret is generated here at run time, so no file in this repository contains one.
# Usage: build.sh <fixture dir> <output dir>; prints dir= and range= lines for GITHUB_OUTPUT.
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

g init -q
g commit -q --allow-empty -m base
base="$(g rev-parse HEAD)"

while IFS=$'\t' read -r path content; do
  mkdir -p "$(dirname "$out/$path")"
  printf '%s\n' "$content" > "$out/$path"
done < <(jq -r '(.files // {}) | to_entries[] | [.key, .value] | @tsv' "$case_file")

if jq -e '.plant' "$case_file" > /dev/null; then
  path="$(jq -er '.plant.path' "$case_file")"
  prefix="$(jq -er '.plant.prefix' "$case_file")"
  length="$(jq -er '.plant.length' "$case_file")"
  format="$(jq -er '.plant.format' "$case_file")"
  body="$(set +o pipefail; head -c 4096 /dev/urandom | LC_ALL=C tr -dc 'A-Za-z0-9' | head -c "$length")"
  [ "${#body}" -eq "$length" ] || { echo "could not generate $length random characters" >&2; exit 1; }
  mkdir -p "$(dirname "$out/$path")"
  # shellcheck disable=SC2059 # the format comes from the case file on purpose
  printf "$format\n" "$prefix$body" > "$out/$path"
fi

g add -A
g commit -q -m "pull request"
head="$(g rev-parse HEAD)"

echo "dir=$out"
echo "range=$base..$head"
