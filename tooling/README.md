# tooling

Stdlib-only Python (3.12) for the CI checks. Tests: `python3 -m unittest discover -s tooling/tests -t .`

| module | what it does |
| --- | --- |
| `practice_ci/config.py` | the one reader of `policy/constants.json` |
| `practice_ci/compatibility.py` | schema compatibility classifier: `proven-safe`, `requires-review` or `invalid`, with a reason (path and rule) per finding; unknown constructs mean review. `classify_check` does the same for a `check.json` profile (any change needs review). The `schema-loosening` guard fragment runs its command line. |
| `practice_ci/reasons.py` | expected-reason assertions: each counter-example in a spec's `reasons.json` names the keyword and instance location it must fail at |
| `practice_ci/guards/` | schema-check's guards mode (apply each mutant, require a red fixture), runnable locally through `scripts/guards.sh` |

Tests: `test_compatibility_cases.py` runs every shell unit case of the guard through the classifier;
`test_compatibility_rules.py` states the rules (including #72's `allOf` cases);
`test_compatibility_mutants.py` applies `mutants/compatibility.json` to the classifier and requires a red test for each;
`test_spec_fixtures.py` checks the spec fixtures, their reasons and their guard mutants with `minischema.py`,
a small evaluator that stands in for the pinned validator binary (CI runs the binary; the evaluator is test support only).
