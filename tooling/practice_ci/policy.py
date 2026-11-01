"""The one reader of policy/constants.json. Every other module asks this one for a value by its dotted
key; there is no default anywhere, so a missing key is an error, never a second copy of the value."""

import json
from pathlib import Path

# tooling/practice_ci/policy.py -> the repository root the tooling was checked out at.
ROOT = Path(__file__).resolve().parents[2]
CONSTANTS = ROOT / "policy" / "constants.json"

_loaded = None


class PolicyError(KeyError):
    """A key the policy does not hold."""


def _constants() -> dict:
    global _loaded
    if _loaded is None:
        with open(CONSTANTS, encoding="utf-8") as f:
            _loaded = json.load(f)
    return _loaded


def value(key: str):
    """The constant at a dotted key, such as "tooling.pythonVersion"."""
    node = _constants()
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            raise PolicyError("missing policy value: " + key)
        node = node[part]
    return node


def path(key: str) -> Path:
    """A constant that is a path relative to the repository root, made absolute."""
    rel = value(key)
    if not isinstance(rel, str) or not rel or rel.startswith("/"):
        raise PolicyError("not a relative path: " + key)
    return ROOT / rel
