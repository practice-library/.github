# main: prints "ok ..." when the change touches no watched path, or changes the changelog, or a commit
# message holds the marker line; otherwise "missing ...".
#   CHANGED    JSON array of changed paths, old and new
#   WATCH      JSON array of watched paths; an entry ending in / covers everything under it
#   CHANGELOG  the changelog path       MARKER  the line that says no release is needed
#   MESSAGES   the change's commit messages
main() {
  local touched
  if ! touched="$(jq -c --argjson w "$WATCH" '
      [.[] | select(. as $f | any($w[]; . as $p
        | if ($p | endswith("/")) then ($f | startswith($p)) else $f == $p end))] | unique' <<<"$CHANGED" 2>/dev/null)"; then
    echo "invalid CHANGED and WATCH must be JSON arrays"; return 0
  fi
  if [ "$touched" = "[]" ]; then echo "ok no watched path changed"; return 0; fi
  if jq -en --arg c "$CHANGELOG" --argjson f "$CHANGED" 'any($f[]; . == $c)' > /dev/null; then
    echo "ok $CHANGELOG changed"; return 0
  fi
  if printf '%s\n' "$MESSAGES" | sed 's/[[:space:]]*$//' | grep -qxF -- "$MARKER"; then
    echo "ok a commit message says: $MARKER"; return 0
  fi
  echo "missing $touched changed, but neither $CHANGELOG nor a \"$MARKER\" line in a commit message"
}
