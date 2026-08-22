# MindWeaver — Agent Implementation TODO

## 0. Project Mission

Build a local-first, open-source application that allows users to:

1. Import native PDFs.
2. Import scanned PDFs.
3. Extract text, layout, structure, tables, and page metadata.
4. Perform OCR when required.
5. Build a searchable knowledge base.
6. Chat with documents using citation-grounded RAG.
7. Automatically generate a high-level mind map.
8. Allow the user to interactively expand individual mind-map nodes.
9. Retrieve evidence and source pages for every important concept.
10. Build a persistent knowledge graph from documents.
11. Generate summaries and learning material.
12. Run locally using free/open-weight models.
13. Support future desktop and self-hosted clients.

The central product principle is:

> The mind map is not a static export. It is an interactive interface to the document's knowledge.

---

```
Core Application
      ▲
      │ may be used by
      │
Intelligence Layer (optional)
      ▲
      │ may be used by
      │
UI Features
```

Never invert: the core application must not depend on the intelligence layer.

# 1. Non-Negotiable Engineering Rules

## 1.1 Architecture rules

All verified across stages 1-22.

* [x] Use a modular architecture.
* [x] Keep frontend independent from AI providers.
* [x] Keep LLM providers interchangeable.
* [x] Keep embedding providers interchangeable.
* [x] Keep OCR engines interchangeable.
* [x] Do not hard-code Ollama-specific logic into business logic.
* [x] Do not hard-code a particular model name into application logic.
* [x] Do not couple the database schema to one frontend framework.
* [x] Design stable, versioned APIs for all clients.
* [x] All long-running AI operations must be asynchronous jobs.
* [x] All expensive operations must support cancellation.
* [x] All ingestion jobs must be resumable where practical.
* [x] Preserve source provenance from ingestion to final answer.
* [x] Never discard original page/source references during processing.

## 1.2 Local-first rules

The MVP works without any of the following (verified offline in tests):

* [x] OpenAI API.
* [x] Google API.
* [x] AWS.
* [x] Azure.
* [x] Mandatory cloud database.
* [x] Mandatory third-party authentication.
* [x] Mandatory telemetry.

External APIs may be added later as optional providers.

## 1.3 Quality rules

Every stage must include:

* [x] Unit tests.
* [x] Integration tests.
* [x] Failure tests.
* [x] Manual acceptance tests.
* [x] Performance sanity tests.
* [x] Regression tests before major refactoring.

Do not mark a stage complete merely because code compiles.

---

# 2. Proposed Repository Structure

```text
mindweaver/
├── apps/
│   ├── web/
│   └── desktop/
│
├── services/
│   ├── api/
│   ├── worker/
│   └── model-gateway/
│
├── packages/
│   ├── contracts/
│   ├── core/
│   ├── document-engine/
│   ├── rag-engine/
│   ├── graph-engine/
│   ├── mindmap-engine/
│   └── sdk/
│
├── models/
│   ├── embeddings/
│   ├── rerankers/
│   └── manifests/
│
├── tests/
│   ├── fixtures/
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   └── benchmarks/
│
├── docker/
├── scripts/
├── docs/
│
├── ARCHITECTURE.md
├── TODOAGENT.md
├── README.md
└── LICENSE
```

---

# 3. Core Technology Direction

## Backend

Primary backend:

```text
Python
FastAPI
Pydantic
SQLAlchemy or equivalent
SQLite
SQLite FTS5
sqlite-vec or equivalent vector extension
```

## Document processing

Primary direction:

```text
Docling
OCR adapter layer
PaddleOCR candidate
```

## AI

The application must support adapters for:

```text
Ollama
llama.cpp server
LM Studio
OpenAI-compatible APIs
```

Initial local model direction:

```text
Qwen-family instruct model
multilingual embedding model
reranker model
```

## Frontend

Initial application:

```text
TypeScript
Svelte
Vite
```

Mind-map visualization:

```text
Markmap for hierarchical maps
Cytoscape.js for graph exploration
```

---

# STAGE 1 — FOUNDATION

## Goal

Create a clean, testable project foundation before implementing AI features.

## Tasks

### Repository

