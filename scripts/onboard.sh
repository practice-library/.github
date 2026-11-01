#!/usr/bin/env bash
# Thin wrapper: all the work is in tooling/practice_ci/onboarding.py, which builds and validates the whole
# plan before it makes any API write. See that file for what it does, and for GH, PIN and REF.
# Usage: PIN=<sha> scripts/onboard.sh [--dry-run] <repo>
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHONPATH="$root/tooling${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m practice_ci.onboarding "$@"
