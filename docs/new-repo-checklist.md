<!-- Generated from templates/docs/new-repo-checklist.md and policy/constants.json by scripts/render.sh. Do not edit. -->
# New repository checklist

Do these once, in order, when a repository joins practice-library. Each step names how to confirm it. The values come from `policy/constants.json`.

## 1. Security settings (Settings, Advanced Security)

- [ ] Private vulnerability reporting: on. Confirm: `GET /repos/practice-library/<repo>/private-vulnerability-reporting` returns `"enabled": true`.
- [ ] Secret scanning: on.
- [ ] Push protection: on.
- [ ] Dependabot alerts: on.
- Confirm the scanning settings: `GET /repos/practice-library/<repo>` shows `security_and_analysis.secret_scanning` and `secret_scanning_push_protection` as `enabled`.

## 2. Merge settings (Settings, General)

- [ ] Allow auto-merge: on. Confirm: `allow_auto_merge` is `true`.
- [ ] Allowed merge methods match the ruleset: ["merge","squash"].

## 3. Maintainers

- [ ] Give the team `@practice-library/maintainers` Write access to the repository.
- [ ] Add `.github/CODEOWNERS`. Confirm: `GET /repos/practice-library/<repo>/codeowners/errors` returns no errors.

```
* @practice-library/maintainers
/ghgraph/graph/nodes/
/ghgraph/INDEX.md
```

## 4. Workflows

- [ ] A caller workflow on `pull_request` that runs the checks the repository needs and ends in a job named `gate`, which calls `gate.yml` with `required: '["leak-scan"]'` (see the README).
- [ ] A caller workflow on `pull_request_target` that calls `automerge.yml` with `allow-paths: '<the repository's own allowlist>'` and `trusted-authors: '["practice-library[bot]"]'`.
- [ ] Pin every `uses:` of this repository to a full commit SHA.

## 5. Ruleset (Settings, Rules, Rulesets)

- [ ] New ruleset, Import a ruleset, then choose `rulesets/main.json` from this repository.
- [ ] Confirm: `GET /repos/practice-library/<repo>/rulesets/<id>` equals `rulesets/main.json` (name, target, enforcement, conditions, bypass actors and rules).

## 6. Live checks

- [ ] A pull request from the automation account that touches only allowlisted paths merges on its own after `gate / gate` passes, with no review.
- [ ] A pull request that touches any other path shows "Review required" and auto-merge stays off.
