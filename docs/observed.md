# Observed on this repository's own runs

Three observations from the canary workflow (`.github/workflows/canary.yml`) in this repository. They were measured, not read from documentation, so they have no home in the fact graphs. Source: [run 41195771306](https://github.com/practice-library/.github/actions/runs/41195771306), read 2026-10-31T12:15:00Z.

- **Concurrency: 5 jobs at a time, against a documented 20.** The 20-shard probe matrix never ran more than 5 jobs at once, judged from the job start and end times in the run's jobs list, on two canary runs. The documented limit for standard GitHub-hosted runners on the Free plan is 20 concurrent jobs ([Actions limits](https://docs.github.com/en/actions/reference/limits)). Run page: "Matrix: probe 20 jobs completed".
- **The organisation's app can start a workflow.** The run was started by `workflow_dispatch` as `practice-library[bot]`. Run page: "Manually triggered October 31, 2026 11:10 practice-library[bot]".
- **Public-repository jobs start on the new organisation.** All 20 jobs of the probe matrix ran on a public repository of a Free organisation. Run page: "Matrix: probe 20 jobs completed".
