# Changelog

All notable changes to MindWeaver are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] — 2026-08-22

First complete desktop release covering milestones M0–M7.

### Added

#### Document pipeline (Stages 1–5)
- Monorepo: FastAPI backend (`services/api`, uv) + Svelte 5 / Vite frontend (`apps/web`)
- Configuration system with validation and hardware profiles (low/medium/high)
- Structured JSON logging with secret redaction; request IDs on every response
- PDF upload with streaming SHA-256 deduplication, size limits, original storage
- Document extraction via pypdf (bookmarks → section tree) or Docling (layout
  intelligence, tables, figures, bboxes) behind a common processor interface
- OCR pipeline for scanned pages: RapidOCR (torch engine), per-page routing,
  confidence flags, result caching, `reprocess-ocr` endpoint
- Structural chunking: section-aware grouping, contextual headers, oversized
  section splitting, caption/table atomicity

#### Retrieval & RAG (Stages 6–7)
- Hybrid search: SQLite FTS5 keyword + vector embeddings (local hashing or
  sentence-transformers) with weighted merge, reranking, relevance threshold
- Evaluation suite: recall@K / MRR over a fixed question set
- Citation-grounded chat: evidence prompt, `grounding`
  (supported_by_source/inference/not_found), "I don't know" behaviour,
  session/message/citation persistence

#### Knowledge layer (Stages 8–10)
- Knowledge graph extraction (LLM-driven) with schema validation,
  dedup/merge, source-chunk attribution, inference marking, versioned replace
- Bounded mind map view (Document → chapters → key concepts by degree)
- Node actions: expand (atomic/idempotent graph growth), explain, evidence,
  related, ask — all with provenance

#### Views & personal layer (Stages 11–13)
- pdf.js viewer: jump-to-page, bbox highlights, text selection → concept
  candidates → confirmed merge into the mind map; split-screen layout
- Cytoscape graph exploration: type/relation filters, search, neighbourhood
  focus, degree-capped rendering
- Personal knowledge: user nodes/connections survive regeneration; notes,
  colour, tags, important/bookmark flags; full-snapshot undo/redo; JSON export

#### Multi-document & learning (Stage 14–15)
- Notebooks: group documents, cross-document retrieval with source labels,
  merged cross-document graph, compare (common concepts, uniques, conflicts)
- Learning outputs: summaries, key concepts, Q&A, flashcards, quiz, study
  guide — every item carries concept/chunk/page provenance

#### Platform (Stages 16–22)
- Model gateway: single access point + status endpoint; contract tests for
  LLM/embedding/reranker/document-processor interfaces
- Job system: lifecycle tracking, progress reporting, cooperative
  cancellation, bounded retries, checkpoints, stale-job recovery
- Security hardening: path-traversal-safe storage keys, upload size limits,
  secret redaction in logs, full data-export endpoint
- Desktop packaging scaffold (Tauri shell, sidecar backend)

### Known limitations
- Upload processing runs inline (job queue is wired but the worker loop is
  still synchronous); cancellation applies at stage boundaries
- Docling/OCR/embeddings extras require separate install steps
