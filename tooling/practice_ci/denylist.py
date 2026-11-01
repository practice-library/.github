"""The denylist guard: which list judges the change, the scan, the checks on the list the change leaves
behind, and the approval of an exemption the change adds or widens.

The rules themselves stay in their fragments (denylist-scan, denylist-exempt, label-approval); this is
the orchestration that used to be written inside the guard workflow's step, moved here so the mutation
runner covers it and scripts/denylist-canary.sh runs exactly what callers run.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path

from . import approval, fragments
from .gitread import GitReadError, blob
from .result import ERROR, FAIL, PASS, Evidence, Result

# Variables this guard sets for the fragments it runs; never inherited from the step's environment.
_OWN = ("DENY", "TEXT_FILE", "BASE_LIST", "HEAD_LIST", "EVENTS")


@dataclass(frozen=True)
class Inputs:
    root: Path
    none: bool
    base: str
    mb: str
    head: str
    list_path: str
    event: str
    label: str
    labels: str
    author: str
    number: str
    repo: str

    @classmethod
    def from_env(cls, root: Path, env) -> "Inputs":
        get = lambda k: env.get(k, "")  # noqa: E731 - an unset input is empty, as in the step
        return cls(root, get("NONE") == "true", get("BASE"), get("MB"), get("HEAD"), get("LIST"),
                   get("EVENT"), get("LABEL"), get("LABELS"), get("AUTHOR"), get("NUMBER"), get("REPO"))


def judge(inp: Inputs, run=fragments.run, approve=approval.judge, say=print) -> Result:
    try:
        return _judge(inp, run, approve, say)
    except GitReadError as e:
        return Result(ERROR, "denylist.git-read", str(e))


def _judge(inp: Inputs, run, approve, say) -> Result:
    where = (Evidence(inp.list_path),)
    base_env = {k: v for k, v in os.environ.items() if k not in _OWN}

    def fragment(name: str, **values) -> Result:
        return run(name, inp.root, {**base_env, **values})

    def scan(deny: str, text_file: str | None = None) -> Result:
        values = {"DENY": deny, "EVENT": inp.event, "MB": inp.mb, "HEAD": inp.head}
        if text_file is not None:
            values["TEXT_FILE"] = text_file
        return fragment("denylist-scan", **values)

    if inp.none:
        # Nothing to compare, but a repository whose list is missing, empty or unreadable is still
        # unguarded: the list is checked against no text at all.
        say("Nothing to compare; checking %s only." % inp.list_path)
        return scan(blob(inp.root, "HEAD", inp.list_path) or "", os.devnull)

    # The list comes from the base commit, so a change cannot edit the list it is checked against. Only
    # when the base has none and the change adds it is the change's own list used, without its
    # exemptions: an exemption never applies to the change that adds it.
    base_list = blob(inp.root, inp.base, inp.list_path) or ""
    head_list = blob(inp.root, inp.head, inp.list_path) or ""
    deny = ""
    if base_list:
        deny = base_list
    elif head_list:
        say("%s is new in this change; it is checked with that list, without its exemptions." % inp.list_path)
        try:
            first = json.loads(head_list)
        except ValueError:
            return Result(FAIL, "denylist.list-not-json", "%s is not JSON" % inp.list_path, where)
        if isinstance(first, dict):
            first.pop("exemptPaths", None)
        deny = json.dumps(first, ensure_ascii=False, separators=(",", ":"))
    scanned = scan(deny)
    say(scanned.message)
    if scanned.status != PASS:
        return scanned

    # The list the change leaves behind is the one the next change is judged with, so it must be usable
    # and not empty: an entry that is not a digest would match nothing.
    if head_list and head_list != base_list:
        following = scan(head_list, os.devnull)
        if following.status == ERROR:
            return following
        if following.status != PASS:
            return Result(FAIL, "denylist.head-list-unusable",
                          "the list this change writes cannot be used: " + following.message, where)
    elif not head_list:
        # Deleting the list leaves the next change unguarded. Judged against the merge base, so a list the
        # base gained after the change branched is not counted as deleted by it.
        if blob(inp.root, inp.mb, inp.list_path):
            return Result(FAIL, "denylist.list-deleted",
                          "this change deletes %s, so the next change would be unguarded" % inp.list_path, where)

    # An exemption the change adds or widens is a loosening of the list, judged like a loosened schema.
    # Widening is judged against the base as it is now, since that is what the merge lands on: an entry the
    # base dropped after the change branched would come back with it.
    exempt = fragment("denylist-exempt", BASE_LIST=base_list, HEAD_LIST=head_list)
    say(exempt.message)
    if exempt.status == ERROR:
        return exempt
    if exempt.reason == "denylist-exempt.ok":
        return Result(PASS, "denylist.clean", scanned.message)
    if exempt.reason != "denylist-exempt.widened":
        return Result(FAIL, "denylist.list-invalid", exempt.message, where)
    if not inp.number:
        return Result(PASS, "denylist.exemption-on-push",
                      "ok not a pull request; the exemption is judged on the pull request")
    approved = approve(approval.Inputs(inp.root, inp.label, inp.labels, inp.author, inp.number, inp.repo), run)
    if approved.status == ERROR or approved.reason == "approval.events-unreadable":
        return approved
    if approved.reason == "label-approval.ok":
        return Result(PASS, "denylist.exemption-approved", "ok exemption accepted: " + approved.detail)
    if approved.reason == "label-approval.missing":
        if (blob(inp.root, inp.mb, inp.list_path) or "") != base_list:
            say("%s changed on the base after this change branched; if the change does not mean to add an "
                "exemption, merge the base in." % inp.list_path)
        return Result(FAIL, "denylist.exemption-unapproved",
                      "a denylist exemption is added or widened; a maintainer reviews it and adds the label "
                      + inp.label, where)
    return Result(FAIL, "denylist.exemption-refused", approved.detail)
