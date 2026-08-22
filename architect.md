# MindWeaver Architecture

## 1. Product Vision

MindWeaver is a local-first knowledge application for turning documents into an explorable knowledge space.

The primary user experience is not:

```text
Upload PDF
   ↓
Chatbot
```

It is:

```text
Upload PDF
   ↓
Understand document structure
   ↓
Build knowledge representation
   ↓
Generate initial mind map
   ↓
User explores knowledge
   ↓
Mind map grows interactively
   ↓
Every important idea leads back to evidence
```

The mind map is the front door to the knowledge.

---

# 2. Architectural Principles

## 2.1 Source before generation

The application must understand the source before generating summaries or answers.

```text
SOURCE
  ↓
STRUCTURE
  ↓
INDEX
  ↓
RETRIEVAL
  ↓
EVIDENCE
  ↓
GENERATION
```

Never reverse this order.

---

## 2.2 Preserve provenance

Every piece of derived knowledge should be traceable.

```text
Mind Map Node
      ↓
Graph Node
      ↓
Concept
      ↓
Source Chunk
      ↓
Section
      ↓
Page
      ↓
Original PDF
```

---

## 2.3 The LLM is not the database

LLMs generate and reason.

The application stores facts and relationships explicitly.

```text
LLM
 ├── extraction
 ├── synthesis
 ├── explanation
 └── generation

Database
 ├── documents
 ├── chunks
 ├── embeddings
 ├── graph nodes
 ├── relationships
 ├── citations
 └── user data
```

---

## 2.4 The mind map is a view

The architecture must support multiple views over the same knowledge.

```text
                   Knowledge Model
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
       Mind Map        Graph          Chat
          │              │              │
          ▼              ▼              ▼
       Learning      Exploration      Answers
```

---

## 2.5 Local-first, API-ready

The initial product runs locally.

The architecture must nevertheless support:

```text
Local Desktop
     │
     ▼
Core Engine
     │
     ├── Local Models
     │
     └── Optional Remote Models
```

Later:

```text
Desktop ─┐
         │
Web ─────┼── API ── Core Engine
```

---

# 3. System Overview

```text
┌───────────────────────────────────────────────────────────────┐
│                         CLIENTS                               │
│                                                               │
│  ┌─────────────┐    ┌─────────────┐    ┌──────────────────┐   │
│  └──────┬──────┘    └──────┬──────┘    └────────┬─────────┘   │
└─────────┼──────────────────┼────────────────────┼─────────────┘
          │                  │                    │
          └──────────────────┼────────────────────┘
                             ▼
┌───────────────────────────────────────────────────────────────┐
│                         API LAYER                             │
│                                                               │
│ Documents │ Search │ Chat │ Mind Maps │ Graph │ Jobs │
└───────────────────────────────┬───────────────────────────────┘
                                ▼
┌───────────────────────────────────────────────────────────────┐
│                        CORE SERVICES                          │
│                                                               │
│ Document Engine                                               │
│ RAG Engine                                                    │
│ Knowledge Graph Engine                                        │
│ Mind Map Engine                                               │
│ Job Engine                                                    │
│ Model Gateway                                                 │
└───────────────┬─────────────────────┬─────────────────────────┘
                │                     │
                ▼                     ▼
┌────────────────────────┐  ┌──────────────────────────────────┐
│      DATA LAYER        │  │          MODEL LAYER             │
│                        │  │                                  │
│ SQLite                 │  │ LLM                              │
│ FTS5                   │  │ Embeddings                       │
│ Vector Store           │  │ Reranker                         │
│ Files                  │  │ OCR                              │
└────────────────────────┘  └──────────────────────────────────┘
```

---

# 4. Document Ingestion Architecture

## 4.1 File lifecycle

```text
User selects PDF
       │
       ▼
Upload validation
       │
       ▼
File hashing
       │
       ├── Duplicate? ──→ Existing document reference
       │
       ▼
Store original
       │
       ▼
Create ingestion job
       │
       ▼
Inspect document
       │
       ├───────────────┬────────────────┐
       ▼               ▼                ▼
 Native text        Scanned           Mixed
       │               │                │
       ▼               ▼                ▼
   Extract          OCR pages       Hybrid pipeline
       │               │                │
       └───────────────┴────────────────┘
                       │
                       ▼
             Canonical Document Model
                       │
                       ▼
                  Ready for indexing
```

---

# 5. Canonical Document Model

All processors must output a project-owned format.

```text
Document
│
├── Metadata
│
├── Pages
│   ├── dimensions
│   ├── extraction method
│   └── OCR confidence
│
├── Sections
│   ├── chapter
│   ├── section
│   └── subsection
│
└── Blocks
    ├── heading
    ├── paragraph
    ├── list
    ├── table
    ├── figure
    └── caption
```

This prevents vendor lock-in.

Docling can be replaced later without rewriting RAG or mind-map logic.

---

# 6. OCR Architecture

```text
Page Inspector
      │
      ▼
Is useful text available?
      │
   ┌──┴──┐
   │     │
  YES    NO
   │     │
   ▼     ▼
Extract  OCR
   │     │
   └──┬──┘
      ▼
Normalize
      │
      ▼
Canonical Page Model
```

