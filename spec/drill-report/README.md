# drill-report

The evidence that a synthetic incident was injected at a known instant and detected, with the time to detect measured rather than asserted. It carries no detector, no notification channel and no consumer's targets or numbers.

## Two checks

**The schema** (`schema.json`, JSON Schema 2020-12) holds the shape: required fields, types, bounds, UTC timestamps on a real calendar date, a 40-hex `commit`, and that `notified: true` brings `notifiedAt` and `notifiedBy`. `check.json` runs it as `schema-check` targets: `examples/` must pass, `counter-examples/` must each fail, and `semantic-counter-examples/` must pass.

**The semantic checker** (`tooling/practice_ci/drill_check.py`) holds what JSON Schema cannot say. A schema validates one value at a time and has no subtraction, no multiplication and no comparison between two fields, so it cannot tell that `mttdMs` is not `detectedAt - injectedAt`. Run it on any report:

```
python3 -m tooling.practice_ci.drill_check report.json
```

It exits 0 when every report is consistent, 1 when one contradicts itself (one line per finding), and 2 on a usage or read error. A report is accepted only when both checks pass. `semantic-counter-examples/` are the reports the schema accepts and the checker refuses, each for one named reason.

## Fields

| Field | Meaning |
| --- | --- |
| `target` | What the incident was injected into. Opaque. |
| `injectedAt`, `detectedAt` | When the incident began and when the detector first reported it. UTC with `Z`. |
| `mttdMs` | `detectedAt - injectedAt` in whole milliseconds, exactly (sub-millisecond differences are a finding). |
| `probeIntervalMs`, `threshold` | The probe interval of the drill and the consecutive failed probes before the detector reports. |
| `productionIntervalMs` | The probe interval the projection is made for. |
| `scaledMttdMs` | `mttdMs * productionIntervalMs / probeIntervalMs`, rounded down. |
| `objectiveMs` | The time to detect the objective allows. |
| `withinObjective` | `scaledMttdMs <= objectiveMs`. Equal is within. |
| `notifiedAt`, `notifiedBy` | Optional. When someone or something was told, and what told them. |
| `notified` | True exactly when both `notifiedAt` and `notifiedBy` are present, so a detection-only drill never reads as a notification. |
| `commit`, `command` | What ran the drill, so a reader can reproduce it. |

## What the checker enforces

- `mttdMs` equals `detectedAt - injectedAt` to the nanosecond, across leap days; `detectedAt` is not before `injectedAt`.
- `scaledMttdMs` is the projection above.
- `withinObjective` is the verdict of `scaledMttdMs` against `objectiveMs`.
- `notified` agrees with `notifiedAt` and `notifiedBy`, and `notifiedAt` is not before `detectedAt`.
- A field of the wrong type or an unreadable timestamp is a finding, never a crash.
