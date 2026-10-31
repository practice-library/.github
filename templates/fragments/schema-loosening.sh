# main: judges one changed JSON file. OLD_FILE is the file on the base commit; NEW_FILE the file on the
# head, or empty when the change deleted it. Prints "invalid ..." when OLD_FILE cannot be read, "skip ..."
# when it is not a JSON schema (its top-level $schema does not name a json-schema.org meta-schema, as an
# instance pointing at its own schema does not), loose ["(deleted)"] when a schema was deleted, and
# otherwise what compare prints.
main() {
  [ -r "${OLD_FILE:-}" ] || { echo "invalid cannot read the base file"; return 0; }
  if ! jq -e 'type == "object" and ((.["$schema"] // "") | type == "string" and test("^https?://json-schema\\.org/"))' "$OLD_FILE" > /dev/null 2>&1; then
    echo "skip not a JSON schema"; return 0
  fi
  if [ -z "${NEW_FILE:-}" ]; then echo 'loose ["(deleted)"]'; return 0; fi
  compare
}

# compare: prints "ok ..." when the schema in NEW_FILE accepts nothing more than the one in OLD_FILE by
# the rules below, otherwise "loose [<path>, ...]". Rules, at every place in the schema:
#   a minimum (minItems, minLength, minProperties, minimum, exclusiveMinimum, minContains) lowered or removed;
#   a maximum (maxItems, maxLength, maxProperties, maximum, exclusiveMaximum, maxContains) raised or removed;
#   a required entry removed; an enum value added; additionalProperties false made anything else;
#   const, pattern or format changed or removed.
# A pattern changed to another string is not loose when the pair is listed in TIGHTEN (unset means no
# list): a JSON array of {"sha256": <64 lower-case hex>, "why": <text>}, each the SHA-256 of the pair
# written as compact JSON, ["<old pattern>","<new pattern>"], with no newline. A list entry is a reviewed
# claim that the new pattern accepts nothing the old one refused. That makes the schema tighter only where
# a pattern counts the normal way, so the list is ignored for a pattern under not, if, oneOf or contains,
# and for the whole file when either schema has a $ref, $dynamicRef or $recursiveRef under one of those
# (it may point at the pattern). A reference from another file is not seen: the guard judges one file. A malformed list prints "invalid", so
# nothing passes on a list that cannot be read; a removed pattern, or a pair not listed, stays loose.
compare() {
  local out list entry path pair hash loose="[]" tightened="[]"
  list="${TIGHTEN-[]}"
  if ! jq -se 'length == 1 and (.[0] | type == "array" and all(.[]; type == "object" and (.sha256 | type == "string" and test("^[0-9a-f]{64}$")) and (.why | type == "string" and length > 0)))' <<<"$list" > /dev/null 2>&1; then
    echo "invalid TIGHTEN must be a JSON array of {sha256, why}"; return 0
  fi
  if ! out="$(jq -cn --slurpfile o "$OLD_FILE" --slurpfile n "$NEW_FILE" '
      $o[0] as $old | $n[0] as $new
      | ["minItems","minLength","minProperties","minimum","exclusiveMinimum","minContains"] as $mins
      | ["maxItems","maxLength","maxProperties","maximum","exclusiveMaximum","maxContains"] as $maxs
      | ["not","if","oneOf","contains"] as $rev
      | ([[$old, $new][] | paths | select((.[-1] | IN("$ref", "$dynamicRef", "$recursiveRef")) and any(.[]; . as $e | $rev | index([$e])))] | length > 0) as $refrev
      | [ $old | paths | select(length > 0 and (.[-1] | type) == "string") ] as $ps
      | [ $ps[] as $p
          | $p[-1] as $k
          | ($old | getpath($p)) as $ov
          | ($new | try getpath($p) catch null) as $nv
          | select(
              if ($mins | index([$k])) != null and ($ov | type) == "number" then ($nv | type) != "number" or $nv < $ov
              elif ($maxs | index([$k])) != null and ($ov | type) == "number" then ($nv | type) != "number" or $nv > $ov
              elif $k == "required" and ($ov | type) == "array" then
                ($nv | if type == "array" then . else [] end) as $nr | any($ov[]; . as $x | ($nr | index([$x])) == null)
              elif $k == "enum" and ($ov | type) == "array" then
                ($nv | type) != "array" or any($nv[]; . as $x | ($ov | index([$x])) == null)
              elif $k == "additionalProperties" and $ov == false then $nv != false
              elif $k == "const" or (($k == "pattern" or $k == "format") and ($ov | type) == "string") then $nv != $ov
              else false end)
          | {path: ($p | map(tostring) | join("/")),
             pair: (if $k == "pattern" and ($ov | type) == "string" and ($nv | type) == "string"
                      and ($refrev | not) and (any($p[]; . as $e | $rev | index([$e])) | not)
                    then [$ov, $nv] else null end)} ]' 2>/dev/null)"; then
    echo "invalid both files must be JSON"; return 0
  fi
  while IFS= read -r entry; do
    path="$(jq -r '.path' <<<"$entry")"
    pair="$(jq -cj '.pair' <<<"$entry")"
    if [ "$pair" != null ]; then
      hash="$(printf '%s' "$pair" | sha256sum | cut -d' ' -f1)"
      if jq -e --arg h "$hash" 'any(.[]; .sha256 == $h)' <<<"$list" > /dev/null; then
        tightened="$(jq -c --arg p "$path" '. + [$p]' <<<"$tightened")"; continue
      fi
    fi
    loose="$(jq -c --arg p "$path" '. + [$p]' <<<"$loose")"
  done < <(jq -c '.[]' <<<"$out")
  if [ "$loose" != "[]" ]; then echo "loose $loose"
  elif [ "$tightened" != "[]" ]; then echo "ok nothing loosened; listed tightenings $tightened"
  else echo "ok nothing loosened"; fi
}
