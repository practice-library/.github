# Generated from templates/selftest/lib/size-count.sh and policy/constants.json by scripts/render.sh. Do not edit.
# main: prints "ok <n> non-fixture lines (limit <L>)" when the lines the change adds or changes outside
# fixtures are at most LIMIT, "over <n> non-fixture lines, more than <L>: split the pull request" when
# they are more, or "invalid ..." when an input cannot be used.
#   NUMSTAT   output of git diff --numstat -M: "<added><TAB><deleted><TAB><path>", a rename written as
#             "<old> => <new>" or "<dir>/{<old> => <new>}/<rest>"; a binary file shows "-" and counts 0.
#             When NUMSTAT is unset, main reads it from git for MB..HEAD (with -z, so a path is never
#             quoted) and recounts each file git calls binary from its diff taken with --text (its added
#             newline-separated lines), so neither a .gitattributes "binary" nor a NUL byte can hide a
#             text file, whatever its name.
#   FIXTURES  JSON array of fixture entries. An entry starting and ending in / is a directory from the
#             root ("/rulesets/"); any other entry ending in / is a directory anywhere in the path
#             ("examples/" covers spec/x/examples/a.json); an entry with no / is a file name anywhere
#             ("INDEX.md"); any other entry is one exact path from the root, a leading / allowed. The
#             entry "/" alone would cover every path and is refused.
#   LIMIT     the most non-fixture lines that pass, a whole number
# A changed line counts once, as an added line; a renamed file counts by its new path, once. Only a
# NUMSTAT given as input has its rename arrows rewritten; read from git, paths are taken as they are.
# The new path of a numstat path: "<old> => <new>" or "<dir>/{<old> => <new>}/<rest>".
SIZE_NEWPATH='def newpath:
  if test("\\{.* => .*\\}") then sub("\\{(?<a>[^{}]*) => (?<b>[^{}]*)\\}"; "\(.b)") | gsub("//"; "/")
  elif test(" => ") then sub("^.* => "; "") else . end;'
main() {
  [[ "${LIMIT:-}" =~ ^[0-9]+$ ]] || { echo "invalid LIMIT must be a whole number"; return 0; }
  jq -en --argjson f "${FIXTURES:-null}" '($f | type) == "array" and all($f[]; type == "string" and length > 0 and . != "/")' > /dev/null 2>&1 \
    || { echo "invalid FIXTURES must be a JSON array of non-empty strings, not \"/\""; return 0; }
  local n raw rec added deleted path old recount="" plain=false
  if [ -z "${NUMSTAT+x}" ]; then
    # Read from git with -z, a rename already gives its new path, so no path is rewritten: a directory
    # named "a => selftest" stays that directory.
    plain=true
    # -z gives every path as it is: without it git quotes a path with non-ASCII bytes, a tab or a quote,
    # and the quoted name would match no file when the line is recounted.
    raw="$(mktemp)" || { echo "invalid the diff could not be read"; return 0; }
    git diff --numstat -z -M --no-ext-diff --no-textconv "$MB" "$HEAD" > "$raw" \
      || { rm -f "$raw"; echo "invalid the diff could not be read"; return 0; }
    # Each record is split on its first two tabs by hand: read would trim tabs at the ends of the path.
    while IFS= read -r -d '' rec; do
      added="${rec%%$'\t'*}"; rec="${rec#*$'\t'}"; deleted="${rec%%$'\t'*}"; path="${rec#*$'\t'}"
      # A rename is "<added><TAB><deleted><TAB>" followed by the old and the new path.
      if [ -z "$path" ]; then IFS= read -r -d '' old; IFS= read -r -d '' path; fi
      # The count below is one line per path, so a path holding a newline cannot be counted.
      if [[ "$path" == *$'\n'* ]]; then rm -f "$raw"; echo "invalid a changed path holds a newline"; return 0; fi
      if [ "$added" = - ]; then
        added="$(git --literal-pathspecs diff --text --no-textconv --no-ext-diff --no-color --unified=0 "$MB" "$HEAD" -- "$path" \
          | LC_ALL=C awk 'f && /^\+/ { n++ } /^@@/ { f = 1 } END { print n + 0 }')" \
          || { rm -f "$raw"; echo "invalid the diff of a binary file could not be read"; return 0; }
      fi
      recount="$recount$added"$'\t'"$deleted"$'\t'"$path"$'\n'
    done < "$raw"
    rm -f "$raw"
    NUMSTAT="$recount"
  fi
  if ! n="$(printf '%s\n' "${NUMSTAT:-}" | jq -R --argjson f "$FIXTURES" --argjson plain "$plain" -n '
      '"$SIZE_NEWPATH"'
      def fixture($p):
        any($f[]; . as $e
          | if ($e | startswith("/")) and ($e | endswith("/")) then ($p | startswith($e | ltrimstr("/")))
            elif ($e | endswith("/")) then (("/" + $p) | contains("/" + $e))
            elif ($e | contains("/")) then $p == ($e | ltrimstr("/"))
            else ($p | split("/") | last) == $e end);
      [inputs | select(length > 0) | split("\t")
        | if length < 3 or (.[0] | test("^([0-9]+|-)$") | not) then error("bad numstat line: " + join("\t")) else . end
        | {added: (if .[0] == "-" then 0 else (.[0] | tonumber) end), path: (.[2:] | join("\t") | if $plain then . else newpath end)}
        | select(fixture(.path) | not) | .added] | add // 0' 2>/dev/null)"; then
    echo "invalid NUMSTAT is not git diff --numstat output"; return 0
  fi
  if [ "$n" -le "$LIMIT" ]; then echo "ok $n non-fixture lines (limit $LIMIT)"
  else echo "over $n non-fixture lines, more than $LIMIT: split the pull request"; fi
}
