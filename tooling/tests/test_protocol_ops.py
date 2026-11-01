"""protocol_ops against a fake GitHub REST API (no network)."""
import hashlib
import json
import unittest
import urllib.parse

from tooling.practice_ci import config, protocol_ops

CFG = config.get("protocol")
BASE = CFG["api"]["base"]
MARKER = CFG["verdict"]["marker"]
BOT = CFG["verdict"]["authors"][0]
REPO = "example-org/receiver"
ME = "receiver"
BODY = "Please add a mode.\n\n```json\n{\"id\": \"synthetic-request\"}\n```\n"


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def verdict(body, author=BOT):
    return {"user": {"login": author}, "body": "<!-- %s%s -->\nAccepted." % (MARKER, sha(body))}


def labels_for(me=ME):
    p = CFG["prefixes"]
    return [{"name": p["kind"] + CFG["poll"]["kind"]}, {"name": p["to"] + me},
            {"name": p["state"] + CFG["poll"]["state"]}]


class FakeGitHub:
    """Routes (method, path) to handlers; records every request."""

    def __init__(self):
        self.calls = []
        self.labels = {}
        self.issues = []
        self.comments = {}
        self.etag = '"v1"'
        self.page_etags = {}
        self.page_size = CFG["api"]["perPage"]

    def __call__(self, method, url, headers, body):
        parts = urllib.parse.urlsplit(url)
        query = dict(urllib.parse.parse_qsl(parts.query))
        payload = json.loads(body) if body else None
        self.calls.append((method, parts.path, query, dict(headers), payload))
        path = parts.path
        if path == "/repos/%s/labels" % REPO:
            if method == "GET":
                return self.page(list(self.labels.values()), url, query)
            self.labels[payload["name"].lower()] = dict(payload)
            return 201, {}, json.dumps(payload).encode()
        if path.startswith("/repos/%s/labels/" % REPO) and method == "PATCH":
            name = urllib.parse.unquote(path.rsplit("/", 1)[1]).lower()
            label = self.labels.pop(name)
            label.update({k: v for k, v in payload.items() if k != "new_name"})
            label["name"] = payload.get("new_name", label["name"])
            self.labels[label["name"].lower()] = label
            return 200, {}, json.dumps(label).encode()
        if path == "/repos/%s/issues" % REPO:
            etag = self.page_etags.get(int(query.get("page", 1)), self.etag)
            if headers.get("If-None-Match") == etag:
                return 304, {"ETag": etag}, b""
            status, h, b = self.page(self.issues, url, query)
            h["ETag"] = etag
            return status, h, b
        if path.startswith("/repos/%s/issues/" % REPO) and path.endswith("/comments"):
            number = int(path.split("/")[-2])
            return self.page(self.comments.get(number, []), url, query)
        return 404, {}, b"{}"

    def page(self, items, url, query):
        size = int(query.get("per_page", self.page_size))
        size = min(size, self.page_size)
        n = int(query.get("page", 1))
        chunk = items[(n - 1) * size:n * size]
        headers = {}
        if n * size < len(items):
            q = dict(query, page=n + 1)
            nxt = urllib.parse.urlsplit(url)._replace(query=urllib.parse.urlencode(q)).geturl()
            headers["Link"] = '<%s>; rel="next", <%s>; rel="last"' % (nxt, nxt)
        return 200, headers, json.dumps(chunk).encode()


def client(fake):
    return protocol_ops.Client("t0ken", transport=fake, settings_=CFG)


class LabelSync(unittest.TestCase):
    def test_creates_fixes_and_is_idempotent(self):
        fake = FakeGitHub()
        first, second = CFG["labels"][0], CFG["labels"][1]
        fake.labels[first["name"].upper().lower()] = {
            "name": first["name"].upper(), "color": "000000", "description": "stale"}
        fake.labels[second["name"]] = dict(second, color=second["color"].upper())
        actions = protocol_ops.sync_labels(client(fake), REPO)
        self.assertIn(("update", first["name"]), actions)
        self.assertNotIn(("update", second["name"]), actions)
        self.assertEqual(len(actions), len(CFG["labels"]) - 1)
        for want in CFG["labels"]:
            have = fake.labels[want["name"].lower()]
            self.assertEqual(have["name"], want["name"])
            self.assertEqual(have["color"].lower(), want["color"])
            self.assertEqual(have["description"], want["description"])
        writes = len([c for c in fake.calls if c[0] != "GET"])
        self.assertEqual(protocol_ops.sync_labels(client(fake), REPO), [])
        self.assertEqual(len([c for c in fake.calls if c[0] != "GET"]), writes)

    def test_reads_every_page_of_labels(self):
        fake = FakeGitHub()
        fake.page_size = 2
        for want in CFG["labels"]:
            fake.labels[want["name"]] = dict(want)
        self.assertEqual(protocol_ops.sync_labels(client(fake), REPO), [])


