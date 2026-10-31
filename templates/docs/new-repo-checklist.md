# New repository checklist

Do these once, in order, when a repository joins @@org.name@@. Each step names how to confirm it. The values come from `policy/constants.json`.

## 1. Security settings (Settings, Advanced Security)

- [ ] Private vulnerability reporting: on. Confirm: `GET /repos/@@org.name@@/<repo>/private-vulnerability-reporting` returns `"enabled": true`.
- [ ] Secret scanning: on.
- [ ] Push protection: on.
- [ ] Dependabot alerts: on.
- Confirm the scanning settings: `GET /repos/@@org.name@@/<repo>` shows `security_and_analysis.secret_scanning` and `secret_scanning_push_protection` as `enabled`.

## 2. Merge settings (Settings, General)

- [ ] Allow auto-merge: on. Confirm: `allow_auto_merge` is `true`.
- [ ] Allowed merge methods match the ruleset: @@json:ruleset.allowedMergeMethods@@.

## 3. Maintainers

- [ ] Give the team `@@org.maintainer@@` Write access to the repository.
- [ ] Add `.github/CODEOWNERS`. Confirm: `GET /repos/@@org.name@@/<repo>/codeowners/errors` returns no errors.

```
* @@org.maintainer@@
@@gen:unowned@@
```

## 4. Workflows

- [ ] A caller workflow on `pull_request` that runs the checks the repository needs and ends in a job named `@@gate.callerJob@@`, which calls `gate.yml` with `required: '@@json:gate.requiredJobs@@'` (see the README).
- [ ] A caller workflow on `pull_request_target` that calls `automerge.yml` with `allow-paths: '<the repository's own allowlist>'` and `trusted-authors: '@@json:org.trustedAuthors@@'`.
- [ ] Pin every `uses:` of this repository to a full commit SHA.

## 5. Ruleset (Settings, Rules, Rulesets)

- [ ] New ruleset, Import a ruleset, then choose `rulesets/main.json` from this repository.
- [ ] Confirm: `GET /repos/@@org.name@@/<repo>/rulesets/<id>` equals `rulesets/main.json` (name, target, enforcement, conditions, bypass actors and rules).

## 6. Live checks

- [ ] A pull request from the automation account that touches only allowlisted paths merges on its own after `@@gen:context@@` passes, with no review.
- [ ] A pull request that touches any other path shows "Review required" and auto-merge stays off.
