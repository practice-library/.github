# Generated from templates/selftest/lib/automerge-decide.sh and policy/constants.json by scripts/render.sh. Do not edit.
# main: decides whether auto-merge may be on for a pull request. Prints "on ..." or "off <reason>".
# It is on only when every condition holds; anything unknown or unexpected keeps it off.
#   AUTHOR   the pull request author's login        TRUSTED  JSON array of trusted logins
#   ALLOW    JSON array of allowlisted paths; an entry ending in / covers everything under it
#   FILES    JSON array of {filename, previous_filename} from the pull request files API
#   CHANGED  the pull request's changed_files count  MAX      the most files that API lists
#   DRAFT    true when the pull request is a draft
main() {
  local trusted listed outside
  if [ "${DRAFT:-}" != false ]; then echo "off the pull request is a draft, or its draft state is unknown"; return 0; fi
  if ! trusted="$(jq -n --arg a "$AUTHOR" --argjson t "$TRUSTED" 'any($t[]; . == $a)' 2>/dev/null)"; then
    echo "off the trusted list is not a JSON array"; return 0
  fi
  if [ "$trusted" != true ]; then echo "off the author is not on the trusted list"; return 0; fi
  if ! listed="$(jq 'length' <<<"$FILES" 2>/dev/null)"; then echo "off the file list is not readable"; return 0; fi
  if ! [[ "$CHANGED" =~ ^[0-9]+$ ]] || ! [[ "$MAX" =~ ^[0-9]+$ ]]; then echo "off the changed or maximum file count is not a number"; return 0; fi
  if [ "$listed" -ge "$MAX" ]; then echo "off the file list may be cut off: $listed listed, the API lists at most $MAX"; return 0; fi
  if [ "$listed" -lt "$CHANGED" ]; then echo "off only $listed of $CHANGED changed files were listed"; return 0; fi
  if [ "$listed" -eq 0 ]; then echo "off no changed file was listed"; return 0; fi
  if ! outside="$(jq -c --argjson allow "$ALLOW" '
      [.[] | .filename, (.previous_filename // empty)] | unique
      | map(select(. as $f | any($allow[]; . as $p
          | if ($p | endswith("/")) then ($f | startswith($p)) else $f == $p end) | not))' <<<"$FILES" 2>/dev/null)"; then
    echo "off the allowlist or file list is not valid JSON"; return 0
  fi
  if [ "$outside" != "[]" ]; then echo "off paths outside the allowlist: $outside"; return 0; fi
  echo "on every changed path, old and new, is on the allowlist"
}
