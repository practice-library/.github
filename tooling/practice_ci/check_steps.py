"""The shell inside workflow steps: extract every `run:` block of a workflow or fragment, and check it parses.

Usage: practice-ci check-steps <file>...
Also the extraction the step tests and the mutation runner use (run_blocks).
"""
import re
import subprocess

from practice_ci import result

CHECK = "check-steps"
_STEP_NAME = re.compile(r"^\s*-\s+name:\s*(?P<name>.*?)\s*$")
_RUN_KEY = re.compile(r"^(?P<ind>\s*)(?P<dash>-\s+)?run:[ ]*(?P<rest>.*?)\s*$")
_BLOCK = re.compile(r"^[|>][-+]?$")


def _indent(line):
    return len(line) - len(line.lstrip(" "))


def run_blocks(text):
    """[(step name, script)] for every run: of the text, a block scalar dedented or a one-line command."""
    lines = text.split("\n")
    blocks, name, i = [], "", 0
    while i < len(lines):
        line = lines[i]
        step = _STEP_NAME.match(line)
        if step:
            name = step.group("name")
        key = _RUN_KEY.match(line)
        if key:
            key_indent = len(key.group("ind")) + (len(key.group("dash")) if key.group("dash") else 0)
            if _BLOCK.match(key.group("rest")):
                body = []
                i += 1
                while i < len(lines) and (lines[i].strip() == "" or _indent(lines[i]) > key_indent):
                    body.append(lines[i])
                    i += 1
                lead = min((_indent(b) for b in body if b.strip()), default=0)
                blocks.append((name, "\n".join(b[lead:] for b in body).rstrip("\n") + "\n"))
                continue
            blocks.append((name, key.group("rest") + "\n"))
        i += 1
    return blocks


def block_named(text, name):
    found = [script for step, script in run_blocks(text) if step == name]
    if len(found) != 1:
        raise KeyError("%d run blocks in steps named %r" % (len(found), name))
    return found[0]


def parse_errors(text, label):
    """The reasons each run block of the text fails `bash -n`."""
    reasons = []
    for step, script in run_blocks(text):
        done = subprocess.run(["bash", "-n"], input=script, capture_output=True, text=True, check=False)
        if done.returncode != 0:
            reasons.append("%s: step %r does not parse: %s" % (label, step, done.stderr.strip()))
    return reasons


def run(args):
    if not args:
        return result.error(CHECK, "usage: practice-ci check-steps <file>...")
    reasons, blocks = [], 0
    for path in args:
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError as exc:
            return result.error(CHECK, "cannot read %s: %s" % (path, exc))
        blocks += len(run_blocks(text))
        reasons += parse_errors(text, path)
    evidence = ["%d run blocks in %d files" % (blocks, len(args))]
    return result.failed(CHECK, reasons, evidence) if reasons else result.passed(CHECK, evidence)
