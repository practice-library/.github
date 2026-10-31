# main: prints "ok ..." when no auto-merge allowlist path (ALLOW, a JSON array; an entry ending in /
# covers everything under it) is owned in the CODEOWNERS text (CODEOWNERS); otherwise "owned [...]",
# or "unsupported <pattern>" for a pattern this check cannot judge (only *, /path and /path/ are
# understood). The last matching line wins, as in GitHub.
main() {
  jq -nr --arg text "$CODEOWNERS" --argjson allow "$ALLOW" '
    def norm: ltrimstr("/");
    [ $text | split("\n")[] | sub("#.*$"; "") | gsub("^\\s+|\\s+$"; "") | select(length > 0)
      | [splits("\\s+")] | {pattern: .[0], owners: .[1:]} ] as $lines
    | ([ $lines[] | select((.pattern == "*" or (.pattern | test("^/[^*?\\[\\]!]+$"))) | not) | .pattern ] | first) as $bad
    | if $bad != null then "unsupported \($bad)"
      else
        [ $allow[] as $a
          | ([ $lines | to_entries[]
               | .value.pattern as $p | ($p | norm) as $q
               | select($p == "*" or $a == $q or ($a | startswith(($q | rtrimstr("/")) + "/"))
                        or (($a | endswith("/")) and ($q | startswith($a)))) ]
             | last) as $hit
          | select($hit != null and ($hit.value.owners | length) > 0)
          | $a ]
        | if length == 0 then "ok no allowlisted path has an owner" else "owned \(tojson)" end
      end'
}
