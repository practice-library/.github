# Generated from templates/selftest/lib/schema-mutate.sh and policy/constants.json by scripts/render.sh. Do not edit.
# main: prints the schema in SCHEMA with one mutant applied, as one line of JSON, or "invalid ..." when
# the mutant cannot be applied. A mutant names a place by JSON Pointer (RFC 6901: "/a/b", "~1" for "/"
# and "~0" for "~"); the place must exist, so a mutant that names nothing is an error, never a pass.
#   SCHEMA  a JSON file
#   MUTANT  {"pointer": "/...", "mutation": "delete"} removes the place,
#           {"pointer": "/...", "mutation": "true"} replaces it with true (a subschema that accepts all),
#           {"pointer": "/...", "set": <value>} replaces it with the value
main() {
  local out
  if ! out="$(jq -c --argjson m "${MUTANT:-null}" '
      def tokens:
        if (type == "string") and startswith("/") then
          .[1:] | split("/")
          | map(if test("~([^01]|$)") then error("~ must be written ~0 or ~1") else gsub("~1"; "/") | gsub("~0"; "~") end)
        else error("pointer must start with /") end;
      . as $doc
      | ($m | if type == "object" and (.pointer | type) == "string" then . else error("mutant must be an object with a pointer") end)
      | ($m.pointer | tokens) as $t
      | (reduce $t[] as $k ({path: [], ok: true};
          if .ok | not then . else
            .path as $p | ($doc | getpath($p)) as $here
            | if ($here | type) == "object" and ($here | has($k)) then .path += [$k]
              elif ($here | type) == "array" and ($k | test("^(0|[1-9][0-9]*)$")) and (($k | tonumber) < ($here | length)) then .path += [$k | tonumber]
              else .ok = false end end)) as $r
      | if ($r.ok | not) then error("no such place: " + $m.pointer)
        elif ($m | has("set")) and ($m | has("mutation")) then error("a mutant has either mutation or set")
        elif ($m | has("set")) then $doc | setpath($r.path; $m.set)
        elif $m.mutation == "delete" then $doc | delpaths([$r.path])
        elif $m.mutation == "true" then $doc | setpath($r.path; true)
        else error("mutation must be delete or true, or use set") end' "$SCHEMA" 2>&1)"; then
    echo "invalid ${out#jq: error (at *): }"; return 0
  fi
  printf '%s\n' "$out"
}
