"""Protocol message reader and revision-bound trust (docs/protocol.md). Stdlib only.

The issue body is untrusted text, read only as data.

  extract(body_bytes) -> "ok <compact JSON>" | "none ..." | "invalid <why>"
  decide(...)         -> how a message-check run treats an event, given the stored verdict
  digest(body_bytes)  -> sha256 hex of the body, the revision a verdict binds to

Command line (used by templates/fragments/message-extract.sh and message-check.yml):
  extract <body-file>
  digest <body-file>
  decide <action> <actor> <author> <digest> <verdict-comments-json-file>
  verdict <status> <digest>
  verdict-id <verdict-comments-json-file>
"""
import hashlib
import json
import re
import sys
import unicodedata

from practice_ci import config

ACCEPTED = "accepted"
INVALID = "invalid"
TAINTED = "tainted"
STATUSES = (ACCEPTED, INVALID, TAINTED)

JUDGE = "judge"
KEEP_INVALID = "invalid"

_OTHER_FENCE = re.compile(r"^ {0,3}(?P<f>`{3,}[^`]*|~{3,}.*)$")
_FENCE_PARTS = re.compile(r"^ {0,3}(?P<f>`{3,}|~{3,})(?P<info>.*)$")
_CLOSE_BLOCK = re.compile(r"^ {0,3}`{3,}[ \t]*$")
_HTML_BLOCK = re.compile(r"^ {0,3}(?:<[!?]|</?[A-Za-z][A-Za-z0-9-]*(?:[\s/>]|$))")
_COMMENT_OPEN = "<!--"


def digest(body):
    """The sha256 of the body bytes: the revision an acceptance binds to."""
    return hashlib.sha256(body).hexdigest()


def _fence_info():
    return config.get("protocol", "fenceOpen")[3:]


def _scan(text):
    """Returns (status, payload): ("block", text), ("none", why) or ("invalid", why)."""
    open_line = re.compile(re.escape(config.get("protocol", "fenceOpen")) + r"[ \t]*")
    info = _fence_info()
    blocks, cur, other, bad = [], None, None, False
    for line in text.replace("\r\n", "\n").split("\n"):
        if other is not None:
            if re.fullmatch(r" {0,3}" + other + r"[ \t]*", line):
                other = None
        elif cur is not None:
            if _CLOSE_BLOCK.fullmatch(line):
                blocks.append("\n".join(cur))
                cur = None
            else:
                cur.append(line)
        elif open_line.fullmatch(line):
            cur = []
        elif _OTHER_FENCE.fullmatch(line):
            m = _FENCE_PARTS.fullmatch(line)
            if re.fullmatch(r"[ \t]*" + re.escape(info) + r"[ \t]*", m["info"]):
                bad = True
            char = "`" if m["f"][0] == "`" else "~"
            other = re.escape(char) + "{" + str(len(m["f"])) + ",}"
        elif _COMMENT_OPEN in line:
            return "invalid", "an HTML comment outside a fence hides text from a reader"
        elif _HTML_BLOCK.match(line):
            return "invalid", "an HTML block outside a fence hides text from a reader"
    fence = config.get("protocol", "fenceOpen")
    if bad:
        return "invalid", "a json block must open with exactly " + fence
    if cur is not None:
        return "invalid", "a " + fence + " block is not closed"
    if not blocks:
        return "none", "no " + fence + " block"
    if len(blocks) > 1:
        return "invalid", "%d %s blocks; a message has one" % (len(blocks), fence)
    return "block", blocks[0]


class _Twice(Exception):
    pass


def _pairs(items):
    seen = set()
    for key, _ in items:
        if key in seen:
            raise _Twice()
        seen.add(key)
    return dict(items)


def _refuse_constant(name):
    raise ValueError(name)


def decode(block):
    """One duplicate-key-aware decode of the block. Returns (value, None) or (None, why)."""
    try:
        value = json.loads(block, object_pairs_hook=_pairs, parse_constant=_refuse_constant)
    except _Twice:
        return None, "a key is given twice in the block"
    except (ValueError, RecursionError):
        return None, "the block is not one JSON object"
    if not isinstance(value, dict):
        return None, "the block is not one JSON object"
    return value, None


def _unsafe_char(ch):
    return unicodedata.category(ch) in config.get("protocol", "unsafeCategories") or "\ud800" <= ch <= "\udfff"


def _unsafe_string(text):
    return any(_unsafe_char(ch) for ch in text)


def has_unsafe(node):
    """True when a key or string anywhere in the decoded value holds an unsafe character."""
    if isinstance(node, str):
        return _unsafe_string(node)
    if isinstance(node, list):
        return any(has_unsafe(item) for item in node)
    if isinstance(node, dict):
        return any(_unsafe_string(key) or has_unsafe(item) for key, item in node.items())
    return False


def _multiline(text):
    return bool(text) and text.splitlines() != [text]