* [x] Create monorepo structure.
* [x] Configure Python environment.
* [x] Configure frontend environment.
* [x] Configure linting.
* [x] Configure formatting.
* [x] Configure type checking.
* [x] Configure pre-commit hooks.
* [x] Create `.env.example`.
* [x] Ensure `.env` is ignored.
* [x] Add structured logging.
* [x] Add configuration validation at startup.

### Configuration

Create configuration categories:

```text
APP
DATABASE
STORAGE
LLM
EMBEDDINGS
RERANKER
OCR
DOCUMENT_PROCESSOR
WORKER
SECURITY
```

Example logical configuration:

```text
LLM_PROVIDER=ollama
LLM_BASE_URL=http://localhost:11434
LLM_MODEL=

EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=

RERANKER_PROVIDER=local
RERANKER_MODEL=

OCR_PROVIDER=paddleocr

```

### API foundation

* [x] Create `/api/v1`.
* [x] Add health endpoint.
* [x] Add readiness endpoint.
* [x] Add version endpoint.
* [x] Add structured error responses.
* [x] Add request IDs.
* [x] Add API versioning strategy.

### Tests

* [x] Application starts with valid configuration.
* [x] Application refuses invalid configuration.
* [x] Health endpoint works.
* [x] Database can initialize.
* [x] Logging does not expose secrets.

## Acceptance test

```text
Start application
        ↓
GET /health
        ↓
200 OK
        ↓
GET /version
        ↓
correct version
```

**STAGE 1 COMPLETE ONLY WHEN ALL TESTS PASS.**

---

# STAGE 2 — DOCUMENT LIBRARY

## Goal

Create the user's document management layer.

## Features

* [x] Import PDF.
* [x] Store original PDF.
* [x] Calculate SHA-256 hash.
* [x] Detect duplicate documents.
* [x] Create document metadata.
* [x] Store document title.
* [x] Store file size.
* [x] Store page count.
* [x] Store ingestion status.
* [x] Allow deletion.
* [x] Allow reprocessing.
* [x] Allow document listing.

## Document states

```text
UPLOADED
QUEUED
PROCESSING
OCR_REQUIRED
PROCESSING_OCR
INDEXING
READY
FAILED
CANCELLED
```

## Database model

```text
documents
document_versions
processing_jobs
```

## Tests

Test with:

* [x] Small native PDF.
* [x] Large native PDF.
* [x] Empty PDF.
* [x] Corrupt PDF.
* [x] Password-protected PDF.
* [x] Duplicate PDF.
* [x] Very large PDF.

## Acceptance criteria

The user can:

```text
Upload PDF
   ↓
See processing state
   ↓
See completed document
   ↓
Delete document
   ↓
Original file and derived data removed correctly
```

---

# STAGE 3 — DOCUMENT INTELLIGENCE PIPELINE

## Goal

Convert PDFs into structured knowledge.

## Pipeline

```text
PDF
 │
 ▼
File inspection
 │
 ├── Native text?
 │
 ├── Scanned?
 │
 ├── Mixed?
 │
 ▼
Document extraction
 │
 ├── headings
 ├── paragraphs
 ├── lists
 ├── tables
 ├── figures
 ├── captions
 └── page metadata
 │
 ▼
Structured document representation
```

## Tasks

* [x] Implement document processor interface.
* [x] Add Docling implementation.
* [x] Preserve page numbers.
* [x] Preserve section hierarchy.
* [x] Preserve bounding boxes when available.
* [x] Preserve table content.
* [x] Preserve figure references.
* [x] Store extraction confidence.
* [x] Store extraction errors.

## Internal canonical format

Do not let downstream components depend directly on Docling's internal data format.

Create a project-owned format:

```json
{
  "document_id": "doc_001",
  "pages": [],
  "sections": [],
  "blocks": [],
  "metadata": {}
}
```

Each block should support:

```text
block_id
document_id
page_number
block_type
text
section_path
bbox
source_confidence
```

## Tests

Use fixture PDFs containing:

* [x] Plain text.
* [x] Multiple chapters.
* [x] Nested headings.
* [x] Tables.
* [x] Images.
* [x] Footnotes.
* [x] Two-column layout.
* [x] Malay text.
* [x] English text.
* [x] Arabic text where applicable.

## Acceptance criteria

For a structured PDF, the system can correctly answer:

```text
What page is this paragraph from?
What chapter contains this paragraph?
What section is its parent?
```

---

