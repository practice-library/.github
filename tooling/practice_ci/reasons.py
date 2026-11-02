"""Expected-reason assertions for negative fixtures.

`each` in schema-check shows that every counter-example fails, not that it fails for the reason it was written
for: after the rule it targets is gone it can keep failing for an unrelated one. A reasons file next to the
fixtures closes that. It maps each counter-example's path (relative to the spec directory) to
    {"keyword": "<the failing keyword>", "instanceLocation": "<JSON Pointer of the wrong value>"}
and a counter-example passes only when the validator reports an error of that keyword at that location
or below it (a closed object may be reported at the object or at the unknown property).

The validator's structured output is read in the standard JSON Schema output format: an object with
"errors" (or a bare list), each error carrying "keywordLocation" (its last segment is the keyword) and
"instanceLocation". NOTE: the pinned jsonschema binary was not available when this was written, so its
flag (reasons.validatorFlag in policy/constants.json) and the exact shape of its output are asserted by
test doubles in tooling/tests, not yet proven against the binary. parse_errors fails closed: output it
cannot read is a finding, never a pass.
"""
import argparse
import json
import os
import subprocess
import sys

from . import config


class ReasonError(ValueError):
    pass


def _last_segment(pointer):
    last = pointer.rstrip("/").rsplit("/", 1)[-1] if pointer else ""
    return last.replace("~1", "/").replace("~0", "~")


def parse_errors(output):
    """The (keyword, instanceLocation) pairs in the validator's structured output, as dicts."""
    try:
        doc = json.loads(output) if isinstance(output, (str, bytes)) else output
    except ValueError as e:
        raise ReasonError("the validator output is not JSON: %s" % e)
    errors = doc.get("errors") if isinstance(doc, dict) else doc
    if not isinstance(errors, list):
        raise ReasonError("the validator output has no list of errors")
    found = []
    for e in errors:
        if not isinstance(e, dict) or not isinstance(e.get("instanceLocation"), str):
            raise ReasonError("an error has no instanceLocation")
        keyword = e.get("keyword")
        if keyword is None:
            location = e.get("keywordLocation", e.get("absoluteKeywordLocation"))
            if not isinstance(location, str):
                raise ReasonError("an error has no keywordLocation")
            keyword = _last_segment(location.split("#", 1)[-1])
        found.append({"keyword": keyword, "instanceLocation": e["instanceLocation"]})
    return found


def _at_or_below(location, expected):
    return location == expected or location.startswith(expected.rstrip("/") + "/")


def holds(errors, expected):
    return any(e["keyword"] == expected["keyword"] and _at_or_below(e["instanceLocation"], expected["instanceLocation"])
               for e in errors)


def load_reasons(path):
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    if not isinstance(doc, dict) or not doc:
        raise ReasonError("%s must be a non-empty object of counter-example -> reason" % path)
    for name, r in doc.items():
        if not (isinstance(r, dict) and set(r) == {"keyword", "instanceLocation"}
                and isinstance(r["keyword"], str) and r["keyword"]
                and isinstance(r["instanceLocation"], str) and (r["instanceLocation"] == "" or r["instanceLocation"].startswith("/"))):
            raise ReasonError("%s: %s needs exactly a keyword and an instanceLocation (a JSON Pointer)" % (path, name))
    return doc


def check(reasons, files, run):
    """Findings (a list of text) for counter-example files `files` ({name: path}) against `reasons`.
    `run(path)` returns the validator's errors for that file (see parse_errors); no errors means it passed."""
    findings = []
    for name in sorted(set(files) - set(reasons)):
        findings.append("%s: no expected reason" % name)
    for name in sorted(set(reasons) - set(files)):
        findings.append("%s: a reason for a file that is not there" % name)
    for name in sorted(set(files) & set(reasons)):
        errors = run(files[name])
        if not errors:
            findings.append("%s: validates, but it is a counter-example" % name)
        elif not holds(errors, reasons[name]):
            want = reasons[name]
            got = ", ".join("%s at %s" % (e["keyword"], e["instanceLocation"] or "(root)") for e in errors)
            findings.append("%s: expected %s at %s, got %s" % (name, want["keyword"], want["instanceLocation"] or "(root)", got))
    return findings


def run_validator(binary, schema, resolve=()):
    finding_rc = config.get("tools", "jsonschema", "findingExitCode")
    flag = config.get("reasons", "validatorFlag")

    def run(path):
        cmd = [binary, "validate", flag]
        for r in resolve:
            cmd += ["--resolve", r]
        proc = subprocess.run(cmd + [schema, path], capture_output=True, text=True)
        if proc.returncode == 0:
            return []
        if proc.returncode != finding_rc:
            raise ReasonError("the validator could not run on %s: exit %d" % (path, proc.returncode))
        return parse_errors(proc.stdout)
    return run


def main(argv=None):
    ap = argparse.ArgumentParser(prog="practice_ci.reasons")
    ap.add_argument("--validator", required=True, help="the pinned jsonschema binary")
    ap.add_argument("--schema", required=True)
    ap.add_argument("--dir", required=True, help="the counter-examples directory")
    ap.add_argument("--reasons", required=True, help="the reasons file; its keys are relative to --base")
    ap.add_argument("--base", required=True, help="the directory the reasons file's keys are relative to")
    ap.add_argument("--resolve", action="append", default=[])
    args = ap.parse_args(argv)
    reasons = load_reasons(args.reasons)
    prefix = os.path.relpath(args.dir, args.base)
    files = {}
    for root, _, names in os.walk(args.dir):
        for n in sorted(names):
            if n.endswith(".json"):
                full = os.path.join(root, n)
                files[os.path.relpath(full, args.base)] = full
    findings = check({k: v for k, v in reasons.items() if k.startswith(prefix + os.sep)}, files,
                     run_validator(args.validator, args.schema, args.resolve))
    for f in findings:
        print("::error::" + f)
    print("%d counter-examples, %d wrong" % (len(files), len(findings)))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
