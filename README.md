<!-- Generated from templates/README.md and policy/constants.json by scripts/render.sh. Do not edit. -->
# .github

Organisation defaults for practice-library: community files and reusable workflows that check pull requests. Every limit, name, pin and URL lives in `policy/constants.json`.

## Adopt

Call the checks from one workflow, pinned to a full commit of this repository with the release tag as a comment, and end it in a job named `gate`:

```yaml
on:
  pull_request:
    types: [opened, synchronize, reopened, labeled, unlabeled]
permissions:
  contents: read
jobs:
  leak-scan:
    uses: practice-library/.github/.github/workflows/leak-scan.yml@<sha> # v3.0.0
  denylist:
    permissions:
      contents: read
      pull-requests: read
    uses: practice-library/.github/.github/workflows/guard.yml@<sha> # v3.0.0
    with:
      guard: denylist
  removed-paths:
    permissions:
      contents: read
      pull-requests: read
    uses: practice-library/.github/.github/workflows/guard.yml@<sha> # v3.0.0
    with:
      guard: removed-paths
  release-note:
    permissions:
      contents: read
      pull-requests: read
    uses: practice-library/.github/.github/workflows/guard.yml@<sha> # v3.0.0
    with:
      guard: release-note
  schema-loosening:
    permissions:
      contents: read
      pull-requests: read
    uses: practice-library/.github/.github/workflows/guard.yml@<sha> # v3.0.0
    with:
      guard: schema-loosening
  gate:
    if: always()
    needs: ["leak-scan","denylist","removed-paths","release-note","schema-loosening"]
    uses: practice-library/.github/.github/workflows/gate.yml@<sha> # v3.0.0
    with:
      needs: ${{ toJSON(needs) }}
```

List the jobs the gate needs in `.github/required-checks.json` as `{"jobs": [...]}`; it must include ["leak-scan","denylist","removed-paths","release-note","schema-loosening"].

## Supported platform

GitHub.com only. GitHub Enterprise Server and other hosts are not supported.

## Required check

Require the check `gate / gate`. The ruleset in `rulesets/main.json` does.

## Links

- [ADOPTING.md](ADOPTING.md): moving to a new release, and what each release changes.
- [CHANGELOG.md](CHANGELOG.md): the API, enforcement, permission and download changes of every release.
- [docs/new-repo-checklist.md](docs/new-repo-checklist.md): bringing a repository in (`scripts/onboard.sh`).
- [spec/README.md](spec/README.md): the contracts under `spec/`.
- [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).
