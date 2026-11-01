"""Exact-head approval receipts.

An approval is a pull request review in state APPROVED whose commit_id is the pull request's current
head, written by a user with a role in approvals.allowedRoles on the repository, who is neither the
pull request author nor a bot. Labels never authorize anything; they only re-run the check.

A publication approval also carries, in the review body, the publication statement on a line of its
own and a line "<headPrefix><head sha>" naming the same head.

REST only. Command line (token in GH_TOKEN):
    python3 -m practice_ci.approvals --repo OWNER/NAME --pr N --kind KIND [--head SHA]
prints "ok approved by <login> ...", "missing ..." or "refused ..." and exits 1 unless approved.
--head is the head the caller meant to judge; a pull request that has moved on is refused.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

from . import config

OK = "ok"
MISSING = "missing"
REFUSED = "refused"


class ApiError(Exception):
    pass


class Verdict:
    def __init__(self, status, message):
        self.status, self.message = status, message

    @property
    def ok(self):
        return self.status == OK

    def __str__(self):
        return "%s %s" % (self.status, self.message)


class RestClient:
    """GET-only GitHub REST client. Paths have no leading slash: repos/OWNER/NAME/pulls/N."""

    def __init__(self, token, cfg=None, opener=urllib.request.urlopen):
        self._cfg = cfg or config.get("approvals")
        self._token, self._opener = token, opener

    def _fetch(self, url):
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": "Bearer " + self._token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": self._cfg["apiVersion"],
            },
        )
        try:
            with self._opener(request, timeout=self._cfg["timeoutSeconds"]) as response:
                return json.loads(response.read().decode("utf-8")), response.headers.get("Link", "")
        except (urllib.error.URLError, ValueError, OSError) as error:
            raise ApiError("GET %s failed: %s" % (url, error)) from error

    def get(self, path):
        return self._fetch("%s/%s" % (self._cfg["apiUrl"], path))[0]

    def get_all(self, path):
        """Every item of a list endpoint, following the Link header's rel=next."""
        url, items = "%s/%s?per_page=%d" % (self._cfg["apiUrl"], path, self._cfg["perPage"]), []
        while url:
            page, link = self._fetch(url)
            if not isinstance(page, list):
                raise ApiError("GET %s did not return a list" % url)
            items.extend(page)
            url = next((m.group(1) for m in re.finditer(r'<([^>]+)>;\s*rel="next"', link)), None)
        return items


def _is_bot(user, cfg):
    return user.get("type") == cfg["botType"] or str(user.get("login", "")).endswith(cfg["botSuffix"])


def _latest_decisions(reviews, cfg):
    """Each reviewer's last review that decides anything (a comment decides nothing), in review order."""
    last = {}
    for item in reviews:
        login = (item.get("user") or {}).get("login")
        if login and item.get("state") in cfg["decisiveStates"]:
            last[login] = item
    return last


def _publication_error(body, head, cfg):
    """Why a review body is not a publication approval of head, or None when it is."""
    lines = [line.strip() for line in (body or "").splitlines()]
    if cfg["publicationStatement"] not in lines:
        return "the review does not carry the publication statement: %s" % cfg["publicationStatement"]
    named = re.escape(cfg["headPrefix"]) + r"(\S+)"
    if head not in [m.group(1) for m in map(lambda line: re.fullmatch(named, line), lines) if m]:
        return "the review does not carry the line %s%s" % (cfg["headPrefix"], head)
    return None


def _refusal(item, head, author, client, repo, kind, cfg):
    """Why this approval at head does not count, or None when it does."""
    login = item["user"]["login"]
    if login == author:
        return "%s is the author of the pull request" % login
    if _is_bot(item["user"], cfg):
        return "%s is a bot" % login
    role = client.get("repos/%s/collaborators/%s/permission" % (repo, login)).get("role_name")
    if role not in cfg["allowedRoles"]:
        return "%s has role %s on %s; one of %s is needed" % (login, role, repo, "/".join(cfg["allowedRoles"]))
    if kind == cfg["publicationKind"]:
        problem = _publication_error(item.get("body"), head, cfg)
        if problem:
            return "%s: %s" % (login, problem)
    return None


def check(client, repo, number, kind, cfg=None, expected=None):
    """The verdict on pull request number for kind, judged at the head it has now."""
    cfg = cfg or config.get("approvals")
    if kind not in cfg["kinds"]:
        return Verdict(REFUSED, "unknown approval kind %s; known: %s" % (kind, ", ".join(cfg["kinds"])))
    pull = client.get("repos/%s/pulls/%s" % (repo, number))
    head, author = pull["head"]["sha"], pull["user"]["login"]
    if expected and expected != head:
        return Verdict(REFUSED, "the pull request moved from %s to %s; this run is stale" % (expected, head))
    decisions = _latest_decisions(client.get_all("repos/%s/pulls/%s/reviews" % (repo, number)), cfg)
    refusals, older = [], []
    for login, item in decisions.items():
        if item["state"] != cfg["approvedState"]:
            continue
        if item.get("commit_id") != head:
            older.append(login)
            continue
        why = _refusal(item, head, author, client, repo, kind, cfg)
        if why is None:
            return Verdict(OK, "approved by %s at %s" % (login, head))
        refusals.append(why)
    if refusals:
        return Verdict(REFUSED, "; ".join(refusals))
    if older:
        return Verdict(MISSING, "%s approved an older head; head %s needs a new approval" % (", ".join(older), head))
    return Verdict(MISSING, "no approving review at head %s" % head)


def main(argv=None, client=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr", required=True)
    parser.add_argument("--kind", required=True)
    parser.add_argument("--head")
    args = parser.parse_args(argv)
    try:
        cfg = config.get("approvals")
        verdict = check(client or RestClient(os.environ["GH_TOKEN"], cfg), args.repo, args.pr, args.kind, cfg, args.head)
    except (ApiError, KeyError) as error:
        verdict = Verdict(REFUSED, "cannot read the approvals of #%s: %s" % (args.pr, error))
    print(verdict)
    return 0 if verdict.ok else 1


if __name__ == "__main__":
    sys.exit(main())
