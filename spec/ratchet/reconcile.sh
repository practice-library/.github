# Generated from templates/spec/ratchet/reconcile.sh and policy/constants.json by scripts/render.sh. Do not edit.
# The reference reconciler for spec/ratchet/schema.json, in bash and jq, so a check in any language can
# be held against the same fixtures. Usage:
#   bash spec/ratchet/reconcile.sh <baseline.json> < found-keys            prints the verdict; exit 0 on ok
#   bash spec/ratchet/reconcile.sh --write <baseline.json> < found-keys    prints a re-recorded baseline
set -euo pipefail
# main: reconciles the findings of one run against a shrink-only baseline (spec/ratchet/schema.json).
#   BASELINE  the baseline file
#   FOUND     the keys the run found, one per line (blank lines and surrounding spaces ignored)
#   WRITE     "true" to print a re-recorded baseline instead of a verdict
# Each key is one of: fresh (found, not listed), explained (found and listed with a reason and an owner),
# unexplained (listed, found or not, with an empty or missing reason or owner), paidOff (listed with a
# reason, no longer found). Prints one line:
#   ok {"explained": [...]}                   nothing fresh, unexplained or paid off
#   fail {"fresh": [...], "unexplained": [...], "paidOff": [...], "explained": [...]}
#   invalid <why>                             the baseline is missing, unreadable or malformed
#   write <baseline JSON>                     with WRITE=true: found keys not listed are added with an
#                                             empty reason and owner (so they still fail), entries no
#                                             longer found are dropped; a reason is never filled in
main() {
  local base
  [ -r "${BASELINE:-}" ] || { echo "invalid cannot read the baseline ${BASELINE:-}"; return 0; }
  base="$(jq -c '
      if type != "object" then error("the baseline must be an object")
      elif .ratchet != 1 then error("ratchet must be 1")
      elif (keys - ["ratchet", "check", "entries"]) != [] then error("unknown keys: " + ((keys - ["ratchet", "check", "entries"]) | join(", ")))
      elif (.check | type) != "string" or (.check | length) == 0 then error("check must be a non-empty string")
      elif (.entries | type) != "array" then error("entries must be an array")
      elif any(.entries[]; type != "object" or (.key | type) != "string" or (.key | test("^\\S(.*\\S)?$") | not)
               or ((has("reason") and (.reason | type) != "string")) or ((has("owner") and (.owner | type) != "string"))
               or ((keys - ["key", "reason", "owner"]) != [])) then error("each entry is {key, reason, owner}, key without outer spaces")
      elif (.entries | map(.key) | length) != (.entries | map(.key) | unique | length) then error("a key is listed twice")
      else . end' "$BASELINE" 2>&1)" || { echo "invalid ${base#jq: error (at *): }"; return 0; }
  printf '%s\n' "${FOUND:-}" | jq -Rr --argjson b "$base" --arg w "${WRITE:-}" -n '
    [inputs | gsub("^\\s+|\\s+$"; "") | select(length > 0)] | unique as $found
    | ($b.entries | map({(.key): .}) | add // {}) as $listed
    | def told($e): (($e.reason // "") | test("\\S")) and (($e.owner // "") | test("\\S"));
    if $w == "true" then
      "write " + ($b | .entries = ([.entries[] | select(.key as $k | $found | index([$k]))]
        + [$found[] | select($listed[.] == null) | {key: ., reason: "", owner: ""}] | sort_by(.key)) | tojson)
    else
      { fresh: [$found[] | select($listed[.] == null)],
        unexplained: [$b.entries[] | select(told(.) | not) | .key] | sort,
        paidOff: [$b.entries[] | select(told(.)) | select(.key as $k | $found | index([$k]) | not) | .key] | sort,
        explained: [$b.entries[] | select(told(.)) | select(.key as $k | $found | index([$k])) | .key] | sort } as $r
      | if ($r.fresh + $r.unexplained + $r.paidOff) == [] then "ok " + ({explained: $r.explained} | tojson)
        else "fail " + ($r | tojson) end
    end'
}
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
