"""A small stdlib JSON Schema (2020-12 subset) evaluator, for the tests only.

It checks the spec fixtures and guard mutants without the pinned validator binary, and returns the
structured findings (keyword, keywordLocation, instanceLocation) the expected-reason assertions read.
It is NOT the CI authority: CI runs the pinned validator. An unknown keyword raises, so a schema that
uses something this file does not implement can never pass silently.
"""
import re

ANNOTATIONS = {"$schema", "$id", "$defs", "$comment", "title", "description", "default", "examples", "format"}


def _ptr(parts):
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def _type_ok(t, v):
    if t == "object":
        return isinstance(v, dict)
    if t == "array":
        return isinstance(v, list)
    if t == "string":
        return isinstance(v, str)
    if t == "boolean":
        return isinstance(v, bool)
    if t == "null":
        return v is None
    if t == "number":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    if t == "integer":
        return (isinstance(v, int) and not isinstance(v, bool)) or (isinstance(v, float) and v.is_integer())
    raise ValueError("unknown type " + t)


def _eq(a, b):
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_eq(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_eq(a[k], b[k]) for k in a)
    return a == b


class Validator:
    def __init__(self, root):
        self.root = root

    def errors(self, instance):
        out = []
        self._check(self.root, instance, [], [], out)
        return out

    def valid(self, instance):
        return not self.errors(instance)

    def _resolve(self, ref):
        if ref == "#":
            return self.root
        if not ref.startswith("#/"):
            raise ValueError("only local references are implemented: " + ref)
        node = self.root
        for part in ref[2:].split("/"):
            node = node[part.replace("~1", "/").replace("~0", "~")]
        return node

    def _check(self, schema, inst, loc, kloc, out):
        if schema is True:
            return
        if schema is False:
            out.append(self._err("false", kloc, loc, "false schema"))
            return
        for key in list(schema):
            if key in ANNOTATIONS:
                continue
            handler = getattr(self, "_k_" + key.lstrip("$").replace("-", "_"), None)
            if handler is None:
                raise ValueError("keyword not implemented by the test validator: " + key)
            handler(schema, schema[key], inst, loc, kloc + [key], out)
        # then/else are applied by `if`; items and others are handled by their own methods.

    @staticmethod
    def _err(keyword, kloc, loc, text):
        return {"keyword": keyword, "keywordLocation": _ptr(kloc), "instanceLocation": _ptr(loc), "error": text}

    def _k_type(self, schema, v, inst, loc, kloc, out):
        types = v if isinstance(v, list) else [v]
        if not any(_type_ok(t, inst) for t in types):
            out.append(self._err("type", kloc, loc, "wrong type"))

    def _k_const(self, schema, v, inst, loc, kloc, out):
        if not _eq(v, inst):
            out.append(self._err("const", kloc, loc, "not the constant"))

    def _k_enum(self, schema, v, inst, loc, kloc, out):
        if not any(_eq(x, inst) for x in v):
            out.append(self._err("enum", kloc, loc, "not in the enum"))

    def _k_pattern(self, schema, v, inst, loc, kloc, out):
        if isinstance(inst, str) and re.search(v, inst) is None:
            out.append(self._err("pattern", kloc, loc, "does not match"))

    def _num(self, name, test):
        def handler(schema, v, inst, loc, kloc, out):
            if isinstance(inst, (int, float)) and not isinstance(inst, bool) and not test(inst, v):
                out.append(self._err(name, kloc, loc, name))
        return handler

    def _k_minimum(self, *a):
        self._num("minimum", lambda i, v: i >= v)(*a)

    def _k_maximum(self, *a):
        self._num("maximum", lambda i, v: i <= v)(*a)

    def _k_minLength(self, schema, v, inst, loc, kloc, out):
        if isinstance(inst, str) and len(inst) < v:
            out.append(self._err("minLength", kloc, loc, "too short"))

    def _k_maxLength(self, schema, v, inst, loc, kloc, out):
        if isinstance(inst, str) and len(inst) > v:
            out.append(self._err("maxLength", kloc, loc, "too long"))

    def _k_minItems(self, schema, v, inst, loc, kloc, out):
        if isinstance(inst, list) and len(inst) < v:
            out.append(self._err("minItems", kloc, loc, "too few"))

    def _k_maxItems(self, schema, v, inst, loc, kloc, out):
        if isinstance(inst, list) and len(inst) > v:
            out.append(self._err("maxItems", kloc, loc, "too many"))

    def _k_required(self, schema, v, inst, loc, kloc, out):
        if isinstance(inst, dict):
            for name in v:
                if name not in inst:
                    out.append(self._err("required", kloc, loc, "missing " + name))

    def _k_properties(self, schema, v, inst, loc, kloc, out):
        if isinstance(inst, dict):
            for name, sub in v.items():
                if name in inst:
                    self._check(sub, inst[name], loc + [name], kloc + [name], out)

    def _k_additionalProperties(self, schema, v, inst, loc, kloc, out):
        if isinstance(inst, dict):
            for name in inst:
                if name not in schema.get("properties", {}):
                    if v is False:
                        out.append(self._err("additionalProperties", kloc, loc, "unknown property " + name))
                    else:
                        self._check(v, inst[name], loc + [name], kloc, out)

    def _k_items(self, schema, v, inst, loc, kloc, out):
        if isinstance(inst, list):
            for i, item in enumerate(inst):
                self._check(v, item, loc + [i], kloc, out)

    def _k_ref(self, schema, v, inst, loc, kloc, out):
        self._check(self._resolve(v), inst, loc, kloc, out)

    def _k_allOf(self, schema, v, inst, loc, kloc, out):
        for i, sub in enumerate(v):
            self._check(sub, inst, loc, kloc + [i], out)

    def _k_anyOf(self, schema, v, inst, loc, kloc, out):
        if all(self._probe(sub, inst) for sub in v):
            out.append(self._err("anyOf", kloc, loc, "no branch matches"))

    def _k_if(self, schema, v, inst, loc, kloc, out):
        probe = []
        self._check(v, inst, loc, kloc, probe)
        branch = "then" if not probe else "else"
        if branch in schema:
            self._check(schema[branch], inst, loc, kloc[:-1] + [branch], out)

    def _k_then(self, *a):
        pass

    def _k_else(self, *a):
        pass

    def _k_contains(self, schema, v, inst, loc, kloc, out):
        if isinstance(inst, list) and not any(not self._probe(v, item) for item in inst):
            out.append(self._err("contains", kloc, loc, "no item matches"))

    def _probe(self, schema, inst):
        probe = []
        self._check(schema, inst, [], [], probe)
        return probe
