# .github

Organisation defaults for @@org.name@@: community files, reusable workflows, and the ruleset record. Every limit, name, pin and URL lives in `policy/constants.json`; the workflows, `rulesets/main.json` and this README are rendered from it by `@@render.script@@`.

## Plug a repository in

Add one workflow that calls the checks it needs and ends in a job named `@@gate.callerJob@@` (pin `<sha>` to a commit of this repository), and list exactly the jobs the gate needs in `@@gate.requiredChecksFile@@` as `{"jobs": [...]}`; it must include @@json:gate.mandatoryJobs@@:

```yaml
on:
  pull_request:
    types: [opened, synchronize, reopened, labeled, unlabeled]
permissions:
  contents: read
jobs:
  leak-scan:
    uses: @@org.name@@/@@org.repo@@/.github/workflows/leak-scan.yml@<sha>
  denylist:
    permissions: { contents: read, pull-requests: read }
    uses: @@org.name@@/@@org.repo@@/.github/workflows/@@guards.workflow@@@<sha>
    with: { guard: denylist }
  removed-paths:
    permissions: { contents: read, pull-requests: read }
    uses: @@org.name@@/@@org.repo@@/.github/workflows/@@guards.workflow@@@<sha>
    with: { guard: removed-paths }
  release-note:
    permissions: { contents: read, pull-requests: read }
    uses: @@org.name@@/@@org.repo@@/.github/workflows/@@guards.workflow@@@<sha>
    with: { guard: release-note }
  schema-loosening:
    permissions: { contents: read, pull-requests: read }
    uses: @@org.name@@/@@org.repo@@/.github/workflows/@@guards.workflow@@@<sha>
    with: { guard: schema-loosening }
  @@gate.callerJob@@:
    if: always()
    needs: @@json:gate.mandatoryJobs@@
    uses: @@org.name@@/@@org.repo@@/.github/workflows/gate.yml@<sha>
    with:
      needs: ${{ toJSON(needs) }}
```

The guards in `@@guards.workflow@@` (input `guard`, one of @@gen:guardids@@) are mechanical review checks:

- `denylist`: no denied term in the added lines, added paths, or the commit messages, author names and committer names. On a push, a merge commit's author name is left out, since a merge made in the browser is authored by whoever merged it; its message and committer are judged. A name that must never fail it, such as a maintainer's account name, goes in the list's optional `allowAuthorNames`: salted hashes of whole names (64 lower-case hex characters each; any other entry makes the check invalid), from `scripts/denylist-hash.sh --names @@guards.denylistFile@@ < names`. An author or committer name that is one of them is not judged; the same word in a message, an added line or an added path still is. A change that cannot be read fails as invalid, never as clean. A consumer needs no `allowAuthorNames` unless a maintainer's name holds a denied word. The list is `@@guards.denylistFile@@` on the base commit: `{"salt": ..., "sha256": [...]}`, salted hashes of one- or two-word terms, so the file does not say what it guards against. `scripts/denylist-hash.sh <list> < terms` prints the entries; a finding names where, never the term. With no list, or an empty one, it fails as unguarded; the change that adds the first list is checked with it. Every changed file is read as text whatever `.gitattributes` says (`-diff` or `binary` hide nothing), but binary files are not scanned in any useful sense: words inside compressed content such as images and archives are not visible. Limits: a term is one or two words, so a list entry of three or more words never matches; text that is encoded (base64, gzip, URL or HTML escapes) or spelled out with separators inside a word is not decoded.
- `removed-paths`: nothing mentions a path the change deleted or renamed away, or a directory that is gone, except the files in the input `history` (default @@json:guards.historyFiles@@).
- `release-note`: a change under a path in the input `watch` adds at least one line with text to `@@guards.changelog@@` (a whitespace-only or blank-line edit does not count) or has a `@@guards.noReleaseMarker@@` line in a commit message. The default `watch` is @@json:guards.releaseWatch@@, so the guard is off until a repository lists its watched paths; this repository watches @@json:self.releaseWatch@@.
- `schema-loosening`: a changed JSON schema (a file whose top-level `$schema` is a json-schema.org meta-schema) that accepts more than before fails until a maintainer who is not the author adds the label `@@guards.loosenLabel@@`: a lowered or removed minimum, a raised or removed maximum, a removed `required` entry, a wider `enum`, a relaxed `additionalProperties: false`, a changed `const`, `pattern` or `format`, or a deleted schema. A changed `pattern` is not flagged when the exact old and new pair is on the reviewed list of tightenings, `guards.tighteningPairs` in `policy/constants.json`: each entry is the SHA-256 of `["<old>","<new>"]` as compact JSON, with why the new pattern accepts nothing the old one refused. The list ships with the workflow at its pin and grows only by pull request here; a caller cannot add to it. An unlisted pair, a removed pattern or a list that cannot be read is still flagged. A base file that cannot be read fails the guard. On a push the guard reports loosening but asks for no label: the label is judged on the pull request, so a branch protected by the ruleset (changes only through pull requests) is what makes a push without one impossible. The label is judged by who added it last, not by when: it stays valid after later pushes until removed, so a maintainer removes and re-adds it after reviewing new changes.

