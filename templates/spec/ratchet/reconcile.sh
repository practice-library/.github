# The reference reconciler for spec/ratchet/schema.json, in bash and jq, so a check in any language can
# be held against the same fixtures. Usage:
#   bash spec/ratchet/reconcile.sh <baseline.json> < found-keys            prints the verdict; exit 0 on ok
#   bash spec/ratchet/reconcile.sh --write <baseline.json> < found-keys    prints a re-recorded baseline
set -euo pipefail
#@include ratchet.sh
WRITE=""
if [ "${1:-}" = --write ]; then WRITE=true; shift; fi
[ $# -eq 1 ] || { echo "usage: reconcile.sh [--write] <baseline.json> < found-keys" >&2; exit 2; }
BASELINE="$1"; FOUND="$(cat)"
out="$(BASELINE="$BASELINE" FOUND="$FOUND" WRITE="$WRITE" main)"
case "$out" in
  ok*) echo "$out" ;;
  write*) printf '%s\n' "${out#write }" | jq . ;;
  *) echo "$out"; exit 1 ;;
esac
