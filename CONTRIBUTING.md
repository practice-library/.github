# Contributing

Thank you for helping. Corrections matter most: if a fact is wrong, open a **Correction** issue with a link to the page that shows the right one and the exact sentence that supports it.

## Pull requests

- One change per pull request, kept small.
- Every fact carries its source: a link to the page, the time it was fetched, and a short quote copied exactly from the page. A fact that cannot be confirmed is marked `unknown`, never guessed.
- Never commit secrets, tokens, personal data or the names of private projects. Every pull request is scanned and fails on a finding.
- A pull request merges only when every required check has passed.

## Ready for review

Before asking for a review, check your own change. Most rework comes from gaps the author can find alone.

1. Break each check you added or changed, in a scratch copy: flip a comparison, delete the check, or make it always true. A named test must fail each time. A check whose removal leaves every test passing is not done.
2. Test every new condition at its boundary with literal values: one under, exactly at, one over. Do not reuse the constant the code uses.
3. Test unhappy and hostile input, not only the happy path: missing fields, unreadable or empty input, a duplicate, trailing whitespace or a trailing newline, input that is too long, something edited or reused. A failed read must end as "unreadable", never as a pass.
4. Hold every limit you write against the schema or contract it feeds: length, pattern, and anchors (match the whole value, not a part of it).
5. Run the repository's own checks, schema fixtures and unit cases, and say in the pull request what was measured, with the numbers, and what was not.
6. Keep to one concern per pull request, and leave deferred work for its own pull request.

## Who merges what

- A pull request from the project's automation account that changes only fact files and the generated graph index merges on its own once every required check has passed.
- Every other pull request needs an approving review from a maintainer, the code owner of everything else.
- The maintainers team has one member, and nobody can approve their own pull request. So changes are authored by the automation account and approved by the maintainer; the maintainer does not author pull requests.
- Pull requests from outside contributors are welcome. A maintainer reviews and merges them.

## Facts

The fact graphs live in [practice-library/graphs](https://github.com/practice-library/graphs); the GitHub facts are under `vendors/github/`. Corrections to a fact go there. This repository holds the organisation defaults and the shared node envelope (`spec/node/schema.json`).

## Security

Do not report security problems in issues or pull requests. See [SECURITY.md](SECURITY.md).
