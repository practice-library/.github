"""Single accessor for policy/constants.json; no other module reads it directly."""
import json
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load(path=None):
    with open(path or os.path.join(_ROOT, "policy", "constants.json"), encoding="utf-8") as f:
        return json.load(f)


def get(*keys, path=None):
    node = load(path)
    for key in keys:
        node = node[key]
    return node
