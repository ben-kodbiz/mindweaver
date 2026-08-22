# MindWeaver

Local-first, open-source application for turning documents into an explorable knowledge space: import PDFs, extract text/structure/tables, OCR scanned pages, build a searchable knowledge base, chat with citation-grounded RAG, and explore knowledge through an interactive mind map backed by a persistent knowledge graph.

## Docs

- `todoagent.md` — the build plan: 25 sequential stages (task source of truth).
- `architect.md` — system architecture reference.
- `AGENTS.md` — workflow rules for AI agents working in this repo.

## Layout

```text
apps/web          Svelte + Vite + TypeScript frontend (npm workspace)
services/api      FastAPI backend (Python, managed with uv)
packages/         shared packages (reserved)
tests/            pytest suite (unit / integration / e2e / benchmarks / fixtures)
docs/ scripts/    project docs and developer scripts
```

## Quick start

```sh
make install       # uv sync + npm install
make dev-api       # backend on http://localhost:8000
make dev-web       # frontend on http://localhost:5173 (proxies /api to :8000)
```

## Checks

```sh
make test          # pytest suite
make lint          # ruff + eslint
make typecheck     # mypy + svelte-check
make check         # test + lint + typecheck + format check
```

Configuration is documented in `.env.example` (prefix `MINDWEAVER_`, nested keys use `__`).

## Status

Stage 1 (Foundation) complete. See `todoagent.md` for the stage list.
