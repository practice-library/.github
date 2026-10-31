<!-- Generated from templates/README.md and policy/constants.json by scripts/render.sh. Do not edit. -->
# .github

Organisation defaults for practice-library: community files, reusable workflows, and the ruleset record. Every limit, name, pin and URL lives in `policy/constants.json`; the workflows, `rulesets/main.json` and this README are rendered from it by `scripts/render.sh`.

## Plug a repository in

Add one workflow that calls the checks it needs and ends in a job named `gate` (pin `<sha>` to a commit of this repository), and list exactly the jobs the gate needs in `.github/required-checks.json` as `{"jobs": [...]}`; it must include ["leak-scan","denylist","removed-paths","release-note","schema-loosening"]:

```yaml
on:
  pull_request:
    types: [opened, synchronize, reopened, labeled, unlabeled]
permissions:
  contents: read
jobs:
  leak-scan:
    uses: practice-library/.github/.github/workflows/leak-scan.yml@<sha>
  denylist:
    permissions: { contents: read, pull-requests: read }
    uses: practice-library/.github/.github/workflows/guard.yml@<sha>
    with: { guard: denylist }
  removed-paths:
    permissions: { contents: read, pull-requests: read }
    uses: practice-library/.github/.github/workflows/guard.yml@<sha>
    with: { guard: removed-paths }
  release-note:
    permissions: { contents: read, pull-requests: read }
    uses: practice-library/.github/.github/workflows/guard.yml@<sha>
    with: { guard: release-note }
  schema-loosening:
    permissions: { contents: read, pull-requests: read }
    uses: practice-library/.github/.github/workflows/guard.yml@<sha>
    with: { guard: schema-loosening }
  gate:
    if: always()
    needs: ["leak-scan","denylist","removed-paths","release-note","schema-loosening"]
    uses: practice-library/.github/.github/workflows/gate.yml@<sha>
    with:
      needs: ${{ toJSON(needs) }}
```

The guards in `guard.yml` (input `guard`, one of denylist, removed-paths, release-note, schema-loosening) are mechanical review checks:

- `denylist`: no denied term in the added lines, added paths, or the commit messages, author names and committer names. The list is `.github/denylist.json` on the base commit: `{"salt": ..., "sha256": [...]}`, salted hashes of one- or two-word terms, so the file does not say what it guards against. `scripts/denylist-hash.sh <list> < terms` prints the entries; a finding names where, never the term. With no list, it passes.
- `removed-paths`: nothing mentions a path the change deleted or renamed away, or a directory that is gone, except the files in the input `history` (default ["CHANGELOG.md"]).
- `release-note`: a change under a path in the input `watch` (default [], off) changes `CHANGELOG.md` or has a `Release: none` line in a commit message. This repository watches ["consumer/","spec/",".github/workflows/","rulesets/"].
- `schema-loosening`: a changed JSON schema (a file whose top-level `$schema` is a json-schema.org meta-schema) that accepts more than before fails until a maintainer who is not the author adds the label `schema-loosening-approved`: a lowered or removed minimum, a raised or removed maximum, a removed `required` entry, a wider `enum`, a relaxed `additionalProperties: false`, or a changed `const`, `pattern` or `format`.

Auto-merge is a second workflow on `pull_request_target` that calls `automerge.yml` with `contents: write`, `pull-requests: write` and the required input `trusted-authors`; its allowlist is `.github/automerge-paths.json` (`{"paths": [...]}`) on the base commit, and the gate fails if CODEOWNERS owns any of those paths. It turns auto-merge on only for a trusted author whose pull request touches nothing outside the allowlist; every other pull request needs a maintainer (`.github/CODEOWNERS`). The ruleset in `rulesets/main.json` requires the `gate / gate` check, so a failed check always blocks the merge. Branches need not be up to date with `main` before merging (strict status checks off): a workflow can only update a branch with its own token, and pushes made with that token start no checks, so strict checks would leave automation pull requests waiting forever. The run on `main` after every merge shows any combination that breaks.

## Contract

Input names are the API: adding an optional input is a minor change; renaming or removing an input, or making one required, is a major change. `schema-check` takes an optional `expect` (`pass` or `fail`) so a repository can keep counter-examples that must fail validation. Inputs starting with `_selftest-` belong to this repository's self-test and are not part of the API. Pin the full commit SHA of a release with the tag as a comment, for example `@<sha> # v2.0.0`; Dependabot proposes the bumps (`consumer/.github/dependabot.yml`). Release tags matching ["refs/tags/v*"] can be neither deleted nor moved (`rulesets/tags.json`).

The fact-node envelope (`spec/node/schema.json`) is checked in CI by JSON Schema only, through `schema-check`. Conformance with `et network check` is verified privately by the maintainers' tooling; `et` is not public, so no workflow here fetches or pins it.

The breaking surface is: input and output names of the reusable workflows, their file names, the required check name `gate / gate`, the keys of `check.json`, the formats of `.github/required-checks.json`, `.github/automerge-paths.json` and `.github/denylist.json`, the label `schema-loosening-approved` and the line `Release: none`. Any change to it is a line in `CHANGELOG.md`. A Dependabot config for repositories that call these workflows is in `consumer/.github/dependabot.yml`.

## Change something

- A pin, limit or path: edit `policy/constants.json`, then run `scripts/render.sh`.
- A schema to check: put a `check.json` (`{"schema": ..., "instances": ...}`, paths relative to it) next to the schema; nothing else changes.
- A new kind of check: a reusable workflow plus one row in `checks` in `policy/constants.json`.
- A self-test case: add a directory under `selftest/fixtures` with a `case.json`.
