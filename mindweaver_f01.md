# Add Feature: Vision + Tool-Calling Intelligence Layer

## Status

- [x] Not started
- [x] Stage 0 complete
- [x] Stage 1 complete
- [x] Stage 2 complete
- [x] Stage 3 complete
- [x] Stage 4 complete
- [x] Stage 5 complete
- [x] Stage 6 complete
- [ ] Stage 7 complete (API: implemented; UI review pending)
- [ ] Stage 8 complete (UI integration pending)
- [x] Stage 9 complete (presets)
- [x] Stage 10 complete (integration test)
- [x] All tests passing

---

# 1. Purpose

Add an OPTIONAL Vision + Tool-Calling Intelligence Layer to the existing
MindWeaver codebase.

This feature must support:

1. Vision-capable local LLMs.
2. Tool/function calling.
3. Structured JSON output.
4. Complex PDF page analysis.
5. OCR fallback/escalation.
6. Evidence-based mind-map node expansion.
7. Model configuration independent of existing providers.
8. Future replacement of Qwen with another compatible model.

The initial target model family is Qwen-compatible local models, but the
architecture MUST NOT hardcode the application to Qwen.

Examples of possible future models:

- Qwen Vision models
- Qwen text/reasoning models
- Gemma-compatible models
- Llama-compatible models
- other OpenAI-compatible local inference servers

---

# 2. CRITICAL RULE: DO NOT BREAK EXISTING CODE

This is an ADDITIVE feature.

Do NOT:

- rewrite the existing RAG pipeline
- replace the existing OCR implementation
- replace the existing LLM implementation
- modify existing database tables unless absolutely necessary
- modify existing API contracts
- rename existing modules
- move existing files
- change existing ingestion behaviour
- require a vision model for normal PDF processing
- require tool calling for existing chat features

Existing application behaviour MUST remain unchanged when this feature is disabled.

The feature must be removable by disabling configuration.

---

# 3. Architecture Principle

The existing application remains the source of truth.

The LLM is an OPTIONAL intelligence layer.

The LLM MUST NOT directly:

- write arbitrary database records
- modify the graph without validation
- execute shell commands
- access arbitrary files
- access the network
- access unrestricted application internals

The LLM can only interact with explicitly registered application tools.

Architecture:

```text
                         EXISTING APPLICATION
                                  │
                                  │
                    Existing RAG / OCR / Graph
                                  │
                                  │
                                  ▼
                         Tool Adapter Layer
                                  │
                                  ▼
┌────────────────────────────────────────────────────────┐
│                 Intelligence Layer                     │
│                                                        │
│  Vision Model ─────┐                                   │
│                    │                                   │
│  Text Model ───────┼──► Model Gateway                  │
│                    │         │                         │
│  Reasoning Model ──┘         ▼                         │
│                         Tool Executor                  │
│                              │                         │
│                         Schema Validator               │
└──────────────────────────────┼─────────────────────────┘
                               │
                               ▼
                         Existing Core

Absolutely. The safest approach is to add this as an **isolated capability layer**, not refactor the existing ingestion/RAG/mind-map pipeline.

Below is a ready-to-save `add_feature.md` for your coding agent.

---

# `add_feature.md`

````md
# Add Feature: Vision + Tool-Calling Intelligence Layer

## Status

- [x] Not started
- [x] Stage 0 complete
- [x] Stage 1 complete
- [x] Stage 2 complete
- [x] Stage 3 complete
- [x] Stage 4 complete
- [x] Stage 5 complete
- [x] Stage 6 complete
- [ ] Stage 7 complete (API: implemented; UI review pending)
- [ ] Stage 8 complete (UI integration pending)
- [x] Stage 9 complete (presets)
- [x] Stage 10 complete (integration test)
- [x] All tests passing

---

# 1. Purpose

Add an OPTIONAL Vision + Tool-Calling Intelligence Layer to the existing
MindWeaver codebase.

This feature must support:

1. Vision-capable local LLMs.
2. Tool/function calling.
3. Structured JSON output.
4. Complex PDF page analysis.
5. OCR fallback/escalation.
6. Evidence-based mind-map node expansion.
7. Model configuration independent of existing providers.
8. Future replacement of Qwen with another compatible model.

The initial target model family is Qwen-compatible local models, but the
architecture MUST NOT hardcode the application to Qwen.

Examples of possible future models:

- Qwen Vision models
- Qwen text/reasoning models
- Gemma-compatible models
- Llama-compatible models
- other OpenAI-compatible local inference servers

---

# 2. CRITICAL RULE: DO NOT BREAK EXISTING CODE

This is an ADDITIVE feature.

Do NOT:

- rewrite the existing RAG pipeline
- replace the existing OCR implementation
- replace the existing LLM implementation
- modify existing database tables unless absolutely necessary
- modify existing API contracts
- rename existing modules
- move existing files
- change existing ingestion behaviour
- require a vision model for normal PDF processing
- require tool calling for existing chat features

Existing application behaviour MUST remain unchanged when this feature is disabled.

The feature must be removable by disabling configuration.

---

# 3. Architecture Principle

The existing application remains the source of truth.

The LLM is an OPTIONAL intelligence layer.

The LLM MUST NOT directly:

- write arbitrary database records
- modify the graph without validation
- execute shell commands
- access arbitrary files
- access the network
- access unrestricted application internals

The LLM can only interact with explicitly registered application tools.

Architecture:

```text
                         EXISTING APPLICATION
                                  │
                                  │
                    Existing RAG / OCR / Graph
                                  │
                                  │
                                  ▼
                         Tool Adapter Layer
                                  │
                                  ▼
