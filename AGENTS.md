# AGENTS.md

MindWeaver is a local-first knowledge app: import PDFs -> extract structure -> index -> RAG + knowledge graph -> interactive mind map. It is built strictly by following two user-authored documents:

- `todoagent.md` — the build plan: 22 sequential stages (audio + mobile stages were dropped; this is a desktop-only app). **This is the task source of truth.** Read the current stage before writing code.
- `architect.md` — architecture reference (provenance, provider abstraction, mind-map-as-view).

## Non-negotiables

- Work stage-by-stage in order (1 -> 22). Never skip ahead to a fancy AI feature while the document pipeline is unreliable.
- **After completing a stage (all tests pass + acceptance verified), STOP and ask the user to review before starting the next stage.**
- Priority: source extraction > source traceability > retrieval > grounded answers > graph > mind map > UI > desktop polish. Never reverse it.
- Keep LLM / embedding / reranker / OCR / TTS behind provider interfaces. No hardcoded provider or model names in business logic.
- Never mark a stage complete merely because code compiles — run the tests.
- The mind map is a view; the knowledge graph is the data. Never discard source/page references during processing.

## Layout

- `services/api` — FastAPI backend (Python, managed with **uv**). Entrypoint `src/mindweaver/main.py:create_app`.
- `apps/web` — Svelte + Vite + TypeScript frontend (npm workspace `@mindweaver/web`).
- `packages/`, `models/`, `docker/` — reserved; not yet populated.
- `tests/` — pytest suite at repo root (`unit/`, `integration/`, `e2e/`, `fixtures/`, `benchmarks/`).
- `services/api/src/mindweaver/extraction/` — document processors. `DocumentProcessor` interface + `get_processor(settings)` registry; outputs the project-owned `CanonicalDocument` (see `document_model.py`) saved to derived storage as `canonical.json`. `pypdf` (default, no extra deps) and `docling` (optional `[docling]` extra — heavy torch stack) backends.
- `services/api/src/mindweaver/ocr/` — `OCRProvider` interface + `RapidOCRProvider` (torch engine, optional `[ocr]` extra) + `OCRPipeline` (render via pypdfium2, cache in `ocr_cache` table). The `hybrid` document backend routes scanned pages to OCR; `pypdf` marks them `OCR_REQUIRED`.
- `services/api/src/mindweaver/chunking/` — structural chunker: groups blocks by section, prepends contextual headers, splits only oversized sections (never mid-paragraph/table/caption). Chunks stored in the `chunks` table; `CHUNKING__MAX_CHARS` controls size.
- `services/api/src/mindweaver/search/` — retrieval: FTS5 (`chunks_fts`), `EmbeddingProvider` (default `local` feature-hash BOW, optional `sentence-transformers` via `[embeddings]` extra), vector store (`chunk_embeddings`, brute-force cosine), local reranker (`RERANKER__ENABLED`), hybrid `search()`, and the `evaluation.py` suite (recall@K/MRR against the search-book fixture). Indexing runs inside `run_chunking`.
- `services/api/src/mindweaver/llm/` — `LLMProvider` interface; `OpenAICompatibleProvider` covers ollama/llama.cpp/LM Studio (config via `LLM__BASE_URL`/`LLM__MODEL`); `StubLLMProvider` (provider `stub`) for offline/tests.
- `services/api/src/mindweaver/chat/` — citation-grounded RAG: `answer_question` (retrieve → evidence prompt → structured JSON with `grounding` ∈ supported_by_source|inference|not_found → citations), `chat_sessions`/`chat_messages`/`chat_citations` tables, `/api/v1/chat/*` routes.
- `services/api/src/mindweaver/graph/` — knowledge graph: `extractor.py` (LLM-driven concept/relation extraction with validation, dedup, source attribution), `service.py` (`graph_nodes`/`graph_edges`/`node_sources`/`graph_versions` tables, versioned replace), `/api/v1/documents/{id}/graph`. Every edge is traceable to source chunks or marked `is_inference`.
- `services/api/src/mindweaver/mindmap/` — shallow bounded mind map view over the graph (chapters → top concepts by degree), invisible source metadata per node, layout preferences (`mindmap_preferences` table). Node actions in `mindmap/actions.py` + `graph/expand.py` (expand/explain/evidence/related/ask under `/api/v1/documents/{id}/mindmap/nodes/{node_id}/...`; expansion is atomic and idempotent). Web UI in `apps/web/src/components/MindMap.svelte` (zoom/pan/collapse/search/focus/reset).
- Source sync: `GET /documents/{id}/file` (original PDF), `GET /documents/{id}/chunks/{chunk_id}/source` (page + optional bbox regions), `POST /documents/{id}/mindmap/selection` (PDF selection → concept candidates, `confirm` merges into graph). PDF viewer is `apps/web/src/components/PdfViewer.svelte` (pdf.js; jump-to-page, highlight, text selection → add to mind map), wired into a split-screen layout in `MindMap.svelte`.
- Graph exploration: `GET /documents/{id}/graph` accepts `node_types`, `relations`, `focus_node_id` (1-hop neighbourhood) and `limit` (degree-ranked cap). Cytoscape view in `apps/web/src/components/GraphView.svelte`; MindMap.svelte header toggles Mind Map ↔ Graph.
- Personal layer: `graph/user_edits.py` (add personal node, notes/colour/tags/flags on any node, connections, merge, undo/redo via full snapshots in `graph_history`, export at `/graph/export`). Regeneration (`replace_graph`) preserves personal nodes + annotations; history is re-baselined on extraction/expansion.
- Notebooks: `notebooks.py` — workspaces grouping documents (`/api/v1/notebooks/*`). Cross-document search with source labels (`search(document_ids=..., with_labels=True)`), merged cross-document graph (stable node ids unify concepts; per-node document list), and `/compare` (common concepts, per-doc uniques, conflicts where one doc's relation meets another doc's `contradicts` over the same node pair).

