# Leak scan

Every push to a public practice-library repository is scanned by [gitleaks](https://github.com/gitleaks/gitleaks) first. The scan has two layers:

| Layer | File | Where it lives |
| --- | --- | --- |
| Secrets | `.gitleaks.toml` (gitleaks' default rules) | This repository, public |
| Names that must not be published | a filled copy of `deny.example.toml` | Outside every repository, on the publishing machine only |

The private list extends the public config, so one command runs both layers. The push step runs it and refuses to push on any finding:

```sh
gitleaks git  --config "$DENY_LIST" --redact --exit-code 1 .   # history about to be pushed
gitleaks dir  --config "$DENY_LIST" --redact --exit-code 1 .   # working tree, including untracked files
```

`--redact` keeps any match out of the logs. GitHub's secret scanning with push protection runs as well; this scan is in addition to it, not a replacement.

## What is measured

The push step records, for each push: whether the scan ran, how many findings it reported, and how many seconds it took. Targets: the scan runs on 100% of pushes, and 0 leaks are found after a push.
