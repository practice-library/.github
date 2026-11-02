"""Conservative JSON Schema compatibility classifier.

classify(old, new) judges whether the schema `new` accepts nothing more than `old`:

  proven-safe     no rule found a place where the new schema may accept more
  requires-review a rule found such a place, or met a construct it cannot judge (unknown means review)
  invalid         an input could not be read

Every finding names a path and the rule that raised it. classify_check() does the same for a
check.json profile: any change to what the gate proves needs review.

The command line (`python3 -m practice_ci.compatibility`) prints one line, the contract of the
schema-loosening guard fragment: "ok ...", "loose [<path>, ...]", "invalid ..." or "skip ...".
"""
import argparse
import hashlib
import json
import os
import re
import sys

from . import config

PROVEN_SAFE = "proven-safe"
REQUIRES_REVIEW = "requires-review"
INVALID = "invalid"

MINS = ("minItems", "minLength", "minProperties", "minimum", "exclusiveMinimum", "minContains")
MAXS = ("maxItems", "maxLength", "maxProperties", "maximum", "exclusiveMaximum", "maxContains")
# Keywords under which a tighter value can make the schema accept more. (A draft-03 `disallow` negates like
# `not`, but it is no schema place, so any change to it is already review as an unknown keyword.)
REVERSING = ("not", "if", "oneOf", "contains")
REFS = ("$ref", "$dynamicRef", "$recursiveRef")
# What names a place a reference resolves to, or the dialect.
IDENTITY = ("$schema", "$id", "id", "$anchor", "$dynamicAnchor", "$recursiveAnchor", "$vocabulary")
SUB = ("items", "additionalItems", "unevaluatedItems", "contains", "propertyNames", "additionalProperties",
       "unevaluatedProperties", "not", "if", "then", "else", "contentSchema")
SUBMAP = ("properties", "patternProperties", "dependentSchemas", "$defs", "definitions")
SUBARR = ("allOf", "anyOf", "oneOf", "prefixItems", "items")
ANNOTATIONS = ("title", "description", "default", "examples", "$comment", "deprecated", "readOnly", "writeOnly",
               "contentMediaType", "contentEncoding", "$defs", "definitions")
HANDLED = MINS + MAXS + ("required", "enum", "const", "pattern", "format", "type")
EVALUATORS = ("allOf", "anyOf", "oneOf", "if", "then", "else", "dependentSchemas", "dependencies")
DELETED = "(deleted)"
ROOT = "(root)"


# ---- JSON helpers that keep JSON's type distinctions (Python's True == 1 would blur them) ----