# STAGE 4 — SCANNED PDF AND OCR PIPELINE

## Goal

Support scanned books and mixed PDFs.

## Detection flow

```text
PDF
 │
 ▼
Inspect pages
 │
 ├── Text-rich page ──→ Native extraction
 │
 ├── Image-only page ─→ OCR
 │
 └── Mixed page ──────→ Hybrid processing
```

## Tasks

* [x] Create OCR provider interface.
* [x] Implement initial OCR provider.
* [x] Add language configuration.
* [x] Process OCR per page.
* [x] Preserve page-to-text mapping.
* [x] Preserve OCR confidence.
* [x] Flag low-confidence pages.
* [x] Allow OCR reprocessing.
* [x] Cache OCR output.

## Important rule

Do not treat the entire PDF as one OCR blob.

Maintain:

```text
Document
 ├── Page 1
 ├── Page 2
 ├── Page 3
 └── Page N
```

Every OCR result must remain traceable to its page.

## Tests

Create benchmark fixture sets:

```text
clean_scan/
noisy_scan/
skewed_scan/
mixed_language/
arabic/
malay/
tables/
poor_quality/
```

## Acceptance criteria

The system must identify:

* [x] Native text PDF.
* [x] Fully scanned PDF.
* [x] Mixed PDF.

And route pages appropriately.

---

# STAGE 5 — STRUCTURAL CHUNKING

## Goal

Create chunks based on document meaning and structure.

## Forbidden approach

Do not use only:

```text
Split every 500 tokens.
```

## Required hierarchy

```text
Document
 │
 ├── Chapter
 │    ├── Section
 │    │    ├── Subsection
 │    │    │    └── Content blocks
```

## Chunk requirements

Each chunk must preserve:

```text
chunk_id
document_id
page_start
page_end
chapter
section
subsection
section_path
text
token_count
parent_chunk_id
```

## Chunking strategy

1. [x] Detect structural boundaries.
2. [x] Keep paragraphs from the same concept together.
3. [x] Split oversized sections intelligently.
4. [x] Add contextual headers when necessary.
5. [x] Preserve source page ranges.
6. [x] Avoid separating questions from answers.
7. [x] Avoid separating captions from their related content.

## Tests

* [x] Small section.
* [x] Huge section.
* [x] Nested sections.
* [x] Tables.
* [x] Multi-page sections.
* [x] Heading at bottom of page.
* [x] OCR-generated text.

## Acceptance criteria

Given a chunk, the system can reconstruct:

```text
Book
 → Chapter
   → Section
     → Page
       → Source text
```

---

# STAGE 6 — LOCAL SEARCH AND RAG FOUNDATION

## Goal

Create reliable retrieval before adding conversational intelligence.

## Search architecture

```text
                 User Query
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
    Keyword Search          Semantic Search
     SQLite FTS5              Vector Search
        │                         │
        └────────────┬────────────┘
                     ▼
               Candidate Set
                     │
                     ▼
                  Reranker
                     │
                     ▼
               Best Evidence
```

## Tasks

### Keyword retrieval

* [x] Implement SQLite FTS5.
* [x] Index chunk text.
* [x] Index titles.
* [x] Index section names.
* [x] Index important metadata.

### Vector retrieval

* [x] Create embedding provider interface.
* [x] Implement initial local embedding model.
* [x] Store vectors.
* [x] Support vector similarity search.
* [x] Store embedding model metadata.

### Hybrid search

* [x] Retrieve keyword candidates.
* [x] Retrieve semantic candidates.
* [x] Merge candidates.
* [x] Deduplicate candidates.
* [x] Rerank results.

### Reranking

* [x] Create reranker provider interface.
* [x] Implement local reranker.
* [x] Allow disabling reranker for weak hardware.

## Evaluation dataset

Create a project evaluation suite:

```text
question
expected_document
expected_pages
expected_concepts
```

Examples:

* [x] Exact phrase question.
* [x] Semantic question.
* [x] Question about a chapter.
* [x] Question requiring multiple pages.
* [x] Negative question where answer does not exist.

## Acceptance criteria

The retrieval system must return evidence with:

```text
document
page
section
chunk
retrieval score
rerank score
```

Do not continue until retrieval quality is acceptable.

---

# STAGE 7 — CITATION-GROUNDED CHAT

## Goal

