# Changelog

One line per change to the surface other repositories depend on. A rename or removal is breaking; an added optional input is not.

## v2.1.0

Additive; the breaking surface is unchanged (workflow file names, every existing input and output, the `gate / gate` context, the keys of `check.json` and the formats of the `.github` files stay as in v2.0.0). A repository pinned to v2.0.0 by commit is unaffected; ADOPTING.md says how to move.

- spec/node/schema.json:
  - `attrs.basis`, optional, `documented` (the default) or `observed`. An observed node's `source` is the https run or record that measured it, its `quote` a line copied exactly from that log, and its `fetched_at` when the measurement ran. Any other `basis` value fails.
  - A new edge kind, `observes`, links an observed node to the documented node about the same quantity, so the two are never merged; a node with an `observes` edge must say `basis: "observed"`.
  - A fifth verdict, `absent`: the page was checked and does not state the fact. It needs a `note` naming the page and has no `value`.
  - `measuredAt` and `attrs.fetched_at` must be real calendar dates and times, as `format` always said; 2026-02-31 now fails.
- spec/refresh-report and spec/sources: moved here from practice-library/graphs, with `$id`s under this repository, real calendar dates, and a robots.txt that answers 429 recorded as `unreachable` (never `absent`).
- spec/ratchet: a shrink-only baseline format with a reference reconciler, `spec/ratchet/reconcile.sh`.
- spec/protocol/message.schema.json and docs/protocol.md: protocol v0, issue-based messages with CloudEvents field names; issue forms for request, answer and blocked; `message-check.yml`, the guard for `issues` events.
- schema-check.yml: optional inputs `mode` (`validate`, `metaschema`, `guards`), `resolve`, `resolve-ids` and `guards`; `instances` is needed only in `validate` mode.
- guard.yml: `guard: size`, optional (the gate does not require it), with the optional inputs `size-limit`, `size-fixtures` and `size-label`; the label `size-approved`. The `schema-loosening` guard now counts a deleted schema as loosened and fails on a base file it cannot read. The `release-note` guard counts only a changelog edit that adds a line with text.
- gate.yml: refuses a practice-library `uses:` pinned to anything but a full commit.
- CONTRIBUTING.md: a ready-for-review self-check; .github/pull_request_template.md carries it as numbers.

## v2.0.0

Breaking: the gate requires four more jobs. A repository pinned to v1.x is unaffected until it moves its pin; to move, add the four guard jobs to its caller workflow and to `.github/required-checks.json`, and add `labeled` and `unlabeled` to its `pull_request` types (`consumer/` has both files).

- guard.yml: new reusable workflow with the required input `guard` (`denylist`, `removed-paths`, `release-note` or `schema-loosening`) and the optional inputs `denylist`, `history`, `watch`, `changelog` and `label`. A caller job needs `contents: read` and `pull-requests: read`.
- gate.yml: the mandatory jobs are `leak-scan`, `denylist`, `removed-paths`, `release-note` and `schema-loosening`. Breaking.
- `.github/denylist.json`: a new file format, `{"salt": ..., "sha256": [...]}`, read from the base commit; `scripts/denylist-hash.sh` writes the entries. A repository without a list, or with an empty one, fails `denylist` as unguarded. The scan reads every file as text, so `.gitattributes` cannot hide a line; compressed binary content is not scanned. On a push, a merge commit's author name is left out, so a browser merge authored by the maintainer does not fail it; its message and committer are judged, and on a pull request every author is judged. The optional `allowAuthorNames` in the list holds salted hashes of whole names, 64 lower-case hex characters each (`scripts/denylist-hash.sh --names`): an author or committer name among them is not judged, while messages, added lines and added paths are. A change that cannot be read fails as invalid. A consumer needs no `allowAuthorNames` unless a maintainer's name holds a denied word.
- The label `schema-loosening-approved` lets a loosened schema through when someone other than the author, and not a bot, adds it.
- consumer/: the caller workflow and `required-checks.json` carry the four guard jobs.

## v1.1.0

Additive; the breaking surface is unchanged (workflow file names, input and output names, the `gate / gate` context, the keys of `check.json` and the formats of the `.github` files stay as in v1.0.0). A repository pinned to v1.0.0 is unaffected.

- spec/node/schema.json: three new edge kinds, `hasRelease` (product to release), `introducedIn` (capability to release) and `removedIn` (capability to release); an edge kind outside the list still fails. schema-check.yml carries the updated copy of the envelope; its inputs and outputs do not change.

## v1.0.0

The first release. Its breaking surface, which a later change may alter only in a major release:

- workflow file names: `leak-scan.yml`, `schema-check.yml`, `discover.yml`, `gate.yml`, `automerge.yml`;
- their input and output names: leak-scan `config`; schema-check `schema`, `instances`, `expect`, `each`; discover `check` and the output `targets`; gate `needs`; automerge `trusted-authors`, `merge-method`;
- the required check name `gate / gate`;
- the keys of `check.json`: `schema`, `instances`, and the optional `expect` and `each`, as one object or a list;
- the format of `.github/required-checks.json`: `{"jobs": [...]}`, equal to the gate's needs and including `leak-scan`;
- the format of `.github/automerge-paths.json`: `{"paths": [...]}`, read on the base commit, none when absent.

Changes in this release:

- gate.yml: removed the input `required`; the gate now reads the jobs from the calling repository's `.github/required-checks.json` (`{"jobs": [...]}`), which must equal its needs and include `leak-scan`. Breaking.
- discover.yml: new reusable workflow with the input `check`, emitting the output `targets`.
- schema-check.yml: new optional input `expect` (`pass` or `fail`).
- schema-check.yml: new optional input `each` (`true` validates every file on its own).
- check.json: may hold a list of targets; optional keys `expect` and `each`.
- spec/node/schema.json: new shared fact-node schema, `$id` https://github.com/practice-library/.github/spec/node/schema.json; schema-check always resolves it.
- spec/node/schema.json: the node envelope is checked in CI by JSON Schema only.
- leak-scan.yml and schema-check.yml: the self-test inputs are `_selftest-fixture` and `_selftest-expect` (leak-scan only); they are not part of the API.
- automerge.yml: removed the input `allow-paths`; the allowlist is read from `.github/automerge-paths.json` (`{"paths": [...]}`) on the base commit, none when absent. Breaking.
- automerge.yml: the input `trusted-authors` is required (no default).
- rulesets/tags.json: release tags matching `v*` cannot be deleted or moved.
- gate.yml: fails when CODEOWNERS owns a path in `.github/automerge-paths.json`.
