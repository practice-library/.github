"""Ownership-based literals lint: a policy value is owned by policy/constants.json, never typed in place.

Only the designated places are judged (they are listed in policy/constants.json under tooling.lint):
  Python under tooling/  a number or string literal as a policy keyword argument (timeout=, label=, ...),
                         as a designated positional argument (urlopen, sleep, ...), or compared with a
                         policy-named variable (limit, size, ...); any string literal that is a URL.
  workflow templates     a timeout, retry count, label name, URL or action pin written as text.
A literal passes when it comes from config.get(...) or a render placeholder (@@...@@).

Usage: practice-ci lint-literals [<root>]   (root defaults to the repository root)
"""
import ast
import os
import re

from practice_ci import config, result

CHECK = "lint-literals"


def _call_name(node):
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _is_literal(node, allowed):
    """A number or string typed in place. None, booleans and the allowed small numbers are not policy."""
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return any(_is_literal(item, allowed) for item in node.elts)
    if isinstance(node, ast.Dict):
        return any(_is_literal(item, allowed) for item in node.values)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        return _is_literal(node.operand, allowed)
    if not isinstance(node, ast.Constant):
        return False
    value = node.value
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, (int, float)):
        return value not in allowed
    return isinstance(value, (str, bytes))


def _name_of(node):
    if isinstance(node, ast.Call) and _call_name(node) == "len" and node.args:
        return _name_of(node.args[0])
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _docstrings(tree):
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                found.add(id(body[0].value))
    return found


def lint_python(source, name, rules):
    """Findings for one Python source text, as 'name:line: reason' strings."""
    tree = ast.parse(source, filename=name)
    allowed = set(rules["allowedNumbers"])
    keywords = set(rules["policyKeywords"])
    calls = {c["call"]: c["positions"] for c in rules["policyCalls"]}
    names = set(rules["policyNames"])
    url = re.compile(rules["urlPattern"])
    docs = _docstrings(tree)
    findings = []

    def add(node, why):
        findings.append("%s:%d: %s" % (name, node.lineno, why))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg in keywords and _is_literal(kw.value, ()):
                    add(kw.value, "literal %s for policy argument %s=; read it with config.get" % (ast.unparse(kw.value), kw.arg))
            for pos in calls.get(_call_name(node), []):
                if pos < len(node.args) and _is_literal(node.args[pos], ()):
                    add(node.args[pos], "literal %s as argument %d of %s(); read it with config.get" % (ast.unparse(node.args[pos]), pos, _call_name(node)))
        elif isinstance(node, ast.Compare):
            operands = [node.left] + list(node.comparators)
            for a, b in zip(operands, operands[1:]):
                for var, lit in ((a, b), (b, a)):
                    if _name_of(var) in names and _is_literal(lit, allowed):
                        add(lit, "literal %s compared with policy value %s; read it with config.get" % (ast.unparse(lit), _name_of(var)))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
            if url.search(node.value):
                add(node, "URL literal %r; read it with config.get" % node.value)
    return findings


def lint_text(text, name, rules):
    """Findings for one workflow template or fragment: designated patterns written as text."""
    compiled = [(r["id"], re.compile(r["regex"]), r["why"]) for r in rules["textRules"]]
    findings = []
    for number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        for rule_id, regex, why in compiled:
            if regex.search(line):
                findings.append("%s:%d: %s: %s" % (name, number, rule_id, why))
    return findings


def _walk(root, subdirs, suffixes, exclude=()):
    for sub in subdirs:
        for folder, dirs, files in os.walk(os.path.join(root, sub)):
            dirs[:] = sorted(d for d in dirs if d not in exclude and d != "__pycache__")
            for f in sorted(files):
                if f.endswith(suffixes):
                    yield os.path.join(folder, f)


def lint_tree(root, rules):
    findings, scanned = [], 0
    for path in _walk(root, rules["pythonRoots"], (".py",), set(rules["pythonExcludeDirs"])):
        scanned += 1
        with open(path, encoding="utf-8") as f:
            findings += lint_python(f.read(), os.path.relpath(path, root), rules)
    for path in _walk(root, rules["templateRoots"], tuple(rules["templateSuffixes"])):
        scanned += 1
        with open(path, encoding="utf-8") as f:
            findings += lint_text(f.read(), os.path.relpath(path, root), rules)
    return findings, scanned


def run(args, constants_path=None):
    if len(args) > 1:
        return result.error(CHECK, "usage: practice-ci lint-literals [<root>]")
    root = args[0] if args else os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    rules = config.get("tooling", "lint", path=constants_path)
    findings, scanned = lint_tree(root, rules)
    evidence = ["%d files scanned" % scanned]
    if findings:
        return result.failed(CHECK, findings, evidence)
    return result.passed(CHECK, evidence)