- `size` (optional: the gate does not require it, so a repository opts in by adding the job and listing it in `@@gate.requiredChecksFile@@`): the lines a pull request adds or changes outside fixtures are at most the input `size-limit` (default @@guards.sizeLimit@@), or the label `@@guards.sizeLabel@@`, added last by someone other than the author and not a bot, lets more through. Fixtures are the input `size-fixtures` (default @@json:guards.sizeFixtures@@): an entry ending in `/` is a directory anywhere in the path, an entry with no `/` a file name anywhere, any other entry one exact path. A renamed file counts once, by its new path; a binary file counts 0. The count is printed either way, for the pull request record.

Auto-merge is a second workflow on `pull_request_target` that calls `automerge.yml` with `contents: write`, `pull-requests: write` and the required input `trusted-authors`; its allowlist is `@@automerge.pathsFile@@` (`{"paths": [...]}`) on the base commit, and the gate fails if CODEOWNERS owns any of those paths. It turns auto-merge on only for a trusted author whose pull request touches nothing outside the allowlist; every other pull request needs a maintainer (`.github/CODEOWNERS`). The ruleset in `rulesets/main.json` requires the `@@gen:context@@` check, so a failed check always blocks the merge. Branches need not be up to date with `@@org.defaultBranch@@` before merging (strict status checks off): a workflow can only update a branch with its own token, and pushes made with that token start no checks, so strict checks would leave automation pull requests waiting forever. The run on `@@org.defaultBranch@@` after every merge shows any combination that breaks.

## Contract

Input names are the API: adding an optional input is a minor change; renaming or removing an input, or making one required, is a major change. `schema-check` takes an optional `expect` (`pass` or `fail`) so a repository can keep counter-examples that must fail validation. Its `mode` is `validate` (default), `metaschema` (check the caller's own schemas, a file or a directory, against their `$schema`), or `guards`. `guards` applies each mutant in a guards file (`{"examples", "counter-examples", "mutants": [{"pointer", "mutation": "delete" | "true"} or {"pointer", "set"}]}`) and passes only when every mutant turns an example or a counter-example red, after checking that the unmutated schema is green. `resolve` lists extra schemas to resolve by `$id`, one path per line, and `resolve-ids` the `$id` each must carry, so a wrong pin fails the check whatever `expect` says. `message-check.yml` is the protocol v0 guard for `issues` events ([docs/protocol.md](docs/protocol.md)). Inputs starting with `_selftest-` belong to this repository's self-test and are not part of the API. Pin the full commit SHA of a release with the tag as a comment, for example `@<sha> # @@release.tag@@`; Dependabot proposes the bumps (`consumer/.github/dependabot.yml`). Release tags matching @@json:tagRuleset.include@@ can be neither deleted nor moved (`rulesets/tags.json`).

The contracts under `spec/` (the fact-node envelope, refresh-report, sources, ratchet and the protocol message) are described in [spec/README.md](spec/README.md) and checked in CI through `schema-check`. To move a repository to a new release, see [ADOPTING.md](ADOPTING.md).

The breaking surface is: input and output names of the reusable workflows, their file names, the required check name `@@gen:context@@`, the keys of `check.json`, the formats of `@@gate.requiredChecksFile@@`, `@@automerge.pathsFile@@` and `@@guards.denylistFile@@`, the labels `@@guards.loosenLabel@@` and `@@guards.sizeLabel@@`, the line `@@guards.noReleaseMarker@@`, and the `$id` of every schema under `spec/`. Any change to it is a line in `CHANGELOG.md`. A Dependabot config for repositories that call these workflows is in `consumer/.github/dependabot.yml`.

## Change something

- A pin, limit or path: edit `policy/constants.json`, then run `@@render.script@@`.
- A schema to check: put a `check.json` (`{"schema": ..., "instances": ...}`, paths relative to it) next to the schema; nothing else changes.
- A new kind of check: a reusable workflow plus one row in `checks` in `policy/constants.json`.
- A self-test case: add a directory under `@@selftest.fixturesDir@@` with a `@@selftest.caseFile@@`.
