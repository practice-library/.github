# Adopting a release

A repository calls this repository's workflows pinned to a commit, with the release tag as a comment. Moving to a new release changes that pin and nothing else, unless the release notes ask for more.

## Move your pins

1. Find the release's commit: `git ls-remote https://github.com/practice-library/.github refs/tags/v2.1.0`. The tag cannot be moved or deleted (`rulesets/tags.json`), but pin the commit it names, not the tag.
2. In every workflow under `.github/workflows/`, change each `uses: practice-library/.github/.github/workflows/<file>.yml@<old sha> # <old tag>` to the new commit and tag. Dependabot proposes this change on its own when the repository uses `consumer/.github/dependabot.yml`.
3. Open the pull request. The gate now refuses any `uses:` of a practice-library workflow or action pinned to a branch, a tag, or a short or upper-case SHA, so a missed line fails with its file and line.
4. Read the CHANGELOG entry between your old tag and the new one. A major release says what each caller must change. A minor release needs no change.

## From v2.0.0 to v2.1.0

Nothing is required. v2.1.0 adds, and every addition is optional, but using one may need a line in your workflow:

- **Gate.** It now refuses a practice-library `uses:` that is not pinned to a full commit. A repository already pinned as the README asks sees no difference.
- **`guard: size`.** An optional guard: add a job and list it in `.github/required-checks.json` to use it.
- **`schema-check`.** A repository built from `consumer/.github/workflows/checks.yml` must copy that job's new `with:` lines (`mode`, `resolve`, `resolve-ids`, `guards`) before a `check.json` row may use those keys. Without them, the keys are dropped and the row runs as plain `validate`. `mode: metaschema` checks your own schemas. `mode: guards` proves each schema guard is covered by a fixture. `resolve` and `resolve-ids` resolve another repository's schema by `$id` and confirm a pin.
- **`message-check.yml`.** The protocol v0 guard for issues events (`docs/protocol.md`).
- **`spec/refresh-report` and `spec/sources`.** These now live here with `$id`s under `https://github.com/practice-library/.github/spec/`. A schema that references the old practice-library/graphs `$id`s keeps working while graphs keeps its pointer copies for one release. Then reference the new `$id`s, pinned by tag.
- **Fact-node envelope.** It adds `attrs.basis`, the `observes` edge, the `absent` verdict, and real calendar dates for `measuredAt` and `attrs.fetched_at`. A node that was valid stays valid unless it carried an impossible date, which `format: date` never allowed.
