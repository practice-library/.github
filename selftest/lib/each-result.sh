# Generated from templates/selftest/lib/each-result.sh and policy/constants.json by scripts/render.sh. Do not edit.
# main: combines per-file exit codes into one. RCS is a space-separated list, FINDING the validator's
# finding exit code. Prints "pass 0" when every file passed, "finding <FINDING>" when every file was
# rejected with a finding, and "mixed 1" otherwise (mixed results, another error, or no files), so an
# expectation of pass or fail holds only when it holds for each file. The last word is the exit code.
main() {
  local rc all_pass=true all_finding=true n=0
  for rc in $RCS; do
    n=$((n + 1))
    [ "$rc" = 0 ] || all_pass=false
    [ "$rc" = "$FINDING" ] || all_finding=false
  done
  if [ "$n" -eq 0 ]; then echo "mixed 1"; return 0; fi
  if [ "$all_pass" = true ]; then echo "pass 0"; elif [ "$all_finding" = true ]; then echo "finding $FINDING"; else echo "mixed 1"; fi
}