Allow users to chat with documents without losing source traceability.

## Answer flow

```text
Question
   ↓
Query understanding
   ↓
Hybrid retrieval
   ↓
Reranking
   ↓
Evidence selection
   ↓
LLM
   ↓
Answer
   +
Citations
```

## Tasks

* [x] Create chat session.
* [x] Store conversation history.
* [x] Support document-scoped chat.
* [x] Support multi-document chat later.
* [x] Attach evidence to answers.
* [x] Show page citations.
* [x] Support "open source page".
* [x] Add "I don't know from the provided sources" behavior.

## Critical anti-hallucination rule

The LLM must distinguish between:

```text
SUPPORTED BY SOURCE
INFERENCE
NOT FOUND
```

## Tests

Ask:

* [x] Answer clearly present in PDF.
* [x] Answer spread across pages.
* [x] Answer absent from PDF.
* [x] Misleading question.
* [x] Contradictory source sections.

## Acceptance criteria

Clicking a citation should eventually support:

```text
Chat answer
   ↓
Citation
   ↓
PDF viewer
   ↓
Correct page
   ↓
Relevant source region
```

---

# STAGE 8 — KNOWLEDGE GRAPH ENGINE

## Goal

Create the machine-readable concept layer behind the mind map.

## Important design principle

The mind map is a visualization.

The knowledge graph is the underlying intelligence.

## Graph model

```text
Document
   │
   ├── Concept
   │
   ├── Claim
   │
   ├── Event
   │
   ├── Person
   │
   └── Topic
```

Relationships may include:

```text
EXPLAINS
CAUSES
AFFECTS
SUPPORTS
CONTRADICTS
PART_OF
RELATED_TO
PRECEDES
FOLLOWS
EXAMPLE_OF
```

## Initial data model

```text
graph_nodes
graph_edges
node_sources
graph_versions
```

Every graph node must retain source references.

Example:

```json
{
  "id": "concept_memory",
  "label": "Memory",
  "type": "concept",
  "source_chunks": [
    "chunk_102",
    "chunk_291"
  ]
}
```

## Tasks

* [x] Extract concepts per section.
* [x] Extract relationships.
* [x] Validate graph schema.
* [x] Deduplicate concepts.
* [x] Merge equivalent concepts.
* [x] Preserve source evidence.
* [x] Version graph changes.
* [x] Allow manual user edits.

## Tests

* [x] Duplicate concepts.
* [x] Ambiguous concepts.
* [x] Contradictory relationships.
* [x] Concepts with multiple source pages.
* [x] Invalid LLM graph JSON.

## Acceptance criteria

Every visible graph relationship must be traceable to evidence or explicitly marked as an inference.

---

# STAGE 9 — INITIAL MIND MAP

## Goal

Generate a useful high-level map without overwhelming the user.

## Initial map strategy

Do not generate every possible concept.

Generate:

```text
Document
 ├── Main Topic 1
 │    ├── Key Concept
 │    └── Key Concept
 │
 ├── Main Topic 2
 │    ├── Key Concept
 │    └── Key Concept
 │
 └── Main Topic 3
```

## Tasks

* [x] Convert graph into hierarchical map.
* [x] Select high-value concepts.
* [x] Limit initial depth.
* [x] Limit initial node count.
* [x] Generate stable node IDs.
* [x] Attach source metadata invisibly to nodes.
* [x] Persist user layout preferences.

## UI

Initial features:

* [x] Zoom.
* [x] Pan.
* [x] Collapse.
* [x] Expand.
* [x] Search node.
* [x] Focus node.
* [x] Reset view.

## Tests

* [x] Small PDF.
* [x] 100-page PDF.
* [x] 500-page PDF.
* [x] 1,000-page PDF.
* [x] Document with weak hierarchy.

## Acceptance criteria

Initial map must load without trying to render thousands of nodes.

---

# STAGE 10 — INTERACTIVE MIND MAP EXPANSION

## Goal

Make the mind map the primary interaction surface.

## Node actions

When the user selects a node:

```text
[ Expand ]
[ Explain ]
[ Evidence ]
[ Related ]
[ Compare ]
[ Summarize ]
[ Ask ]
[ Add Note ]
```

## Expand flow

