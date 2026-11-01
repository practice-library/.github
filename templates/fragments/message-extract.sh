# protocol: runs tooling/practice_ci/protocol.py (docs/protocol.md), which holds every rule about a message
# body and about whom a message trusts. PRACTICE_CI_TOOLING is the directory holding practice_ci; unset, it is
# the tooling directory of the working directory. The body is untrusted text, read only as data.
protocol() {
  python3 -I -c 'import sys; sys.path.insert(0, sys.argv[1]); from practice_ci import protocol; sys.exit(protocol.main(sys.argv[2:]))' \
    "${PRACTICE_CI_TOOLING:-@@protocol.toolingDir@@}" "$@"
}

# main: finds the message block in an issue body. BODY_FILE is a file holding the body. Prints one line:
#   ok <compact JSON>   one message block, decoded once without a key given twice
#   none ...            no message block: the issue is not a message
#   invalid <why>       anything else (docs/protocol.md, "A message")
main() {
  protocol extract "${BODY_FILE:-}"
}
