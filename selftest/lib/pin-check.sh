# Generated from templates/selftest/lib/pin-check.sh and policy/constants.json by scripts/render.sh. Do not edit.
# main: prints "ok ..." when every uses: in ROOT/.github/workflows/*.yml or *.yaml that names a workflow
# or action of ORG is pinned to a full commit (40 lower-case hex characters), otherwise
# "unpinned [<file>:<line> <ref>, ...]". A branch or a tag can move, so either is refused; a uses: of
# another owner, a local ./ path or a docker:// image is not judged. The owner is compared without case.
# Each file is parsed as YAML (yq, which follows anchors, aliases and merge keys), so a uses: written as
# a quoted key, a flow mapping, a block scalar or an alias is judged like any other. The uses: GitHub reads
# are judged: jobs.<id>.uses and jobs.<id>.steps[].uses. A file that does not parse prints "invalid".
#   ROOT  the checked-out repository     ORG  the organisation whose references must be pinned
#   YQ    the yq (mikefarah, v4) binary, default yq
main() {
  local dir="${ROOT:-.}/.github/workflows" yq="${YQ:-yq}" files=() f found="" uses one
  [ -n "${ORG:-}" ] || { echo "invalid ORG is empty"; return 0; }
  [ -d "$dir" ] || { echo "ok no workflows"; return 0; }
  for f in "$dir"/*.yml "$dir"/*.yaml; do [ -f "$f" ] && files+=("$f"); done
  [ "${#files[@]}" -gt 0 ] || { echo "ok no workflows"; return 0; }
  command -v "$yq" > /dev/null 2>&1 || { echo "invalid no yq to read the workflows"; return 0; }
  for f in "${files[@]}"; do
    uses="$("$yq" -o=json '[.jobs // {} | to_entries[]
        | ((.value.uses | select(. != null)), (.value.steps // [] | .[] | .uses | select(. != null)))
        | {"line": line, "v": .}]' "$f" 2>/dev/null)" \
      || { echo "invalid ${f#"${ROOT:-.}/"} is not YAML"; return 0; }
    one="$(jq -sr --arg org "$(printf '%s' "$ORG" | tr '[:upper:]' '[:lower:]')" --arg f "${f#"${ROOT:-.}/"}" '
        (add // []) | .[]
        | (.v | tostring | gsub("^\\s+|\\s+$"; "")) as $v
        | ($v | split("/")[0] | ascii_downcase) as $owner
        | select($owner == $org and ($v | contains("/")))
        | (if ($v | contains("@")) then ($v | sub("^.*@"; "")) else "(none)" end) as $ref
        | select($ref | test("^[0-9a-f]{40}$") | not)
        | "\($f):\(.line) \($ref)"' <<<"$uses")" || { echo "invalid ${f#"${ROOT:-.}/"} could not be judged"; return 0; }
    [ -n "$one" ] && found="$found$one"$'\n'
  done
  if [ -z "$found" ]; then echo "ok every $ORG reference is pinned to a commit"; return 0; fi
  echo "unpinned $(printf '%s' "$found" | jq -Rsc 'split("\n") | map(select(length > 0))')"
}