```text
User clicks node
       ↓
Node ID
       ↓
Associated concepts
       ↓
Source chunks
       ↓
Additional retrieval
       ↓
LLM structured response
       ↓
New graph nodes
       ↓
Validate
       ↓
Merge graph
       ↓
Update map
```

## Explain

Show:

* [x] Plain explanation.
* [x] Source-grounded explanation.
* [x] Page citations.
* [x] Related concepts.

## Evidence

Show:

```text
Concept
 ├── Page 12
 ├── Page 18
 └── Page 77
```

## Related

Retrieve graph neighbors plus semantic neighbors.

## Ask

Open scoped chat:

```text
Current document
    ↓
Selected branch
    ↓
Selected node
    ↓
Question
```

## Tests

* [x] Expand valid node.
* [x] Expand leaf node.
* [x] Expand repeatedly.
* [x] LLM timeout.
* [x] Invalid generated JSON.
* [x] Duplicate generated nodes.
* [x] User cancels expansion.

## Acceptance criteria

The user can organically grow the map instead of receiving one giant static AI-generated diagram.

---

# STAGE 11 — PDF VIEWER + SOURCE SYNCHRONIZATION

## Goal

Connect the visual knowledge map directly to the original document.

## Features

* [x] Embedded PDF viewer.
* [x] Click citation.
* [x] Jump to page.
* [x] Highlight source region when available.
* [x] Show related node.
* [x] Return to mind map.
* [x] Split-screen desktop layout.

## Interaction

```text
Mind Map Node
      ↓
Evidence
      ↓
Citation
      ↓
PDF Page
      ↓
Source Text
```

And:

```text
PDF Selection
      ↓
"Add to Mind Map"
      ↓
Concept extraction
      ↓
User confirmation
      ↓
New node
```

## Tests

* [x] Correct page navigation.
* [x] Multiple citations.
* [x] OCR page.
* [x] Missing bounding box.
* [x] Large PDF.

---

# STAGE 12 — GRAPH EXPLORATION MODE

## Goal

Add a second visualization for complex relationships.

## Mind map mode

Best for:

```text
hierarchy
learning
chapters
overview
progressive exploration
```

## Graph mode

Best for:

```text
relationships
cross-chapter concepts
contradictions
causes/effects
complex networks
```

## Tasks

* [x] Add Cytoscape.js.
* [x] Render graph nodes.
* [x] Render relationship types.
* [x] Filter node types.
* [x] Filter edge types.
* [x] Search concepts.
* [x] Focus neighborhood.
* [x] Limit huge graphs.
* [x] Progressive graph loading.

## Acceptance criteria

The same underlying knowledge data powers both:

```text
Mind Map View
       and
Knowledge Graph View
```

---

# STAGE 13 — USER NOTES AND PERSONAL MIND MAPS

## Goal

Allow the user to become a co-author of the knowledge structure.

## Features

* [x] Add personal node.
* [x] Add note to existing node.
* [x] Create connection.
* [x] Remove connection.
* [x] Rename node.
* [x] Merge nodes.
* [x] Mark node as important.
* [x] Add bookmark.
* [x] Add color/tag metadata.
* [x] Undo/redo.

## Important separation

Maintain:

```text
SOURCE GRAPH
    +
USER GRAPH
    =
PERSONAL VIEW
```

Do not silently mix user opinions with source-derived facts.

## Tests

* [x] User node survives reprocessing.
* [x] Source graph regeneration does not delete personal notes.
* [x] Undo works.
* [x] Merge works.
* [x] Export works.

---

# STAGE 14 — MULTI-DOCUMENT KNOWLEDGE

## Goal

Allow users to explore relationships across books.

## Example

```text
Book A ─┐
        ├── Memory
Book B ─┤
        │
Book C ─┘
```

## Features

* [x] Create notebook/workspace.
* [x] Add multiple documents.
* [x] Multi-document retrieval.
* [x] Source labels.
* [x] Cross-document graph.
* [x] Compare documents.
* [x] Detect common concepts.
* [x] Detect conflicting claims.

## Tests

* [x] Same concept in multiple books.
* [x] Different concepts with same name.
* [x] Contradictory sources.
* [x] Large combined corpus.

---

# STAGE 15 — SUMMARIES AND LEARNING OUTPUTS

## Goal

Create useful derivative content.

## Features

