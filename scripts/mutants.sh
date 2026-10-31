#!/usr/bin/env bash
# Proves each guard in a unit-tested library is covered: for every mutant in selftest/mutants/<lib>.json
# ([{"name": ..., "find": ..., "replace": ...}]), applies it to a copy of selftest/lib/<lib>.sh and runs
# that library's unit cases; the mutant must turn at least one named case red. Fails when a mutant
# survives, when its find text is not in the library (a stale mutant), or when a case errors.
# Usage: scripts/mutants.sh [<lib> ...]   (no argument: every file under selftest/mutants)
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
lib_dir="$(jq -er '.selftest.libDir' policy/constants.json)"
files=()
if [ $# -gt 0 ]; then for n in "$@"; do files+=("selftest/mutants/$n.json"); done; else files=(selftest/mutants/*.json); fi
total=0; bad=0
for f in "${files[@]}"; do
  name="$(basename "$f" .json)"; lib="$lib_dir/$name.sh"
  [ -f "$lib" ] || { echo "FAIL $name: no library $lib"; bad=$((bad + 1)); continue; }
  cp "$lib" "$lib.orig"
  n="$(jq 'length' "$f")"
  for ((i = 0; i < n; i++)); do
    total=$((total + 1))
    m="$(jq -r --argjson i "$i" '.[$i].name' "$f")"
    if ! FIND="$(jq -r --argjson i "$i" '.[$i].find' "$f")" REPLACE="$(jq -r --argjson i "$i" '.[$i].replace' "$f")" \
        python3 -I -c 'import os, sys
p = sys.argv[1]; s = open(p).read(); f = os.environ["FIND"]
if f not in s: sys.exit(1)
open(p, "w").write(s.replace(f, os.environ["REPLACE"], 1))' "$lib"; then
      echo "FAIL $name/$m: the find text is not in $lib (a stale mutant)"; bad=$((bad + 1)); cp "$lib.orig" "$lib"; continue
    fi
    # A mutant that breaks the syntax would turn every case red without testing anything.
    if ! bash -n "$lib" 2>/dev/null; then
      echo "FAIL $name/$m: the mutated library does not parse, so it proves nothing"; bad=$((bad + 1)); cp "$lib.orig" "$lib"; continue
    fi
    red="$(bash scripts/unit.sh "$name" 2>&1 | sed -n 's/^FAIL \([^:]*\):.*/\1/p' | tr '\n' ' ')" || true
    cp "$lib.orig" "$lib"
    if [ -n "$red" ]; then echo "caught $name/$m by $red"
    else echo "FAIL $name/$m: survived, no case turned red"; bad=$((bad + 1)); fi
  done
  rm -f "$lib.orig"
done
echo "$total mutants, $bad not caught"
[ "$bad" -eq 0 ]