┌────────────────────────────────────────────────────────┐
│                 Intelligence Layer                     │
│                                                        │
│  Vision Model ─────┐                                   │
│                    │                                   │
│  Text Model ───────┼──► Model Gateway                  │
│                    │         │                         │
│  Reasoning Model ──┘         ▼                         │
│                         Tool Executor                  │
│                              │                         │
│                         Schema Validator               │
└──────────────────────────────┼─────────────────────────┘
                               │
                               ▼
                         Existing Core
````

---

# 4. Feature Isolation

Create a NEW feature directory.

Suggested structure:

```text
src/
├── existing_modules/
│
├── intelligence/
│   ├── __init__.py
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings.py
│   │   └── validation.py
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── openai_compatible.py
│   │   └── qwen_adapter.py
│   │
│   ├── vision/
│   │   ├── __init__.py
│   │   ├── analyzer.py
│   │   ├── page_selector.py
│   │   └── escalation.py
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── registry.py
│   │   ├── executor.py
│   │   ├── schemas.py
│   │   │
│   │   ├── document_tools.py
│   │   ├── rag_tools.py
│   │   └── graph_tools.py
│   │
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── mindmap.py
│   │   ├── vision.py
│   │   └── tool_result.py
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── orchestrator.py
│   │   ├── node_expansion.py
│   │   └── evidence_validator.py
│   │
│   └── tests/
│       ├── test_config.py
│       ├── test_tools.py
│       ├── test_vision.py
│       ├── test_schemas.py
│       └── test_orchestrator.py
```

Adapt the path to the actual repository structure.

Do not force the existing codebase to conform to this directory structure.

---

# STAGE 0 — REPOSITORY INSPECTION

## Goal

Understand the current codebase BEFORE making changes.

### Checklist

* [ ] Read existing `todoagent.md`.
* [ ] Read existing `architect.md`.
* [ ] Identify existing OCR module.
* [ ] Identify existing RAG module.
* [ ] Identify existing LLM/model provider abstraction.
* [ ] Identify existing graph/mind-map logic.
* [ ] Identify existing configuration system.
* [ ] Identify existing API layer.
* [ ] Identify existing test framework.
* [ ] Document integration points.

### Required Output

Create:

```text
docs/intelligence-integration-analysis.md
```

Document:

```text
Existing OCR module:
Existing RAG module:
Existing LLM module:
Existing graph module:
Existing configuration:
Existing API:
Existing tests:

Safe integration points:
Files that MUST NOT be modified:
Files that MAY require small integration hooks:
```

STOP implementation if the architecture is unclear.

Do not guess.

---

# STAGE 1 — FEATURE CONFIGURATION

## Goal

Add configuration without changing existing configuration behaviour.

### Configuration Example

