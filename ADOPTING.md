# Adopting a release

A repository calls this repository's workflows pinned to a commit, with the release tag as a comment. Moving to a new release changes that pin and may change more: a minor release may enforce more strictly than the one before, so a check that passed can fail after the bump. Read the release's entry in [CHANGELOG.md](CHANGELOG.md) before you merge the bump.

## What every release entry lists

Each release in the CHANGELOG names, under these headings or in lines that say the same:

- **API changes:** added, renamed or removed workflows, inputs, outputs, check names, file formats and labels (the breaking surface is listed in the README's contract).
- **Enforcement changes:** what the checks now refuse that they accepted before. A minor release may add these.
- **Permissions and downloads:** every permission a caller's job must grant and everything a workflow downloads (tool, version, URL, sha256).
- **Consumer steps:** what a caller must do, in order, or "none".

A release whose entry lacks one of these is incomplete; report it.

## Move your pins

1. Find the release's commit: `git ls-remote https://github.com/practice-library/.github refs/tags/<tag>`. The tag cannot be moved or deleted (`rulesets/tags.json`), but pin the commit it names, not the tag.
2. In every workflow under `.github/workflows/`, change each `uses: practice-library/.github/.github/workflows/<file>.yml@<old sha> # <old tag>` to the new commit and tag. Dependabot proposes this change on its own when the repository uses `consumer/.github/dependabot.yml`.
3. Open the pull request. The gate refuses any `uses:` of a practice-library workflow or action pinned to a branch, a tag, or a short or upper-case SHA, so a missed line fails with its file and line. It reads each workflow as YAML, so an anchor, an alias or a quoted key does not hide a reference. It follows a local `uses: ./path` into a composite action or a local reusable workflow, so a reference inside one is judged too. A workflow that does not parse, a `uses:` that is not a string, or a local path that leaves the repository or names nothing, fails the gate.
4. Read the CHANGELOG entries between your old tag and the new one, and do their consumer steps.

## Downloads and permissions

The gate downloads yq (a pinned release from github.com, verified by its sha256) to read your workflows; the step prints the version, URL and sha256 it used. The workflows' own pins, versions and digests are in `policy/constants.json`. The permissions a caller's jobs must grant are in the README's example; a release that needs more says so under "Permissions and downloads".

## From v2 to v3.0.0

v3.0.0 is a major release: see its entry in the CHANGELOG for every renamed or removed input and check, and do each consumer step. After the bump, the gate's pin check also follows local actions, so a local composite action that calls a practice-library action by a branch or tag now fails.
