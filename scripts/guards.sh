#!/usr/bin/env bash
# Runs schema-check's guards mode on a contract, locally: every mutant in the guards file must turn an
# example or a counter-example red (#26, #35).
#   scripts/guards.sh <jsonschema binary> <schema> <guards file> [--resolve <schema file>]...
# The binary is the pinned jsonschema release (tools.jsonschema in policy/constants.json).
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[ $# -ge 3 ] || { echo "usage: scripts/guards.sh <jsonschema binary> <schema> <guards file> [--resolve <file>]..." >&2; exit 2; }
validator="$1"; schema="$2"; guards="$3"; shift 3
tooling="$(jq -er '.tooling.dir' "$root/policy/constants.json")"
package="$(jq -er '.tooling.package' "$root/policy/constants.json")"
PYTHONPATH="$root/$tooling" exec python3 -P -m "$package.guards" --validator "$validator" --schema "$schema" --guards "$guards" "$@"