## Commands (from repo root — always use the Makefile targets)

```sh
make install        # uv sync --project services/api && npm install
make test           # full pytest suite
make test-unit      # pytest tests/unit
make test-integration
make lint           # ruff check + eslint
make typecheck      # mypy + svelte-check
make check          # test + lint + typecheck + format-check
make dev-api        # uvicorn on :8000
make dev-web        # vite on :5180 (proxies /api -> :8000)
```

## Config & API conventions

- pydantic-settings; env prefix `MINDWEAVER_`, nested separator `__` (e.g. `MINDWEAVER_LLM__BASE_URL`). See `.env.example`. `.env` is never committed (pre-commit hook blocks it).
- All endpoints live under `/api/v1` (API versioning strategy). Error bodies are `{"error": {"code", "message", "request_id"}}`; every response carries `X-Request-ID`.
- `DOCUMENT_PROCESSOR__BACKEND=pypdf|hybrid|docling`. `pypdf` uses PDF bookmarks for section hierarchy; scanned pages set `OCR_REQUIRED`. `hybrid` routes scanned pages through `OCR__PROVIDER` (rapidocr) with results cached in `ocr_cache`. `docling` needs `uv sync --project services/api --extra docling` and infers heading levels from font-size tiers.

## Gotchas

- Root is a virtual uv workspace (no Python at root). Use `uv run --project services/api <cmd>` or the Makefile — plain `uv run`/`pytest` at root won't work.
- SQLite needs parent directories to exist before the file is opened; `init_database` in `services/api/src/mindweaver/database.py` handles this — keep it that way.
- Logging (`logging_conf.py`) redacts secrets registered via `register_secret` (the configured `SECURITY__SECRET_KEY`). Don't bypass it.
- `create_app(settings=None)` takes an explicit `Settings`; tests build their own tmp-dir SQLite settings instead of using the module-level `app` (which uses `./data`).
- Only `services/api` has a uv dev group (pytest/ruff/mypy/httpx); when adding Python deps for future stages, put them there.