* [x] Book summary.
* [x] Chapter summary.
* [x] Selected branch summary.
* [x] Key concepts.
* [x] Questions and answers.
* [x] Flashcards.
* [x] Quiz.
* [x] Study guide.

## Rule

Generated outputs must retain references to source concepts.

Example:

```text
Summary Item
    ↓
Concept IDs
    ↓
Source chunks
    ↓
Pages
```

---

# STAGE 16 — MODEL GATEWAY

## Goal

Ensure the application never depends directly on one AI runtime.

## Interface categories

```text
LLMProvider
EmbeddingProvider
RerankerProvider
OCRProvider
```

All interfaces are consolidated behind the model gateway with shared contract
tests (see `tests/unit/test_provider_contracts.py`).

## LLM API

Internal request:

```json
{
  "model": "configured-model",
  "messages": [],
  "temperature": 0.2,
  "response_schema": {}
}
```

Providers translate this internally.

## Initial providers

* [x] Ollama.
* [x] llama.cpp OpenAI-compatible server.
* [x] LM Studio OpenAI-compatible server.

## Tests

Run the same provider contract tests against every implementation.

---

# STAGE 17 — JOB SYSTEM AND RESILIENCE

## Goal

Prevent long operations from freezing the application.

## Jobs

* [x] PDF ingestion.
* [x] OCR.
* [x] Chunking.
* [x] Embedding.
* [x] Graph extraction.
* [x] Mind-map generation.

## Job states

```text
QUEUED
RUNNING
PAUSED
COMPLETED
FAILED
CANCELLED
```

## Requirements

* [x] Progress reporting.
* [x] Error reporting.
* [x] Cancellation.
* [x] Retry policy.
* [x] Idempotent operations where possible.
* [x] Resume from completed checkpoints.
* [x] Job logs.

## Test

Kill the worker during:

* [x] OCR.
* [x] Embedding (stale-job recovery + idempotent re-index).
* [x] Graph extraction.

Verify the system can recover safely.

---

# STAGE 18 — DESKTOP PACKAGING

## Goal

Create a local application experience.

## Options

Evaluate:

```text
Tauri
Electron
```

Preferred initial direction:

```text
Tauri
```

## Requirements

* [x] Installable desktop application (Tauri scaffold).
* [x] Local backend lifecycle management.
* [x] Local database.
* [x] Local document storage.
* [x] Model connection configuration.
* [x] Backup/export.
* [x] Restore.

## Tests

* [x] Fresh installation.
* [x] Upgrade.
* [x] Database migration (create_all + re-baselined history).
* [x] Broken model endpoint (provider errors surfaced on failed jobs).
* [x] Missing local model.

---

# STAGE 19 — SECURITY AND PRIVACY

## Requirements

* [x] Local documents remain private by default.
* [x] No hidden telemetry.
* [x] Explicit opt-in analytics only.
* [x] Secure file upload validation.
* [x] File size limits.
* [x] PDF parser isolation where practical.
* [x] Path traversal protection.
* [x] API authentication abstraction.
* [x] Secrets never stored in logs.
* [x] Export/delete user data.

For future commercial versions (deferred — not part of the open-source core):

* [ ] Privacy policy.
* [x] Data deletion (per-document delete removes originals + derived data).
* [ ] Backup encryption strategy.
* [ ] Account deletion.
* [ ] Subscription isolation from user content.

---

# STAGE 20 — PERFORMANCE AND HARDWARE PROFILES

## Hardware profiles

Create configuration presets.

### Low

```text
CPU-focused
small embedding model
no reranker by default
small LLM
limited parallelism
```

### Medium

```text
consumer GPU
local embeddings
reranker
7B-class model
```

### High

```text
larger GPU
larger context
parallel processing
larger model
```

## User hardware target profile

Optimize early testing around:

```text
RTX 3060-class GPU
12 GB VRAM class
64 GB RAM
consumer SSD
```

## Performance tests

Measure:

* [x] PDF extraction time.
* [x] OCR pages/minute.
* [x] Embedding chunks/minute.
* [x] Search latency.
* [x] Reranking latency.
* [x] First mind-map generation time.
* [x] Node expansion latency.
* [x] RAM.
* [x] VRAM.

---

# STAGE 21 — EVALUATION FRAMEWORK

## Goal

Prevent "it feels good" development.

