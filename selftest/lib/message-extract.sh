# Generated from templates/selftest/lib/message-extract.sh and policy/constants.json by scripts/render.sh. Do not edit.
# main: finds the message block in an issue body (docs/protocol.md). The body is untrusted text, read
# only as data. Prints one line:
#   ok <compact JSON>   exactly one fenced block opened by a line ```json, holding one JSON object
#   none ...            no such block: the issue is not a message
#   invalid <why>       more than one block, an unclosed block, a body over 65536 bytes, control or
#                       bidirectional-override characters in the block, or a block that is not one
#                       JSON object
#   BODY_FILE  a file holding the issue body
main() {
  [ -r "${BODY_FILE:-}" ] || { echo "invalid cannot read the body"; return 0; }
  local size; size="$(wc -c < "$BODY_FILE" | tr -d ' ')"
  [ "$size" -le 65536 ] || { echo "invalid the body is $size bytes, more than 65536"; return 0; }
  jq -Rsr '
    gsub("\r\n"; "\n") | split("\n")
    | reduce .[] as $l ({blocks: [], cur: null};
        if .cur == null then
          (if ($l | test("^```json[ \t]*$")) then .cur = [] else . end)
        elif ($l | test("^```[ \t]*$")) then .blocks += [.cur | join("\n")] | .cur = null
        else .cur += [$l] end)
    | if .cur != null then "invalid a ```json block is not closed"
      elif (.blocks | length) == 0 then "none no ```json block"
      elif (.blocks | length) > 1 then "invalid \(.blocks | length) ```json blocks; a message has one"
      elif (.blocks[0] | test("[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]")) then "invalid a control character in the block"
      elif (.blocks[0] | test("[‎‏‪-‮⁦-⁩]")) then "invalid a bidirectional-override character in the block"
      else (.blocks[0] | try fromjson catch null) as $j
        | if ($j | type) == "object" then "ok " + ($j | tojson) else "invalid the block is not one JSON object" end
      end' "$BODY_FILE"
}
