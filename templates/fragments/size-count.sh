# main: prints "ok <n> non-fixture lines (limit <L>)" when the lines the change adds or changes outside
# fixtures are at most LIMIT, "over <n> non-fixture lines, more than <L>: split the pull request" when
# they are more, or "invalid ..." when an input cannot be used.
#   NUMSTAT   output of git diff --numstat -M: "<added><TAB><deleted><TAB><path>", a rename written as
#             "<old> => <new>" or "<dir>/{<old> => <new>}/<rest>"; a binary file shows "-" and counts 0.
#             When NUMSTAT is unset, main reads it from git for MB..HEAD and recounts each file git
#             calls binary from its diff taken with --text (its added newline-separated lines), so
#             neither a .gitattributes "binary" nor a NUL byte can hide a text file.
#   FIXTURES  JSON array of fixture entries. An entry starting and ending in / is a directory from the
#             root ("/rulesets/"); any other entry ending in / is a directory anywhere in the path
#             ("examples/" covers spec/x/examples/a.json); an entry with no / is a file name anywhere
#             ("INDEX.md"); any other entry is one exact path from the root, a leading / allowed. The
#             entry "/" alone would cover every path and is refused.
#   LIMIT     the most non-fixture lines that pass, a whole number
# A changed line counts once, as an added line; a renamed file counts by its new path, once.
# The new path of a numstat path: "<old> => <new>" or "<dir>/{<old> => <new>}/<rest>".
SIZE_NEWPATH='def newpath:
  if test("\\{.* => .*\\}") then sub("\\{(?<a>[^{}]*) => (?<b>[^{}]*)\\}"; "\(.b)") | gsub("//"; "/")
  elif test(" => ") then sub("^.* => "; "") else . end;'
main() {
  [[ "${LIMIT:-}" =~ ^[0-9]+$ ]] || { echo "invalid LIMIT must be a whole number"; return 0; }
  jq -en --argjson f "${FIXTURES:-null}" '($f | type) == "array" and all($f[]; type == "string" and length > 0 and . != "/")' > /dev/null 2>&1 \
    || { echo "invalid FIXTURES must be a JSON array of non-empty strings, not \"/\""; return 0; }
  local n line path added recount=""
  if [ -z "${NUMSTAT+x}" ]; then
    NUMSTAT="$(git diff --numstat -M --no-ext-diff --no-textconv "$MB" "$HEAD")" \
      || { echo "invalid the diff could not be read"; return 0; }
    while IFS= read -r line; do
      case "$line" in
        -$'\t'-$'\t'*)
          path="$(jq -Rr "$SIZE_NEWPATH newpath" <<<"${line#-$'\t'-$'\t'}")"
          added="$(git diff --text --no-textconv --no-ext-diff --no-color --unified=0 "$MB" "$HEAD" -- "$path" \
            | LC_ALL=C awk 'f && /^\+/ { n++ } /^@@/ { f = 1 } END { print n + 0 }')" \
            || { echo "invalid the diff of $path could not be read"; return 0; }
          recount="$recount$added"$'\t'0$'\t'"$path"$'\n' ;;
        *) [ -n "$line" ] && recount="$recount$line"$'\n' ;;
      esac
    done <<<"$NUMSTAT"
    NUMSTAT="$recount"
  fi
  if ! n="$(printf '%s\n' "${NUMSTAT:-}" | jq -R --argjson f "$FIXTURES" -n '
      '"$SIZE_NEWPATH"'
      def fixture($p):
        any($f[]; . as $e
          | if ($e | startswith("/")) and ($e | endswith("/")) then ($p | startswith($e | ltrimstr("/")))
            elif ($e | endswith("/")) then (("/" + $p) | contains("/" + $e))
            elif ($e | contains("/")) then $p == ($e | ltrimstr("/"))
            else ($p | split("/") | last) == $e end);
      [inputs | select(length > 0) | split("\t")
        | if length < 3 or (.[0] | test("^([0-9]+|-)$") | not) then error("bad numstat line: " + join("\t")) else . end
        | {added: (if .[0] == "-" then 0 else (.[0] | tonumber) end), path: (.[2:] | join("\t") | newpath)}
        | select(fixture(.path) | not) | .added] | add // 0' 2>/dev/null)"; then
    echo "invalid NUMSTAT is not git diff --numstat output"; return 0
  fi
  if [ "$n" -le "$LIMIT" ]; then echo "ok $n non-fixture lines (limit $LIMIT)"
  else echo "over $n non-fixture lines, more than $LIMIT: split the pull request"; fi
}
