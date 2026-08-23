<script lang="ts">
  import { onMount } from "svelte";
  import MindMap from "./components/MindMap.svelte";
  import type { DocumentInfo } from "./lib/types";
  import { listDocuments, deleteDocument } from "./lib/api";

  let view = $state<"documents" | "map">("documents");
  let currentDocument = $state<DocumentInfo | null>(null);
  let documents = $state<DocumentInfo[]>([]);
  let error = $state<string | null>(null);
  let backendVersion = $state<string | null>(null);
  let selectedFile = $state<File | null>(null);
  let uploading = $state(false);
  let uploadMessage = $state<string | null>(null);

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

  function pickFile(event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    selectedFile = input.files?.[0] ?? null;
    uploadMessage = null;
  }

  async function upload() {
    if (!selectedFile) return;
    uploading = true;
    uploadMessage = "Reading your PDF…";
    try {
      const body = new FormData();
      body.append("file", selectedFile);
      const res = await fetch("/api/v1/documents", { method: "POST", body });
      if (res.status === 409) {
        uploadMessage = "That PDF is already in your library.";
        return;
      }
      if (!res.ok) {
        const detail = await res.json().catch(() => null);
        throw new Error(detail?.error?.message ?? `HTTP ${res.status}`);
      }
      uploadMessage = `Added "${selectedFile.name}".`;
      selectedFile = null;
      await refresh();
    } catch {
      uploadMessage =
        "Sorry — that PDF could not be added. Is it a normal PDF file?";
    } finally {
      uploading = false;
    }
  }

  function friendlyStatus(status: string): string {
    const words: Record<string, string> = {
      uploaded: "Added",
      queued: "Waiting",
      processing: "Reading",
      ocr_required: "Needs OCR",
      processing_ocr: "Reading scanned pages",
      ready: "Ready",
      failed: "Failed",
    };
    return words[status] ?? status;
  }

  let ocrBusy = $state<string | null>(null);

  async function runOcr(doc: DocumentInfo) {
    if (ocrBusy) return;
    ocrBusy = doc.id;
    uploadMessage = null;
    try {
      await fetch(`/api/v1/documents/${doc.id}/reprocess-ocr`, {
        method: "POST",
      });
      await refresh();
    } catch {
      uploadMessage = "Could not read the scanned pages.";
    } finally {
      ocrBusy = null;
    }
  }

  function openMap(doc: DocumentInfo) {
    currentDocument = doc;
    view = "map";
  }

  async function remove(doc: DocumentInfo) {
    const name = doc.title || doc.original_filename;
    if (!confirm(`Delete "${name}"? This cannot be undone.`)) return;
    try {
      await deleteDocument(doc.id);
      documents = documents.filter((d) => d.id !== doc.id);
    } catch {
      uploadMessage = "Could not delete the document.";
    }
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
      <h2>Add a PDF</h2>
      <div class="upload">
        <input type="file" accept=".pdf,application/pdf" onchange={pickFile} />
        <button onclick={upload} disabled={!selectedFile || uploading}>
          {uploading ? "Working…" : "Add to library"}
        </button>
      </div>
      {#if uploadMessage}
        <p class="upload-msg">{uploadMessage}</p>
      {/if}
    </section>

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
            <div class="doc">
              <button class="doc-open" onclick={() => openMap(doc)}>
                <span class="doc-title"
                  >{doc.title || doc.original_filename}</span
                >
                <span class="doc-meta">
                  {friendlyStatus(doc.status)} · {doc.page_count ?? "?"} pages
                </span>
              </button>
              {#if doc.status === "ocr_required"}
                <button
                  class="ocr-btn"
                  onclick={() => runOcr(doc)}
                  disabled={ocrBusy === doc.id}
                >
                  {ocrBusy === doc.id ? "Reading…" : "Read scanned pages"}
                </button>
              {/if}
              <button
                class="doc-delete"
                onclick={() => remove(doc)}
                title="Delete"
              >
                &times;
              </button>
            </div>
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
  .upload {
    display: flex;
    gap: 0.6rem;
    align-items: center;
    margin-bottom: 0.4rem;
  }
  .upload button {
    padding: 0.45rem 1rem;
    border: none;
    border-radius: 6px;
    background: #1565c0;
    color: #fff;
    cursor: pointer;
  }
  .upload button:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .upload-msg {
    color: #555;
    font-size: 0.9rem;
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
    gap: 0.6rem;
    padding: 0.4rem 0.4rem 0.4rem 0;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    background: #fff;
  }
  .doc-open {
    flex: 1;
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.5rem 1rem;
    background: transparent;
    border: none;
    cursor: pointer;
    text-align: left;
    font: inherit;
    color: inherit;
    border-radius: 8px 0 0 8px;
  }
  .doc-open:hover {
    background: #f4f7fb;
  }
  .doc-title {
    font-weight: 600;
  }
  .ocr-btn {
    margin-left: 0.6rem;
    padding: 0.25rem 0.6rem;
    border: none;
    border-radius: 5px;
    background: #f9a825;
    color: #3e2723;
    cursor: pointer;
    font-size: 0.78rem;
  }
  .ocr-btn:disabled {
    opacity: 0.6;
  }
  .doc-meta {
    color: #888;
    font-size: 0.85rem;
  }
  .doc-delete {
    padding: 0.25rem 0.55rem;
    border: none;
    border-radius: 5px;
    background: transparent;
    color: #999;
    cursor: pointer;
    font-size: 1.1rem;
    line-height: 1;
  }
  .doc-delete:hover {
    background: #fdecea;
    color: #c62828;
  }
</style>