def _type(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "array"
    return "object"


def _eq(a, b):
    ta = _type(a)
    if ta != _type(b):
        return False
    if ta == "array":
        return len(a) == len(b) and all(_eq(x, y) for x, y in zip(a, b))
    if ta == "object":
        return a.keys() == b.keys() and all(_eq(a[k], b[k]) for k in a)
    return a == b


def _in(x, items):
    return any(_eq(x, y) for y in items)


def _is_num(v):
    return _type(v) == "number"


def _paths(doc, prefix=()):
    """Every path below the root, depth first, object keys in document order (as jq's `paths` walks them)."""
    if isinstance(doc, dict):
        for k in doc:
            yield prefix + (k,)
            yield from _paths(doc[k], prefix + (k,))
    elif isinstance(doc, list):
        for i, v in enumerate(doc):
            yield prefix + (i,)
            yield from _paths(v, prefix + (i,))


def _at(doc, path):
    for k in path:
        if isinstance(doc, dict) and isinstance(k, str):
            doc = doc.get(k)
        elif isinstance(doc, list) and isinstance(k, int) and 0 <= k < len(doc):
            doc = doc[k]
        else:
            return None
    return doc


def _walk_objects(doc):
    if isinstance(doc, dict):
        yield doc
        for v in doc.values():
            yield from _walk_objects(v)
    elif isinstance(doc, list):
        for v in doc:
            yield from _walk_objects(v)


def _where(path):
    return "/".join(str(e) for e in path) if path else ROOT


def _is_schema_place(p):
    if not p:
        return True
    last = p[-1]
    if isinstance(last, str) and last in SUB and _is_schema_place(p[:-1]):
        return True
    if len(p) >= 2 and isinstance(p[-2], str) and isinstance(last, str) and p[-2] in SUBMAP and _is_schema_place(p[:-2]):
        return True
    if len(p) >= 2 and isinstance(p[-2], str) and isinstance(last, int) and p[-2] in SUBARR and _is_schema_place(p[:-2]):
        return True
    return False


def _places(doc):
    return [()] + [p for p in _paths(doc) if _is_schema_place(p)]


def _under_reversing(p):
    return any(isinstance(e, str) and e in REVERSING for e in p)


def _sort_key(p):
    """jq's order for a path: numbers before strings, element by element."""
    return tuple((0, e, "") if isinstance(e, int) else (1, 0, e) for e in p)


def _keys_of(v):
    return sorted(v) if isinstance(v, dict) else []


def _len_of(v):
    return len(v) if isinstance(v, list) else -1


# ---- the classifier ----

class _Judge:
    def __init__(self, old, new):
        self.old, self.new = old, new
        self.ref_under_reversing = any(
            isinstance(p[-1], str) and p[-1] in REFS and _under_reversing(p)
            for doc in (old, new) for p in _paths(doc))
        full = re.compile(config.get("compatibility", "fullDialectPattern"))
        self.uneval_counts = (
            all(isinstance(d, dict) and "$schema" in d for d in (old, new))
            and all(isinstance(o["$schema"], str) and full.fullmatch(o["$schema"]) is not None
                    for d in (old, new) for o in _walk_objects(d) if "$schema" in o))
        self.places = _places(old)
        self.new_places = _places(new)
        self.all_places = sorted({*self.places, *self.new_places}, key=_sort_key)

    def refuses(self, obj, k):
        """A key leaving properties or patternProperties is refused only while nothing else can take it."""
        if not isinstance(obj, dict) or k not in ("properties", "patternProperties"):
            return False
        other = "patternProperties" if k == "properties" else "properties"
        if other in obj:
            return False
        if obj.get("additionalProperties") is False:
            return True
        return (self.uneval_counts and obj.get("unevaluatedProperties") is False
                and "additionalProperties" not in obj
                and not any(a in obj for a in EVALUATORS + REFS))

    def findings(self):
        """(path, rule, pair-or-None) in the order the rules run, first finding per path kept."""
        seen, out = set(), []
        for path, rule, pair in self._all():
            if path not in seen:
                seen.add(path)
                out.append((path, rule, pair))
        return out

    def _all(self):
        yield from self._rules_at_every_path()
        for path, rule in self._structure():
            yield _where(path), rule, None

    def _rules_at_every_path(self):
        old, new = self.old, self.new
        for p in _paths(old):
            k = p[-1]
            if not isinstance(k, str):
                continue
            ov, nv = _at(old, p), _at(new, p)
            rule = None
            if k in MINS and _is_num(ov):
                rule = "minimum-lowered" if (not _is_num(nv) or nv < ov) else None
            elif k in MAXS and _is_num(ov):
                rule = "maximum-raised" if (not _is_num(nv) or nv > ov) else None
            elif k == "required" and isinstance(ov, list):
                nr = nv if isinstance(nv, list) else []
                rule = "required-removed" if any(not _in(x, nr) for x in ov) else None
            elif k == "enum" and isinstance(ov, list):
                rule = "enum-widened" if (not isinstance(nv, list) or any(not _in(x, ov) for x in nv)) else None
            elif k in ("additionalProperties", "unevaluatedProperties") and ov is False:
                rule = "closure-opened" if nv is not False else None
            elif k == "const" or (k in ("pattern", "format") and isinstance(ov, str)):
                rule = "value-changed" if not _eq(nv, ov) else None
            if rule is None:
                continue
            pair = None
            if k == "pattern" and isinstance(ov, str) and isinstance(nv, str) \
                    and not self.ref_under_reversing and not _under_reversing(p):
                pair = [ov, nv]
            yield _where(p), rule, pair

    def _structure(self):
        yield from self._per_place()
        yield from self._siblings()
        yield from self._defs_with_uneval()
        yield from self._identity_added()
        yield from self._reference_in_reversing_context()
        yield from self._reference_changed()

    # -- what the rules above cannot show safe --

    def _per_place(self):
        old, new = self.old, self.new
        for s in self.places:
            o, n = _at(old, s), _at(new, s)
            if isinstance(o, bool):
                if o is False and n is not False and n is not None:
                    yield s, "false-subschema-opened"
                continue
            if not isinstance(o, dict):
                continue
            if n is True:
                if any(k not in ANNOTATIONS for k in o):
                    yield s, "subschema-made-true"
                continue
            if n is False or n is None:
                continue
            if not isinstance(n, dict):
                yield s, "subschema-shape-replaced"
                continue
            for k in sorted(o):
                if k in ANNOTATIONS:
                    continue
                if k not in n:
                    if not (k in ("properties", "patternProperties") and self.refuses(o, k) and self.refuses(n, k)):
                        yield s + (k,), "keyword-removed"
                elif k == "type":
                    ot = o["type"] if isinstance(o["type"], list) else [o["type"]]
                    t = n["type"]
                    nt = t if isinstance(t, list) else ([t] if isinstance(t, str) else [])
                    if any(not _in(x, ot) for x in nt):
                        yield s + (k,), "type-widened"
                elif k in HANDLED:
                    # Judged at every path above in the type its rule compares; any other type is loose.
                    if k in MINS + MAXS:
                        want = "number"
                    elif k in ("required", "enum"):
                        want = "array"
                    elif k == "const":
                        want = _type(o[k])
                    else:
                        want = "string"
                    if _type(o[k]) != want and not _eq(o[k], n[k]):
                        yield s + (k,), "keyword-changed"
                elif k in REFS:
                    continue
                elif k in REVERSING:
                    if not _eq(o[k], n[k]):
                        yield s + (k,), "reversing-keyword-changed"
                elif k in ("allOf", "anyOf", "prefixItems"):
                    if isinstance(o[k], list) and (not isinstance(n[k], list) or len(n[k]) != len(o[k])):
                        if not (k == "allOf" and self._grows_at_end(o[k], n[k])):
                            yield s + (k,), "list-length-changed"
                elif k == "items" and isinstance(o[k], list):
                    if not isinstance(n[k], list) or len(n[k]) != len(o[k]):
                        yield s + (k,), "list-length-changed"
                elif k in ("properties", "patternProperties", "dependentSchemas"):
                    for x in _keys_of(o[k]):
                        if x in _keys_of(n[k]):
                            continue
                        if self.refuses(o, k) and self.refuses(n, k):
                            continue
                        yield s + (k, x), "entry-removed"
                elif k in SUB or k in SUBMAP or k in SUBARR:
                    continue
                elif not _eq(o[k], n[k]):
                    yield s + (k,), "keyword-changed"

    @staticmethod
    def _grows_at_end(old_branches, new_branches):
        """allOf holds every branch, so one that only gains branches after the old ones accepts nothing more."""
        return (isinstance(new_branches, list) and len(new_branches) > len(old_branches)
                and _eq(old_branches, new_branches[:len(old_branches)]))

    def _siblings(self):
        """Beside a keyword that judges what the others leave, a keyword taking more for itself moves it out."""
        old, new = self.old, self.new
        for s in self.places:
            o, n = _at(old, s), _at(new, s)
            if not (isinstance(o, dict) and isinstance(n, dict)):
                continue

            def judges(k):
                return k in o and o[k] is not True

            def added(k):
                return k not in o and k in n

            if judges("additionalProperties") or judges("unevaluatedProperties"):
                for k in ("properties", "patternProperties"):
                    known = _keys_of(o.get(k))
                    for x in _keys_of(n.get(k)):
                        if x in known:
                            continue
                        if judges("unevaluatedProperties") or not _eq(n[k][x], o.get("additionalProperties")):
                            yield s + (k, x), "moved-out-of-closure"
            if judges("items") or judges("unevaluatedItems"):
                if _len_of(n.get("prefixItems")) > _len_of(o.get("prefixItems")):
                    yield s + ("prefixItems",), "moved-out-of-closure"
            if judges("additionalItems") or judges("unevaluatedItems"):
                if isinstance(n.get("items"), list) and _len_of(n.get("items")) > _len_of(o.get("items")):
                    yield s + ("items",), "moved-out-of-closure"
            if judges("unevaluatedProperties") and added("additionalProperties"):
                yield s + ("additionalProperties",), "moved-out-of-closure"
            if judges("unevaluatedItems"):
                for k in ("items", "additionalItems", "contains"):
                    if added(k):
                        yield s + (k,), "moved-out-of-closure"
            if judges("unevaluatedProperties") or judges("unevaluatedItems"):
                for k in EVALUATORS:
                    if not _eq(o.get(k), n.get(k)):
                        yield s + (k,), "evaluator-changed-beside-unevaluated"
            # minContains defaults to 1 beside contains: one added below that accepts an array with no match.
            if "contains" in o and added("minContains") and _is_num(n.get("minContains")) and n["minContains"] < 1:
                yield s + ("minContains",), "min-contains-below-one"

    def _defs_with_uneval(self):
        """A definition a reference reaches can evaluate properties or items for an unevaluated keyword."""
        old, new = self.old, self.new
        unevaluated = any(
            ("unevaluatedProperties" in o and o["unevaluatedProperties"] is not True)
            or ("unevaluatedItems" in o and o["unevaluatedItems"] is not True)
            for o in _walk_objects(old))
        if not unevaluated:
            return
        if not any(isinstance(p[-1], str) and p[-1] in REFS for doc in (old, new) for p in _paths(doc)):
            return
        for k in ("$defs", "definitions"):
            if not _eq(_at(old, (k,)), _at(new, (k,))):
                yield (k,), "definitions-changed-beside-unevaluated"

    def _identity_added(self):
        """A $schema, $id, $anchor, $dynamicAnchor or $vocabulary added moves what a reference reaches."""
        for s in self.all_places:
            o, n = _at(self.old, s), _at(self.new, s)
            if not isinstance(n, dict):
                continue
            for k in IDENTITY:
                if isinstance(o, dict) and k in o:
                    continue
                if k in n:
                    yield s + (k,), "identity-added"

    def _reference_in_reversing_context(self):
        """With a reference under not, if, oneOf or contains any place may be reached there: every change is loose."""
        if not self.ref_under_reversing:
            return
        for s in self.places:
            o, n = _at(self.old, s), _at(self.new, s)
            if not isinstance(o, dict) or not isinstance(n, dict):
                if not _eq(o, n) and n is not None:
                    yield s, "reference-context-changed"
                continue
            for k in sorted({*o, *n}):
                if k in ANNOTATIONS:
                    continue
                if k in SUB:
                    changed = (k in o) != (k in n)
                elif k in SUBMAP or k in SUBARR:
                    changed = not _eq(self._shape(o.get(k)), self._shape(n.get(k)))
                else:
                    changed = not _eq(o.get(k), n.get(k))
                if changed:
                    yield s + (k,), "reference-context-changed"

    @staticmethod
    def _shape(v):
        if isinstance(v, dict):
            return sorted(v)
        if isinstance(v, list):
            return len(v)
        return v

    def _reference_changed(self):
        for s in self.all_places:
            o, n = _at(self.old, s), _at(self.new, s)
            for r in REFS:
                a = o.get(r) if isinstance(o, dict) else None
                b = n.get(r) if isinstance(n, dict) else None
                if not _eq(a, b):
                    yield s + (r,), "reference-changed"


def _pair_hash(pair):
    return hashlib.sha256(json.dumps(pair, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def tighten_list_is_valid(entries):
    pattern = re.compile(config.get("compatibility", "tightenHashPattern"))
    return isinstance(entries, (list, tuple)) and all(
        isinstance(e, dict) and isinstance(e.get("sha256"), str) and pattern.fullmatch(e["sha256"]) is not None
        and isinstance(e.get("why"), str) and len(e["why"]) > 0 for e in entries)


def classify(old, new, tighten=None):
    """Classify the change from schema `old` to schema `new` (parsed JSON). `tighten` is the reviewed list of
    {"sha256", "why"} pattern pairs; a listed pair is a claim that the new pattern accepts nothing the old refused."""
    tighten = [] if tighten is None else tighten
    if not tighten_list_is_valid(tighten):
        return {"verdict": INVALID, "reasons": [{"path": "", "rule": "tighten-list", "text": "TIGHTEN must be a JSON array of {sha256, why}"}],
                "tightened": []}
    listed = {e["sha256"] for e in tighten}
    reasons, tightened = [], []
    for path, rule, pair in _Judge(old, new).findings():
        if pair is not None and _pair_hash(pair) in listed:
            tightened.append(path)
        else:
            reasons.append({"path": path, "rule": rule})
    return {"verdict": REQUIRES_REVIEW if reasons else PROVEN_SAFE, "reasons": reasons, "tightened": tightened}


def classify_check(old, new):
    """check.json: any change to what the gate proves (a row removed, `expect` changed, `schema` retargeted, ...)
    needs review. Rows and the policy profile's single object are both read; anything else is invalid."""
    def rows(doc):
        if isinstance(doc, dict):
            return [doc]
        if isinstance(doc, list) and all(isinstance(r, dict) for r in doc):
            return doc
        return None
    o, n = rows(old), rows(new)
    if o is None or n is None:
        return {"verdict": INVALID, "reasons": [{"path": "", "rule": "check-shape", "text": "a check profile is an object or an array of objects"}],
                "tightened": []}
    reasons = []
    for i in range(max(len(o), len(n))):
        if i >= len(n):
            reasons.append({"path": str(i), "rule": "check-row-removed"})
        elif i >= len(o):
            reasons.append({"path": str(i), "rule": "check-row-added"})
        else:
            for k in sorted({*o[i], *n[i]}):
                if not _eq(o[i].get(k), n[i].get(k)):
                    reasons.append({"path": "%d/%s" % (i, k), "rule": "check-row-changed"})
    return {"verdict": REQUIRES_REVIEW if reasons else PROVEN_SAFE, "reasons": reasons, "tightened": []}


# ---- the guard's line ----

def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _read_one(text):
    """The one JSON value in `text`, or raise ValueError (jq -s length == 1)."""
    decoder = json.JSONDecoder()
    values, i = [], 0
    while True:
        while i < len(text) and text[i] in " \t\r\n":
            i += 1
        if i >= len(text):
            break
        value, i = decoder.raw_decode(text, i)
        values.append(value)
    if len(values) != 1:
        raise ValueError("not exactly one value")
    return values[0]


def _line(result):
    if result["verdict"] == INVALID:
        return "invalid " + result["reasons"][0]["text"]
    paths = [r["path"] for r in result["reasons"]]
    if paths:
        return "loose " + json.dumps(paths, separators=(",", ":"), ensure_ascii=False)
    if result["tightened"]:
        return "ok nothing loosened; listed tightenings " + json.dumps(result["tightened"], separators=(",", ":"), ensure_ascii=False)
    return "ok nothing loosened"


def judge_files(old_file, new_file, tighten_text=None, name=""):
    """What the guard prints for one changed file. `new_file` empty means the change deleted it."""
    if not old_file or not os.access(old_file, os.R_OK) or not os.path.isfile(old_file):
        return "invalid cannot read the base file"
    is_check = os.path.basename(name or "") == config.get("compatibility", "checkFile")
    try:
        old = _load(old_file)
    except (OSError, ValueError):
        old = None
    if not is_check:
        schema_url = re.compile(config.get("compatibility", "schemaUrlPattern"))
        declared = old.get("$schema") if isinstance(old, dict) else None
        if not (isinstance(declared, str) and schema_url.search(declared)):
            return "skip not a JSON schema"
    elif old is None:
        return "invalid both files must be JSON"
    if not new_file:
        return "loose " + json.dumps([DELETED])
    try:
        text = "[]" if tighten_text is None else tighten_text
        tighten = _read_one(text)
    except ValueError:
        tighten = False  # not a list: classify() reports it invalid
    if is_check:
        try:
            return _line(classify_check(old, _load(new_file)))
        except (OSError, ValueError):
            return "invalid both files must be JSON"
    try:
        new = _load(new_file)
    except (OSError, ValueError):
        return "invalid both files must be JSON"
    return _line(classify(old, new, tighten))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="practice_ci.compatibility")
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", default="", help="empty when the change deleted the file")
    ap.add_argument("--tighten", default=None)
    ap.add_argument("--name", default="", help="the file's path in the repository")
    args = ap.parse_args(argv)
    print(judge_files(args.old, args.new, args.tighten, args.name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
