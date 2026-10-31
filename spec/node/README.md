# node

`spec/node/schema.json` is the normative contract for a fact node. Any other description of a node's shape, whether a README, a domain schema that `$ref`s it, or a consumer's checker, is subordinate to it. When they disagree, the schema is right and the other one is the bug.

It is rendered from `templates/spec/node/schema.json`. Edit the template, then run `scripts/render.sh`.

## Its `$id`

`https://github.com/practice-library/.github/spec/node/schema.json` is stable. A consumer resolves its reference by that `$id` and pins the file by tag or commit, never by branch (`schema-check` with `resolve` and `resolve-ids` does both). The `$id` does not change within a major release.

## Changes

Changes are additive within a major release: a new optional field, a new enum value, a rule that refuses only what the documented contract already refused. Anything else is a new major tag, as CONTRIBUTING says for releases. Every change has a CHANGELOG line, and a change the schema-loosening guard flags needs the founder's approval label.

What each field means is in [spec/README.md](../README.md#node). The cases that must pass and fail are `selftest/fixtures/schema-node-*`; `guards.json` names a fixture that catches each guard.
