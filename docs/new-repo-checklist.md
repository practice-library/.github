<!-- Generated from templates/docs/new-repo-checklist.md and policy/constants.json by scripts/render.sh. Do not edit. -->
# New repository checklist

Do these once, in order, when a repository joins practice-library. The automation account runs every step through the API except step 3, which only an organisation owner can do. Each step names how to confirm it. The values come from `policy/constants.json`. In the commands, `$R` is `practice-library/<repo>`; run each one as the automation account, through the app token wrapper.

## 0. A clone that pushes as the automation account

- [ ] In a fresh clone, make git ask `gh` for credentials, so pushes use the app token instead of a keychain login (which GitHub refuses):
  `git config --local --add credential.helper ''` then `git config --local --add credential.helper '!gh auth git-credential'`.
- [ ] Set the author to the automation account (`user.name` and `user.email`), with no co-author trailer.

## 1. Security settings

- [ ] Private vulnerability reporting: `gh api -X PUT repos/$R/private-vulnerability-reporting`. Confirm: a `GET` of the same path returns `"enabled": true`.
- [ ] Secret scanning and push protection: `gh api -X PATCH repos/$R -f 'security_and_analysis[secret_scanning][status]=enabled' -f 'security_and_analysis[secret_scanning_push_protection][status]=enabled'`. Confirm: both show `enabled` in `GET repos/$R`.
- [ ] Dependabot alerts: `gh api -X PUT repos/$R/vulnerability-alerts`. Confirm: a `GET` of the same path returns 204.
- [ ] A denylist, `.github/denylist.json` (`{"salt": "<random hex>", "sha256": []}`, then `scripts/denylist-hash.sh .github/denylist.json < terms` for the entries); without one, `denylist` fails as unguarded. Confirm: the file has at least one entry.
- [ ] If a maintainer's account name, or any name that merges or commits, holds a denied word: its hash in the list's `allowAuthorNames` (`scripts/denylist-hash.sh --names .github/denylist.json < names`), so that name never fails `denylist`. Confirm: a commit by that name in a pull request passes `denylist`.
- [ ] The label `schema-loosening-approved`, which lets a loosened JSON schema through: `gh api -X POST repos/$R/labels -f name=schema-loosening-approved -f color=d93f0b -f 'description=A maintainer reviewed a loosened JSON schema'`. Confirm: `GET repos/$R/labels/schema-loosening-approved` returns it.

## 2. Merge settings

- [ ] Auto-merge on, and only the ruleset's merge methods (["merge","squash"]) allowed: `gh api -X PATCH repos/$R -F allow_auto_merge=true` plus `-F allow_<method>_merge=false` for every other method. Confirm: `GET repos/$R` shows them.

## 3. Maintainers (organisation owner, by hand)

- [ ] Give the team `@practice-library/maintainers` Write access to the repository: Organisation, Teams, the team, Repositories, Add repository, then Role: Write. The automation account cannot do this: the app has no organisation members permission. Confirm: `GET repos/$R/teams` lists the team with `push`.

## 4. Files, in one pull request from the automation account

- [ ] `.github/CODEOWNERS`, giving everything to the maintainers and leaving the repository's auto-merge allowlist unowned:

```
* @practice-library/maintainers
<one line per allowlisted path, with no owner>
```

- [ ] A caller workflow on `pull_request` and `push` that runs the checks the repository needs and ends in a job named `gate`, which calls `gate.yml`; list exactly the jobs the gate needs in `.github/required-checks.json` as `{"jobs": [...]}`, including ["leak-scan","denylist","removed-paths","release-note","schema-loosening"] (see the README).
- [ ] A caller workflow on `pull_request_target` that calls `automerge.yml` with `trusted-authors: '["practice-library[bot]"]'`; list the paths that may merge without review in `.github/automerge-paths.json` as `{"paths": [...]}` (absent means none).
- [ ] Pin every `uses:` of this repository to a full commit SHA of `.github`.
- Confirm: `GET repos/$R/codeowners/errors` returns no errors, and the pull request's `gate / gate` check passes. Neither CODEOWNERS nor the auto-merge caller is on the default branch yet, so this first pull request needs no review and does not merge itself: a maintainer merges it.

## 5. Ruleset

- [ ] `gh api -X POST repos/$R/rulesets --input rulesets/main.json`, from this repository's default branch.
- [ ] Confirm: `GET repos/$R/rulesets/<id>` equals `rulesets/main.json` (name, target, enforcement, conditions, bypass actors and rules).

## 6. Live checks, after the step 4 pull request is merged

- [ ] A pull request from the automation account that touches only allowlisted paths merges on its own after `gate / gate` passes, with no review. Skip it when the allowlist is empty.
- [ ] A pull request that touches any other path shows "Review required", and auto-merge stays off.
