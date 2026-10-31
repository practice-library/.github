# Changelog

One line per change to the surface other repositories depend on. A rename or removal is breaking; an added optional input is not.

## Unreleased

- gate.yml: removed the input `required`; the gate now reads the jobs from the calling repository's `.github/required-checks.json` (`{"jobs": [...]}`), which must equal its needs and include `leak-scan`. Breaking.
- discover.yml: new reusable workflow with the input `check`, emitting the output `targets`.
- schema-check.yml: new optional input `expect` (`pass` or `fail`).
- schema-check.yml: new optional input `each` (`true` validates every file on its own).
- check.json: may hold a list of targets; optional keys `expect` and `each`.
- spec/node/schema.json: new shared fact-node schema, `$id` https://github.com/practice-library/.github/spec/node/schema.json; schema-check always resolves it.
- leak-scan.yml and schema-check.yml: the self-test inputs are `_selftest-fixture` and `_selftest-expect` (leak-scan only); they are not part of the API.
- automerge.yml: removed the input `allow-paths`; the allowlist is read from `.github/automerge-paths.json` (`{"paths": [...]}`) on the base commit, none when absent. Breaking.
- automerge.yml: the input `trusted-authors` is required (no default).
- gate.yml: fails when CODEOWNERS owns a path in `.github/automerge-paths.json`.
