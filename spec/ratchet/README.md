# ratchet

A shrink-only baseline lets a check keep today's findings and refuse new ones. `schema.json` is the file format; `reconcile.sh` is the reference reconciler (bash and jq), and `selftest/unit/ratchet/` holds its fixtures, so a check in any language can be held to the same results.

Reconciling a run's found keys against the baseline gives each key one result:

| Result | When | Verdict |
| --- | --- | --- |
| `fresh` | found, not listed | fail |
| `explained` | found, listed with a reason and an owner | pass |
| `unexplained` | listed with an empty or missing reason or owner, found or not | fail |
| `paidOff` | listed with a reason, no longer found | fail until the entry is removed |

A baseline that is missing, unreadable or malformed, or that lists a key twice, is a failure, never an empty list.

`bash spec/ratchet/reconcile.sh --write <baseline> < found-keys` re-records a measurement: it adds found keys that are not listed, with an empty reason and owner, so they still fail; it drops entries no longer found; it never fills a reason, so it cannot clear a judgement.
