<script lang="ts">
  import { onMount, tick } from "svelte";
  import * as pdfjsLib from "pdfjs-dist";
  import { TextLayer } from "pdfjs-dist";
  import workerUrl from "pdfjs-dist/build/pdf.worker.mjs?url";
  import type { SourceRegion } from "../lib/api";

  pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;

  let {
    documentId,
    jumpToPage = 1,
    highlights = [],
    onAddSelection = () => {},
  }: {
    documentId: string;
    jumpToPage?: number;
    highlights?: SourceRegion[];
    onAddSelection?: (text: string, pageNumber: number) => void;
  } = $props();

  let page = $state(1);
  let pageCount = $state(0);
  let scale = $state(1.2);
  let doc = $state<pdfjsLib.PDFDocumentProxy | null>(null);
  let error = $state<string | null>(null);
  let loading = $state(true);
  let selectedText = $state("");
  let container = $state<HTMLDivElement>();
  let canvasEl = $state<HTMLCanvasElement>();
  let textLayerEl = $state<HTMLDivElement>();
  let highlightEl = $state<HTMLDivElement>();

  onMount(async () => {
    try {
      const res = await fetch(`/api/v1/documents/${documentId}/file`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const data = await blob.arrayBuffer();
      doc = await pdfjsLib.getDocument({ data }).promise;
      pageCount = doc.numPages;
      loading = false; // template mounts the <canvas>
      await tick();
      await renderPage(page);
    } catch {
      error =
        "Could not display this PDF in the browser. You can still download it from the library.";
      loading = false;
    }
  });

  $effect(() => {
    if (doc && jumpToPage >= 1 && jumpToPage <= pageCount) {
      gotoPage(jumpToPage);
    }
  });

  async function renderPage(pageNumber: number) {
    if (!doc) return;
    // The canvas mounts only after `loading` flips; flush bindings first.
    await tick();
    if (!canvasEl) return;
    const pdfPage = await doc.getPage(pageNumber);
    const baseViewport = pdfPage.getViewport({ scale: 1 });
    // Cap very large pages so the browser canvas stays manageable.
    const maxSide = 1600;
    const effective = Math.min(
      scale,
      Math.max(0.4, maxSide / Math.max(baseViewport.width, baseViewport.height))
    );
    const viewport = pdfPage.getViewport({ scale: effective });
    canvasEl.width = viewport.width;
    canvasEl.height = viewport.height;

    const renderContext = {
      canvasContext: canvasEl.getContext("2d")!,
      viewport,
    } as never;
    await pdfPage.render(renderContext).promise;

    // text layer for selection
    if (textLayerEl) {
      // eslint-disable-next-line svelte/no-dom-manipulating
      textLayerEl.innerHTML = "";
      textLayerEl.style.width = `${viewport.width}px`;
      textLayerEl.style.height = `${viewport.height}px`;
      const textLayer = new TextLayer({
        textContentSource: pdfPage.streamTextContent({
          includeMarkedContent: true,
        }),
        container: textLayerEl,
        viewport,
      });
      await textLayer.render();
    }

    renderHighlights(pageNumber, viewport, pdfPage);
    selectedText = "";
  }

  function renderHighlights(
    pageNumber: number,
    viewport: pdfjsLib.PageViewport,
    pdfPage: pdfjsLib.PDFPageProxy,
  ) {
    if (!highlightEl) return;
    // eslint-disable-next-line svelte/no-dom-manipulating
    highlightEl.innerHTML = "";
    const regions = highlights.filter(
      (h) => h.page_number === pageNumber && h.bbox,
    );
    const pageHeight = pdfPage.view[3] - pdfPage.view[1];
    for (const region of regions) {
      if (!region.bbox) continue;
      const box = document.createElement("div");
      box.className = "highlight";
      box.style.left = `${region.bbox.left * viewport.scale}px`;
      box.style.top = `${(pageHeight - region.bbox.top) * viewport.scale}px`;
      box.style.width = `${(region.bbox.right - region.bbox.left) * viewport.scale}px`;
      box.style.height = `${(region.bbox.top - region.bbox.bottom) * viewport.scale}px`;
      // eslint-disable-next-line svelte/no-dom-manipulating
      highlightEl.appendChild(box);
    }
  }

  async function gotoPage(target: number) {
    page = Math.max(1, Math.min(target, pageCount));
    await renderPage(page);
  }

  function onTextSelect() {
    const selection = window.getSelection()?.toString().trim() ?? "";
    selectedText = selection;
  }

  function submitSelection() {
    if (!selectedText) return;
    onAddSelection(selectedText, page);
    selectedText = "";
  }
</script>

<div class="viewer" role="application" aria-label="PDF viewer">
  <header class="toolbar">
    <button onclick={() => gotoPage(page - 1)} disabled={page <= 1}
      >← Prev</button
    >
    <input
      type="number"
      min="1"
      max={pageCount}
      bind:value={page}
      oninput={() => {
        if (page >= 1 && page <= pageCount) gotoPage(page);
      }}
    />
    <span>of {pageCount}</span>
    <button onclick={() => gotoPage(page + 1)} disabled={page >= pageCount}
      >Next →</button
    >
    <button onclick={() => (scale = Math.min(3, scale * 1.15))}>+</button>
    <button onclick={() => (scale = Math.max(0.5, scale * 0.85))}>−</button>
    {#if selectedText}
      <button class="add" onclick={submitSelection}
        >Add selection to mind map</button
      >
    {/if}
  </header>

  {#if loading}
    <p class="status">Loading PDF…</p>
  {:else if error}
    <p class="status error">{error}</p>
  {:else if doc}
    <div class="page-wrap">
      <div class="page" bind:this={container}>
        <canvas bind:this={canvasEl}></canvas>
        <div
          class="text-layer"
          bind:this={textLayerEl}
          onmouseup={onTextSelect}
          role="presentation"
        ></div>
        <div class="highlights" bind:this={highlightEl}></div>
      </div>
    </div>
  {/if}
</div>

<style>
  .viewer {
    display: flex;
    flex-direction: column;
    height: 100%;
    font-family: system-ui, sans-serif;
    background: #eceff1;
  }
  .toolbar {
    display: flex;
    gap: 0.4rem;
    align-items: center;
    padding: 0.4rem 0.6rem;
    background: #fff;
    border-bottom: 1px solid #ddd;
  }
  .toolbar input {
    width: 4rem;
  }
  .toolbar button {
    padding: 0.25rem 0.6rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    background: #fff;
    color: #213547;
    cursor: pointer;
  }
  .toolbar button:disabled {
    opacity: 0.5;
  }
  .toolbar .add {
    background: #e8f5e9;
    border-color: #81c784;
  }
  .page-wrap {
    flex: 1;
    overflow: auto;
    padding: 1rem;
  }
  .page {
    position: relative;
    margin: 0 auto;
    width: max-content;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
    background: #fff;
  }
  .text-layer {
    position: absolute;
    inset: 0;
    overflow: hidden;
    opacity: 0.25;
    line-height: 1;
    user-select: text;
  }
  .text-layer :global(span) {
    position: absolute;
    white-space: pre;
    transform-origin: 0% 0%;
  }
  .highlights {
    position: absolute;
    inset: 0;
    pointer-events: none;
  }
  .highlights :global(.highlight) {
    position: absolute;
    background: rgba(255, 235, 59, 0.45);
    border: 1px solid #f9a825;
    pointer-events: none;
  }
  .status {
    padding: 2rem;
    color: #666;
  }
  .error {
    color: #c62828;
  }
</style>
