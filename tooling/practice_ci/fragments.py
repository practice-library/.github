"""Runs a shell fragment from this checkout's fragments directory and turns its verdict into a Result.

The fragments stay the single authored source of the rules they hold; this module only runs them. Each
fragment prints one verdict line, "<token> <detail>". VOCABULARY declares, per fragment, every token it
may print and the status that token means; a token outside that closed set, a fragment that exits
non-zero, or an unknown fragment is an error, never a pass. A fragment whose success output is a JSON
document declares the token JSON.
"""

import json
import os
import subprocess
from pathlib import Path

from . import policy
from .result import ERROR, FAIL, PASS, Result

JSON = "<json>"

VOCABULARY = {
    "automerge-decide": {"on": PASS, "off": FAIL},
    "codeowners-allow": {"ok": PASS, "owned": FAIL, "unsupported": FAIL},
    "denylist-exempt": {"ok": PASS, "widened": FAIL, "invalid": FAIL},
    "denylist-scan": {"ok": PASS, "found": FAIL, "unguarded": FAIL, "invalid": FAIL},
    "discover-targets": {"ok": PASS, "error": FAIL},
    "each-result": {"pass": PASS, "finding": FAIL, "mixed": FAIL},
    "gate-required": {"ok": PASS, "missing": FAIL, "unlisted": FAIL, "invalid": FAIL},
    "label-approval": {"ok": PASS, "missing": FAIL, "refused": FAIL},
    "message-extract": {"ok": PASS, "none": FAIL, "invalid": FAIL},
    "pin-check": {"ok": PASS, "unpinned": FAIL, "invalid": FAIL},
    "release-note": {"ok": PASS, "missing": FAIL, "invalid": FAIL},
    "removed-refs": {"ok": PASS, "referenced": FAIL, "invalid": FAIL},
    "schema-loosening": {"ok": PASS, "skip": PASS, "loose": FAIL, "invalid": FAIL},
    "schema-mutate": {JSON: PASS, "invalid": FAIL},
    "size-count": {"ok": PASS, "over": FAIL, "invalid": FAIL},
    "tool-checkout": {"ok": PASS, "mismatch": FAIL, "bootstrap": FAIL, "invalid": FAIL},
    "tool-identity": {"ok": PASS, "invalid": FAIL},
}

# Fragments no command here runs: they ship inside a published artifact (spec/ratchet/reconcile.sh).
NOT_RUN_HERE = frozenset({"ratchet"})


def source(name: str) -> Path:
    return policy.path("render.fragmentsDir") / (name + ".sh")


def judge(name: str, output: str) -> Result:
    """The Result a fragment's output means, by its declared vocabulary."""
    vocabulary = VOCABULARY[name]
    if JSON in vocabulary:
        try:
            json.loads(output)
        except ValueError:
            pass
        else:
            return Result(vocabulary[JSON], name + ".json", output.split("\n", 1)[0], detail=output)
    first = output.split("\n", 1)[0]
    token, _, rest = first.partition(" ")
    if token not in vocabulary or token == JSON:
        return Result(ERROR, name + ".unknown-verdict", "%s printed no verdict it declares: %.200s" % (name, first))
    detail = rest if "\n" not in output else rest + "\n" + output.split("\n", 1)[1]
    return Result(vocabulary[token], name + "." + token, first, detail=detail)


def run(name: str, root: Path, env: dict | None = None) -> Result:
    """Runs fragment name's main in the caller's tree root, with env (the current environment when None)."""
    if name not in VOCABULARY:
        return Result(ERROR, "fragment.unknown", "no fragment with a declared vocabulary: " + name)
    script = source(name)
    if not script.is_file():
        return Result(ERROR, "fragment.missing", "the tooling checkout has no " + str(script))
    proc = subprocess.run(
        ["bash", "-c", 'set -euo pipefail; source "$1"; main', "practice-ci", str(script)],
        cwd=root,
        env=dict(os.environ) if env is None else env,
        stdout=subprocess.PIPE,
        check=False,
    )
    output = proc.stdout.decode("utf-8", "replace").rstrip("\n")
    if proc.returncode != 0:
        return Result(ERROR, name + ".exit", "%s stopped with exit %d" % (name, proc.returncode), detail=output)
    return judge(name, output)
