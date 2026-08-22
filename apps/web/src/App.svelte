<script lang="ts">
  import { onMount } from "svelte";
  import MindMap from "./components/MindMap.svelte";
  import type { DocumentInfo } from "./lib/types";
  import { listDocuments } from "./lib/api";

  let view = $state<"documents" | "map">("documents");
  let currentDocument = $state<DocumentInfo | null>(null);
  let documents = $state<DocumentInfo[]>([]);
  let error = $state<string | null>(null);
  let backendVersion = $state<string | null>(null);

  onMount(async () => {
    await refresh();
    try {
      const res = await fetch("/api/v1/version");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      backendVersion = (await res.json()).version;
    } catch {
      error = "Backend not reachable. Start it with `make dev-api`.";
    }
  });

  async function refresh() {
    try {
      const body = await listDocuments();
      documents = body.items;
      error = null;
    } catch {
      error = "Could not load documents.";
    }
  }

  function openMap(doc: DocumentInfo) {
    currentDocument = doc;
    view = "map";
  }

  function backToList() {
    view = "documents";
    refresh();
  }
</script>

{#if view === "map" && currentDocument}
  <MindMap
    documentId={currentDocument.id}
    title={currentDocument.title}
    onBack={backToList}
  />
{:else}
  <main>
    <h1>MindWeaver</h1>
    <p class="subtitle">Local-first knowledge application.</p>
    {#if backendVersion}
      <p class="ok">Backend connected: mindweaver {backendVersion}</p>
    {:else if error}
      <p class="err">{error}</p>
    {/if}

    <section>
      <h2>Documents</h2>
      {#if documents.length === 0}
        <p class="empty">
          No documents yet. Upload a PDF via the API (<code
            >POST /api/v1/documents</code
          >).
        </p>
      {/if}
      <ul class="docs">
        {#each documents as doc (doc.id)}
          <li>
            <button class="doc" onclick={() => openMap(doc)}>
              <span class="doc-title">{doc.title || doc.original_filename}</span
              >
              <span class="doc-meta">
                {doc.status} · {doc.page_count ?? "?"} pages
              </span>
            </button>
          </li>
        {/each}
      </ul>
    </section>
  </main>
{/if}

<style>
  main {
    font-family: system-ui, sans-serif;
    max-width: 720px;
    margin: 3rem auto;
    padding: 0 1rem;
  }
  h1 {
    margin-bottom: 0.2rem;
  }
  .subtitle {
    color: #666;
    margin-top: 0;
  }
  .ok {
    color: #2e7d32;
  }
  .err {
    color: #c62828;
  }
  .empty {
    color: #888;
  }
  .docs {
    list-style: none;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .doc {
    width: 100%;
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.7rem 1rem;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    background: #fff;
    cursor: pointer;
    text-align: left;
  }
  .doc:hover {
    background: #f4f7fb;
  }
  .doc-title {
    font-weight: 600;
  }
  .doc-meta {
    color: #888;
    font-size: 0.85rem;
  }
</style>
