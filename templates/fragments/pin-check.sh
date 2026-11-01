# main: prints "ok ..." when every uses: in ROOT/.github/workflows/*.yml or *.yaml that names a workflow
# or action of ORG is pinned to a full commit (40 lower-case hex characters), otherwise
# "unpinned [<file>:<line> <ref>, ...]". A branch or a tag can move, so either is refused; a uses: of
# another owner or a docker:// image is not judged. The owner is compared without case.
# Each file is parsed as YAML (yq, with every alias and merge key that names an alias expanded first), so a uses: written as
# a quoted key, a flow mapping, a block scalar or an alias is judged like any other. The uses: GitHub reads
# are judged: jobs.<id>.uses and jobs.<id>.steps[].uses.
# A local uses: (./path) is followed: a directory is a composite action, read from its action.yml or
# action.yaml (runs.steps[].uses), a file is a reusable workflow. Each file is read once, and nesting deeper
# than the limit is refused. A local path that leaves the repository (a ".." segment) or names nothing is refused.
# A file that does not parse, a uses: that is not a string, or a local reference that cannot be followed prints
# "invalid <why>": the check refuses what it cannot read.
# This check downloads nothing itself; the caller fetches yq (pinned by sha256) before it runs.
#   ROOT  the checked-out repository     ORG  the organisation whose references must be pinned
#   YQ    the yq (mikefarah, v4) binary, default yq
pc_uses() {
  case "$2" in
    workflow) "$yq" -o=json 'explode(.) | [.jobs // {} | to_entries[]
        | ((.value.uses | select(. != null)), (.value.steps // [] | .[] | .uses | select(. != null)))
        | {"line": line, "v": .}]' "$1" ;;
    *) "$yq" -o=json 'explode(.) | [.runs.steps // [] | .[] | .uses | select(. != null) | {"line": line, "v": .}]' "$1" ;;
  esac
}

# pc_scan <file> <workflow|action> <depth>: appends unpinned references to pc_found, sets pc_invalid and returns 1
# when something cannot be read.
pc_scan() {
  local file="$1" kind="$2" depth="$3" rel uses line one local_refs v path target
  rel="${file#"${ROOT:-.}/"}"
  case "$pc_seen" in *"|$rel|"*) return 0 ;; esac
  pc_seen="$pc_seen|$rel|"
  uses="$(pc_uses "$file" "$kind" 2>/dev/null)" || { pc_invalid="$rel is not YAML"; return 1; }
  line="$(jq -sr '[add // [] | .[] | select((.v | type) != "string") | .line] | first // empty' <<<"$uses" 2>/dev/null)" \
    || { pc_invalid="$rel could not be judged"; return 1; }
  [ -z "$line" ] || { pc_invalid="$rel:$line uses is not a string"; return 1; }
  one="$(jq -sr --arg org "$(printf '%s' "$ORG" | tr '[:upper:]' '[:lower:]')" --arg f "$rel" '
      (add // []) | .[]
      | (.v | gsub("^\\s+|\\s+$"; "")) as $v
      | ($v | split("/")[0] | ascii_downcase) as $owner
      | select($owner == $org and ($v | contains("/")))
      | (if ($v | contains("@")) then ($v | sub("^.*@"; "")) else "(none)" end) as $ref
      | select($ref | test("^[0-9a-f]{40}$") | not)
      | "\($f):\(.line) \($ref)"' <<<"$uses")" || { pc_invalid="$rel could not be judged"; return 1; }
  [ -z "$one" ] || pc_found="$pc_found$one"$'\n'
  local_refs="$(jq -sr '(add // []) | .[] | (.v | gsub("^\\s+|\\s+$"; "")) as $v | select($v | startswith("./")) | "\(.line)\t\($v)"' <<<"$uses")" \
    || { pc_invalid="$rel could not be judged"; return 1; }
  while IFS=$'\t' read -r line v; do
    [ -n "$v" ] || continue
    path="${v#./}"
    if [ "$depth" -ge "$pc_max" ]; then pc_invalid="$rel:$line local uses nest deeper than $pc_max"; return 1; fi
    case "/$path/" in */../*) pc_invalid="$rel:$line local uses $v leaves the repository"; return 1 ;; esac
    target="${ROOT:-.}/$path"
    if [ -d "$target" ]; then
      if [ -f "$target/action.yml" ]; then target="$target/action.yml"
      elif [ -f "$target/action.yaml" ]; then target="$target/action.yaml"
      else pc_invalid="$rel:$line local action $v has no action.yml"; return 1; fi
      pc_scan "$target" action $((depth + 1)) || return 1
    elif [ -f "$target" ]; then
      pc_scan "$target" workflow $((depth + 1)) || return 1
    else
      pc_invalid="$rel:$line local uses $v names nothing"; return 1
    fi
  done <<<"$local_refs"
}

main() {
  local dir="${ROOT:-.}/.github/workflows" yq="${YQ:-yq}" files=() f
  local pc_found="" pc_invalid="" pc_seen="|" pc_max=@@pinCheck.maxLocalDepth@@
  [ -n "${ORG:-}" ] || { echo "invalid ORG is empty"; return 0; }
  [ -d "$dir" ] || { echo "ok no workflows"; return 0; }
  for f in "$dir"/*.yml "$dir"/*.yaml; do [ -f "$f" ] && files+=("$f"); done
  [ "${#files[@]}" -gt 0 ] || { echo "ok no workflows"; return 0; }
  command -v "$yq" > /dev/null 2>&1 || { echo "invalid no yq to read the workflows"; return 0; }
  for f in "${files[@]}"; do
    pc_scan "$f" workflow 0 || { echo "invalid $pc_invalid"; return 0; }
  done
  if [ -z "$pc_found" ]; then echo "ok every $ORG reference is pinned to a commit"; return 0; fi
  echo "unpinned $(printf '%s' "$pc_found" | jq -Rsc 'split("\n") | map(select(length > 0))')"
}
