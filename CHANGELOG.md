# Changelog

One line per change to the surface other repositories depend on. A rename or removal is breaking; an added optional input is not.

## Unreleased

## v2.6.0

Additive in the surface (#42): the denylist file gains an optional key, and a change that adds or widens an exemption needs the existing loosening label. The denylist guard also refuses more for every repository: a renamed file is read whole at its new path, and a head list that is not JSON fails.

- guard.yml `denylist`: the denylist file may carry `exemptPaths`, a list of `{"glob", "terms"}`. An added line of a file under a glob is not found for the hashes in `terms`, or for any entry when `terms` is left out; added paths, commit messages, names and every other file are judged as before. A glob is relative to the root, `*` and `?` stay in one segment, a `**` segment spans any number, and the first segment holds no wildcard. The exemptions come from the base commit, so they never apply to the change that adds them, and a first list is used without them. A pull request that adds or widens an entry fails until a maintainer who is not the author adds the `label` input's label (default `schema-loosening-approved`); on a push it is reported. A head list that is not JSON now fails the guard. Each line an exemption lets through is printed with its glob. The content diff is read with `--no-renames`, so a file moved out of an exempt tree is judged whole at its new path.

## v2.5.0

Additive in the surface; several guards refuse more than before (part 1 of #35).

- guard.yml `schema-loosening`: a key added under a sibling `properties` or `patternProperties` of an `additionalProperties` or `unevaluatedProperties` that was `false` is reported as a loosening (a property added under `allOf`, `then` or `dependentSchemas` beside an `unevaluatedProperties: false` is not yet seen, #35), as is `unevaluatedProperties: false` made anything else. v2.4.0's `attrs.status` and v2.1.0's `attrs.basis` are the cases this would have reported.
- message-check.yml: a protocol message whose JSON block gives a key twice, at any depth and whatever the values, is refused. The check runs `python3`, which GitHub-hosted runners have; a runner without it refuses every message. Fences are read as CommonMark reads them (three or more backticks or tildes, indented by up to three spaces; a backtick line whose info string holds a backtick is inline code), so a ```` ```json ```` quoted inside another fence is not read as the message, and a json block opened by anything but ```` ```json ```` at the start of a line (`~~~json`, ```` ````json ````, an indented ```` ```json ````) is refused.
- guard.yml `release-note`: the changelog count is taken inside the guard from the diff. A line moved within the changelog no longer counts, and a content line starting with `++` now does.
- spec/ratchet/reconcile.sh: `--check <name>` refuses a baseline recorded for another check.
- guard.yml `size`: a file git treats as binary is recounted from its text diff, whatever its name, so a NUL byte or a `binary` attribute cannot hide lines; a path read from git is taken as it is, so a directory named like a rename (`a => selftest`) no longer counts as a fixture; a changed path holding a newline is refused; a real binary file now counts its newline-separated lines, so a repository adding images may list those folders as fixtures. The fixture entry `"/"` is refused.
- scripts/mutants.sh: a mutant that leaves its library with a bash syntax error is an error, not a caught mutant. A mutant that breaks a jq or Python program inside a library is not detected this way.

## v2.4.0

Additive. All three changes widen a schema and were reviewed as loosenings (label on #48). `schema-loosening` reports the new `rel` and `format` values but not the new `attrs.status` property, since it does not yet see a property added under `additionalProperties: false` (#35).

- spec/node/schema.json: `attrs.status`, optional, one of `in-force`, `notified-not-in-force`, `draft` or `superseded`, for a fact that is a rule with a legal or published state (#47). Any other value fails, and so does any other unknown attribute. A domain schema may narrow the list or forbid `status`.
- spec/node/schema.json: six edge relations for legal texts (#49): `issuedBy` (an instrument to the authority that issued it), `partOf` (a provision to its instrument), `madeUnder` (rules or directions to the enabling provision), `imposes` (a provision to the obligation, timeline, penalty or exemption it creates), `amends` (an instrument to the instrument it amends) and `commencedBy` (a provision to the notification that brought it into force). Any other relation still fails; a domain schema may restrict `rel` to the values it uses.
- spec/sources/schema.json: `format` may be `pdf` (#46). The quote is matched in the text extracted from the document, with whitespace collapsed; any other unknown format still fails. A reader of the sources list that does not support `pdf` should refuse such a host with a clear message.

## v2.3.0

Additive.

- gate.yml: the pin check reads each workflow as YAML, with yq 4.44.3 fetched and pinned by sha256, instead of line by line. A `uses:` written as a quoted key, a flow mapping, a block scalar, an anchor or alias (including `jobs:` itself as an alias), or through a merge key that names an alias, is judged like any other. A workflow that does not parse fails the gate. Only `jobs.<id>.uses` and `jobs.<id>.steps[].uses` are judged; a `uses` key anywhere else is not.

## v2.2.0

Additive.

- guard.yml: `schema-loosening` no longer flags a `pattern` change whose exact old and new pair is on the reviewed list `guards.tighteningPairs` (SHA-256 of the pair). The list starts with the three v2.1.0 date and time tightenings (node `measuredAt` and `attrs.fetched_at`, and `$defs.time` moved from practice-library/graphs). Any other pattern change is still flagged, and so is a listed one under `not`, `if`, `oneOf` or `contains`.

## v2.1.0

Additive; the breaking surface is unchanged (workflow file names, every existing input and output, the `gate / gate` context, the keys of `check.json` and the formats of the `.github` files stay as in v2.0.0). A repository pinned to v2.0.0 by commit is unaffected; ADOPTING.md says how to move.

- spec/node/schema.json:
  - `attrs.basis`, optional, `documented` (the default) or `observed`. An observed node's `source` is the https run or record that measured it, its `quote` a line copied exactly from that log, and its `fetched_at` when the measurement ran. Any other `basis` value fails.
  - A new edge kind, `observes`, links an observed node to the documented node about the same quantity, so the two are never merged; a node with an `observes` edge must say `basis: "observed"`.
  - A fifth verdict, `absent`: the page was checked and does not state the fact. It needs a `note` naming the page and has no `value`.
  - `measuredAt` and `attrs.fetched_at` must be real calendar dates and times, as `format` always said; 2026-02-31 now fails. The `T` in `fetched_at` may be lower case, as RFC 3339 allows.
- spec/refresh-report and spec/sources: moved here from practice-library/graphs, with `$id`s under this repository, real calendar dates, and a robots.txt that answers 429 recorded as `unreachable` (never `absent`).
- spec/ratchet: a shrink-only baseline format with a reference reconciler, `spec/ratchet/reconcile.sh`.
- spec/protocol/message.schema.json and docs/protocol.md: protocol v0, issue-based messages with CloudEvents field names; issue forms for request, answer and blocked; `message-check.yml`, the guard for `issues` events.
- consumer kit: the schema-check job passes every key a `check.json` row may carry, generated from the checks row.
- schema-check.yml: optional inputs `mode` (`validate`, `metaschema`, `guards`), `resolve`, `resolve-ids` and `guards`; `instances` is needed only in `validate` mode. A `$id` that does not match `resolve-ids` is a setup error that fails the check even when `expect` is `fail`.
- guard.yml: `guard: size`, optional (the gate does not require it), with the optional inputs `size-limit`, `size-fixtures` (an entry starting and ending in `/` is a directory from the root; any other entry with a `/` is one path from the root, and may start with `/`) and `size-label`; it reads the diff with the change's own `.gitattributes` ignored; the label `size-approved`. The `schema-loosening` guard now counts a deleted schema as loosened and fails on a base file it cannot read. The `release-note` guard counts only a changelog edit that adds a line with text.
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
