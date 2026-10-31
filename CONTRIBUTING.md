# Contributing

Thank you for helping. Corrections matter most: if a fact is wrong, open a **Correction** issue with a link to the page that shows the right one and the exact sentence that supports it.

## Pull requests

- One change per pull request, kept small.
- Every fact carries its source: a link to the page, the time it was fetched, and a short quote copied exactly from the page. A fact that cannot be confirmed is marked `unknown`, never guessed.
- Never commit secrets, tokens, personal data or the names of private projects. Every pull request is scanned and fails on a finding.
- A pull request merges only when every required check has passed.

## Who merges what

- A pull request from the project's automation account that changes only fact files and the generated graph index merges on its own once every required check has passed.
- Every other pull request needs an approving review from a maintainer, the code owner of everything else.
- The maintainers team has one member, and nobody can approve their own pull request. So changes are authored by the automation account and approved by the maintainer; the maintainer does not author pull requests.
- Pull requests from outside contributors are welcome. A maintainer reviews and merges them.

## The facts graph

Each fact is one file in `ghgraph/graph/nodes/`, named after its id, and must match `ghgraph/schema.json`. `ghgraph/INDEX.md` is generated, never edited by hand. After adding or changing a fact, regenerate it and check the graph:

```sh
et network index --graph ghgraph
et network check --graph ghgraph
```

## Security

Do not report security problems in issues or pull requests. See [SECURITY.md](SECURITY.md).
