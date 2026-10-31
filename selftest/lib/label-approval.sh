# Generated from templates/selftest/lib/label-approval.sh and policy/constants.json by scripts/render.sh. Do not edit.
# main: prints "ok approved by <login>" when the pull request carries LABEL and the last person to add
# it is neither the author nor a bot; "missing ..." when the label is not on the pull request; otherwise
# "refused ..." (added by the author, by a bot, or by no one the events show). Who added it last counts,
# so removing it and adding it again changes the verdict.
#   LABEL   the approval label
#   LABELS  JSON array of the labels on the pull request now
#   AUTHOR  the pull request author's login
#   EVENTS  one line per time LABEL was added, oldest first: "<login><TAB><actor type>"
main() {
  local last login type
  if ! jq -en --arg l "$LABEL" --argjson ls "$LABELS" '($ls | type) == "array" and any($ls[]; . == $l)' > /dev/null 2>&1; then
    if jq -en --argjson ls "$LABELS" '($ls | type) == "array"' > /dev/null 2>&1; then
      echo "missing the label $LABEL is not on the pull request"; return 0
    fi
    echo "refused LABELS must be a JSON array"; return 0
  fi
  last="$(printf '%s\n' "${EVENTS:-}" | awk 'NF { l = $0 } END { print l }')"
  if [ -z "$last" ] || [[ "$last" != *$'\t'* ]]; then
    echo "refused no event shows who added $LABEL"; return 0
  fi
  login="${last%%$'\t'*}"; type="${last#*$'\t'}"
  if [ -z "$login" ] || [ "$login" = "$AUTHOR" ] || [ "$type" = Bot ] || [[ "$login" == *"[bot]" ]]; then
    echo "refused $LABEL must be added by someone other than the author and not by a bot (last added by: ${login:-unknown})"; return 0
  fi
  echo "ok approved by $login"
}
