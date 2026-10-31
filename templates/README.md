# .github

Organisation defaults for @@org.name@@: community files, reusable workflows, and the ruleset record. Every limit, name, pin and URL lives in `policy/constants.json`; the workflows, `rulesets/main.json` and this README are rendered from it by `@@render.script@@`.

## Plug a repository in

Add one workflow that calls the checks it needs and ends in a job named `@@gate.callerJob@@` (pin `<sha>` to a commit of this repository):

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

Auto-merge is a second workflow on `pull_request_target` that calls `automerge.yml` with `contents: write` and `pull-requests: write`. The ruleset in `rulesets/main.json` requires the `@@gate.context@@` check, so a failed check always blocks the merge.

## Change something

- A pin, limit or path: edit `policy/constants.json`, then run `@@render.script@@`.
- A schema to check: add a row to `schemas` in `policy/constants.json`.
- A self-test case: add a directory under `@@selftest.fixturesDir@@` with a `@@selftest.caseFile@@`.