```yaml
intelligence:
  enabled: false

  models:

    text:
      enabled: false
      provider: openai-compatible
      base_url: http://localhost:1234/v1
      model: ""

    vision:
      enabled: false
      provider: openai-compatible
      base_url: http://localhost:1234/v1
      model: ""

  tools:
    enabled: false
    max_iterations: 5
    timeout_seconds: 30

  vision_analysis:
    enabled: false
    analyze_all_pages: false
    confidence_threshold: 0.70

    triggers:
      low_ocr_confidence: true
      complex_layout: true
      tables: true
      diagrams: true

  node_expansion:
    enabled: false
    require_evidence: true
    max_children: 8
```

### Environment Variable Override

Support optional overrides:

```text
MW_INTELLIGENCE_ENABLED
MW_TEXT_MODEL_ENABLED
MW_TEXT_MODEL_BASE_URL
MW_TEXT_MODEL_NAME

MW_VISION_MODEL_ENABLED
MW_VISION_MODEL_BASE_URL
MW_VISION_MODEL_NAME

MW_TOOLS_ENABLED
MW_VISION_ENABLED
```

### Rules

* Existing configuration must continue working.
* Default intelligence feature state = DISABLED.
* Invalid intelligence configuration must fail clearly.
* Existing application must start normally without this configuration.

### Tests

* [ ] Application starts without intelligence config.
* [ ] Intelligence disabled by default.
* [ ] Valid config loads.
* [ ] Invalid provider rejected.
* [ ] Invalid URL rejected.
* [ ] Environment override works.
* [ ] Existing config tests still pass.

---

# STAGE 2 — MODEL GATEWAY

## Goal

Create an abstraction for local models.

### Base Interface

Conceptual interface:

```python
class ModelGateway:

    def chat(self, messages, **options):
        ...

    def structured(self, messages, schema, **options):
        ...

    def chat_with_tools(self, messages, tools, **options):
        ...

    def analyze_image(self, image, prompt, **options):
        ...
```

Actual implementation should follow existing project language/style.

### Initial Provider

Implement:

```text
OpenAI-compatible API adapter
```

This allows support for local servers such as:

```text
LM Studio
llama.cpp server
vLLM
other compatible servers
```

Do not make Qwen-specific HTTP calls unless absolutely necessary.

Qwen should be selected by model configuration, not application code.

### Model Capability Declaration

Each configured model must declare capabilities:

```json
{
  "chat": true,
  "vision": true,
  "structured_output": true,
  "tool_calling": true
}
```

Example:

```text
Text model:
  chat: true
  vision: false
  tools: true

Vision model:
  chat: true
  vision: true
  tools: optional
```

The application must check capabilities before using a feature.

### Tests

Use a fake/mock local model server.

Test:

* [ ] Chat request.
* [ ] Structured response.
* [ ] Tool call response.
* [ ] Vision request.
* [ ] Connection failure.
* [ ] Timeout.
* [ ] Invalid JSON.
* [ ] Model capability mismatch.

Do not require downloading a real model during CI.

---

# STAGE 3 — SAFE TOOL REGISTRY

## Goal

Allow the LLM to request information from the application.

The model does NOT execute code.

The model requests a named tool.

The application validates and executes it.

Architecture:

```text
LLM
 │
 │ tool request
 ▼
Tool Registry
 │
 │ validate name + arguments
 ▼
Tool Executor
 │
 ▼
Existing Application Service
 │
 ▼
Tool Result
 │
 ▼
LLM
```

## Initial Read-Only Tools

### Tool: search_document

```json
{
  "name": "search_document",
  "description": "Search the current document for relevant passages",
  "parameters": {
    "query": "string",
    "limit": "integer"
  }
}
```

Must call existing RAG/search functionality.

Do not duplicate the RAG engine.

---

### Tool: get_chunk

```json
{
  "name": "get_chunk",
  "parameters": {
    "chunk_id": "string"
  }
}
```

Returns existing chunk data.

---

### Tool: get_page

```json
{
  "name": "get_page",
  "parameters": {
    "document_id": "string",
    "page_number": "integer"
  }
}
```

Returns:

* text if available
* metadata
* image reference only when permitted

---

### Tool: get_graph_node

