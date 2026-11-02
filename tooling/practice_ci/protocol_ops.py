"""Protocol operations over REST (docs/protocol.md): label reconciliation and a polling client.

Every limit, label, URL and marker comes from policy/constants.json (key "protocol") through config.
"""
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from . import config, protocol

_NEXT = re.compile(r'<([^>]+)>\s*;\s*rel="next"')


class ApiError(Exception):
    pass


def urllib_transport(timeout):
    """A transport: (method, url, headers, body) -> (status, headers, bytes). 304 is a result."""
    def send(method, url, headers, body):
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as err:
            if err.code == 304:
                return 304, dict(err.headers), b""
            raise ApiError("%s %s -> HTTP %d" % (method, url, err.code)) from err
    return send


def header(headers, name):
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return None


def next_link(headers):
    """The URL of rel="next" in a Link header, or None."""
    match = _NEXT.search(header(headers, "Link") or "")
    return match.group(1) if match else None


class Client:
    """A REST client. `settings_` is the "protocol" constants block; `transport` is injectable.

    It caches each page's ETag, items and next link. Repeat listings revalidate every
    page and return None only when all pages respond with 304.
    """

    def __init__(self, token=None, transport=None, settings_=None):
        self.cfg = settings_ if settings_ is not None else config.get("protocol")
        self.token = token if token is not None else os.environ.get(self.cfg["tokenEnv"], "")
        self.transport = transport or urllib_transport(self.cfg["api"]["timeoutSeconds"])
        self.etags = {}

    def _headers(self, extra=None):
        headers = {
            "Accept": self.cfg["api"]["accept"],
            "X-GitHub-Api-Version": self.cfg["api"]["version"],
            "Content-Type": "application/json",
        }
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        headers.update(extra or {})
        return headers

    def url(self, path, params=None):
        url = self.cfg["api"]["base"] + path
        return url + "?" + urllib.parse.urlencode(params, safe=":,") if params else url

    def write(self, method, path, payload):
        status, _, data = self.transport(method, self.url(path), self._headers(),
                                         json.dumps(payload).encode("utf-8"))
        return json.loads(data) if data else None

    def get_all(self, path, params=None, conditional=False):
        """Every item of a paginated listing, following Link rel=next, at most maxPages pages.

        With conditional=True every cached page carries its ETag. A 304 reuses that
        page's items and next link; only an entirely unchanged listing returns None.
        Cache updates are committed only after the complete listing succeeds.
        """
        api = self.cfg["api"]
        url = self.url(path, dict(params or {}, per_page=api["perPage"]))
        items = []
        pending = {}
        unchanged = True
        for _ in range(api["maxPages"]):
            cached = self.etags.get(url) if conditional else None
            extra = {"If-None-Match": cached[0]} if cached else None
            status, headers, data = self.transport("GET", url, self._headers(extra), None)
            if status == 304 and cached:
                etag, page_items, following = cached
                following = next_link(headers) if header(headers, "Link") is not None else following
            elif status == 200:
                unchanged = False
                etag = header(headers, "ETag")
                page_items = json.loads(data)
                following = next_link(headers)
            else:
                raise ApiError("GET %s -> HTTP %d" % (url, status))
            if conditional:
                pending[url] = (etag, page_items, following) if etag else None
            items.extend(page_items)
            url = following
            if not url:
                for page_url, page in pending.items():
                    if page is None:
                        self.etags.pop(page_url, None)
                    else:
                        self.etags[page_url] = page
                return None if conditional and unchanged else items
        raise ApiError("more than %d pages of %s" % (api["maxPages"], path))


# ---- label reconciliation -------------------------------------------------------------------

def sync_labels(client, repo, catalog=None):
    """Create missing labels; fix name case, colour and description of existing ones.

    Returns the ("create"|"update", name) actions taken; a second run returns [].
    """
    catalog = client.cfg["labels"] if catalog is None else catalog
    have = {lab["name"].lower(): lab for lab in client.get_all("/repos/%s/labels" % repo)}
    actions = []
    for want in catalog:
        cur = have.get(want["name"].lower())
        if cur is None:
            client.write("POST", "/repos/%s/labels" % repo, want)
            actions.append(("create", want["name"]))
        elif (cur["name"] != want["name"] or cur["color"].lower() != want["color"]
              or (cur.get("description") or "") != want["description"]):
            client.write("PATCH", "/repos/%s/labels/%s" % (repo, urllib.parse.quote(cur["name"], safe="")),
                         {"new_name": want["name"], "color": want["color"],
                          "description": want["description"]})
            actions.append(("update", want["name"]))
    return actions


# ---- routing and revision verification --------------------------------------------------------

def label_names(issue):
    return [lab["name"] for lab in issue.get("labels", [])]


def route(issue, cfg):
    """The repositories a message is addressed to, from its to: labels."""
    prefix = cfg["prefixes"]["to"]
    return [n[len(prefix):] for n in label_names(issue) if n.startswith(prefix)]


def body_digest(body):
    return hashlib.sha256((body or "").encode("utf-8")).hexdigest()


def accepted_digest(comments, cfg, app_login=None):
    """The body digest message-check last accepted, or None.

    It reads the verdict message-check writes (protocol.render_verdict): the newest one, by the verdict
    author or the app login; a verdict that is not an acceptance yields None.
    """
    trusted = {cfg["verdictAuthor"]} | ({app_login} if app_login else set())
    return protocol.accepted_body_digest(comments, trusted)


def verify(client, repo, issue, app_login=None):
    """True only when the body is exactly the revision message-check accepted."""
    cfg = client.cfg
    if cfg["prefixes"]["state"] + cfg["verdict"]["invalidState"] in label_names(issue):
        return False
    comments = client.get_all("/repos/%s/issues/%d/comments" % (repo, issue["number"]))
    digest = accepted_digest(comments, cfg, app_login)
    return digest is not None and digest == body_digest(issue.get("body"))


# ---- polling ---------------------------------------------------------------------------------

def poll(client, repo, me, app_login=None, since=None):
    """Open request messages addressed to `me` in `repo` whose body is the accepted revision.

    Returns None when every listing page is unchanged (304), else the verified issues.
    Edited, unjudged and wrongly routed messages, and pull requests, are left out.
    """
    cfg = client.cfg
    prefixes = cfg["prefixes"]
    params = {
        "labels": ",".join([prefixes["kind"] + cfg["poll"]["kind"], prefixes["to"] + me,
                            prefixes["state"] + cfg["poll"]["state"]]),
        "state": "open",
    }
    if since:
        params["since"] = since
    previous_etags = client.etags.copy()
    try:
        issues = client.get_all("/repos/%s/issues" % repo, params, conditional=True)
        if issues is None:
            return None
        return [i for i in issues
                if "pull_request" not in i and me in route(i, cfg) and verify(client, repo, i, app_login)]
    except Exception:
        client.etags = previous_etags
        raise