For mixed documents, processing is page-aware.

Never classify an entire document as simply "OCR" if only some pages require it.

---

# 7. Structural Chunking Architecture

Traditional RAG:

```text
Text
 ↓
500 tokens
 ↓
500 tokens
 ↓
500 tokens
```

MindWeaver:

```text
Book
 │
 ├── Chapter
 │    │
 │    ├── Section
 │    │    │
 │    │    ├── Subsection
 │    │    │    │
 │    │    │    ├── Paragraph Group
 │    │    │    └── Paragraph Group
```

Each chunk knows its position.

```text
Chunk
 ├── document
 ├── pages
 ├── chapter
 ├── section
 ├── section path
 └── source blocks
```

This is essential for both citation quality and mind-map hierarchy.

---

# 8. Retrieval Architecture

```text
                        USER QUESTION
                              │
                              ▼
                       Query Processing
                              │
                  ┌───────────┴───────────┐
                  ▼                       ▼
             FTS5 Search             Vector Search
                  │                       │
                  └───────────┬───────────┘
                              ▼
                       Candidate Merger
                              │
                              ▼
                           Reranker
                              │
                              ▼
                        Evidence Set
                              │
                              ▼
                             LLM
```

The retrieval system must be usable independently of chat.

This allows:

```text
Chat
Mind-map expansion
Evidence lookup
Related concepts
Comparison
Graph generation
```

to use the same retrieval engine.

---

# 9. Knowledge Graph Architecture

The graph is the bridge between documents and visual exploration.

```text
Source Chunks
      │
      ▼
Concept Extraction
      │
      ▼
Relationship Extraction
      │
      ▼
Validation
      │
      ▼
Knowledge Graph
      │
      ├──────────────┐
      ▼              ▼
   Mind Map       Graph View
```

Graph nodes may represent:

```text
Concept
Person
Event
Claim
Topic
Place
Question
```

Every source-derived node maintains evidence.

---

# 10. Mind Map Architecture

## Initial generation

The initial map is deliberately shallow.

```text
                    DOCUMENT
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
      Topic A        Topic B        Topic C
        │              │              │
      ...             ...            ...
```

## Progressive expansion

```text
User selects Topic A
         │
         ▼
Retrieve evidence
         │
         ▼
Find graph neighbors
         │
         ▼
LLM generates candidate children
         │
         ▼
Schema validation
         │
         ▼
Deduplication
         │
         ▼
Graph update
         │
         ▼
Mind map update
```

The application never needs to generate an enormous map at startup.

---

# 11. Node Interaction Model

```text
                    ┌─────────────┐
                    │    NODE     │
                    └──────┬──────┘
                           │
        ┌──────────┬───────┼───────┬───────────┐
        ▼          ▼       ▼       ▼           ▼
     Expand     Explain Evidence Related      Ask
```

Each action uses a different pipeline.

## Expand

```text
Node → Retrieval → Graph Expansion → New Children
```

## Explain

```text
Node → Evidence → LLM → Explanation + Citations
```

## Evidence

```text
Node → Source Chunks → Pages
```

## Related

```text
Node → Graph Neighbors + Semantic Search
```

## Ask

```text
Node Scope → RAG → Answer
```

---

# 12. Source Graph and User Graph

User edits must not corrupt source knowledge.

```text
              SOURCE GRAPH
                   │
                   │
              USER GRAPH
                   │
                   ▼
              COMBINED VIEW
```

Source graph:

```text
AI/source-derived
evidence-backed
regeneratable
```

User graph:

```text
notes
personal nodes
manual relationships
annotations
bookmarks
```

This separation allows reprocessing without deleting the user's work.

---

# 13. AI Model Gateway

The core application talks to interfaces.

```text
                  Core Engine
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
     Ollama       llama.cpp        LM Studio
        │              │              │
        └──────────────┼──────────────┘
                       ▼
                 Local Models
```

The same abstraction applies to:

```text
LLM
Embedding
Reranking
OCR
```

This makes hardware and model upgrades easy.

---

# 14. Job Architecture

Heavy operations do not run inside normal API requests.

```text
API Request
     │
     ▼
Create Job
     │
     ▼
Job Queue
     │
     ▼
Worker
     │
     ├── Document processing
     ├── OCR
     ├── Embeddings
     ├── Graph extraction
     └── Graph extraction
```

Job state:

```text
QUEUED
RUNNING
PAUSED
COMPLETED
FAILED
CANCELLED
```

Long operations should emit progress.

---

# 15. Data Architecture

Initial local database:

```text
SQLite
├── relational metadata
├── FTS5
├── vectors
├── graph nodes
├── graph edges
├── jobs
└── user preferences
```

Large original files remain in filesystem/object storage abstraction.

```text
Storage
├── originals/
├── derived/
├── previews/
└── exports/
```

Do not store filesystem paths as the application's permanent identity for documents.

Use stable IDs.

---

# 16. API Architecture

API domains:

```text
/api/v1/documents
/api/v1/search
/api/v1/chat
/api/v1/mindmaps
/api/v1/graphs
/api/v1/jobs
/api/v1/export
```

