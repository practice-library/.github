"""schema-check's guards mode, runnable locally: apply each mutant in a guards file to a schema and require
that it turns at least one example or counter-example red.

A guards file is {"examples": <dir or [dirs]>, "counter-examples": <dir or [dirs]>, "mutants": [...]}, the
directories relative to the file. A mutant names a place by JSON Pointer (RFC 6901) that must exist, and either
{"mutation": "delete"}, {"mutation": "true"} or {"set": <value>}. A mutant that names nothing is an error,
never a pass.
"""
import argparse
import copy
import json
import os
import re
import subprocess
import tempfile

from .. import config

PASS, FINDING, ERROR = "pass", "finding", "error"


class MutantError(ValueError):
    pass


def _tokens(pointer):
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise MutantError("pointer must start with /")
    out = []
    for t in pointer[1:].split("/"):
        if re.search(r"~([^01]|$)", t):
            raise MutantError("~ must be written ~0 or ~1")
        out.append(t.replace("~1", "/").replace("~0", "~"))
    return out


def apply_mutant(doc, mutant):
    """The schema with one mutant applied (a new document)."""
    if not isinstance(mutant, dict) or not isinstance(mutant.get("pointer"), str):
        raise MutantError("mutant must be an object with a pointer")
    if "set" in mutant and "mutation" in mutant:
        raise MutantError("a mutant has either mutation or set")
    doc = copy.deepcopy(doc)
    parent, key, here = None, None, doc
    for t in _tokens(mutant["pointer"]):
        if isinstance(here, dict) and t in here:
            parent, key, here = here, t, here[t]
        elif isinstance(here, list) and re.fullmatch(r"0|[1-9][0-9]*", t) and int(t) < len(here):
            parent, key, here = here, int(t), here[int(t)]
        else:
            raise MutantError("no such place: " + mutant["pointer"])
    if parent is None:
        raise MutantError("the document itself cannot be mutated")
    if "set" in mutant:
        parent[key] = mutant["set"]
    elif mutant.get("mutation") == "delete":
        del parent[key]
    elif mutant.get("mutation") == "true":
        parent[key] = True
    else:
        raise MutantError("mutation must be delete or true, or use set")
    return doc


def _dirs(value):
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and value and all(isinstance(v, str) for v in value):
        return value
    raise MutantError("a directory or a list of directories is required")


def _files(base, dirs):
    out = []
    for d in _dirs(dirs):
        full = os.path.join(base, d)
        if not os.path.isdir(full):
            raise MutantError("no directory " + d)
        for root, _, names in os.walk(full):
            out += [os.path.join(root, n) for n in names if n.endswith(".json")]
    return sorted(out)


def load_guards(path):
    with open(path, encoding="utf-8") as f:
        g = json.load(f)
    base = os.path.dirname(os.path.abspath(path))
    if not isinstance(g, dict) or not isinstance(g.get("mutants"), list) or not g["mutants"]:
        raise MutantError("guards must be {examples, counter-examples, mutants: [at least one]}")
    examples, counters = _files(base, g.get("examples")), _files(base, g.get("counter-examples"))
    if not examples or not counters:
        raise MutantError("guards needs at least one example and one counter-example")
    return examples, counters, g["mutants"], base


def judge(validate, schema, examples, counters):
    """('green', None) or ('red', file) or ('error', file); validate(schema, path) -> PASS | FINDING | ERROR."""
    for f in examples:
        r = validate(schema, f)
        if r == FINDING:
            return "red", f
        if r != PASS:
            return "error", f
    for f in counters:
        r = validate(schema, f)
        if r == PASS:
            return "red", f
        if r != FINDING:
            return "error", f
    return "green", None


def run(schema, guards_path, validate):
    """Findings (text) for `schema` (a parsed document) against the guards file; empty means every mutant was caught."""
    examples, counters, mutants, base = load_guards(guards_path)
    verdict, where = judge(validate, schema, examples, counters)
    if verdict != "green":
        return ["the unmutated schema already gives %s %s; fix the fixtures first" % (verdict, os.path.relpath(where, base))]
    findings = []
    for m in mutants:
        label = json.dumps(m, sort_keys=True)
        try:
            mutated = apply_mutant(schema, m)
        except MutantError as e:
            findings.append("%s: %s" % (label, e))
            continue
        verdict, where = judge(validate, mutated, examples, counters)
        if verdict == "green":
            findings.append("survived %s: no example or counter-example turned red" % label)
        elif verdict == "error":
            findings.append("%s: the validator could not run on %s" % (label, os.path.relpath(where, base)))
    return findings


def subprocess_validator(binary, resolve=()):
    finding_rc = config.get("tools", "jsonschema", "findingExitCode")

    def validate(schema, path):
        with tempfile.TemporaryDirectory() as tmp:
            sp = os.path.join(tmp, "schema.json")
            with open(sp, "w", encoding="utf-8") as f:
                json.dump(schema, f)
            cmd = [binary, "validate"]
            for r in resolve:
                cmd += ["--resolve", r]
            rc = subprocess.run(cmd + [sp, path], capture_output=True).returncode
        return PASS if rc == 0 else FINDING if rc == finding_rc else ERROR
    return validate


def main(argv=None):
    ap = argparse.ArgumentParser(prog="practice_ci.guards")
    ap.add_argument("--validator", required=True, help="the pinned jsonschema binary")
    ap.add_argument("--schema", required=True)
    ap.add_argument("--guards", required=True)
    ap.add_argument("--resolve", action="append", default=[])
    args = ap.parse_args(argv)
    with open(args.schema, encoding="utf-8") as f:
        schema = json.load(f)
    try:
        findings = run(schema, args.guards, subprocess_validator(args.validator, args.resolve))
    except MutantError as e:
        print("::error::" + str(e))
        return 1
    for f in findings:
        print("::error::" + f)
    print("%d findings" % len(findings))
    return 1 if findings else 0
