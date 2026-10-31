# collect: prints "<where><TAB><text>" for every added line, added path, and commit message, author name
# and committer name of the change MB..HEAD in the current repository. The content diff is taken with
# --text and --no-textconv, so no .gitattributes in the change (-diff, binary, a diff driver) can hide a
# line. Words inside compressed binary files (images, archives) are not visible as text.
collect() {
  git diff --text --no-textconv --no-ext-diff --no-color --unified=0 "$MB" "$HEAD" | awk '
    /^\+\+\+ / { f = substr($0, 7); next }
    /^@@/ { match($0, /\+[0-9]+/); n = substr($0, RSTART + 1, RLENGTH - 1) + 0; next }
    /^\+/ { print f ":" n "\t" substr($0, 2); n++ }'
  # An added path is reported by its place in the list, since the path may hold the term.
  git diff --name-only --diff-filter=AR --no-ext-diff "$MB" "$HEAD" | awk '{ print "added path " NR "\t" $0 }'
  git log --format='::guard-commit:: %H%n%an%n%cn%n%B' "$MB..$HEAD" | awk '
    /^::guard-commit:: / { c = substr($0, 18); next }
    { print "commit " c "\t" $0 }'
}

# main: prints "ok ..." when no line holds a denied term, "found <n> <where>..." when lines do,
# "unguarded ..." when there is no list or it is empty, or "invalid ..." when DENY cannot be used.
# The term itself is never printed.
#   DENY       JSON {"salt": "<text>", "sha256": ["<hex>", ...]}: each entry is sha256(salt + ":" + term),
#              where a term is one word or two adjacent words, lower case, words joined by one space;
#              empty when the repository has no list
#   TEXT_FILE  lines "<where><TAB><text>"; when unset, the change MB..HEAD is collected (see collect)
# A text is cut into words of [a-z0-9]; each word, each two adjacent words, and those two written
# together are checked. scripts/denylist-hash.sh lists a two-word term both ways ("ab cd" and "abcd"),
# so "Ab Cd", "ab-cd" and "AbCd" all match it.
main() {
  if [ -z "${DENY:-}" ]; then echo "unguarded no denylist: add one (scripts/denylist-hash.sh)"; return 0; fi
  if [ -z "${TEXT_FILE:-}" ]; then
    TEXT_FILE="$(mktemp)"
    collect > "$TEXT_FILE" || { echo "invalid the change could not be read"; return 0; }
  fi
  TEXT_FILE="$TEXT_FILE" python3 -I -c '
import hashlib, json, os, re, sys
try:
    deny = json.loads(os.environ["DENY"])
    salt = deny["salt"]
    hashes = set(deny["sha256"])
    assert isinstance(salt, str) and salt and all(isinstance(h, str) for h in hashes)
except Exception:
    print("invalid the denylist must be {\"salt\": text, \"sha256\": [hex, ...]}")
    sys.exit(0)
if not hashes:
    print("unguarded the denylist has no entries")
    sys.exit(0)
def h(term):
    return hashlib.sha256((salt + ":" + term).encode()).hexdigest()
found = []
with open(os.environ["TEXT_FILE"], encoding="utf-8", errors="replace") as f:
    for line in f:
        where, _, text = line.rstrip("\n").partition("\t")
        words = re.findall(r"[a-z0-9]+", text.lower())
        terms = set(words)
        for a, b in zip(words, words[1:]):
            terms.add(a + " " + b)
            terms.add(a + b)
        if any(h(t) in hashes for t in terms):
            found.append(where)
if found:
    seen = list(dict.fromkeys(found))
    print("found %d %s" % (len(found), ", ".join(seen[:20])))
else:
    print("ok no denied term in the change")
'
}
