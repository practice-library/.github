# Generated from templates/selftest/lib/gate-required.sh and policy/constants.json by scripts/render.sh. Do not edit.
# main: prints "ok ..." when every job id in REQUIRED (a JSON array) is a key of NEEDS (the caller's
# toJSON(needs)); otherwise "missing ..." or "invalid ...". The caller fails unless the first word is ok.
main() {
  local count missing
  if ! count="$(jq -n --argjson r "$REQUIRED" 'if ($r | type) == "array" then $r | length else error("not an array") end' 2>/dev/null)"; then
    echo "invalid required must be a JSON array of job ids"; return 0
  fi
  if ! missing="$(jq -cn --argjson n "$NEEDS" --argjson r "$REQUIRED" '$r - ($n | keys)' 2>/dev/null)"; then
    echo "invalid needs must be the caller's toJSON(needs)"; return 0
  fi
  if [ "$count" -eq 0 ]; then echo "missing no required job was named"; return 0; fi
  if [ "$missing" = "[]" ]; then echo "ok every required job is among the needs"; else echo "missing $missing"; fi
}
