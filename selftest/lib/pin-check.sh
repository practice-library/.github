# Generated from templates/selftest/lib/pin-check.sh and policy/constants.json by scripts/render.sh. Do not edit.
# main: prints "ok ..." when every uses: in ROOT/.github/workflows/*.yml or *.yaml that names a workflow
# or action of ORG is pinned to a full commit (40 lower-case hex characters), otherwise
# "unpinned [<file>:<line> <ref>, ...]". A branch or a tag can move, so either is refused; a uses: of
# another owner, a local ./ path or a docker:// image is not judged. The owner is compared without case.
#   ROOT  the checked-out repository     ORG  the organisation whose references must be pinned
main() {
  local dir="${ROOT:-.}/.github/workflows" files=() f found
  [ -n "${ORG:-}" ] || { echo "invalid ORG is empty"; return 0; }
  [ -d "$dir" ] || { echo "ok no workflows"; return 0; }
  for f in "$dir"/*.yml "$dir"/*.yaml; do [ -f "$f" ] && files+=("$f"); done
  [ "${#files[@]}" -gt 0 ] || { echo "ok no workflows"; return 0; }
  found="$(awk -v org="$(printf '%s' "$ORG" | tr '[:upper:]' '[:lower:]')" '
    /^[ \t]*(-[ \t]+)?uses:[ \t]*/ {
      v = $0
      sub(/^[ \t]*(-[ \t]+)?uses:[ \t]*/, "", v)
      sub(/[ \t]+#.*$/, "", v); sub(/[ \t]+$/, "", v)
      if (v ~ /^".*"$/ || v ~ /^'"'"'.*'"'"'$/) v = substr(v, 2, length(v) - 2)
      owner = v; sub(/\/.*$/, "", owner)
      if (tolower(owner) != org || v !~ /\//) next
      ref = v; if (ref ~ /@/) sub(/^.*@/, "", ref); else ref = "(none)"
      if (ref !~ /^[0-9a-f]+$/ || length(ref) != 40) {
        f = FILENAME; sub(/^.*\/\.github\/workflows\//, ".github/workflows/", f)
        print f ":" FNR " " ref
      }
    }' "${files[@]}")"
  if [ -z "$found" ]; then echo "ok every $ORG reference is pinned to a commit"; return 0; fi
  echo "unpinned $(printf '%s\n' "$found" | jq -Rsc 'split("\n") | map(select(length > 0))')"
}
