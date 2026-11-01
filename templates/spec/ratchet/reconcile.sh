# The reference reconciler for spec/ratchet/schema.json, in bash and jq, so a check in any language can
# be held against the same fixtures. Usage:
#   bash spec/ratchet/reconcile.sh <baseline.json> < found-keys            prints the verdict; exit 0 on ok
#   bash spec/ratchet/reconcile.sh --write <baseline.json> < found-keys    prints a re-recorded baseline
#   --check <name> before the baseline refuses a baseline recorded for another check.
set -euo pipefail
#@include ratchet.sh
WRITE=""; CHECK=""
while [ $# -gt 1 ]; do
  case "$1" in
    --write) WRITE=true; shift ;;
    --check) [ -n "${2:-}" ] || { echo "usage: --check needs a check name" >&2; exit 2; }; CHECK="$2"; shift 2 ;;
    *) break ;;
  esac
done
[ $# -eq 1 ] || { echo "usage: reconcile.sh [--write] [--check <name>] <baseline.json> < found-keys" >&2; exit 2; }
BASELINE="$1"; FOUND="$(cat)"
out="$(BASELINE="$BASELINE" FOUND="$FOUND" WRITE="$WRITE" CHECK="$CHECK" main)"
case "$out" in
  ok*) echo "$out" ;;
  write*) printf '%s\n' "${out#write }" | jq . ;;
  *) echo "$out"; exit 1 ;;
esac
