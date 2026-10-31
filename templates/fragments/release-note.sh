# main: prints "ok ..." when the change touches no watched path, or adds a line with text to the
# changelog (a whitespace-only edit does not count), or a commit message holds the marker line;
# otherwise "missing ...".
#   CHANGED    JSON array of changed paths, old and new
#   WATCH      JSON array of watched paths; an entry ending in / covers everything under it
#   CHANGELOG  the changelog path       MARKER  the line that says no release is needed
#   MESSAGES   the change's commit messages
#   CHANGELOG_ADDED  how many lines the change adds to the changelog that hold a non-space character
main() {
  local touched
  [[ "${CHANGELOG_ADDED:-}" =~ ^[0-9]+$ ]] || { echo "invalid CHANGELOG_ADDED must be a count"; return 0; }
  if ! touched="$(jq -c --argjson w "$WATCH" '
      [.[] | select(. as $f | any($w[]; . as $p
        | if ($p | endswith("/")) then ($f | startswith($p)) else $f == $p end))] | unique' <<<"$CHANGED" 2>/dev/null)"; then
    echo "invalid CHANGED and WATCH must be JSON arrays"; return 0
  fi
  if [ "$touched" = "[]" ]; then echo "ok no watched path changed"; return 0; fi
  if [ "$CHANGELOG_ADDED" -gt 0 ] && jq -en --arg c "$CHANGELOG" --argjson f "$CHANGED" 'any($f[]; . == $c)' > /dev/null; then
    echo "ok $CHANGELOG has $CHANGELOG_ADDED added lines"; return 0
  fi
  if printf '%s\n' "$MESSAGES" | sed 's/[[:space:]]*$//' | grep -qxF -- "$MARKER"; then
    echo "ok a commit message says: $MARKER"; return 0
  fi
  echo "missing $touched changed, but neither $CHANGELOG nor a \"$MARKER\" line in a commit message"
}
