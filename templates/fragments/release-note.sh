# main: prints "ok ..." when the change touches no watched path, or adds a line with text to the
# changelog (a whitespace-only edit does not count), or a commit message holds the marker line;
# otherwise "missing ...".
#   CHANGED    JSON array of changed paths, old and new
#   WATCH      JSON array of watched paths; an entry ending in / covers everything under it
#   CHANGELOG  the changelog path       MARKER  the line that says no release is needed
#   MESSAGES   the change's commit messages
#   CHANGELOG_ADDED  how many lines the change adds to the changelog that hold a non-space character.
#             When unset, main counts them from git for MB..HEAD: added lines (git drops blank ones), after the hunk
#             header (so a line that starts with ++ counts), minus lines the same change removes (so a
#             line moved within the changelog counts nothing), with whitespace changes ignored.
main() {
  local touched
  if [ -z "${CHANGELOG_ADDED+x}" ]; then
    [ -n "${MB:-}" ] && [ -n "${HEAD:-}" ] || { echo "invalid CHANGELOG_ADDED is unset and there is no MB..HEAD to count from"; return 0; }
    CHANGELOG_ADDED="$(git diff -w --ignore-blank-lines --no-ext-diff --no-textconv --text --no-color --unified=0 "$MB" "$HEAD" -- "$CHANGELOG" \
      | jq -Rsr '
          split("\n") as $l
          | ([range(0; $l | length) | select($l[.] | startswith("@@"))] | first) as $i
          | if $i == null then 0
            else [$l[$i:][] | select(startswith("+")) | .[1:]] as $added
              | [$l[$i:][] | select(startswith("-")) | .[1:]] as $removed
              | reduce $removed[] as $r ($added; (index([$r]) // null) as $k | if $k == null then . else del(.[$k]) end)
              | length
            end')" || { echo "invalid the changelog diff could not be read"; return 0; }
  fi
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
