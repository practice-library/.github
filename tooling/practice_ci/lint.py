"""The policy-literals lint: a value the policy owns is written once, in policy/constants.json, and every
consumer refers to it. It checks ownership in three narrow places, not every literal in the repository:

1. Workflow templates (templates/**/*.yml, outside comments): the runner image, job timeouts, the
   interpreter version and action pins must be policy placeholders; no download URL, retry count or
   40-hex commit may be written out; no value of a label the policy owns may appear. A #@include names
   only a bootstrap fragment (render.bootstrapIncludes): executable code is never inlined otherwise.
2. The package (tooling/practice_ci): only policy.py names the constants file; a call to policy.value
   takes the key alone (no default to drift from the policy); and the designated policy-bearing keyword
   arguments (DESIGNATED) are never given a literal.
3. Generated files are not linted: scripts/render.sh --check proves they are exactly the render.

Field names, language syntax, test data and historical prose (CHANGELOG, docs) are out of scope.
"""

import ast
import re
from pathlib import Path

from . import policy
from .result import FAIL, PASS, Evidence, Result

# Workflow keys whose value the policy owns: the whole value must be placeholders or an expression.
OWNED_KEYS = ("runs-on", "timeout-minutes", "python-version")
# Policy keys whose values are label names (or a label prefix) a workflow must not spell out.
LABEL_KEYS = ("guards.loosenLabel", "guards.sizeLabel", "protocol.invalidLabel", "protocol.kindLabelPrefix")
# Keyword arguments that carry policy wherever they appear in the package.
DESIGNATED = frozenset({"timeout", "retries", "label", "url", "default"})

_PLACEHOLDERS = re.compile(r"(?:@@[A-Za-z0-9_.:-]+@@|\$\{\{[^}]*\}\})+")
_KEY_LINE = re.compile(r"^\s*(?:-\s+)?([A-Za-z0-9_-]+):\s*(.*?)\s*$")
_URL = re.compile(r"https?://")
_RETRY = re.compile(r"--retry(?:-[a-z-]+)?[ =]+[0-9]")
_SHA1 = re.compile(r"(?<![0-9a-f])[0-9a-f]{40}(?![0-9a-f])")
_INCLUDE = re.compile(r"^\s*#@include\s+(\S+)")


def _owned_value(value: str) -> bool:
    value = value.split(" #", 1)[0].strip().strip("'\"")
    return bool(_PLACEHOLDERS.fullmatch(value))


def _uses_ok(value: str) -> bool:
    value = value.split(" #", 1)[0].strip()
    return value.startswith("./") or "@@" in value


def lint_template(path: Path, rel: str, labels: list[str], includes: list[str]) -> list[tuple[str, Evidence, str]]:
    found = []
    for n, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
        at = Evidence(rel, n)
        inc = _INCLUDE.match(line)
        if inc and inc.group(1) not in includes:
            found.append(("include", at, "only the bootstrap (render.bootstrapIncludes) is inlined; %s runs from "
                                         "the tooling checkout" % inc.group(1)))
        if line.lstrip().startswith("#"):
            continue
        m = _KEY_LINE.match(line)
        if m and m.group(1) in OWNED_KEYS and m.group(2) and not _owned_value(m.group(2)):
            found.append(("owned-key", at, "%s must be a policy placeholder" % m.group(1)))
        if m and m.group(1) == "uses" and not _uses_ok(m.group(2)):
            found.append(("pin", at, "an action or workflow reference must come from the policy"))
        if _URL.search(line):
            found.append(("download", at, "a URL must come from the policy"))
        if _RETRY.search(line):
            found.append(("retry", at, "a retry count must come from the policy"))
        if _SHA1.search(line):
            found.append(("pin", at, "a commit must come from the policy"))
        for label in labels:
            if label in line:
                found.append(("label", at, "the label %r must come from the policy" % label))
    return found


def _literal(node) -> bool:
    return (isinstance(node, ast.Constant) and node.value is not None) or isinstance(node, ast.JoinedStr)


def lint_python(path: Path, rel: str, constants_name: str) -> list[tuple[str, Evidence, str]]:
    found = []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
    accessor = path.name == "policy.py"
    # Docstrings are prose: they may name the file.
    prose = {id(n.body[0].value) for n in ast.walk(tree)
             if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
             and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}
    for node in ast.walk(tree):
        if (not accessor and id(node) not in prose and isinstance(node, ast.Constant) and isinstance(node.value, str)
                and constants_name in node.value):
            found.append(("policy-file", Evidence(rel, node.lineno), "only policy.py reads " + constants_name))
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg in DESIGNATED and _literal(kw.value):
                found.append(("policy-literal", Evidence(rel, kw.value.lineno),
                              "%s= is policy: read it with policy.value" % kw.arg))
        f = node.func
        if (isinstance(f, ast.Attribute) and f.attr == "value" and isinstance(f.value, ast.Name)
                and f.value.id == "policy" and (len(node.args) != 1 or node.keywords)):
            found.append(("policy-default", Evidence(rel, node.lineno), "policy.value takes the key alone"))
    return found


def run(root: Path) -> Result:
    labels = [policy.value(k) for k in LABEL_KEYS]
    includes = policy.value("render.bootstrapIncludes")
    templates = policy.path("render.templatesDir")
    package = policy.path("tooling.package")
    found = []
    files = 0
    for path in sorted(templates.rglob("*.yml")):
        files += 1
        found += lint_template(path, str(path.relative_to(root)), labels, includes)
    for path in sorted(package.rglob("*.py")):
        files += 1
        found += lint_python(path, str(path.relative_to(root)), policy.CONSTANTS.name)
    for rule, at, why in found:
        print("FAIL %s %s:%d: %s" % (rule, at.path, at.line, why))
    if found:
        return Result(FAIL, "lint.findings", "lint: %d files, %d findings" % (files, len(found)),
                      tuple(at for _, at, _ in found))
    return Result(PASS, "lint.clean", "lint: %d files, no finding" % files)