```json
{
  "name": "get_graph_node",
  "parameters": {
    "node_id": "string"
  }
}
```

---

### Tool: get_graph_neighbors

```json
{
  "name": "get_graph_neighbors",
  "parameters": {
    "node_id": "string",
    "depth": "integer"
  }
}
```

### Security Rules

Tools MUST:

* validate input schema
* validate document ownership/scope
* enforce limits
* have timeouts
* return structured data
* log execution
* reject unknown tools

Tools MUST NOT:

* execute arbitrary Python
* execute shell commands
* access arbitrary paths
* fetch arbitrary URLs
* modify system configuration

### Tests

* [ ] Known tool works.
* [ ] Unknown tool rejected.
* [ ] Invalid arguments rejected.
* [ ] Excessive limit rejected/clamped.
* [ ] Cross-document access rejected.
* [ ] Timeout handled.
* [ ] Tool error returned safely.

---

# STAGE 4 — VISION ESCALATION LAYER

## Goal

Use vision ONLY when necessary.

Do NOT send every PDF page to a vision model.

### Pipeline

```text
PDF Page
   │
   ▼
Existing Extraction/OCR
   │
   ▼
Quality Evaluation
   │
   ├── Good ───────────────► Existing pipeline
   │
   └── Needs Analysis
            │
            ▼
      Vision Escalation
            │
            ▼
      Vision Model Analysis
            │
            ▼
      Structured Result
```

### Trigger Conditions

Examples:

```text
OCR confidence below threshold
Complex table detected
Diagram detected
Multi-column layout
Low extracted text density
Malformed reading order
Existing parser reports failure
```

### Vision Output Schema

Example:

```json
{
  "page_number": 42,
  "content_type": "diagram",
  "summary": "A diagram showing...",
  "entities": [],
  "relationships": [],
  "suggested_text": null,
  "confidence": 0.85
}
```

Do not let the vision model overwrite the original OCR result.

Store the result as:

```text
Original extraction
+
Vision interpretation
```

Both must remain traceable.

### Tests

Use fixture images.

Test:

* [ ] Clean page skips vision.
* [ ] Low-confidence page triggers vision.
* [ ] Complex page triggers vision.
* [ ] Vision unavailable falls back safely.
* [ ] Vision timeout falls back safely.
* [ ] Original OCR remains unchanged.

---

# STAGE 5 — STRUCTURED MIND-MAP EXPANSION

## Goal

Allow the model to propose new mind-map nodes using evidence.

### User Action

```text
User clicks:

[ Childhood Trauma ]

        ↓

[ Expand with AI ]
```

### Processing

```text
Node selected
      │
      ▼
Gather current node context
      │
      ▼
LLM requests evidence using tools
      │
      ▼
Application returns evidence
      │
      ▼
LLM proposes expansion
      │
      ▼
Schema validation
      │
      ▼
Evidence validation
      │
      ▼
Duplicate detection
      │
      ▼
RETURN PROPOSAL
```

IMPORTANT:

Do NOT automatically commit generated nodes to the graph in the first version.

Return a proposal for user review.

### Required Output Schema

```json
{
  "action": "expand_node",
  "node_id": "node-123",

  "children": [
    {
      "label": "Emotional Effects",
      "relationship": "HAS_EFFECT",

      "description": "Brief description",

      "evidence": [
        {
          "chunk_id": "chunk-100",
          "page_number": 25
        }
      ]
    }
  ]
}
```

### Validation Rules

Reject:

* nodes without labels
* nodes without evidence when evidence is required
* invalid source chunk IDs
* chunks from another document
* duplicate children
* more than configured maximum children

### UI Requirement

Generated nodes must be visibly marked as:

```text
AI Proposal
```

The user can:

```text
[ Accept ]

[ Edit ]

[ Reject ]
```

Only accepted nodes enter the permanent graph.

### Tests

* [ ] Valid proposal accepted.
* [ ] Missing evidence rejected.
* [ ] Invalid chunk rejected.
* [ ] Duplicate detected.
* [ ] User rejection does not modify graph.
* [ ] Existing graph remains unchanged.

---

# STAGE 6 — TOOL-CALLING ORCHESTRATOR

## Goal

Create the agent loop.

The LLM can request multiple tools within a controlled limit.

