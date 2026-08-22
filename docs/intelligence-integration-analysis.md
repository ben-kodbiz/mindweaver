# Intelligence Layer — Integration Analysis (Stage 0)

## Existing modules (integration points)

| Capability | Module | Reuse via |
|---|---|---|
| OCR | `mindweaver/ocr/*` (RapidOCR provider, pipeline, cache) | tool `get_page` metadata; escalation trigger reads page confidence |
| RAG / retrieval | `mindweaver/search/service.py::search` | tool `search_document` |
| Chunks | `mindweaver/chunking/service.py::list_chunks` | tools `get_chunk`, evidence validation |
| Graph | `mindweaver/graph/service.py::get_graph` | tools `get_graph_node` / `get_graph_neighbors`; expansion target |
| Personal edits | `mindweavever/graph/user_edits.py` (actual: `mindweaver/graph/user_edits.py`) | proposal acceptance inserts personal nodes/connections |
| LLM abstraction | `mindweaver/llm/*` (chat-only) | untouched; intelligence layer has its own gateway with vision+tools |
| Config | `mindweaver/config.py::Settings` | new additive field `intelligence` |
| API | FastAPI routers under `/api/v1` | new namespaced router `/api/v1/intelligence/*` |
| Tests | pytest at repo root (`tests/unit`, `tests/integration`) | new intelligence tests follow same layout |

## Safe integration points
- `config.py`: add one additive `intelligence` field.
- `main.py`: register one new router.
- `models/__init__.py`: export one new additive table.
- Frontend `GraphView.svelte`: feature-detect via `/intelligence/status`.

## Files that MUST NOT be modified
- Existing RAG pipeline (`search/service.py` internals), OCR providers, chat RAG,
  graph extraction/validation, user-edit semantics, existing route contracts.

## Small hooks allowed
- None required beyond router registration + settings field.
