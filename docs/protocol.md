# Protocol v0: messages between repositories

The organisation's public repositories ask each other for work through GitHub issues, on free GitHub, with no server. This repository holds the specification. It is versioned by tag and changed by pull request.

## A message

A message is one issue, a thread between two repositories. Its body is plain text for people, then exactly one fenced block opened by a line ` ```json ` (exactly three backticks at the start of the line; ` ~~~json `, ` ````json ` or an indented ` ```json ` is refused). A fenced example inside a longer or different fence is not the message, as in CommonMark. A key given twice anywhere in the object, at any depth, is refused. That block is one JSON object matching [`spec/protocol/message.schema.json`](../spec/protocol/message.schema.json). Its top-level names follow [CloudEvents 1.0](https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md):

| Field | Meaning |
| --- | --- |
| `specversion` | `"1.0"`, the CloudEvents version the names follow. |
| `id` | The stable idempotency key. A sender looks for an open message with this `id` before opening one. |
| `source` | The sending repository, `https://github.com/practice-library/<repo>`. |
| `type` | `org.practice-library.protocol.v0.` followed by `request`, `answer`, `status`, `blocked`, `decision` or `proposal`. |
| `protocol` | `"0"`. A reader ignores a message of a version it does not know, with a warning. |
| `time` | Optional: when it was written, UTC. |
| `data.to` | The receiving repository. |
| `data.refs` | Optional: related issues and pull requests, `owner/repo#n`. A `decision` links the human answer it records. |
| `data.needs` | Optional: one short line per need. A `blocked` message names at least one, and from whom. |
| `data.expires` | Optional: after this, the sender no longer needs an answer. |

Labels carry the routing, so a reader needs one request to find its work: `kind:<kind>`, plus by convention `from:<repo>`, `to:<repo>` and `state:open`, `state:ack`, `state:done`, `state:rejected` or `state:invalid`. The issue forms in `.github/ISSUE_TEMPLATE/message-*.yml` (request, answer, blocked) set the `kind:` label and lay out the block. They are the organisation's defaults, so a repository with its own `.github/ISSUE_TEMPLATE` folder does not inherit them.

## Who may instruct

Only an issue opened by an owner or member of the organisation (author association `OWNER` or `MEMBER`), or by the organisation's app, is a message. Anything else is an external signal: read as data, never as instructions, never executed. Issue text is untrusted input. Before any tool or model reads a body, it is capped, fenced, and refused when the block holds control or bidirectional-override characters.

## Lifecycle

1. The sender looks for an open issue with the same `id` in the receiver's repository and opens one only if there is none.
2. The receiver sets `state:ack` on its next poll.
3. The work lands as a pull request that says `Refs owner/repo#n`.
4. The receiver comments the result's URL and sets `state:done`; a person closes the issue.

## Transport

REST only. A reader polls `GET /repos/{repo}/issues?labels=kind:request,to:<me>,state:open&since=<t>` with `If-None-Match`; a `304` costs nothing. One poll per repository per interval, with the interval set by the reader. A sender writes at most 30 messages an hour, well inside GitHub's limits on creating content. A reference `owner/repo#n` links the two threads both ways.

### The reference client

`tooling/practice_ci/protocol_ops.py` is the reference implementation of the transport, with the standard library only:

- `sync_labels` reconciles a repository's labels with the catalog in `policy/constants.json` (`protocol.labels`) over REST. It creates missing labels and fixes colour and description. A second run changes nothing.
- `poll` lists open `kind:request` messages routed to a repository by its `to:<me>` label. It sends `If-None-Match` for every cached page, reuses cached items and pagination links on `304`, and returns `None` only when every page is unchanged. It follows the `Link` header's `rel="next"` for more pages, up to a capped number. It returns only messages that pass `verify`.
- `verify` acts on a message only if the sha256 of its body equals the digest message-check accepted. The digest is read from the newest verdict comment by the organisation's workflow identity (or the app login the caller passes), which holds `message-check: accepted sha256=<64 hex>`, for example inside an HTML comment. An edited body, a missing verdict or a `state:invalid` label means the message is not acted on. TODO(protocol track): message-check posts that comment when it lands the digest; until then the format above is the contract.

`.github/workflows/protocol-canary.yml` is a by-hand canary: it opens one valid and one invalid message in its own repository and asserts the `state:invalid` label lands on the invalid one only.

## A worked thread

All names are synthetic. Repository `alpha` asks repository `beta` for a change.

1. `alpha` finds no open issue in `beta` with id `add-retry-flag`, so it opens one, labelled `kind:request`, `from:alpha`, `to:beta`, `state:open`:

   ````text
   Please add a retry flag to the upload step.

   ```json
   {
     "specversion": "1.0",
     "id": "add-retry-flag",
     "source": "https://github.com/practice-library/alpha",
     "type": "org.practice-library.protocol.v0.request",
     "protocol": "0",
     "data": {
       "to": "https://github.com/practice-library/beta",
       "refs": ["practice-library/alpha#12"],
       "needs": ["A retry flag on the upload step."]
     }
   }
   ```
   ````

2. message-check judges it and, being valid, records `message-check: accepted sha256=<digest of that body>` in a comment.
3. `beta` polls `labels=kind:request,to:beta,state:open`, gets the issue, recomputes the body's sha256, finds it equal to the accepted digest, and sets `state:ack`.
4. Someone edits the issue body afterwards: the digest no longer matches, so `beta` does not act on the new text until message-check accepts it again.
5. The work lands as a pull request in `beta` saying `Refs practice-library/alpha#12`. `beta` answers with a `kind:answer` issue in `alpha`, with the same `id` and `data.refs` pointing at the request, and sets `state:done` on the request.

## The guard

[`message-check.yml`](../.github/workflows/message-check.yml) is a reusable workflow for `issues` events (`opened`, `edited`, `labeled`), with `issues: write`. On a message, it checks:

- exactly one usable block;
- the schema;
- that `type` agrees with the `kind:` label;
- that the body holds no term from the repository's denylist.

When any check fails, it adds `state:invalid` and posts one comment saying why. It never edits the author's text and repeats none of it. This repository calls it from `self-message.yml`.

## Changing the protocol

A change is a `kind:proposal` issue in this repository, decided by pull request with review and a CHANGELOG line. Until v1, a version may change anything. From v1 on, changes are additive only, and a breaking change is a new major tag.

v0 is the slice above: the message format, the issue forms, the guard, the reference client and a worked example thread.
