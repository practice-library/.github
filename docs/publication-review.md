# Publication review checklist

Everything in practice-library is public: files, commit messages, author and committer names, branch names, pull request and issue text, comments, review bodies, labels, release notes, tag messages, workflow logs and artifacts. Anything pushed or posted here is published, even if it is later deleted: forks, caches and mirrors may keep it.

Material reaches these repositories in one way only: it is written for them, or it is extracted from somewhere else by the allowlist below. A reviewer works through this checklist at the exact head of a pull request before accepting it, and names the head in the receipt. The guards (`leak-scan`, `denylist`) are a backstop, not the review: a hashed denylist only knows the terms someone listed.

## 1. The allowlist: what may be published

Only these kinds of material may be extracted into a public repository. Anything not listed stays out until this list is changed by a reviewed pull request here.

- [ ] Reusable workflows, scripts and their tests that run on public inputs only.
- [ ] Schemas, their examples and counter-examples, and the mutants that test them.
- [ ] Fixtures that are synthetic: generated or written for the test, with invented names, ids, hosts and values. A fixture copied from a real run, record or message is not synthetic, even when edited.
- [ ] Facts quoted from public sources, with the public URL and the date read.
- [ ] Documentation written for a public reader.

For each file in the diff, the reviewer can say which item above it falls under.

## 2. What is never published

None of these may appear in a file, a commit (message, author, committer), a branch name, a pull request or issue, a comment, a label, a log line or an artifact:

- [ ] Credentials of any kind: tokens, keys, passwords, cookies, signed URLs, connection strings, key-store item names that identify a credential.
- [ ] Names of private repositories, private hosts, private paths or private URLs, and links into them (including issue and pull request numbers of private repositories).
- [ ] Names of people, accounts, seats, agents, machines or sessions other than this organisation's public automation account and its public maintainers team.
- [ ] Vendor, provider or tooling choices that are not already public in this organisation, and anything about how the work behind these repositories is organised or run.
- [ ] Customer, tenant or personal data, real or "anonymised", and real identifiers of any record.
- [ ] Costs, budgets, quotas, usage figures and capacity numbers that are not published by their owner.
- [ ] Session ids, run ids or log excerpts from private systems.

When in doubt, leave it out and ask a maintainer.

## 3. Checks at the head

- [ ] **Diff:** every changed file read, binary files included (an image or archive can carry text the scan cannot see).
- [ ] **History:** every commit on the branch, not only the final diff. Each commit becomes public on merge, and a later commit that removes something does not unpublish it.
- [ ] **Metadata:** commit messages, author and committer names and emails, trailers (no co-author trailers naming private accounts), and the branch name.
- [ ] **Conversation:** the pull request title and body, every comment and review body, and the linked issue.
- [ ] **Fixtures:** each one is synthetic (section 1); hosts use reserved names such as `example.com`, `example.invalid` or `ex.test`.
- [ ] **Guards:** `leak-scan` and `denylist` are green at this head. A green guard does not replace the read above.
- [ ] **Licence:** new material can be published under the licence the repository declares, and quoted material carries its source.

## 4. Public CI never receives private material

- [ ] A workflow reads only this repository, other public repositories at a pinned commit, and public downloads pinned by checksum.
- [ ] No secret other than the token GitHub issues to the run is passed to a job, and none is needed by a public check.
- [ ] No step checks out, fetches from or posts to a private repository or host.
- [ ] Nothing a job prints or uploads (logs, artifacts, caches, job summaries) contains material from section 2. Assume every log is public.

## 5. If something private is published

1. Treat it as published, whatever happens next. Deleting a comment or force-pushing does not unpublish it.
2. Revoke and replace any credential at once, before anything else.
3. Tell the maintainers through a private channel. Do not describe the material in a public issue.
4. Removing it from history needs a maintainer's decision, because it rewrites published commits.
5. Add a counter-example or a denylist entry so the guard catches the same kind of material next time, and note the gap in this checklist if the review missed it.

## Receipt

The reviewer's receipt names the head it read and says the checklist was applied:

```
ACCEPT
Head: <40-hex head>
Publication review: sections 1-4 checked at this head.
```