The API should return stable contracts.

Example:

```text
Client
  ↓
Node ID
  ↓
API
  ↓
Core service
  ↓
Graph/retrieval
  ↓
Structured response
```

The client should not know whether the backend uses Ollama, Qwen, SQLite, or another implementation.

---

# 17. Desktop Architecture

Initial deployment:

```text
┌───────────────────────────────┐
│         Desktop Shell         │
│                               │
│  ┌─────────────────────────┐  │
│  │       Web Frontend      │  │
│  └────────────┬────────────┘  │
│               │               │
│  ┌────────────▼────────────┐  │
│  │       Local API         │  │
│  └────────────┬────────────┘  │
│               │               │
│  ┌────────────▼────────────┐  │
│  │     Local Database      │  │
│  └─────────────────────────┘  │
└───────────────────────────────┘
```

Models may run:

```text
inside application
or
through Ollama
or
through llama.cpp server
or
through LM Studio
```

---

# 18. Security Architecture

```text
User Document
      │
      ▼
Validation
      │
      ▼
Safe Storage
      │
      ▼
Processing
      │
      ▼
Derived Data
```

Security requirements:

* Validate files.
* Restrict upload sizes.
* Avoid arbitrary path access.
* Keep secrets out of logs.
* Separate user data in future hosted versions.
* Make telemetry opt-in.
* Support complete deletion.

---

# 19. Scalability Strategy

The first version does not need Kubernetes.

Do not over-engineer.

Start:

```text
One machine
One API
One worker
SQLite
Local filesystem
```

Scale later:

```text
Single machine
     ↓
Separate worker
     ↓
Multiple workers
     ↓
PostgreSQL/object storage if genuinely necessary
```

The architecture should permit scaling without requiring it on day one.

---

# 20. Most Important Data Flow

```text
                    ORIGINAL PDF
                         │
                         ▼
                 DOCUMENT INSPECTION
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
        NATIVE EXTRACTION           OCR
              │                     │
              └──────────┬──────────┘
                         ▼
                 CANONICAL DOCUMENT
                         │
                         ▼
                STRUCTURAL CHUNKING
                         │
           ┌─────────────┼─────────────┐
           ▼             ▼             ▼
        FTS INDEX      VECTORS      SOURCE LINKS
           │             │             │
           └─────────────┼─────────────┘
                         ▼
                  KNOWLEDGE GRAPH
                         │
             ┌───────────┴───────────┐
             ▼                       ▼
          MIND MAP                 RAG CHAT
             │                       │
             └───────────┬───────────┘
                         ▼
                    USER EXPLORES
                         │
                         ▼
               NEW RETRIEVAL REQUEST
                         │
                         ▼
                 PROGRESSIVE EXPANSION
```

---

# 21. The Product's Differentiator

Most document AI applications do this:

```text
Document → Chat
```

Some do:

```text
Document → Chat → Static Mind Map
```

MindWeaver should do:

```text
Document
   ↓
Knowledge Structure
   ↓
Evidence-backed Graph
   ↓
Interactive Mind Map
   ↓
User Curiosity
   ↓
Selective Retrieval
   ↓
Progressive Knowledge Expansion
```

The user's curiosity determines where computation goes.

A 1,000-page book does not need to become a 1,000-node diagram immediately.

The user begins with:

```text
Book
 ├── Topic A
 ├── Topic B
 └── Topic C
```

Then explores:

```text
Topic B
   ↓
Expand
   ↓
Topic B.1
Topic B.2
Topic B.3
```

Then:

```text
Topic B.2
   ↓
Ask
   ↓
Grounded answer + evidence
```

This is the fundamental architectural idea behind the product.

---

# 22. Development Priority

```text
PRIORITY 1
Reliable PDF extraction
        ↓
PRIORITY 2
Reliable source/page tracking
        ↓
PRIORITY 3
Reliable hybrid retrieval
        ↓
PRIORITY 4
Citation-grounded answers
        ↓
PRIORITY 5
Persistent knowledge graph
        ↓
PRIORITY 6
Interactive progressive mind map
        ↓
PRIORITY 7
Personal knowledge editing
        ↓
PRIORITY 8
Desktop packaging
```

Do not reverse this order.

A beautiful mind map built on bad extraction and hallucinated concepts is a useless product.

---

# 23. Final Architecture Principle

The long-term architecture can be summarized as:

```text
                        USER
                         │
                         ▼
                    CURIOSITY
                         │
                         ▼
                     MIND MAP
                         │
                         ▼
                  KNOWLEDGE GRAPH
                         │
                         ▼
                   RETRIEVAL ENGINE
                         │
                         ▼
                   SOURCE EVIDENCE
                         │
                         ▼
                        LLM
                         │
                         ▼
               EXPLANATION / EXPANSION
                         │
                         └───────────────┐
                                         │
                                         ▼
                                  UPDATED MIND MAP
```

The LLM should enhance exploration.

The document remains the source of truth.

The graph preserves knowledge.

The mind map makes that knowledge navigable.

The user decides what to explore next.