class Polling(unittest.TestCase):
    def issue(self, fake, number, body, labels=None, accepted=None):
        fake.issues.append({"number": number, "body": body, "labels": labels or labels_for()})
        fake.comments[number] = [verdict(accepted if accepted is not None else body)]

    def test_sends_auth_version_and_label_filter(self):
        fake = FakeGitHub()
        protocol_ops.poll(client(fake), REPO, ME)
        method, path, query, headers, _ = fake.calls[0]
        self.assertEqual(headers["Authorization"], "Bearer t0ken")
        self.assertEqual(headers["X-GitHub-Api-Version"], CFG["api"]["version"])
        self.assertEqual(query["labels"].split(","), [l["name"] for l in labels_for()])

    def test_304_is_unchanged_and_sends_etag(self):
        fake = FakeGitHub()
        self.issue(fake, 1, BODY)
        c = client(fake)
        self.assertEqual([i["number"] for i in protocol_ops.poll(c, REPO, ME)], [1])
        self.assertIsNone(protocol_ops.poll(c, REPO, ME))
        self.assertEqual(fake.calls[-1][3].get("If-None-Match"), fake.etag)

    def test_pagination_follows_link_header(self):
        fake = FakeGitHub()
        fake.page_size = 2
        for n in range(1, 6):
            self.issue(fake, n, BODY + str(n))
        found = protocol_ops.poll(client(fake), REPO, ME)
        self.assertEqual([i["number"] for i in found], [1, 2, 3, 4, 5])

    def test_later_page_change_after_first_page_304(self):
        fake = FakeGitHub()
        fake.page_size = 1
        self.issue(fake, 1, BODY)
        self.issue(fake, 2, BODY + "old")
        c = client(fake)
        protocol_ops.poll(c, REPO, ME)
        edited = BODY + "new"
        fake.issues[1]["body"] = edited
        fake.comments[2] = [verdict(edited)]
        fake.page_etags[2] = '"page-two-v2"'
        fake.calls.clear()
        found = protocol_ops.poll(c, REPO, ME)
        self.assertIsNotNone(found)
        self.assertEqual([i["body"] for i in found], [BODY, edited])
        listing = [call for call in fake.calls if call[1] == "/repos/%s/issues" % REPO]
        self.assertEqual(len(listing), 2)
        self.assertTrue(all(call[3].get("If-None-Match") == fake.etag for call in listing))
        self.assertIsNone(protocol_ops.poll(c, REPO, ME))

    def test_page_cap_is_enforced(self):
        fake = FakeGitHub()
        fake.page_size = 1
        cfg = json.loads(json.dumps(CFG))
        cfg["api"]["maxPages"] = 2
        for n in range(1, 4):
            self.issue(fake, n, BODY)
        with self.assertRaises(protocol_ops.ApiError):
            protocol_ops.poll(protocol_ops.Client("", transport=fake, settings_=cfg), REPO, ME)

    def test_failed_poll_retries_pagination_and_verification(self):
        for failure in ("pages", "verification"):
            with self.subTest(failure=failure):
                fake = FakeGitHub()
                fake.page_size = 1
                cfg = json.loads(json.dumps(CFG))
                cfg["api"]["maxPages"] = 1
                self.issue(fake, 1, BODY)
                if failure == "pages":
                    self.issue(fake, 2, BODY)
                else:
                    fake.comments[1].append(verdict(BODY))
                c = protocol_ops.Client("", transport=fake, settings_=cfg)
                for _ in range(2):
                    with self.assertRaises(protocol_ops.ApiError):
                        protocol_ops.poll(c, REPO, ME)
                    self.assertEqual(c.etags, {})
                cfg["api"]["maxPages"] = 3
                found = protocol_ops.poll(c, REPO, ME)
                self.assertEqual(len(found), len(fake.issues))
                self.assertIsNone(protocol_ops.poll(c, REPO, ME))

    def test_edited_message_is_rejected(self):
        fake = FakeGitHub()
        self.issue(fake, 7, BODY + "edited after acceptance\n", accepted=BODY)
        self.assertEqual(protocol_ops.poll(client(fake), REPO, ME), [])

    def test_unverified_and_untrusted_verdicts_are_rejected(self):
        fake = FakeGitHub()
        fake.issues.append({"number": 8, "body": BODY, "labels": labels_for()})
        fake.issues.append({"number": 9, "body": BODY, "labels": labels_for()})
        fake.comments[9] = [verdict(BODY, author="someone-else")]
        self.assertEqual(protocol_ops.poll(client(fake), REPO, ME), [])

    def test_latest_verdict_wins(self):
        fake = FakeGitHub()
        edited = BODY + "v2\n"
        fake.issues.append({"number": 3, "body": edited, "labels": labels_for()})
        fake.comments[3] = [verdict(BODY), verdict(edited)]
        self.assertEqual([i["number"] for i in protocol_ops.poll(client(fake), REPO, ME)], [3])
        fake.comments[3] = [verdict(edited), verdict(BODY)]
        fake.etag = '"v2"'
        self.assertEqual(protocol_ops.poll(client(fake), REPO, ME), [])

    def test_routes_by_to_label_and_skips_pull_requests(self):
        fake = FakeGitHub()
        self.issue(fake, 1, BODY, labels=labels_for("someone-else"))
        self.issue(fake, 2, BODY)
        fake.issues[-1]["pull_request"] = {}
        self.issue(fake, 3, BODY)
        self.assertEqual([i["number"] for i in protocol_ops.poll(client(fake), REPO, ME)], [3])

    def test_app_login_is_a_trusted_verdict_author(self):
        fake = FakeGitHub()
        fake.issues.append({"number": 4, "body": BODY, "labels": labels_for()})
        fake.comments[4] = [verdict(BODY, author="example-app[bot]")]
        self.assertEqual(protocol_ops.poll(client(fake), REPO, ME), [])
        found = protocol_ops.poll(client(fake), REPO, ME, app_login="example-app[bot]")
        self.assertEqual([i["number"] for i in found], [4])


class Links(unittest.TestCase):
    def test_next_link(self):
        h = {"link": '<https://x/a?page=2>; rel="next", <https://x/a?page=9>; rel="last"'}
        self.assertEqual(protocol_ops.next_link(h), "https://x/a?page=2")
        self.assertIsNone(protocol_ops.next_link({"Link": '<https://x/a?page=1>; rel="prev"'}))
        self.assertIsNone(protocol_ops.next_link({}))


if __name__ == "__main__":
    unittest.main()
