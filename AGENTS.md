# Guide for automated contributors

This repository holds the organisation's shared policy, reusable workflows and CI tooling. Humans and
automated agents follow the same rules; this file is the short version.

## Module map

| Path | What it is | Edit by hand? |
| --- | --- | --- |
| `policy/constants.json` | Every limit, label, URL, pin, timeout and name. The single source of policy. | yes |
| `policy/constants.schema.json` | The schema `constants.json` must satisfy. Add a field here when you add one there. | yes |
| `templates/` | Sources of the generated files. `templates/fragments/` holds shell libraries (`*.sh`) and YAML snippets (`*.yml`) that templates include with `#@include <file>`. | yes |
| `spec/` | Schemas and examples shipped to consumers. | yes |
| `tooling/practice_ci/` | The CI tooling, Python 3.12, standard library only. `config.py` is the only reader of `constants.json`; `result.py` is the one result shape; `__main__.py` dispatches subcommands; each other module is one command. | yes |
| `tooling/tests/` | `unittest` tests of the tooling and of the shell inside workflow steps. | yes |
| `scripts/practice-ci` | Launcher: `python3 -I scripts/practice-ci <command> [args]`. Isolated mode, only `tooling/` on `sys.path`, never caller code. | yes |
| `scripts/*.sh` | `render.sh`, `unit.sh`, `mutants.sh`, `discover.sh` and friends. | yes |
| `selftest/` | Fixtures (`fixtures/`), shell unit cases (`unit/<lib>/*.json`) and mutants (`mutants/*.json`). | yes |

## Source versus generated

Generated, never edited by hand (each starts with a "Generated from ..." header, or is JSON rendered from a template):
`.github/workflows/*`, `README.md`, `rulesets/*`, `consumer/*`, `docs/new-repo-checklist.md`.
Their sources are under `templates/`. After changing a template, a fragment or `policy/constants.json`:

```sh
scripts/render.sh          # rewrite the generated files
scripts/render.sh --check  # what CI runs: fails if a generated file differs from its render
```

## Test commands

```sh
python3 -m unittest discover -s tooling/tests -t .   # tooling, step shell, literals lint, mutation runner
bash scripts/unit.sh [<lib> ...]                      # shell unit cases, loaded from templates/fragments/*.sh
bash scripts/mutants.sh [<name> ...]                  # every mutant must turn a behavioural test red
python3 -I scripts/practice-ci lint-literals          # the literals rule below
python3 -I scripts/practice-ci check-steps <file>...  # the shell in workflow steps parses
```

`unit.sh` and `mutants.sh` need `jq`; the `pin-check` cases need `yq` (CI installs it).

A mutant counts as killed only by a behavioural failure: a mutated file that does not parse (bash, a jq
program, a step) is an error, not a kill. Mutant files are arrays (a library under `templates/fragments`)
or `{"target", "tests", "mutants"}` objects (the shell inside a workflow or fragment's steps, or a Python module when `target` ends in `.py`). An object may hold `"unit": "<lib>"` instead of `"tests"`: the mutant is then judged by that library's unit cases (the shell fragments that call the Python guards).

## The literals rule

A limit, timeout, retry count, label name, URL or pin is written once, in `policy/constants.json` (and its
schema), and read with `config.get(...)` in Python or a `@@a.b.c@@` placeholder in a template. Never type it
in place. `lint-literals` enforces this where policy lives: timeout, retry, label and URL arguments and
policy-named comparisons in `tooling/`, and timeouts, retries, labels, URLs and action pins in workflow
templates and fragments. The designated places are listed under `tooling.lint` in the constants.

Also: no duplication (one source per fact; do not keep a second copy of a library or a list), and close an
issue by fixing the mechanism, with a test that fails before the change and passes after.

## Public hygiene

This repository is public.

- Commit messages and pull request text: plain description of the change. No tool or assistant
  attribution trailers.
- No personal names, internal system names or private repository names, anywhere.
- Do not state or imply which vendors anyone uses.
- No secrets, tokens or credentials; the leak scan and the denylist guard run on every change.
- Do not merge your own pull request, and do not approve it.
