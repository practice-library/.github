#!/usr/bin/env bash
# Proves each guard is covered: every mutant in tooling.mutantsDir (selftest/mutants/<name>.json) must
# turn a named test red for a reason. The runner is tooling/practice_ci/mutants.py: it applies each mutant
# to an isolated copy of the checkout, never to this tree, and counts a mutant that does not parse (bash,
# Python, or a changed jq or Python program inside a shell file) or that only makes tests error as an
# invalid mutant, not a kill.
# Usage: scripts/mutants.sh [<name> ...]   (no argument: every mutants file)
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$root/$(jq -er '.tooling.launcher' "$root/policy/constants.json")" mutants "$@"
