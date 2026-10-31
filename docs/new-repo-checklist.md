# New repository checklist

Run this for every new practice-library repository. On the free plan, security settings have no organisation-wide default, so each repository needs them switched on by hand.

## Before the first push

- [ ] The leak scan runs clean on everything to be published (see `leak-scan/README.md`).
- [ ] A licence file matches the content: Apache-2.0 for code, CC BY 4.0 for prose and graphs, CC0 for pure data.

## Settings, then Code security

- [ ] Private vulnerability reporting: on.
- [ ] Secret scanning: on.
- [ ] Push protection: on.
- [ ] Dependabot alerts: on.
- [ ] Code scanning default setup: on, for repositories that hold code.

## Settings, then Actions

- [ ] Default workflow permissions: read repository contents only.
- [ ] Fork pull requests: require approval for all outside contributors, first-time ones included.
- [ ] No repository secrets.

## Settings, then Rules

- [ ] Main is protected: changes by pull request only, no force pushes, no deletion.
- [ ] Required status checks: the ones named for that repository.

## Read back

Confirm each setting from the API rather than by looking:

```sh
r=practice-library/<repo>
gh api repos/$r --jq .security_and_analysis                      # secret scanning, push protection
gh api repos/$r/private-vulnerability-reporting --jq .enabled   # true
gh api repos/$r/actions/permissions/workflow --jq .default_workflow_permissions   # "read"
```

A repository is ready when every box is ticked and every read-back matches.
