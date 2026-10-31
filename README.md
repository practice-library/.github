<!-- Generated from templates/README.md and policy/constants.json by scripts/render.sh. Do not edit. -->
# .github

Organisation defaults for practice-library: community files, reusable workflows, and the ruleset record. Every limit, name, pin and URL lives in `policy/constants.json`; the workflows, `rulesets/main.json` and this README are rendered from it by `scripts/render.sh`.

## Plug a repository in

Add one workflow that calls the checks it needs and ends in a job named `gate` (pin `<sha>` to a commit of this repository), and list exactly the jobs the gate needs in `.github/required-checks.json` as `{"jobs": [...]}`; it must include ["leak-scan"]:

```yaml
on: [pull_request]
permissions:
  contents: read
jobs:
  leak-scan:
    uses: practice-library/.github/.github/workflows/leak-scan.yml@<sha>
  gate:
    if: always()
    needs: [leak-scan]
    uses: practice-library/.github/.github/workflows/gate.yml@<sha>
    with:
      needs: ${{ toJSON(needs) }}
```

Auto-merge is a second workflow on `pull_request_target` that calls `automerge.yml` with `contents: write`, `pull-requests: write` and the required input `trusted-authors`; its allowlist is `.github/automerge-paths.json` (`{"paths": [...]}`) on the base commit, and the gate fails if CODEOWNERS owns any of those paths. It turns auto-merge on only for a trusted author whose pull request touches nothing outside the allowlist; every other pull request needs a maintainer (`.github/CODEOWNERS`). The ruleset in `rulesets/main.json` requires the `gate / gate` check, so a failed check always blocks the merge. Branches need not be up to date with `main` before merging (strict status checks off): a workflow can only update a branch with its own token, and pushes made with that token start no checks, so strict checks would leave automation pull requests waiting forever. The run on `main` after every merge shows any combination that breaks.

## Contract

Input names are the API: adding an optional input is a minor change; renaming or removing an input, or making one required, is a major change. `schema-check` takes an optional `expect` (`pass` or `fail`) so a repository can keep counter-examples that must fail validation. Inputs starting with `_selftest-` belong to this repository's self-test and are not part of the API. Pin the full commit SHA of a release with the tag as a comment, for example `@<sha> # v1.1.0`; Dependabot proposes the bumps (`consumer/.github/dependabot.yml`). Release tags matching ["refs/tags/v*"] can be neither deleted nor moved (`rulesets/tags.json`).

The fact-node envelope (`spec/node/schema.json`) is checked in CI by JSON Schema only, through `schema-check`. Conformance with `et network check` is verified privately by the maintainers' tooling; `et` is not public, so no workflow here fetches or pins it.

The breaking surface is: input and output names of the reusable workflows, their file names, the required check name `gate / gate`, the keys of `check.json`, and the formats of `.github/required-checks.json` and `.github/automerge-paths.json`. Any change to it is a line in `CHANGELOG.md`. A Dependabot config for repositories that call these workflows is in `consumer/.github/dependabot.yml`.

## Change something

- A pin, limit or path: edit `policy/constants.json`, then run `scripts/render.sh`.
- A schema to check: put a `check.json` (`{"schema": ..., "instances": ...}`, paths relative to it) next to the schema; nothing else changes.
- A new kind of check: a reusable workflow plus one row in `checks` in `policy/constants.json`.
- A self-test case: add a directory under `selftest/fixtures` with a `case.json`.
