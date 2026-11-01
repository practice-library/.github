# Generated from templates/selftest/lib/denylist-scan.sh and policy/constants.json by scripts/render.sh. Do not edit.
# collect: prints "<where><TAB><text>" for every added line, added path, and commit message, author name
# and committer name of the change MB..HEAD in the current repository. A name is printed with the where
# "author <sha>" or "committer <sha>" by a git log of its own, so no message line can pose as a name.
# Each git read goes to a file first and any failed read makes collect fail, so a change that cannot be
# read is never judged clean. The content diff is taken with --no-renames, so a moved file's every line
# is read at its new path (a rename out of an exempt tree carries nothing past the guard), and with
# --text and --no-textconv, so no
# .gitattributes in the change (-diff, binary, a diff driver) can hide a line. Words inside compressed
# binary files (images, archives) are not visible as text.
# A "+++ " line is a file header only between "diff --git" and the first "@@"; inside a hunk it is an
# added line that starts with "++". --no-prefix keeps the path at a fixed place whatever the config;
# git ends the header with a tab when the path holds a space, and that tab is dropped.
# EVENT is the GitHub event. On push, the author name of a merge commit is not judged: a merge made in
# the browser is authored by whoever pressed merge. Its message and committer are judged like any other.
# On any other event, or when EVENT is unset, every author name is judged.
collect() {
  local skip=() buf
  if [ "${EVENT:-}" = push ]; then skip=(--no-merges); fi
  buf="$(mktemp)" || return 1
  git diff --text --no-textconv --no-ext-diff --no-color --no-prefix --no-renames --unified=0 "$MB" "$HEAD" > "$buf" \
    || { rm -f "$buf"; return 1; }
  awk '
    /^diff --git / { hdr = 1; next }
    hdr && /^\+\+\+ / { f = substr($0, 5); sub(/\t$/, "", f); next }
    /^@@/ { hdr = 0; match($0, /\+[0-9]+/); n = substr($0, RSTART + 1, RLENGTH - 1) + 0; next }
    !hdr && /^\+/ { print f ":" n "\t" substr($0, 2); n++ }' "$buf"
  # An added path is reported by its place in the list, since the path may hold the term.
  git diff --name-only --diff-filter=AR --no-ext-diff "$MB" "$HEAD" > "$buf" || { rm -f "$buf"; return 1; }
  awk '{ print "added path " NR "\t" $0 }' "$buf"
  git log ${skip[@]+"${skip[@]}"} --format='author %H%x09%an' "$MB..$HEAD" > "$buf" || { rm -f "$buf"; return 1; }
  cat "$buf"
  git log --format='committer %H%x09%cn' "$MB..$HEAD" > "$buf" || { rm -f "$buf"; return 1; }
  cat "$buf"
  git log --format='::guard-commit:: %H%n%B' "$MB..$HEAD" > "$buf" \
    || { rm -f "$buf"; return 1; }
  awk '
    /^::guard-commit:: / { c = substr($0, 18); next }
    { print "commit " c "\t" $0 }' "$buf"
  rm -f "$buf"
}

# main: prints "ok ..." when no line holds a denied term, "found <n> <where>..." when lines do,
# "unguarded ..." when there is no list or it is empty, or "invalid ..." when DENY cannot be used.
# The term itself is never printed.
#   DENY       JSON {"salt": "<text>", "sha256": ["<hex>", ...], "allowAuthorNames": ["<hex>", ...]}: each
#              sha256 entry is sha256(salt + ":" + term), where a term is one word or two adjacent words,
#              lower case, words joined by one space; empty when the repository has no list. The optional
#              allowAuthorNames entries are sha256(salt + ":" + name) of whole names, written the same way:
#              64 lower-case hex characters each; an author or committer name that is one of them is
#              not judged. Messages, added lines and added paths are judged whatever the name.
#              The optional exemptPaths is a list of {"glob": <path glob>, "terms": [<hex>, ...]}: an added
#              line of a file whose path matches a glob is not found for the sha256 entries in terms, or for
#              any entry when terms is absent. It applies to added lines only; added paths, messages and
#              names are judged as before. A glob is relative to the root: * and ? stay inside one path
#              segment, a segment that is exactly ** spans any number of segments, and the first segment
#              holds no wildcard, so no glob covers the whole repository. Each line an exemption lets
#              through is printed with its glob (the first 20, after the count).
#   EVENT      the GitHub event; push leaves merge commits out (see collect)
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
    allow = deny.get("allowAuthorNames", [])
    assert isinstance(salt, str) and salt and isinstance(allow, list)
    allow = set(allow)
    assert all(isinstance(h, str) for h in hashes)
    assert all(re.fullmatch(r"[0-9a-f]{64}", h) for h in allow)
