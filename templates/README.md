# .github

Organisation defaults for @@org.name@@: community files and reusable workflows that check pull requests. Every limit, name, pin and URL lives in `policy/constants.json`.

## Adopt

Call the checks from one workflow, pinned to a full commit of this repository with the release tag as a comment, and end it in a job named `@@gate.callerJob@@`:

```yaml
on:
  pull_request:
    types: [opened, synchronize, reopened, labeled, unlabeled]
permissions:
  contents: read
jobs:
  leak-scan:
    uses: @@org.name@@/@@org.repo@@/.github/workflows/leak-scan.yml@<sha> # @@release.tag@@
  denylist:
    permissions:
      contents: read
      pull-requests: read
    uses: @@org.name@@/@@org.repo@@/.github/workflows/@@guards.workflow@@@<sha> # @@release.tag@@
    with:
      guard: denylist
  removed-paths:
    permissions:
      contents: read
      pull-requests: read
    uses: @@org.name@@/@@org.repo@@/.github/workflows/@@guards.workflow@@@<sha> # @@release.tag@@
    with:
      guard: removed-paths
  release-note:
    permissions:
      contents: read
      pull-requests: read
    uses: @@org.name@@/@@org.repo@@/.github/workflows/@@guards.workflow@@@<sha> # @@release.tag@@
    with:
      guard: release-note
  schema-loosening:
    permissions:
      contents: read
      pull-requests: read
    uses: @@org.name@@/@@org.repo@@/.github/workflows/@@guards.workflow@@@<sha> # @@release.tag@@
    with:
      guard: schema-loosening
  @@gate.callerJob@@:
    if: always()
    needs: @@json:gate.mandatoryJobs@@
    uses: @@org.name@@/@@org.repo@@/.github/workflows/gate.yml@<sha> # @@release.tag@@
    with:
      needs: ${{ toJSON(needs) }}
```

List the jobs the gate needs in `@@gate.requiredChecksFile@@` as `{"jobs": [...]}`; it must include @@json:gate.mandatoryJobs@@.

## Supported platform

GitHub.com only. GitHub Enterprise Server and other hosts are not supported.

## Required check

Require the check `@@gen:context@@`. The ruleset in `rulesets/main.json` does.

## Links

- [ADOPTING.md](ADOPTING.md): moving to a new release, and what each release changes.
- [CHANGELOG.md](CHANGELOG.md): the API, enforcement, permission and download changes of every release.
- [docs/new-repo-checklist.md](docs/new-repo-checklist.md): bringing a repository in (`scripts/onboard.sh`).
- [spec/README.md](spec/README.md): the contracts under `spec/`.
- [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).
