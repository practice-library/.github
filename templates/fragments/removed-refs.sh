# main: prints "ok ..." when nothing in the tree ROOT mentions a path the change removed, otherwise
# "referenced [{path, at}, ...]".
#   DELETED  JSON array of paths the change deleted or renamed away
#   ROOT     the tree after the change
#   HISTORY  JSON array of files whose mentions are a record of the past and are allowed
# Besides each removed path, every parent directory that no longer exists is looked for, as "dir/"
# and as "dir". A mention must not be preceded by a path character, so "x/a.json" is not "a.json".
main() {
  local terms t esc hits
  if ! jq -en --argjson d "$DELETED" --argjson h "$HISTORY" '($d | type) == "array" and ($h | type) == "array"' > /dev/null 2>&1; then
    echo "invalid DELETED and HISTORY must be JSON arrays"; return 0
  fi
  terms="$(
    jq -r '.[]' <<<"$DELETED" | while IFS= read -r p; do
      [ -n "$p" ] || continue
      printf '%s\n' "$p"
      d="$(dirname "$p")"
      while [ "$d" != . ] && [ "$d" != / ]; do
        if [ ! -e "$ROOT/$d" ]; then printf '%s/\n%s\n' "$d" "$d"; fi
        d="$(dirname "$d")"
      done
    done | sort -u | awk '{ print length($0) "\t" $0 }' | sort -rn | cut -f2-
  )"
  hits="$(
    while IFS= read -r t; do
      [ -n "$t" ] || continue
      esc="$(printf '%s' "$t" | sed 's/[][\.*^$+?(){}|/]/\\&/g')"
      grep -rnIE --exclude-dir=.git "(^|[^A-Za-z0-9._/-])${esc}(\$|[^A-Za-z0-9_-])" "$ROOT" 2>/dev/null \
        | while IFS= read -r m; do
            file="${m%%:*}"; rest="${m#*:}"; file="${file#"$ROOT"/}"
            jq -en --arg f "$file" --argjson h "$HISTORY" 'any($h[]; . == $f)' > /dev/null && continue
            jq -cn --arg p "$t" --arg at "$file:${rest%%:*}" '{path: $p, at: $at}'
          done
    done <<<"$terms" | jq -sc 'unique_by(.at) | .[:20]'
  )"
  if [ "$hits" = "[]" ]; then echo "ok no removed path is mentioned"; else echo "referenced $hits"; fi
}