except Exception:
    print("invalid the denylist must be {\"salt\": text, \"sha256\": [hex, ...], \"allowAuthorNames\": [hex, ...]}")
    sys.exit(0)
def glob_re(g):
    segs = g.split("/")
    out = ""
    for i, seg in enumerate(segs):
        last = i == len(segs) - 1
        if seg == "**":
            out += ".+" if last else "(?:[^/]+/)*"
            continue
        out += "".join("[^/]*" if c == "*" else "[^/]" if c == "?" else re.escape(c) for c in seg)
        if not last:
            out += "/"
    return re.compile(out)
exempt = []
try:
    rules = deny.get("exemptPaths", [])
    assert isinstance(rules, list)
    for r in rules:
        assert isinstance(r, dict) and set(r) <= {"glob", "terms"}
        g = r["glob"]
        assert isinstance(g, str) and re.fullmatch(r"[A-Za-z0-9._*?-]+(/[A-Za-z0-9._*?-]+)*", g)
        segs = g.split("/")
        assert not re.search(r"[*?]", segs[0]) and ".." not in segs and "." not in segs
        assert all(s == "**" or "**" not in s for s in segs)
        t = r.get("terms")
        assert t is None or (isinstance(t, list) and t and all(isinstance(x, str) and re.fullmatch(r"[0-9a-f]{64}", x) for x in t))
        exempt.append((g, glob_re(g), None if t is None else set(t)))
except Exception:
    print("invalid exemptPaths must be [{\"glob\": path glob whose first segment has no wildcard, \"terms\": [hex, ...]}]")
    sys.exit(0)
line_row = re.compile(r"(.+):([0-9]+)")
if not hashes:
    print("unguarded the denylist has no entries")
    sys.exit(0)
def h(term):
    return hashlib.sha256((salt + ":" + term).encode()).hexdigest()
# A name row is exactly "author <id>" or "committer <id>"; a path or a line in a file named "author x"
# never is, since its where carries ":<line>" or starts with "added path".
name_row = re.compile(r"(?:author|committer) (?:[0-9a-f]{40}|[0-9a-f]{64})")
found = []
let_through = []
# Rows are split on "\n" only, as collect wrote them: a lone "\r" inside a line or a message must not
# start a row whose where the change chose.
with open(os.environ["TEXT_FILE"], encoding="utf-8", errors="replace", newline="\n") as f:
    for line in f:
        where, _, text = line.rstrip("\n").partition("\t")
        words = re.findall(r"[a-z0-9]+", text.lower())
        if name_row.fullmatch(where) and h(" ".join(words)) in allow:
            continue
        terms = set(words)
        for a, b in zip(words, words[1:]):
            terms.add(a + " " + b)
            terms.add(a + b)
        hit = {h(t) for t in terms} & hashes
        if not hit:
            continue
        m = line_row.fullmatch(where) if exempt else None
        if m:
            for g, rx, t in exempt:
                if rx.fullmatch(m.group(1)) and (t is None or hit <= t):
                    let_through.append("%s (%s)" % (where, g))
                    break
            else:
                found.append(where)
        else:
            found.append(where)
note = ""
if let_through:
    note = "; exempt %d: %s" % (len(let_through), ", ".join(let_through[:20]))
if found:
    seen = list(dict.fromkeys(found))
    print("found %d %s%s" % (len(found), ", ".join(seen[:20]), note))
else:
    print("ok no denied term in the change" + note)
'
}
