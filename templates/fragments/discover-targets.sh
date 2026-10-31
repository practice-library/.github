# main: prints "ok <JSON array>" with what the check in ROW (one row of checks) runs on, or "error <why>".
# With a targetFile, every <dir>/<targetFile> tracked by git is a target. The file holds one object or a
# list of them; each must have every key in inputs (paths, made relative to the repository root) and may
# have keys from optionalPathInputs (paths, made relative the same way; a value of several lines is one
# path per line) and from optionalInputs (values, copied as they are). Without a targetFile there is one
# repository-wide target. Run it from the repository root.
main() {
  local target_file found targets
  target_file="$(jq -r '.targetFile // empty' <<<"$ROW")" || { echo "error the row is not valid JSON"; return 0; }
  if [ -z "$target_file" ]; then echo 'ok [{"target":"repository"}]'; return 0; fi
  found="$(git ls-files -- "$target_file" "*/$target_file" | { grep -v -E "${EXCLUDE:-^$}" || true; })"
  [ -n "$found" ] || { echo "error no $target_file found"; return 0; }
  if ! targets="$(set -o pipefail; while IFS= read -r f; do
      jq -c --arg dir "$(dirname "$f")" --arg f "$f" --argjson row "$ROW" '
        (if type == "array" then . else [.] end)[]
        | ($row.inputs + ($row.optionalPathInputs // [])) as $paths
        | if type != "object" then error($f + ": each target must be an object")
          elif ((keys - $paths - ($row.optionalInputs // [])) | length) > 0 then error($f + ": unknown keys " + ((keys - $paths - ($row.optionalInputs // [])) | tojson))
          elif (($row.inputs - keys) | length) > 0 then error($f + ": missing keys " + (($row.inputs - keys) | tojson))
          elif any(to_entries[]; (.key as $k | $paths | index([$k])) != null and (.value | type) != "string") then error($f + ": a path must be a string")
          else {target: $dir} + with_entries(
            if (.key as $k | $paths | index([$k])) != null
            then .value |= (split("\n") | map(select(length > 0) | if $dir == "." then . else $dir + "/" + . end) | join("\n")) else . end) end' "$f" || exit 1
    done <<<"$found" | jq -sc '.')"; then
    echo "error a $target_file is not valid"; return 0
  fi
  [ "$(jq 'length' <<<"$targets")" -gt 0 ] || { echo "error no target in any $target_file"; return 0; }
  while IFS= read -r p; do
    [ -e "$p" ] || { echo "error $p does not exist"; return 0; }
  done < <(jq -r --argjson row "$ROW" '.[] | .[($row.inputs + ($row.optionalPathInputs // []))[]] // empty | split("\n")[]' <<<"$targets")
  echo "ok $targets"
}
