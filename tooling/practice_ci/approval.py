"""Label approval: reads who added the approval label from the pull request's events and judges it with
the label-approval fragment. One implementation for every guard that lets a label through (an exemption,
a loosened schema, a larger pull request)."""

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import fragments
from .result import FAIL, Result


class EventsError(RuntimeError):
    """The label events of the pull request could not be read."""


@dataclass(frozen=True)
class Inputs:
    root: Path
    label: str
    labels: str
    author: str
    number: str
    repo: str

    @classmethod
    def from_env(cls, root: Path, env) -> "Inputs":
        get = lambda k: env.get(k, "")  # noqa: E731 - an unset input is empty, as in the step
        return cls(root, get("LABEL"), get("LABELS"), get("AUTHOR"), get("NUMBER"), get("REPO"))


def read_label_events(inp: Inputs) -> str:
    """One "<login><TAB><type>" line per time the label was added, oldest first, from the GitHub API."""
    program = ('.[] | select(.event == "labeled" and .label.name == %s) | [.actor.login, .actor.type] | @tsv'
               % json.dumps(inp.label))
    proc = subprocess.run(
        ["gh", "api", "--paginate", "repos/%s/issues/%s/events" % (inp.repo, inp.number), "--jq", program],
        cwd=inp.root, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise EventsError(proc.stderr.strip())
    return proc.stdout.rstrip("\n")


def judge(inp: Inputs, run=fragments.run, events=read_label_events) -> Result:
    """The label-approval fragment's Result (reasons label-approval.ok, .missing, .refused), or a fail
    with reason approval.events-unreadable when the events cannot be read."""
    try:
        added = events(inp)
    except EventsError:
        return Result(FAIL, "approval.events-unreadable", "cannot read the label events of #" + inp.number)
    env = {k: v for k, v in os.environ.items() if k != "EVENTS"}
    env.update(LABEL=inp.label, LABELS=inp.labels, AUTHOR=inp.author, EVENTS=added)
    return run("label-approval", inp.root, env)
