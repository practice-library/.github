"""The mutation runner. Every mutant is applied to an isolated copy of this checkout, never to the tree
itself, and the copy is restored after each one.

A mutants file is <tooling.mutantsDir>/<name>.json, either a list of {"name", "find", "replace"} for the
fragment <name>.sh, judged by its unit cases, or {"suite": ..., "target": <path>, "mutants": [...]}
where a mutant may name its own "target". Suites:
  unit:<fragment>  scripts/unit.sh <fragment>; a red case is a FAIL whose result is not "error ..."
  canary           scripts/denylist-canary.sh; a red scenario is a FAIL, an ERROR is not a kill
  lint             the policy-literals lint; exit 1 is a kill, anything else an error
  unittest:<glob>  python -I -m unittest over tooling/tests files matching the glob; FAIL kills, ERROR not

A mutant is caught only when a test turns red for a reason, that is a wrong verdict. A mutant whose
program does not parse (bash -n, Python compile, or a changed jq or Python program embedded in a shell
file), or that only makes tests error, is an invalid mutant: it proves nothing, and the run fails.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import policy
from .result import FAIL, PASS, Result


@dataclass(frozen=True)
class Mutant:
    name: str
    target: str
    find: str
    replace: str


def load(path: Path) -> tuple[str, list[Mutant]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        suite = "unit:" + path.stem
        target = str(Path(policy.value("render.fragmentsDir")) / (path.stem + ".sh"))
        rows = data
    else:
        suite = data["suite"]
        target = data.get("target")
        rows = data["mutants"]
    if not rows:
        raise ValueError("no mutants")
    out = []
    for row in rows:
        where = row.get("target") or target
        if not where:
            raise ValueError("mutant %s names no target" % row.get("name"))
        out.append(Mutant(row["name"], where, row["find"], row["replace"]))
    return suite, out


# --- suites -------------------------------------------------------------------------------------------

def _command(suite: str, copy: Path) -> list[str]:
    kind, _, arg = suite.partition(":")
    if kind == "unit" and arg:
        return ["bash", str(copy / policy.value("self.unitScript")), arg]
    if kind == "canary" and not arg:
        return ["bash", str(copy / policy.value("self.denylistCanary"))]
    if kind == "lint" and not arg:
        return [str(copy / policy.value("tooling.launcher")), "lint"]
    if kind == "unittest" and arg:
        tooling = Path(policy.value("tooling.package")).parent
        return [sys.executable, "-I", "-B", "-m", "unittest", "discover", "-s", str(copy / tooling / "tests"),
                "-t", str(copy / tooling), "-p", arg]
    raise ValueError("unknown suite: " + suite)


def purge_bytecode(copy: Path) -> None:
    """Drops every compiled module in the copy. A restored source can have the size and the whole-second
    mtime of the mutant it replaces, and Python would then load the mutant's cached bytecode for it."""
    for cache in sorted(copy.rglob("__pycache__")):
        shutil.rmtree(cache, ignore_errors=True)


