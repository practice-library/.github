# Changelog

One line per change to the surface other repositories depend on. A rename or removal is breaking; an added optional input is not.

## v1.1.0

Additive; the breaking surface is unchanged (workflow file names, input and output names, the `gate / gate` context, the keys of `check.json` and the formats of the `.github` files stay as in v1.0.0). A repository pinned to v1.0.0 is unaffected.

- spec/node/schema.json: three new edge kinds, `hasRelease` (product to release), `introducedIn` (capability to release) and `removedIn` (capability to release); an edge kind outside the list still fails. schema-check.yml carries the updated copy of the envelope; its inputs and outputs do not change.

## v1.0.0

The first release. Its breaking surface, which a later change may alter only in a major release:

- workflow file names: `leak-scan.yml`, `schema-check.yml`, `discover.yml`, `gate.yml`, `automerge.yml`;
- their input and output names: leak-scan `config`; schema-check `schema`, `instances`, `expect`, `each`; discover `check` and the output `targets`; gate `needs`; automerge `trusted-authors`, `merge-method`;
- the required check name `gate / gate`;
- the keys of `check.json`: `schema`, `instances`, and the optional `expect` and `each`, as one object or a list;
- the format of `.github/required-checks.json`: `{"jobs": [...]}`, equal to the gate's needs and including `leak-scan`;
- the format of `.github/automerge-paths.json`: `{"paths": [...]}`, read on the base commit, none when absent.

Changes in this release:

- gate.yml: removed the input `required`; the gate now reads the jobs from the calling repository's `.github/required-checks.json` (`{"jobs": [...]}`), which must equal its needs and include `leak-scan`. Breaking.
- discover.yml: new reusable workflow with the input `check`, emitting the output `targets`.
- schema-check.yml: new optional input `expect` (`pass` or `fail`).
- schema-check.yml: new optional input `each` (`true` validates every file on its own).
- check.json: may hold a list of targets; optional keys `expect` and `each`.
- spec/node/schema.json: new shared fact-node schema, `$id` https://github.com/practice-library/.github/spec/node/schema.json; schema-check always resolves it.
- spec/node/schema.json: the node envelope is checked in CI by JSON Schema only; conformance with `et network check` is verified privately, and no workflow fetches or pins `et`.
- leak-scan.yml and schema-check.yml: the self-test inputs are `_selftest-fixture` and `_selftest-expect` (leak-scan only); they are not part of the API.
- automerge.yml: removed the input `allow-paths`; the allowlist is read from `.github/automerge-paths.json` (`{"paths": [...]}`) on the base commit, none when absent. Breaking.
- automerge.yml: the input `trusted-authors` is required (no default).
- rulesets/tags.json: release tags matching `v*` cannot be deleted or moved.
- gate.yml: fails when CODEOWNERS owns a path in `.github/automerge-paths.json`.
