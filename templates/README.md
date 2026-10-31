# .github

Organisation defaults for @@org.name@@: community files, reusable workflows, and the ruleset record. Every limit, name, pin and URL lives in `policy/constants.json`; the workflows, `rulesets/main.json` and this README are rendered from it by `@@render.script@@`.

## Plug a repository in

Add one workflow that calls the checks it needs and ends in a job named `@@gate.callerJob@@` (pin `<sha>` to a commit of this repository), and list exactly the jobs the gate needs in `@@gate.requiredChecksFile@@` as `{"jobs": [...]}`; it must include @@json:gate.mandatoryJobs@@:

```yaml
on: [pull_request]
permissions:
  contents: read
jobs:
  leak-scan:
    uses: @@org.name@@/@@org.repo@@/.github/workflows/leak-scan.yml@<sha>
  @@gate.callerJob@@:
    if: always()
    needs: [leak-scan]
    uses: @@org.name@@/@@org.repo@@/.github/workflows/gate.yml@<sha>
    with:
      needs: ${{ toJSON(needs) }}
```

Auto-merge is a second workflow on `pull_request_target` that calls `automerge.yml` with `contents: write`, `pull-requests: write` and the required input `trusted-authors`; its allowlist is `@@automerge.pathsFile@@` (`{"paths": [...]}`) on the base commit, and the gate fails if CODEOWNERS owns any of those paths. It turns auto-merge on only for a trusted author whose pull request touches nothing outside the allowlist; every other pull request needs a maintainer (`.github/CODEOWNERS`). The ruleset in `rulesets/main.json` requires the `@@gen:context@@` check, so a failed check always blocks the merge. Branches need not be up to date with `@@org.defaultBranch@@` before merging (strict status checks off): a workflow can only update a branch with its own token, and pushes made with that token start no checks, so strict checks would leave automation pull requests waiting forever. The run on `@@org.defaultBranch@@` after every merge shows any combination that breaks.

## Contract

Input names are the API: adding an optional input is a minor change; renaming or removing an input, or making one required, is a major change. `schema-check` takes an optional `expect` (`pass` or `fail`) so a repository can keep counter-examples that must fail validation. Inputs starting with `_selftest-` belong to this repository's self-test and are not part of the API. Until release tags exist, pin a full commit SHA.

The breaking surface is: input and output names of the reusable workflows, their file names, the required check name `@@gen:context@@`, the keys of `check.json`, and the formats of `@@gate.requiredChecksFile@@` and `@@automerge.pathsFile@@`. Any change to it is a line in `CHANGELOG.md`. A Dependabot config for repositories that call these workflows is in `consumer/.github/dependabot.yml`.

## Change something

- A pin, limit or path: edit `policy/constants.json`, then run `@@render.script@@`.
- A schema to check: put a `check.json` (`{"schema": ..., "instances": ...}`, paths relative to it) next to the schema; nothing else changes.
- A new kind of check: a reusable workflow plus one row in `checks` in `policy/constants.json`.
- A self-test case: add a directory under `@@selftest.fixturesDir@@` with a `@@selftest.caseFile@@`.