def run_suite(suite: str, copy: Path, original: Path) -> tuple[int, str]:
    purge_bytecode(copy)
    env = dict(os.environ)
    # The canary reads one past merge commit's author from history; the copy has no .git.
    env["CANARY_HISTORY"] = str(original)
    proc = subprocess.run(_command(suite, copy), cwd=copy, env=env, stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    return proc.returncode, proc.stdout.decode("utf-8", "replace")


_UNIT = re.compile(r"^FAIL (\S+?): want \S+, got: (.*)$")
_TEST = re.compile(r"^(FAIL|ERROR): (\S+)")


def outcome(suite: str, rc: int, out: str) -> tuple[list[str], list[str]]:
    """(red, errors): what turned red for a reason, and what only errored."""
    red, errors = [], []
    kind = suite.partition(":")[0]
    for line in out.split("\n"):
        if kind == "unit":
            m = _UNIT.match(line)
            if m:
                (errors if m.group(2).startswith("error ") else red).append(m.group(1))
            elif line.startswith("FAIL "):
                errors.append(line[5:].split(":", 1)[0])
        elif kind == "canary":
            if line.startswith("FAIL "):
                red.append(line[5:].split(":", 1)[0])
            elif line.startswith("ERROR "):
                errors.append(line[6:].split(":", 1)[0])
        elif kind == "unittest":
            m = _TEST.match(line)
            if m:
                (red if m.group(1) == "FAIL" else errors).append(m.group(2))
    if kind == "lint":
        if rc == 1:
            red = [line for line in out.split("\n") if line.startswith("FAIL ")] or ["lint"]
        elif rc != 0:
            errors = ["lint exit %d" % rc]
    if rc != 0 and not red and not errors:
        errors = ["%s exit %d" % (suite, rc)]
    return red, errors


# --- parse checks -------------------------------------------------------------------------------------

_QUOTED = re.compile(r"'([^']*)'")
_JQ_OPTIONS = re.compile(
    r"jq(?:\s+(?:--(?:arg|argjson|slurpfile|rawfile)\s+\w+\s+(?:\"[^\"]*\"|\S+)|-[A-Za-z]+|--[a-z-]+))*\s+$")
_JQ_VAR = re.compile(r"--(arg|argjson|slurpfile|rawfile)\s+(\w+)")


def programs(text: str) -> list[tuple[str, str, tuple]]:
    """The jq and Python programs written as single-quoted arguments in a shell file."""
    flat = text.replace("\\\n", " ")
    found = []
    for m in _QUOTED.finditer(flat):
        before = flat[max(0, m.start() - 600):m.start()]
        if re.search(r"python3 -I -c\s*$", before):
            found.append(("python", m.group(1), ()))
            continue
        at = before.rfind("jq")
        if at >= 0 and "'" not in before[at:] and _JQ_OPTIONS.fullmatch(before[at:]):
            found.append(("jq", m.group(1), tuple(_JQ_VAR.findall(before[at:]))))
    return found


def compiles(kind: str, body: str, variables: tuple) -> bool:
    if kind == "python":
        try:
            compile(body, "<embedded>", "exec")
        except SyntaxError:
            return False
        return True
    args = ["jq", "-n"]
    for flag, name in variables:
        args += ["--arg", name, ""] if flag in ("arg", "rawfile") else ["--argjson", name, "null"]
    args.append("def __probe: (%s); empty" % body)
    return subprocess.run(args, capture_output=True, check=False).returncode == 0


def parse_problem(target: Path, original: str, mutated: str) -> str | None:
    if target.suffix == ".py":
        try:
            compile(mutated, str(target), "exec")
        except SyntaxError as e:
            return "Python does not compile: %s" % e.msg
        return None
    if target.suffix != ".sh":
        return None
    if subprocess.run(["bash", "-n", str(target)], capture_output=True, check=False).returncode != 0:
        return "bash -n refuses it"
    before, after = programs(original), programs(mutated)
    if len(before) != len(after):
        return None
    for (kind, body, variables), old in zip(after, before):
        if (kind, body, variables) == old:
            continue
        # Judge a changed program only where the checker can compile the unmutated one.
        if compiles(*old) and not compiles(kind, body, variables):
            return "a changed %s program does not compile" % kind
    return None


# --- the run ------------------------------------------------------------------------------------------

def _one(m: Mutant, label: str, suite: str, copy: Path, original: Path) -> tuple[bool, str]:
    target = copy / m.target
    if not target.is_file():
        return False, "FAIL %s: no target %s" % (label, m.target)
    raw = target.read_bytes()
    text = raw.decode("utf-8")
    if m.find not in text:
        return False, "FAIL %s: the find text is not in %s (a stale mutant)" % (label, m.target)
    mutated = text.replace(m.find, m.replace, 1)
    if mutated == text:
        return False, "FAIL %s: the mutant changes nothing" % label
    target.write_bytes(mutated.encode("utf-8"))
    try:
        problem = parse_problem(target, text, mutated)
        if problem:
            return False, "FAIL %s: invalid mutant, %s, so it proves nothing" % (label, problem)
        rc, out = run_suite(suite, copy, original)
        red, errors = outcome(suite, rc, out)
        if red:
            return True, "caught %s by %s" % (label, " ".join(red))
        if errors:
            return False, "FAIL %s: invalid mutant, it only made %s error" % (label, " ".join(errors))
        return False, "FAIL %s: survived, nothing turned red" % label
    finally:
        target.write_bytes(raw)


def run(root: Path, names: list[str]) -> Result:
    directory = policy.path("tooling.mutantsDir")
    files = [directory / (n + ".json") for n in names] if names else sorted(directory.glob("*.json"))
    total = bad = 0
    scratch = Path(tempfile.mkdtemp(prefix="practice-ci-mutants-"))
    try:
        copy = scratch / "tree"
        shutil.copytree(root, copy, symlinks=True, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        green: dict[str, bool] = {}
        for f in files:
            try:
                suite, mutants = load(f)
                _command(suite, copy)
            except (OSError, ValueError, KeyError) as e:
                print("FAIL %s: unreadable mutants file: %s" % (f.stem, e))
                bad += 1
                continue
            if suite not in green:
                rc, out = run_suite(suite, copy, root)
                green[suite] = rc == 0 and outcome(suite, rc, out) == ([], [])
                if not green[suite]:
                    print("FAIL %s: the unmutated copy is not green, so no mutant can be judged:\n%s" % (suite, out))
            for m in mutants:
                total += 1
                label = "%s/%s" % (f.stem, m.name)
                if not green[suite]:
                    bad += 1
                    continue
                caught, line = _one(m, label, suite, copy, root)
                print(line, flush=True)
                bad += 0 if caught else 1
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    message = "%d mutants, %d not caught" % (total, bad)
    if bad or not total:
        return Result(FAIL, "mutants.not-caught", message)
    return Result(PASS, "mutants.all-caught", message)
