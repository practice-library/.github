#!/usr/bin/env bash
# Prints the denylist entries for the terms on standard input, one term per line, with the salt of the
# given denylist file: sha256(salt + ":" + term). A term is one word or two words, compared in lower case
# over [a-z0-9]; a two-word term is printed both as "a b" and as "ab". The terms are never written down.
# Usage: scripts/denylist-hash.sh .github/denylist.json < terms   (append the output to its sha256 list)
# With --names, each line is a whole author or committer name of any length, printed once:
#        scripts/denylist-hash.sh --names .github/denylist.json < names   (append to allowAuthorNames)
set -euo pipefail
NAMES=""
if [ "${1:-}" = --names ]; then NAMES=1; shift; fi
[ $# -eq 1 ] || { echo "usage: denylist-hash.sh [--names] <denylist.json> < terms" >&2; exit 2; }
NAMES="$NAMES" SALT="$(jq -er '.salt' "$1")" python3 -I -c '
import hashlib, os, re, sys
salt = os.environ["SALT"]
for line in sys.stdin:
    words = re.findall(r"[a-z0-9]+", line.lower())
    if not words:
        continue
    if os.environ["NAMES"]:
        print(hashlib.sha256((salt + ":" + " ".join(words)).encode()).hexdigest())
        continue
    if len(words) > 2:
        sys.exit("a term is one or two words: " + str(len(words)) + " given")
    for term in {" ".join(words), "".join(words)}:
        print(hashlib.sha256((salt + ":" + term).encode()).hexdigest())
'