### Flow

```text
User Request
     │
     ▼
Orchestrator
     │
     ▼
Model
     │
     ├── Needs information?
     │
     ├── NO ──► Final response
     │
     └── YES
          │
          ▼
       Tool Call
          │
          ▼
       Validate
          │
          ▼
       Execute
          │
          ▼
       Return Result
          │
          └────────► Model
```

### Limits

```yaml
tools:
  max_iterations: 5
  max_tool_calls: 10
  timeout_seconds: 30
```

Prevent:

```text
LLM
 ↓
Tool
 ↓
LLM
 ↓
Tool
 ↓
LLM
 ↓
Tool
 ↓
∞
```

### Required Logging

Log:

```text
request_id
document_id
model
tool_name
duration
success/failure
iteration
```

Do NOT log entire private document contents unless debug logging explicitly allows it.

### Tests

* [ ] Single tool call.
* [ ] Multiple tool calls.
* [ ] Final answer after tools.
* [ ] Iteration limit reached.
* [ ] Tool call limit reached.
* [ ] Model failure.
* [ ] Tool failure.
* [ ] Timeout.
* [ ] Infinite loop prevented.

---

# STAGE 7 — API INTEGRATION

## Goal

Expose this feature without breaking existing APIs.

All new endpoints must be versioned or namespaced.

Example:

```text
/api/intelligence/status

/api/intelligence/models

/api/intelligence/vision/analyze

/api/intelligence/mindmap/expand
```

Do not modify existing endpoints unless adding a backwards-compatible optional field.

### Feature Disabled Behaviour

When:

```text
intelligence.enabled = false
```

New endpoints should clearly return:

```json
{
  "enabled": false,
  "message": "Intelligence features are disabled"
}
```

The rest of the application must continue normally.

### Tests

* [ ] Existing API tests pass unchanged.
* [ ] New endpoints work when enabled.
* [ ] New endpoints disabled safely.
* [ ] Invalid request rejected.
* [ ] Existing endpoints unaffected.

---

# STAGE 8 — UI INTEGRATION

## Goal

Add optional UI controls without redesigning the existing application.

Add feature detection.

Example:

```text
if intelligence enabled:
    show AI controls
else:
    hide AI controls
```

## Mind-Map Context Menu

Optional actions:

```text
┌─────────────────────────────┐
│ Expand normally             │
│                             │
│ ─────────────────────────── │
│ ✨ Expand with AI           │
│ 🔍 Find evidence           │
│ 👁 Analyze source page     │
└─────────────────────────────┘
```

Do not change the existing default click behaviour.

### AI Proposal UI

```text
Existing Node
     │
     ▼
┌─────────────────────┐
│ AI Proposed Nodes   │
│                     │
│ ○ Cause A           │
│ ○ Cause B           │
│ ○ Effect A          │
│                     │
│ [Accept All]        │
│ [Review Individually]│
│ [Reject]            │
└─────────────────────┘
```

### Tests

* [ ] AI controls hidden when disabled.
* [ ] Existing mind-map interaction unchanged.
* [ ] Proposal displayed.
* [ ] Accept works.
* [ ] Reject works.
* [ ] Error displayed safely.

---

# STAGE 9 — CONFIGURATION PRESETS

## Goal

Make local model configuration easy.

Create presets, but do not hardcode model names into business logic.

Example:

```yaml
presets:

  lmstudio-local:
    provider: openai-compatible
    base_url: http://localhost:1234/v1

  llamacpp-local:
    provider: openai-compatible
    base_url: http://localhost:8080/v1
```

Users configure models separately:

```yaml
text:
  preset: lmstudio-local
  model: configured-model-name

vision:
  preset: lmstudio-local
  model: configured-vision-model-name
```

### Future

Architecture should allow:

```text
Model A → vision

Model B → reasoning

Model C → embeddings

Model D → reranking
```

without code changes.

---

# STAGE 10 — INTEGRATION TEST

## End-to-End Test Scenario

Use a test document containing:

* normal text
* headings
* table
* diagram
* complex page

Test:

