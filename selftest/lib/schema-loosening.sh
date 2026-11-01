# Generated from templates/selftest/lib/schema-loosening.sh and policy/constants.json by scripts/render.sh. Do not edit.
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
#   a required entry removed; an enum value added; additionalProperties or unevaluatedProperties false
#   made anything else; a key added under properties or patternProperties beside an additionalProperties
#   or unevaluatedProperties that was false (the new key accepts what the false refused, as below);
#   const, pattern or format changed or removed; and, since a change the guard cannot show safe needs the
#   label: a type set that gains a type or loses its type, any change under not, if, oneOf or contains
#   (they do not count the normal way); beside an additionalProperties, items, additionalItems,
#   unevaluatedProperties or unevaluatedItems that is not true, a properties or patternProperties key,
#   prefixItems or list items added, and beside an unevaluated one an additionalProperties, items,
#   additionalItems or contains added or an allOf, anyOf, oneOf, if, then, else, dependentSchemas or
#   dependencies changed (a key whose schema is the old additionalProperties is not counted); a
#   minContains below 1 added beside contains; a changed $defs or definitions in a file with a reference
#   and an unevaluated keyword that is not true; a $ref, $dynamicRef or $recursiveRef added,
#   removed or changed; an allOf, anyOf, prefixItems or list items that changes length; any constraint
#   keyword removed; a subschema made true or a false one opened; and any other keyword changed
#   (multipleOf, uniqueItems, ...).
#   Annotations (title, description, default, examples, $comment, ...) and $defs entries are not judged.
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
              elif ($k == "additionalProperties" or $k == "unevaluatedProperties") and $ov == false then $nv != false
              elif $k == "const" or (($k == "pattern" or $k == "format") and ($ov | type) == "string") then $nv != $ov
              else false end)
          | {path: ($p | map(tostring) | join("/")),
             pair: (if $k == "pattern" and ($ov | type) == "string" and ($nv | type) == "string"
                      and ($refrev | not) and (any($p[]; . as $e | $rev | index([$e])) | not)
                    then [$ov, $nv] else null end)} ]
        # What the rules above cannot show safe is loose. A schema place is the root, a keyword holding one
        # subschema, an entry of a keyword holding a map of them, or an item of one holding a list.
        + ( ["items","additionalItems","unevaluatedItems","contains","propertyNames","additionalProperties",
             "unevaluatedProperties","not","if","then","else"] as $sub
          | ["properties","patternProperties","dependentSchemas","$defs","definitions"] as $submap
          | ["allOf","anyOf","oneOf","prefixItems","items"] as $subarr
          | ["title","description","default","examples","$comment","deprecated","readOnly","writeOnly",
             "contentMediaType","contentEncoding","contentSchema","$anchor","$dynamicAnchor","$id","$schema",
             "$vocabulary","$defs","definitions"] as $annot
          | ["$ref","$dynamicRef","$recursiveRef"] as $refs
          | ($mins + $maxs + ["required","enum","const","pattern","format","type"]) as $handled
          | def isschema: length == 0
              or ((.[-1] | type) == "string" and (.[-1] | IN($sub[])) and (.[:-1] | isschema))
              or (length >= 2 and (.[-2] | type) == "string" and (.[-2] | IN($submap[])) and (.[-1] | type) == "string" and (.[:-2] | isschema))
              or (length >= 2 and (.[-2] | type) == "string" and (.[-2] | IN($subarr[])) and (.[-1] | type) == "number" and (.[:-2] | isschema));
            def at($t; $p): $t | try getpath($p) catch null;
            def closed: type == "object" and (.additionalProperties == false or .unevaluatedProperties == false);
            def where($p): if ($p | length) == 0 then "(root)" else $p | map(tostring) | join("/") end;
            ([[]] + [$old | paths | select(isschema)]) as $places
          | ([[]] + [$new | paths | select(isschema)]) as $newplaces
          | [ ( $places[] as $s | at($old; $s) as $o | at($new; $s) as $n
                | if ($o | type) == "boolean" then
                    # A false subschema opened.
                    (select($o == false and ($s | length) > 0 and $n != false and $n != null) | where($s))
                  elif ($o | type) != "object" then empty
                  elif $n == true then
                    # A subschema with constraints made true.
                    (select(any($o | keys[]; IN($annot[]) | not)) | where($s))
                  elif ($n | type) != "object" then empty
                  else
                    ( $o | keys[] as $k
                      | select($k | IN($annot[]) | not)
                      | if ($n | has($k)) | not then
                          # A constraint removed (a removed properties map under a closed object refuses more).
                          select(($k | IN("properties", "patternProperties")) and ($o | closed) and ($n | closed) | not)
                          | where($s + [$k])
                        elif $k == "type" then
                          # A type set that gained a type.
                          ($o.type | if type == "array" then . else [.] end) as $ot
                          | ($n.type | if type == "array" then . elif type == "string" then [.] else [] end) as $nt
                          | select(any($nt[]; . as $x | $ot | index([$x]) | not)) | where($s + [$k])
                        elif $k | IN($handled[]) then empty
                        elif $k | IN($refs[]) then empty
                        elif $k | IN("not", "if", "oneOf", "contains") then
                          # Not monotonic (contains with maxContains counts matches): any change may accept more.
                          select($o[$k] != $n[$k]) | where($s + [$k])
                        elif $k | IN("allOf", "anyOf", "prefixItems") then
                          # A list of subschemas that changed length cannot be compared item by item.
                          select(($o[$k] | type) == "array" and (($n[$k] | type) != "array" or ($n[$k] | length) != ($o[$k] | length)))
                          | where($s + [$k])
                        elif $k == "items" and ($o[$k] | type) == "array" then
                          select(($n[$k] | type) != "array" or ($n[$k] | length) != ($o[$k] | length)) | where($s + [$k])
                        elif $k | IN("properties", "patternProperties", "dependentSchemas") then
                          # An entry removed, unless the object stays closed (then the entry is refused).
                          ($n[$k] | if type == "object" then keys else [] end) as $nk
                          | ($o[$k] | if type == "object" then keys[] else empty end)
                          | select(. as $x | $nk | index([$x]) | not)
                          | select($k == "dependentSchemas" or ((($o | closed) and ($n | closed)) | not))
                          | where($s + [$k, .])
                        elif $k | IN($sub[]) or IN($submap[]) or IN($subarr[]) then empty
                        else
                          # Any other keyword changed (multipleOf, uniqueItems, dependentRequired, ...).
                          select($o[$k] != $n[$k]) | where($s + [$k])
                        end )
                  end ),
              # Beside a keyword that judges what the others leave (additionalProperties, items, additionalItems,
              # unevaluatedProperties, unevaluatedItems, unless it is true), a keyword that takes more properties
              # or items for itself moves them out from under it: what it refused may now pass.
              ( $places[] as $s | at($old; $s) as $o | at($new; $s) as $n
                | select(($o | type) == "object" and ($n | type) == "object")
                | def judges($k): $o | has($k) and .[$k] != true;
                  def keysof($v): $v | if type == "object" then keys else [] end;
                  def len($v): $v | if type == "array" then length else -1 end;
                  def added($k): ($o | has($k) | not) and ($n | has($k));
                  ( select(judges("additionalProperties") or judges("unevaluatedProperties"))
                    | ["properties", "patternProperties"][] as $k
                    | keysof($o[$k]) as $ok | keysof($n[$k])[] | select(. as $x | $ok | index([$x]) | not)
                    # A key whose schema is the old additionalProperties accepts what it did before.
                    | select(judges("unevaluatedProperties") or $n[$k][.] != $o.additionalProperties)
                    | where($s + [$k, .]) ),
                  ( select(judges("items") or judges("unevaluatedItems"))
                    | select(len($n.prefixItems) > len($o.prefixItems)) | where($s + ["prefixItems"]) ),
                  ( select(judges("additionalItems") or judges("unevaluatedItems"))
                    | select(($n.items | type) == "array" and len($n.items) > len($o.items)) | where($s + ["items"]) ),
                  ( select(judges("unevaluatedProperties")) | select(added("additionalProperties")) | where($s + ["additionalProperties"]) ),
                  ( select(judges("unevaluatedItems")) | ["items", "additionalItems", "contains"][] as $k
                    | select(added($k)) | where($s + [$k]) ),
                  ( select(judges("unevaluatedProperties") or judges("unevaluatedItems"))
                    | ["allOf", "anyOf", "oneOf", "if", "then", "else", "dependentSchemas", "dependencies"][] as $k
                    | select($o[$k] != $n[$k]) | where($s + [$k]) ),
                  # minContains defaults to 1 beside contains: one added below that accepts an array with no match.
                  ( select(($o | has("contains")) and added("minContains") and ($n.minContains | type) == "number" and $n.minContains < 1)
                    | where($s + ["minContains"]) ) ),
              # A definition a reference reaches can evaluate properties or items for an unevaluated keyword the
              # guard cannot tie it to, so in a file with both a changed $defs or definitions is loose.
              ( select(any($old | .. | objects; (has("unevaluatedProperties") and .unevaluatedProperties != true)
                                                 or (has("unevaluatedItems") and .unevaluatedItems != true)))
                | select(any($old, $new | paths; .[-1] | IN($refs[])))
                | ["$defs", "definitions"][] as $k | select(at($old; [$k]) != at($new; [$k])) | where([$k]) ),
              # A reference added, removed or changed: the guard cannot follow it.
              ( ($places + $newplaces | unique)[] as $s
                | $refs[] as $r
                | (at($old; $s) | if type == "object" then .[$r] else null end) as $or
                | (at($new; $s) | if type == "object" then .[$r] else null end) as $nr
                | select($or != $nr) | where($s + [$r]) ) ]
          | map({path: ., pair: null}) )
        | reduce .[] as $e ([]; if any(.[]; .path == $e.path) then . else . + [$e] end)' 2>/dev/null)"; then
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