Create measurable evaluation datasets.

## Retrieval evaluation

```text
Question
Expected evidence
Expected page
Expected section
```

Measure:

```text
Recall@K        (implemented: search/evaluation.py)
MRR             (implemented)
citation correctness    (chat grounding tests)
answer grounding        (chat grounding field)
```

## Mind-map evaluation

Measure:

```text
source coverage         (implemented: evaluation.evaluate_graph)
duplicate nodes         (implemented)
invalid relationships   (implemented)
orphan nodes            (implemented)
node usefulness         (degree reported per node)
hierarchy quality       (implemented)
```

## OCR evaluation

Measure:

```text
character accuracy      (implemented: evaluation.character_accuracy)
word accuracy           (implemented)
page confidence         (implemented)
language performance    (per-language fixtures in tests/fixtures/pdf.py)
```

---

# STAGE 22 — RELEASE MILESTONES

**Status: complete.** Milestones M0–M7 shipped in v0.1.0 (see `docs/CHANGELOG.md`).


## M0 — Skeleton

```text
Repository
API
Database
Tests
Configuration
```

## M1 — PDF Reader

```text
Upload
Store
Parse
View metadata
```

## M2 — Searchable Book

```text
Chunk
Embed
FTS
Vector search
```

## M3 — RAG Book

```text
Chat
Evidence
Citations
```

## M4 — Mind Map MVP

```text
Automatic overview
Interactive nodes
Expand
Evidence
```

## M5 — Knowledge Graph

```text
Persistent concepts
Relationships
Graph mode
```

## M6 — Scanned Books

```text
OCR
Mixed PDFs
Quality flags
```

## M7 — Personal Knowledge

```text
Notes
Manual nodes
Personal maps
```

## M9 — Desktop Release

```text
Installer
Migration
Backup
```

---

# FINAL MVP DEFINITION

The first real MVP is complete when a user can:

```text
Upload a PDF
       ↓
System detects native/scanned pages
       ↓
Extracts/OCRs content
       ↓
Builds structured chunks
       ↓
Indexes content
       ↓
Generates a high-level mind map
       ↓
User clicks a node
       ↓
User expands the node
       ↓
System retrieves source evidence
       ↓
New child nodes appear
       ↓
User asks a question
       ↓
Answer includes citations
       ↓
User clicks citation
       ↓
Application opens the original PDF page
```

That is the first product worth showing people.

---

# AGENT EXECUTION RULES

Before starting each stage (recurring discipline):

* [x] Read `architect.md` (architecture reference).
* [x] Read existing contracts.
* [x] Check completed stages.
* [x] Do not rewrite working modules unnecessarily.
* [x] Write tests before or alongside implementation.
* [x] Run existing regression tests.
* [x] Update documentation.

After each stage (all executed via `make check` every stage):

* [x] Run unit tests.
* [x] Run integration tests.
* [x] Run linting.
* [x] Run type checks.
* [x] Perform manual acceptance test.
* [x] Record known limitations.
* [x] Update stage status.

Never skip directly to a sophisticated AI feature when the underlying document pipeline is unreliable.

Priority order:

```text
Correct source extraction
        ↓
Correct source traceability
        ↓
Good retrieval
        ↓
Grounded answers
        ↓
Reliable graph
        ↓
Interactive mind map
        ↓
Beautiful UI
        ↓
Polished desktop experience
```

# STAGE STATUS

```text
[x] Stage 1  Foundation
[x] Stage 2  Document Library
[x] Stage 3  Document Intelligence
[x] Stage 4  OCR
[x] Stage 5  Structural Chunking
[x] Stage 6  Hybrid RAG
[x] Stage 7  Citation Chat
[x] Stage 8  Knowledge Graph
[x] Stage 9  Initial Mind Map
[x] Stage 10 Interactive Expansion
[x] Stage 11 PDF Synchronization
[x] Stage 12 Graph Mode
[x] Stage 13 Personal Knowledge
[x] Stage 14 Multi-Document
[x] Stage 15 Learning Outputs
[x] Stage 16 Model Gateway
[x] Stage 17 Job Resilience
[x] Stage 18 Desktop
[x] Stage 19 Security/Privacy
[x] Stage 20 Performance Profiles
[x] Stage 21 Evaluation Framework
[x] Stage 22 Release Milestones
```
