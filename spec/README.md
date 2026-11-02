# Contracts

Each contract is a JSON Schema (2020-12) whose `$id` is its URL in this repository, so any repository can pin it by tag and resolve it by `$id`. Every contract except the node envelope is a directory with `schema.json`, `examples/` that must pass and `counter-examples/` that must fail, each for one named reason. Its `check.json` lists two targets for `schema-check`: the examples with expect pass, and the counter-examples with expect fail and `each`, so every one of them must fail on its own. The node envelope's cases are under `selftest/fixtures/schema-node-*`.

| Contract | `$id` path | What it is |
| --- | --- | --- |
| node | `spec/node/schema.json` | The envelope every fact node shares. A domain schema references it and declares only its type values. |
| refresh-report | `spec/refresh-report/schema.json` | The report a fact-refresh run writes: robots.txt verdicts, the requests made, and one outcome per fact. |
| sources | `spec/sources/schema.json` | The list of hosts a graph may cite, with the per-host and run-wide limits a refresh run keeps. |
| drill-report | `spec/drill-report/schema.json` | The report of an incident-detection drill: when the incident was injected and detected, the time to detect measured and projected, and whether anyone was notified. Its arithmetic is checked by `tooling/practice_ci/drill_check.py` ([drill-report/README.md](drill-report/README.md)). |
| ratchet | `spec/ratchet/schema.json` | A shrink-only baseline that lets a check keep today's findings and refuse new ones. |
| protocol message | `spec/protocol/message.schema.json` | The JSON block of an issue-based message between repositories ([docs/protocol.md](../docs/protocol.md)). |

refresh-report and sources moved here from practice-library/graphs in v2.1.0. Their content is unchanged except for the `$id`, real calendar dates in `$defs.time`, and the 429 rule below.

## node

The schema is the normative contract and its `$id` is stable ([node/README.md](node/README.md)).

`attrs.verdict` is `allowed`, `denied` or `limited` for what a page states, `unknown` when it could not be confirmed, and `absent` when the page was checked and does not state it. An `absent` node has a `note` naming the page checked and no `value`. `attrs.basis` is `documented` (the default) or `observed`. An observed node's `source` is the run or record that measured it, and its `quote` a line copied exactly from that log. A node with an `observes` edge must be observed. `attrs.status`, optional, is `in-force`, `notified-not-in-force` (published, with a later start), `draft` or `superseded`, for a fact that is a rule with a legal or published state; a domain schema may narrow the list or forbid it, never add a value. Besides the product relations, an edge may be `issuedBy`, `partOf`, `madeUnder`, `imposes`, `amends` or `commencedBy` for legal texts (an instrument, its provisions and the duties they impose); a domain schema may restrict `rel` to the values it uses. `measuredAt` and `attrs.fetched_at` are real calendar dates. Whether an `observes` edge points at a documented node of the same graph needs the other nodes, so the graph's own checker judges it.

## refresh-report

The seam between a public refresh run and the consumer that turns its report into pull requests. A run keeps these rules:

1. **robots.txt first, every run.** Before fetching any page, the run fetches robots.txt of every host it would read and records each in `robots`. When one disallows a path the run would fetch, or cannot be read, the run fetches no page and records `aborted`. Cannot be read means a 5xx, a 429 or a network error, and counts as a disallow (`unreachable`). Any other 4xx means there is no robots.txt (`absent`). A 429 asks the run to slow down and never means permission.
2. **Only listed hosts.** Pages come only from hosts in the graph's sources list, redirects included, within each host's `maxRequestsPerRun`, `maxBytes` and `timeoutSeconds`, with the listed user agent and conditional requests.
3. **A run-wide cap.** `maxRequestsPerRun` bounds the whole run, robots.txt included, and `requests` records the count. When the cap is reached the run stops. Facts not reached wait for the next run, which starts from the oldest `measuredAt`.
4. **429 and 503 on a page.** With `Retry-After` at most `retryAfterMaxSeconds`, the run waits and retries once. Otherwise, or when the retry fails too, it stops fetching that host for the run, and that host's remaining facts are `unreadable`, with the status and `retryAfterSeconds` recorded. It never retries a page twice.
5. **The report.** Each fact fetched is `unchanged` when its quote is in the page text, `changed` when the page was read and the quote is not in it, and `unreadable` otherwise, with the reason.

What the consumer does with each outcome (pull requests, issues, auto-merge) is its own process. For the fact graphs, see practice-library/graphs.

## sources

A graph's sources list holds the run-wide request cap, the Retry-After limit and how many unreadable runs open an issue. Then it lists every host a node may cite, with:

- its robots.txt verdict when it was added;
- the sentence of its terms that bears on automated reading, and, when the terms page has no such clause, an optional `terms.note` (1 to `spec.termsNoteMaxLength` characters in `policy/constants.json`, 300) that says so, so the quote is read as the nearest relevant sentence and not as a clause;
- the page format: `markdown`, `text`, `html`, `json` or `pdf` (the quote is matched in the text extracted from the PDF, with whitespace collapsed);
- the per-host limits.

The robots.txt verdict is evidence for adding the host; the run still re-reads robots.txt every time. A host whose robots.txt disallows the reader is not listed.

## drill-report

See [drill-report](drill-report/README.md).

## ratchet

See [ratchet](ratchet/README.md).
