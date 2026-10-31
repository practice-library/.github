# Generated from templates/selftest/lib/schema-loosening.sh and policy/constants.json by scripts/render.sh. Do not edit.
# main: prints "ok ..." when the schema in NEW_FILE accepts nothing more than the one in OLD_FILE by
# the rules below, otherwise "loose [<path>, ...]". Rules, at every place in the schema:
#   a minimum (minItems, minLength, minProperties, minimum, exclusiveMinimum, minContains) lowered or removed;
#   a maximum (maxItems, maxLength, maxProperties, maximum, exclusiveMaximum, maxContains) raised or removed;
#   a required entry removed; an enum value added; additionalProperties false made anything else;
#   const, pattern or format changed or removed.
main() {
  local out
  if ! out="$(jq -cn --slurpfile o "$OLD_FILE" --slurpfile n "$NEW_FILE" '
      $o[0] as $old | $n[0] as $new
      | ["minItems","minLength","minProperties","minimum","exclusiveMinimum","minContains"] as $mins
      | ["maxItems","maxLength","maxProperties","maximum","exclusiveMaximum","maxContains"] as $maxs
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
          | $p | map(tostring) | join("/") ]' 2>/dev/null)"; then
    echo "invalid both files must be JSON"; return 0
  fi
  if [ "$out" = "[]" ]; then echo "ok nothing loosened"; else echo "loose $out"; fi
}
