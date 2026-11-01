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

## The guard

[`message-check.yml`](../.github/workflows/message-check.yml) is a reusable workflow for `issues` events (`opened`, `edited`, `labeled`), with `issues: write`. On a message, it checks:

- exactly one usable block;
- the schema;
- that `type` agrees with the `kind:` label;
- that the body holds no term from the repository's denylist.

When any check fails, it adds `state:invalid` and posts one comment saying why. It never edits the author's text and repeats none of it. This repository calls it from `self-message.yml`.

## Changing the protocol

A change is a `kind:proposal` issue in this repository, decided by pull request with review and a CHANGELOG line. Until v1, a version may change anything. From v1 on, changes are additive only, and a breaking change is a new major tag.

v0 is the slice above: the message format, the issue forms and the guard. A label-sync script, a polling client and a worked example thread follow in their own pull requests.
