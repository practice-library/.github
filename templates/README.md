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

- `denylist`: no denied term in the added lines, added paths, or the commit messages, author names and committer names. On a push, a merge commit's author name is left out, since a merge made in the browser is authored by whoever merged it; its message and committer are judged. A name that must never fail it, such as a maintainer's account name, goes in the list's optional `allowAuthorNames`: salted hashes of whole names (64 lower-case hex characters each; any other entry makes the check invalid), from `scripts/denylist-hash.sh --names @@guards.denylistFile@@ < names`. An author or committer name that is one of them is not judged; the same word in a message, an added line or an added path still is. A change that cannot be read fails as invalid, never as clean. A consumer needs no `allowAuthorNames` unless a maintainer's name holds a denied word. The list is `@@guards.denylistFile@@` on the base commit: `{"salt": ..., "sha256": [...]}`, salted hashes of one- or two-word terms, so the file does not say what it guards against. `scripts/denylist-hash.sh <list> < terms` prints the entries; a finding names where, never the term. With no list, or an empty one, it fails as unguarded; the change that adds the first list is checked with it. Every changed file is read as text whatever `.gitattributes` says (`-diff` or `binary` hide nothing), but binary files are not scanned in any useful sense: words inside compressed content such as images and archives are not visible.
- `removed-paths`: nothing mentions a path the change deleted or renamed away, or a directory that is gone, except the files in the input `history` (default @@json:guards.historyFiles@@).
- `release-note`: a change under a path in the input `watch` (default @@json:guards.releaseWatch@@, off) changes `@@guards.changelog@@` or has a `@@guards.noReleaseMarker@@` line in a commit message. This repository watches @@json:self.releaseWatch@@.
- `schema-loosening`: a changed JSON schema (a file whose top-level `$schema` is a json-schema.org meta-schema) that accepts more than before fails until a maintainer who is not the author adds the label `@@guards.loosenLabel@@`: a lowered or removed minimum, a raised or removed maximum, a removed `required` entry, a wider `enum`, a relaxed `additionalProperties: false`, or a changed `const`, `pattern` or `format`.

Auto-merge is a second workflow on `pull_request_target` that calls `automerge.yml` with `contents: write`, `pull-requests: write` and the required input `trusted-authors`; its allowlist is `@@automerge.pathsFile@@` (`{"paths": [...]}`) on the base commit, and the gate fails if CODEOWNERS owns any of those paths. It turns auto-merge on only for a trusted author whose pull request touches nothing outside the allowlist; every other pull request needs a maintainer (`.github/CODEOWNERS`). The ruleset in `rulesets/main.json` requires the `@@gen:context@@` check, so a failed check always blocks the merge. Branches need not be up to date with `@@org.defaultBranch@@` before merging (strict status checks off): a workflow can only update a branch with its own token, and pushes made with that token start no checks, so strict checks would leave automation pull requests waiting forever. The run on `@@org.defaultBranch@@` after every merge shows any combination that breaks.

## Contract

Input names are the API: adding an optional input is a minor change; renaming or removing an input, or making one required, is a major change. `schema-check` takes an optional `expect` (`pass` or `fail`) so a repository can keep counter-examples that must fail validation. Inputs starting with `_selftest-` belong to this repository's self-test and are not part of the API. Pin the full commit SHA of a release with the tag as a comment, for example `@<sha> # @@release.tag@@`; Dependabot proposes the bumps (`consumer/.github/dependabot.yml`). Release tags matching @@json:tagRuleset.include@@ can be neither deleted nor moved (`rulesets/tags.json`).

The fact-node envelope (`spec/node/schema.json`) is checked in CI by JSON Schema only, through `schema-check`. Conformance with `et network check` is verified privately by the maintainers' tooling; `et` is not public, so no workflow here fetches or pins it.

The breaking surface is: input and output names of the reusable workflows, their file names, the required check name `@@gen:context@@`, the keys of `check.json`, the formats of `@@gate.requiredChecksFile@@`, `@@automerge.pathsFile@@` and `@@guards.denylistFile@@`, the label `@@guards.loosenLabel@@` and the line `@@guards.noReleaseMarker@@`. Any change to it is a line in `CHANGELOG.md`. A Dependabot config for repositories that call these workflows is in `consumer/.github/dependabot.yml`.

## Change something

- A pin, limit or path: edit `policy/constants.json`, then run `@@render.script@@`.
- A schema to check: put a `check.json` (`{"schema": ..., "instances": ...}`, paths relative to it) next to the schema; nothing else changes.
- A new kind of check: a reusable workflow plus one row in `checks` in `policy/constants.json`.
- A self-test case: add a directory under `@@selftest.fixturesDir@@` with a `@@selftest.caseFile@@`.
