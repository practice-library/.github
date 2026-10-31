# Live proof: auto-merge and its limit

Two pull requests from the automation account (`practice-library[bot]`) against `main` in this repository, opened on 2026-10-31, one on each side of the allowlist in `.github/automerge-paths.json`.

## Allowlisted path: merged with no human

- Pull request: [#7](https://github.com/practice-library/.github/pull/7), head `dd3e064e918f268dc48e70df8009efe2f1ec1fe7`.
- Change: `ghgraph/graph/nodes/limit.actions.job-execution-time.json` re-fetched at 2026-10-31T14:10:23Z with the quote unchanged, so only `fetched_at` moves; `ghgraph/INDEX.md` regenerated to match.
- `automerge / automerge` decided `on`; auto-merge enabled by `github-actions` at 2026-10-31T14:10:56Z.
- Required check `gate / gate` passed, after `discover`, `render`, `unit`, `leak-scan (repository) / leak-scan`, both `schema-check` targets and every self-test.
- Merged by `github-actions` (bot) at 2026-10-31T14:11:32Z, merge commit `963cdffae031e19b1c15d2c69564dea683357719`. No review, no human action.

## Protected path: stays unmerged

- Pull request: [#8](https://github.com/practice-library/.github/pull/8), head `0caf3de77ec1e02193fcca63027727d832424786`.
- Change: one line in `README.md` (and its template `templates/README.md`), which CODEOWNERS gives to `@practice-library/maintainers`.
- Every check passed, `gate / gate` included; `automerge / automerge` decided `off`, so auto-merge was never enabled.
- State after the checks: open, merge state `BLOCKED`, review requested from `practice-library/maintainers` (the ruleset on `main` requires a code owner review). It merges only when a maintainer approves.