```text
1. Import document
       │
2. Existing ingestion runs
       │
3. Normal pages skip vision
       │
4. Complex page triggers vision
       │
5. Document becomes searchable
       │
6. User creates/selects mind-map node
       │
7. User selects "Expand with AI"
       │
8. Model calls search_document
       │
9. Model calls get_chunk
       │
10. Model proposes children
       │
11. Evidence validated
       │
12. User reviews proposal
       │
13. User accepts one node
       │
14. Only accepted node enters graph
```

### Regression Test

Run the complete existing test suite:

```text
Existing tests: PASS
New intelligence tests: PASS
Integration tests: PASS
```

No feature is considered complete if existing functionality regresses.

---

# PERFORMANCE REQUIREMENTS

The intelligence layer must not block normal document usage.

Heavy operations should be asynchronous.

```text
User Action
    │
    ▼
Create Job
    │
    ▼
Background Processing
    │
    ▼
Progress
    │
    ▼
Result
```

Add cancellation support where the existing architecture permits.

---

# ERROR HANDLING

The following must degrade gracefully:

```text
Vision model unavailable
Text model unavailable
LM Studio offline
Model timeout
Invalid model response
Malformed JSON
Tool failure
OCR failure
GPU out of memory
```

Example:

```text
Vision failed
     │
     ▼
Log error
     │
     ▼
Preserve existing OCR result
     │
     ▼
Return feature-specific error
     │
     ▼
Application continues
```

Never crash the entire application because an optional AI feature failed.

---

# SECURITY REQUIREMENTS

The model is untrusted input.

Treat model output as data, not instructions.

Never allow:

```text
Model output
     │
     ▼
eval()
exec()
shell command
arbitrary file path
arbitrary SQL
unrestricted network request
```

All tools must have explicit schemas and allowlists.

---

# OBSERVABILITY

Add feature-specific logging:

```text
intelligence.model.request
intelligence.model.response
intelligence.tool.call
intelligence.tool.success
intelligence.tool.failure
intelligence.vision.escalation
intelligence.vision.skip
intelligence.schema.invalid
intelligence.proposal.created
```

Track timings:

```text
model_latency_ms
tool_latency_ms
vision_latency_ms
total_request_latency_ms
```

---

# DEFINITION OF DONE

The feature is complete only when:

* [ ] Existing application behaviour is unchanged by default.
* [ ] Intelligence is disabled by default.
* [ ] Feature can be enabled via configuration.
* [ ] Text model is configurable.
* [ ] Vision model is configurable.
* [ ] OpenAI-compatible local API works.
* [ ] Tool registry works.
* [ ] Tools are read-only and schema-validated.
* [ ] Tool execution limits exist.
* [ ] Vision escalation works.
* [ ] Vision does not overwrite original extraction.
* [ ] Structured output is validated.
* [ ] AI mind-map expansion requires evidence.
* [ ] AI-generated nodes are proposals first.
* [ ] User approval is required before graph modification.
* [ ] Existing tests still pass.
* [ ] New unit tests pass.
* [ ] Integration tests pass.
* [ ] End-to-end test passes.
* [ ] Feature can be disabled without code changes.

---

# FINAL AGENT INSTRUCTION

DO NOT perform a large refactor.

DO NOT replace working components simply because a new abstraction appears
cleaner.

Prefer adapters around existing components.

The objective is:

```
Existing Application
       +
Optional Intelligence Layer
```

NOT:

```
Existing Application
       ↓
   Rewrite Everything
       ↓
New Experimental Architecture
```

Before modifying a core existing file:

1. Explain why modification is necessary.
2. Check whether an adapter can avoid the modification.
3. Preserve backwards compatibility.
4. Add a regression test.

The existing application is the priority.

The new Vision + Tool-Calling layer must remain modular, optional,
configurable, testable, and removable.

````

---

## One thing I'd add to your existing `todoagent.md`

Add this dependency rule near the top:

```text
Core Application
      ▲
      │ may be used by
      │
Intelligence Layer
      ▲
      │ may be used by
      │
UI Features
````

**Never this:**

```text
Core Application
      │
      ▼
Intelligence Layer
      │
      ▼
Specific Qwen Model
```

That would lock your entire app to one model ecosystem.

The proposed `add_feature.md` lets you experiment with Qwen vision models through LM Studio or another compatible local server, while keeping your existing app functional if the AI layer is turned off.
