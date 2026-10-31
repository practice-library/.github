# Generated from templates/selftest/lib/denylist-scan.sh and policy/constants.json by scripts/render.sh. Do not edit.
# main: prints "ok ..." when no line of TEXT_FILE holds a denied term, "found <n> <where>..." when lines
# do, or "invalid ..." when DENY cannot be used. The term itself is never printed.
#   DENY       JSON {"salt": "<text>", "sha256": ["<hex>", ...]}: each entry is sha256(salt + ":" + term),
#              where a term is one word or two adjacent words, lower case, words joined by one space
#   TEXT_FILE  lines "<where><TAB><text>"; <where> is what a finding reports
# A text is cut into words of [a-z0-9]; each word, each two adjacent words, and those two written
# together are checked. scripts/denylist-hash.sh lists a two-word term both ways ("ab cd" and "abcd"),
# so "Ab Cd", "ab-cd" and "AbCd" all match it.
main() {
  python3 -I -c '
import hashlib, json, os, re, sys
try:
    deny = json.loads(os.environ["DENY"])
    salt = deny["salt"]
    hashes = set(deny["sha256"])
    assert isinstance(salt, str) and salt and all(isinstance(h, str) for h in hashes)
except Exception:
    print("invalid the denylist must be {\"salt\": text, \"sha256\": [hex, ...]}")
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
