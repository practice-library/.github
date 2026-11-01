# Generated from templates/selftest/lib/denylist-exempt.sh and policy/constants.json by scripts/render.sh. Do not edit.
# main: judges whether a change adds or widens a denylist exemption. BASE_LIST is the denylist file on
# the base commit and HEAD_LIST the one on the head; either is empty when that commit has none. Prints
# "ok ..." when every exemptPaths entry of the head list is also, exactly, an entry of the base list (an
# entry removed is fine), "widened [<glob>, ...]" naming each head entry that is new or changed, or
# "invalid ..." when a list that is there cannot be read. Widening is a loosening: it needs the approval
# label, and it never applies to the change that makes it, since the scan reads the base list.
main() {
  local out
  if ! out="$(jq -cn --arg b "${BASE_LIST:-}" --arg h "${HEAD_LIST:-}" '
      def entries($s): if $s == "" then [] else ($s | fromjson | .exemptPaths // [])
        | if type == "array" then . else error("exemptPaths is not a list") end end;
      entries($b) as $old
      | [entries($h)[] | . as $e | select(($old | index([$e])) == null)
         | if type == "object" then (.glob // "(no glob)" | tostring) else tojson end]' 2>/dev/null)"; then
    echo "invalid a denylist file is not JSON, or its exemptPaths is not a list"; return 0
  fi
  if [ "$out" = "[]" ]; then echo "ok no exemption added or widened"; else echo "widened $out"; fi
}
