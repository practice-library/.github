# Generated from templates/selftest/lib/message-extract.sh and policy/constants.json by scripts/render.sh. Do not edit.
# main: finds the message block in an issue body (docs/protocol.md). The body is untrusted text, read
# only as data. Prints one line:
#   ok <compact JSON>   exactly one fenced block opened by a line ```json, holding one JSON object
#   none ...            no such block: the issue is not a message
#   invalid <why>       more than one block, an unclosed block, a body over 65536 bytes, control or
#                       bidirectional-override characters in the block, a block that is not one JSON
#                       object, an object with a key given twice, or a json block opened by any fence
#                       other than exactly ``` (````json, ~~~json)
# Fences follow CommonMark: any other fence (``` or ~~~, three or more, with any info string) opens a
# block that is skipped until a closing fence of the same character at least as long, so a ```json
# quoted inside a longer fence is an example, not the message.
#   BODY_FILE  a file holding the issue body
main() {
  [ -r "${BODY_FILE:-}" ] || { echo "invalid cannot read the body"; return 0; }
  local size found block
  size="$(wc -c < "$BODY_FILE" | tr -d ' ')"
  [ "$size" -le 65536 ] || { echo "invalid the body is $size bytes, more than 65536"; return 0; }
  found="$(jq -Rsr '
    gsub("\r\n"; "\n") | split("\n")
    | reduce .[] as $l ({blocks: [], cur: null, other: null, bad: false};
        if .other != null then
          (.other as $o | if ($l | test("^" + $o + "[ \t]*$")) then .other = null else . end)
        elif .cur != null then
          (if ($l | test("^```+[ \t]*$")) then .blocks += [.cur | join("\n")] | .cur = null
           else .cur += [$l] end)
        elif ($l | test("^```json[ \t]*$")) then .cur = []
        elif ($l | test("^(`{3,}|~{3,})")) then
          ($l | capture("^(?<f>`{3,}|~{3,})(?<info>.*)$")) as $m
          | (if ($m.info | test("^[ \t]*json[ \t]*$")) then .bad = true else . end)
          | .other = (($m.f[0:1] | if . == "`" then "`" else "~" end) as $c
                      | "\($c){\($m.f | length),}")
        else . end)
    | if .bad then "invalid a json block must open with exactly ```json"
      elif .cur != null then "invalid a ```json block is not closed"
      elif (.blocks | length) == 0 then "none no ```json block"
      elif (.blocks | length) > 1 then "invalid \(.blocks | length) ```json blocks; a message has one"
      elif (.blocks[0] | test("[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]")) then "invalid a control character in the block"
      elif (.blocks[0] | test("[\u200e\u200f\u202a-\u202e\u2066-\u2069]")) then "invalid a bidirectional-override character in the block"
      else "block " + (.blocks[0] | @base64) end' "$BODY_FILE")"
  [ "${found%% *}" = block ] || { echo "$found"; return 0; }
  block="$(printf '%s' "${found#block }" | jq -Rr '@base64d')"
  jq -se 'length == 1 and (.[0] | type) == "object"' <<<"$block" > /dev/null 2>&1 \
    || { echo "invalid the block is not one JSON object"; return 0; }
  # A key given twice: the parsed object keeps only one value, so read the token stream instead. A
  # repeated leaf path, or any path under an object that has already closed, is a key given twice.
  jq -en --stream '
      reduce inputs as $e ({closed: {}, leaves: {}, dup: false};
        . as $s
        | if $s.dup then $s
          elif ($e | length) == 1 then $s | .closed[$e[0][:-1] | tojson] = true
          else ($e[0]) as $p
            | if $s.leaves[$p | tojson] or any(range(0; $p | length); $s.closed[$p[:.] | tojson] // false)
              then $s | .dup = true else $s | .leaves[$p | tojson] = true end
          end) | .dup | not' <<<"$block" > /dev/null 2>&1 \
    || { echo "invalid a key is given twice in the block"; return 0; }
  echo "ok $(jq -c . <<<"$block")"
}
