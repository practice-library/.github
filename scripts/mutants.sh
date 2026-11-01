#!/usr/bin/env bash
# Proves each guard is covered: for every file under the mutants directory (selftest.mutantsDir), applies
# each mutant ({"name", "find", "replace"}) to the file it targets and checks that a behavioural test turns red.
#   library mutants   <mutantsDir>/<lib>.json is an array; it mutates <libDir>/<lib>.sh and runs that
#                     library's unit cases (scripts/unit.sh); a case must report "FAIL <lib>/<case>: want ...".
#   step mutants      an object {"target": <file>, "tests": [<unittest module>, ...], "mutants": [...]};
#                     it mutates the workflow or fragment <file> (the shell inside its steps), or a Python
#                     module when <file> ends in .py, and runs the tests; a test must fail an assertion
#                     ("FAIL: <test>"). Instead of "tests" the object may hold "unit": <lib>, and then the
#                     mutant is judged by that library's unit cases, as for a library mutant.
# A mutant counts as killed only by such a behavioural failure. One that leaves the shell with a syntax
# error, a jq program that does not compile (selftest.parseErrorPatterns) or a step that does not parse
# proves nothing and is an error. Also an error: a mutant that survives, or whose find text is not in the
# target (a stale mutant).
# Usage: scripts/mutants.sh [<name> ...]   (no argument: every file under the mutants directory)
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
constants=policy/constants.json
lib_dir="$(jq -er '.selftest.libDir' "$constants")"
mutants_dir="$(jq -er '.selftest.mutantsDir' "$constants")"
parse_errors="$(jq -er '.selftest.parseErrorPatterns | join("|")' "$constants")"
launcher="$(jq -er '.tooling.launcher' "$constants")"
files=()
if [ $# -gt 0 ]; then for n in "$@"; do files+=("$mutants_dir/$n.json"); done; else files=("$mutants_dir"/*.json); fi

orig="$(mktemp)"
target=""
restore() { if [ -n "$target" ]; then cp "$orig" "$target"; fi; }
trap 'restore; rm -f "$orig"' EXIT

# New lines of parse-error noise in $1 that the unmutated run (in $2) did not have.
new_noise() { comm -13 <(grep -E -- "$parse_errors" <<<"$2" | sort -u || true) <(grep -E -- "$parse_errors" <<<"$1" | sort -u || true); }

total=0; bad=0
for f in "${files[@]}"; do
  name="$(basename "$f" .json)"
  kind=lib
  jq -e 'type == "object"' "$f" > /dev/null && kind=step
  tests=()
  if [ "$kind" = lib ]; then
    target="$lib_dir/$name.sh"
    run_tests() { bash scripts/unit.sh "$name" 2>&1; }
    red_of() { sed -n 's/^FAIL \([^ :]*\): want .*/\1/p' <<<"$1" | tr '\n' ' '; }
  else
    target="$(jq -er '.target' "$f")"
    if jq -e 'has("unit")' "$f" > /dev/null; then
      unit_lib="$(jq -er '.unit' "$f")"
      run_tests() { PYTHONDONTWRITEBYTECODE=1 bash scripts/unit.sh "$unit_lib" 2>&1; }
      red_of() { sed -n 's/^FAIL \([^ :]*\): want .*/\1/p' <<<"$1" | tr '\n' ' '; }
    else
      while IFS= read -r t; do tests+=("$t"); done < <(jq -r '.tests[]' "$f")
      run_tests() { PYTHONDONTWRITEBYTECODE=1 python3 -m unittest "${tests[@]}" 2>&1; }
      red_of() { sed -n 's/^FAIL: \([^ ]*\) .*/\1/p' <<<"$1" | tr '\n' ' '; }
    fi
  fi
  [ -f "$target" ] || { echo "FAIL $name: no file $target"; bad=$((bad + 1)); target=""; continue; }
  cp "$target" "$orig"
  if ! baseline="$(run_tests)"; then
    echo "FAIL $name: $target already fails its tests unmutated, so no mutant of it can be judged"
    bad=$((bad + 1)); target=""; continue
  fi
  muts="$(jq -c 'if type == "array" then . else .mutants end' "$f")"
  n="$(jq 'length' <<<"$muts")"
  for ((i = 0; i < n; i++)); do
    total=$((total + 1))
    m="$(jq -r --argjson i "$i" '.[$i].name' <<<"$muts")"
    if ! FIND="$(jq -r --argjson i "$i" '.[$i].find' <<<"$muts")" REPLACE="$(jq -r --argjson i "$i" '.[$i].replace' <<<"$muts")" \
        python3 -I -c 'import os, sys
p = sys.argv[1]; s = open(p).read(); f = os.environ["FIND"]
if f not in s: sys.exit(1)
open(p, "w").write(s.replace(f, os.environ["REPLACE"], 1))' "$target"; then
      echo "FAIL $name/$m: the find text is not in $target (a stale mutant)"; bad=$((bad + 1)); cp "$orig" "$target"; continue
    fi
    # A mutant that breaks the syntax would turn every case red without testing anything.
    if [ "$kind" = lib ]; then
      parses=true; bash -n "$target" 2> /dev/null || parses=false
    elif [[ "$target" == *.py ]]; then
      parses=true; python3 -I -c 'import ast, sys; ast.parse(open(sys.argv[1], encoding="utf-8").read())' "$target" > /dev/null 2>&1 || parses=false
    else
      parses=true; python3 -I "$launcher" check-steps "$target" > /dev/null 2>&1 || parses=false
    fi
    if [ "$parses" = false ]; then
      echo "FAIL $name/$m: the mutated $target does not parse, so it proves nothing"; bad=$((bad + 1)); cp "$orig" "$target"; continue
    fi
    out="$(run_tests || true)"
    cp "$orig" "$target"
    # A jq or Python program inside the shell that no longer compiles fails its cases by crashing, not by behaviour.
    noise="$(new_noise "$out" "$baseline")"
    if [ -n "$noise" ]; then
      echo "FAIL $name/$m: the mutant breaks a program inside $target (a parse error, not a behaviour), so it proves nothing: $(head -n 1 <<<"$noise")"
      bad=$((bad + 1)); continue
    fi
    red="$(red_of "$out")"
    if [ -n "$red" ]; then echo "caught $name/$m by $red"
    else echo "FAIL $name/$m: survived, no case turned red"; bad=$((bad + 1)); fi
  done
  target=""
done
echo "$total mutants, $bad not caught"
[ "$bad" -eq 0 ]
