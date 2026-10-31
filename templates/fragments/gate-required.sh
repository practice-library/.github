# main: prints "ok ..." when the job ids in REQUIRED (the jobs array of the repository's required-checks
# file) are exactly the keys of NEEDS (the caller's toJSON(needs)) and include every id in MANDATORY;
# otherwise "missing ...", "unlisted ..." or "invalid ...". The caller fails unless the first word is ok.
main() {
  local missing unlisted absent
  if ! jq -en --argjson r "$REQUIRED" '($r | type) == "array" and ($r | length) > 0 and all($r[]; type == "string")' > /dev/null 2>&1; then
    echo "invalid the required-checks file must list job ids in a non-empty jobs array"; return 0
  fi
  if ! jq -en --argjson n "$NEEDS" '($n | type) == "object"' > /dev/null 2>&1; then
    echo "invalid needs must be the caller's toJSON(needs)"; return 0
  fi
  missing="$(jq -cn --argjson n "$NEEDS" --argjson r "$REQUIRED" '$r - ($n | keys)')"
  unlisted="$(jq -cn --argjson n "$NEEDS" --argjson r "$REQUIRED" '($n | keys) - $r')"
  absent="$(jq -cn --argjson r "$REQUIRED" --argjson m "$MANDATORY" '$m - $r')"
  if [ "$absent" != "[]" ]; then echo "missing jobs every repository must run: $absent"; return 0; fi
  if [ "$missing" != "[]" ]; then echo "missing listed in the required-checks file but not in needs: $missing"; return 0; fi
  if [ "$unlisted" != "[]" ]; then echo "unlisted in needs but not in the required-checks file: $unlisted"; return 0; fi
  echo "ok the needs are exactly the required-checks file"
}