def needs_multiline(value):
    needs = value.get("data", {}).get("needs") if isinstance(value.get("data"), dict) else None
    return isinstance(needs, list) and any(isinstance(n, str) and _multiline(n) for n in needs)


def extract(body):
    """Reads an issue body (bytes) as a message. Returns one line: ok <json> | none <why> | invalid <why>."""
    limit = config.get("protocol", "maxBodyBytes")
    if len(body) > limit:
        return "invalid the body is %d bytes, more than %d" % (len(body), limit)
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return "invalid the body is not UTF-8"
    status, payload = _scan(text)
    if status != "block":
        return status + " " + payload
    value, why = decode(payload)
    if why:
        return "invalid " + why
    if needs_multiline(value):
        return "invalid a needs entry spans more than one line"
    if has_unsafe(value):
        return "invalid a control, format, line-separator or paragraph-separator character, or a lone surrogate, in the block"
    return "ok " + json.dumps(value, separators=(",", ":"), ensure_ascii=False)


# Revision-bound trust. The verdict is a comment by config protocol.verdictAuthor holding
# <!-- <marker> {"status": ..., "sha256": ...} -->; the digest is the body revision it speaks for.

def render_verdict(status, body_digest):
    if status not in STATUSES:
        raise ValueError("unknown verdict status: " + status)
    marker = config.get("protocol", "verdictMarker")
    return "<!-- %s %s -->" % (marker, json.dumps({"status": status, "sha256": body_digest}, sort_keys=True, separators=(",", ":")))


def parse_verdict(comments):
    """The latest verdict among issue comments (a list of GitHub comment objects), or None."""
    found = find_verdict(comments)
    return found[1] if found else None


def find_verdict(comments):
    """The latest verdict comment as (comment, verdict), or None. Only the verdict author's comments count."""
    author = config.get("protocol", "verdictAuthor")
    pattern = re.compile(r"\A<!-- " + re.escape(config.get("protocol", "verdictMarker")) + r" (\{.*?\}) -->")
    found = None
    for comment in comments:
        if (comment.get("user") or {}).get("login") != author:
            continue
        m = pattern.match(comment.get("body") or "")
        if not m:
            continue
        try:
            verdict = json.loads(m.group(1))
        except ValueError:
            continue
        if isinstance(verdict, dict) and verdict.get("status") in STATUSES and isinstance(verdict.get("sha256"), str):
            found = (comment, verdict)
    return found


def decide(action, actor, author, body_digest, verdict):
    """What a run does with an event. Returns (what, status, reason):

    what   JUDGE (read the body now) or KEEP_INVALID (the message is invalid, judge nothing)
    status the verdict to store for body_digest (ACCEPTED is stored only after a judged body is valid)
    reason why, for an invalid result

    A body is judged only when it is the sender's own revision: the issue was just opened, or the author
    edited it. An edit by anyone else taints the issue; it stays invalid until the author resubmits (edits
    again), and no later event, a trusted relabel included, rehabilitates it. On any other event the
    stored verdict must speak for the body as it is now.
    """
    if action == "opened":
        return JUDGE, None, None
    if action == "edited":
        if actor == author:
            return JUDGE, None, None
        return KEEP_INVALID, TAINTED, "its body was edited by someone other than its author; the author resubmits by editing it"
    if verdict is None:
        return KEEP_INVALID, TAINTED, "its body has no stored revision verdict; the author resubmits by editing it"
    if verdict["status"] == TAINTED:
        return KEEP_INVALID, TAINTED, "its body was edited by someone other than its author; the author resubmits by editing it"
    if verdict["sha256"] != body_digest:
        return KEEP_INVALID, TAINTED, "its body changed after it was accepted; the author resubmits by editing it"
    return JUDGE, None, None


def read_body(path):
    """The body bytes in a file, or None when it cannot be read."""
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return None


def extract_file(path):
    body = read_body(path)
    return "invalid cannot read the body" if body is None else extract(body)


def main(argv):
    cmd, args = argv[0], argv[1:]
    if cmd == "extract":
        print(extract_file(args[0]))
    elif cmd == "digest":
        with open(args[0], "rb") as f:
            print(digest(f.read()))
    elif cmd == "decide":
        action, actor, author, body_digest, comments_file = args
        with open(comments_file, encoding="utf-8") as f:
            verdict = parse_verdict(json.load(f))
        what, status, reason = decide(action, actor, author, body_digest, verdict)
        print(json.dumps({"what": what, "status": status, "reason": reason}, separators=(",", ":")))
    elif cmd == "verdict-id":
        with open(args[0], encoding="utf-8") as f:
            found = find_verdict(json.load(f))
        print(found[0]["id"] if found else "")
    elif cmd == "verdict":
        print(render_verdict(args[0], args[1]))
    else:
        print("usage: protocol.py extract|digest|decide|verdict ...", file=sys.stderr)
        return 2
    return 0
