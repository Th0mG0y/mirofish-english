# Contributing

Thanks for your interest in contributing.

## Before You Start

- Read [`README.md`](./README.md) and [`SETUP.md`](./SETUP.md).
- Open an issue first for large changes, refactors, or feature proposals.
- Keep changes focused and easy to review.

## Branches

- Use `main` for the stable public branch.
- Use `develop` for ongoing development work.
- Open pull requests against `develop` unless the change is an urgent docs-only or hotfix update.

## Local Setup

From the repo root:

```powershell
npm run setup:all
```

If you want to mirror the one-click scripts exactly, or you hit graph or ontology import errors during local work, also run:

```powershell
cd backend
uv pip install "anthropic>=0.40.0" "graphiti-core==0.28.2" "neo4j==5.26.0"
cd ..
```

Then run:

```powershell
npm run dev
```

## Contribution Guidelines

- Do not commit secrets, `.env` files, tokens, credentials, or local databases.
- Keep `.env` examples and docs in sync with code changes.
- Keep `README.md`, `SETUP.md`, and provider/setup notes in sync when workflow or report behavior changes.
- Preserve AGPL notices, attribution, and license files.
- Prefer small pull requests over large mixed changes.
- Update setup or README content when developer workflow changes.
- If you change the report pipeline, keep the report intent, evidence brief, claim ledger, quality gates, and run-trace behavior documented.

## Suggested Checks

If your change touches the backend:

```powershell
cd backend
uv run pytest tests -q
cd ..
```

If your change touches report generation, make sure the report reliability tests still pass, especially the intent, schema, search, evidence, claim-ledger, and quantitative-validation coverage.

If your change affects setup or provider behavior, verify the relevant `.env` example still matches the code.

## Pull Requests

Please include:

- what changed
- why it changed
- how you tested it
- any setup, migration, or provider impacts

If your PR changes public behavior, docs, or environment variables, update the related markdown files in the same PR.
