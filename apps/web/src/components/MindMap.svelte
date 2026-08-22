<script lang="ts">
  import { onMount } from "svelte";
  import { SvelteSet } from "svelte/reactivity";
  import PdfViewer from "./PdfViewer.svelte";
  import type { MindMap, MindMapNode } from "../lib/types";
  import {
    addSelection,
    expandNode,
    explainNode,
    getChunkSource,
    getMindMap,
    getNodeEvidence,
    type SelectionCandidates,
    type SourceRegion,
  } from "../lib/api";

  let {
    documentId,
    title,
    onBack,
  }: { documentId: string; title: string; onBack: () => void } = $props();

  const H_GAP = 190;
  const V_GAP = 46;
  const NODE_W = 150;
  const NODE_H = 30;

  let mindmap = $state<MindMap | null>(null);
  let error = $state<string | null>(null);
  let loading = $state(true);

  let collapsed = new SvelteSet<string>();
  let zoom = $state(1);
  let panX = $state(90);
  let panY = $state(180);
  let dragging = $state(false);
  let dragStart = $state({ x: 0, y: 0, px: 0, py: 0 });
  let selectedId = $state<string | null>(null);
  let search = $state("");
  let focusIndex = $state(0);
  let matches = $state<string[]>([]);

  let showPdf = $state(false);
  let pdfPage = $state(1);
  let pdfHighlights = $state<SourceRegion[]>([]);
  let actionBusy = $state(false);
  let actionError = $state<string | null>(null);
  let explanation = $state<string | null>(null);
  let relatedText = $state<string | null>(null);
  let evidenceText = $state<string | null>(null);
  let selectionCandidates = $state<SelectionCandidates | null>(null);
  let selectionBusy = $state(false);

  interface Placed {
    node: MindMapNode;
    x: number;
    y: number;
    parent: Placed | null;
  }
  let placed = $state<Placed[]>([]);

  onMount(async () => {
    try {
      mindmap = await getMindMap(documentId);
      rebuild();
    } catch {
      error = "Could not load the mind map.";
    } finally {
      loading = false;
    }
  });

  function rebuild() {
    if (!mindmap) return;
    placed = layoutTree(mindmap.root);
  }

  function layoutTree(root: MindMapNode): Placed[] {
    const result: Placed[] = [];
    let yCursor = 0;
    const visit = (node: MindMapNode, depth: number, parent: Placed | null) => {
      const entry: Placed = { node, x: depth * H_GAP, y: yCursor, parent };
      result.push(entry);
      yCursor += V_GAP;
      const isCollapsed = collapsed.has(node.id) || node.children.length === 0;
      if (!isCollapsed) {
        for (const child of node.children) visit(child, depth + 1, entry);
      }
    };
    visit(root, 0, null);
    return result;
  }

  function nodeWidth(): number {
    const depth = placed.reduce((max, p) => Math.max(max, p.node.depth), 0);
    return depth * H_GAP + NODE_W + 40;
  }
  function nodeHeight(): number {
    return Math.max(placed.length * V_GAP + 80, 240);
  }

  function toggle(id: string) {
    if (collapsed.has(id)) {
      collapsed.delete(id);
    } else {
      collapsed.add(id);
    }
    rebuild();
  }

  function onMouseDown(event: MouseEvent) {
    if (event.button !== 0) return;
    dragging = true;
    dragStart = { x: event.clientX, y: event.clientY, px: panX, py: panY };
  }

  function onMouseMove(event: MouseEvent) {
    if (!dragging) return;
    panX = dragStart.px + (event.clientX - dragStart.x);
    panY = dragStart.py + (event.clientY - dragStart.y);
  }

  function onMouseUp() {
    dragging = false;
  }

  function onWheel(event: WheelEvent) {
    const factor = event.deltaY > 0 ? 0.9 : 1.12;
    zoom = Math.min(2.5, Math.max(0.3, zoom * factor));
  }

  function reset() {
    zoom = 1;
    panX = 90;
    panY = 180;
    collapsed.clear();
    rebuild();
  }

  function expandAll() {
    collapsed.clear();
    rebuild();
  }

  function collapseAll() {
    collapsed.clear();
    for (const id of collectIds(mindmap?.root)) collapsed.add(id);
    rebuild();
  }

  function collectIds(node?: MindMapNode): string[] {
    if (!node) return [];
    const ids = [node.id];
    for (const child of node.children) ids.push(...collectIds(child));
    return ids;
  }

  function runSearch() {
    const term = search.trim().toLowerCase();
    if (!term) {
      matches = [];
      return;
    }
    matches = placed
      .filter((p) => p.node.label.toLowerCase().includes(term))
      .map((p) => p.node.id);
    focusIndex = 0;
    focusNext();
  }

  function focusNext() {
    if (!matches.length) return;
    const id = matches[focusIndex % matches.length];
    focusIndex += 1;
    focusNode(id);
  }

  function focusNode(id: string) {
    const entry = placed.find((p) => p.node.id === id);
    if (!entry) return;
    panX = 60 - entry.x * zoom + 20;
    panY = 160 - entry.y * zoom + 30;
    selectedId = id;
  }

  function linkPath(x1: number, y1: number, x2: number, y2: number): string {
    const mid = (x1 + x2) / 2;
    return `M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`;
  }

  function truncate(label: string): string {
    return label.length > 22 ? label.slice(0, 21) + "…" : label;
  }

  function nodeColor(nodeType: string): string {
    if (nodeType === "root") return "#37474f";
    if (nodeType === "topic") return "#1565c0";
    return "#6a1b9a";
  }

  async function runAction(action: string) {
    if (!selectedNode || !mindmap) return;
    actionBusy = true;
    actionError = null;
    explanation = null;
    relatedText = null;
    evidenceText = null;
    const node = selectedNode.node;
    try {
      if (action === "expand") {
        mindmap = await expandNode(documentId, node.id);
        rebuild();
      } else if (action === "explain") {
        const result = await explainNode(documentId, node.id);
        explanation = result.explanation;
        relatedText = (result.related_concepts ?? [])
          .map((r) => `${r.label}${r.relation ? ` (${r.relation})` : ""}`)
          .join(", ");
      } else if (action === "evidence") {
        const evidence = await getNodeEvidence(documentId, node.id);
        evidenceText = `pages: ${evidence.pages.join(", ") || "—"}\n` +
          evidence.chunks.map((c) => `  p${c.page_start} ${c.section_path.join(" / ")}`).join("\n");
      } else if (action === "pdf") {
        const evidence = await getNodeEvidence(documentId, node.id);
        const targetPage = evidence.pages[0] ?? node.source?.pages?.[0] ?? 1;
        pdfPage = targetPage;
        pdfHighlights = [];
        if (evidence.chunks.length) {
          try {
            const source = await getChunkSource(documentId, evidence.chunks[0].chunk_id);
            pdfHighlights = source.regions.filter((r) => r.page_number === targetPage);
          } catch {
            pdfHighlights = [];
          }
        }
        showPdf = true;
      }
    } catch {
      actionError = "Action failed. Is the LLM configured?";
    } finally {
      actionBusy = false;
    }
  }

  async function handleSelection(text: string, pageNumber: number) {
    selectionText = text;
    selectionPage = pageNumber;
    selectionBusy = true;
    selectionCandidates = null;
    try {
      selectionCandidates = await addSelection(documentId, text, pageNumber, false);
    } catch {
      actionError = "Could not extract concepts from the selection.";
    } finally {
      selectionBusy = false;
    }
  }

  let selectionText = $state("");
  let selectionPage = $state(1);

  async function confirmSelection() {
    if (!selectionCandidates) return;
    selectionBusy = true;
    try {
      const result = await addSelection(documentId, selectionText, selectionPage, true);
      selectionCandidates = null;
      actionError = result.added ? "Added to the mind map." : "Nothing new to add.";
      mindmap = await getMindMap(documentId);
      rebuild();
    } catch {
      actionError = "Could not confirm the selection.";
    } finally {
      selectionBusy = false;
    }
  }

  const selectedNode = $derived(
    placed.find((p) => p.node.id === selectedId) ?? null,
  );
</script>

<div class="map-shell">
  <header>
    <button class="back" onclick={onBack}>← Documents</button>
    <h1>{title}</h1>
    <div class="controls">
      <input
        type="search"
        placeholder="Search node"
        bind:value={search}
        oninput={runSearch}
      />
      <button onclick={focusNext} disabled={matches.length === 0}>Next</button>
      <button onclick={() => (zoom = Math.min(2.5, zoom * 1.2))}>+</button>
      <button onclick={() => (zoom = Math.max(0.3, zoom * 0.8))}>−</button>
      <button onclick={expandAll}>Expand</button>
      <button onclick={collapseAll}>Collapse</button>
      <button onclick={reset}>Reset</button>
    </div>
  </header>

  {#if loading}
    <p class="status">Loading mind map…</p>
  {:else if error}
    <p class="status error">{error}</p>
  {:else if mindmap}
    <div class="canvas-wrap">
      <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
      <div
        class="canvas"
        role="application"
        aria-label="Mind map canvas"
        onmousedown={onMouseDown}
        onmousemove={onMouseMove}
        onmouseup={onMouseUp}
        onmouseleave={onMouseUp}
        onwheel={onWheel}
      >
        <svg
          width={nodeWidth() * zoom + 200}
          height={nodeHeight() * zoom + 200}
          class="map-svg"
        >
          <g transform={`translate(${panX} ${panY}) scale(${zoom})`}>
            {#each placed as p (p.node.id)}
              {#if p.parent}
                <path
                  d={linkPath(
                    p.parent.x + NODE_W,
                    p.parent.y + NODE_H / 2,
                    p.x,
                    p.y + NODE_H / 2,
                  )}
                  stroke="#b0bec5"
                  stroke-width="1.5"
                  fill="none"
                />
              {/if}
            {/each}
            {#each placed as p (p.node.id)}
              <g
                class="node"
                class:selected={selectedId === p.node.id}
                transform={`translate(${p.x} ${p.y})`}
                onclick={() => {
                  toggle(p.node.id);
                  selectedId = p.node.id;
                }}
                onkeydown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    toggle(p.node.id);
                    selectedId = p.node.id;
                  }
                }}
                role="button"
                tabindex="0"
              >
                <rect
                  width={NODE_W}
                  height={NODE_H}
                  rx="6"
                  fill={nodeColor(p.node.node_type)}
                  stroke={p.node.children.length ? "#263238" : "none"}
                  stroke-width="1.5"
                />
                <text x="10" y="20" fill="#fff" font-size="12">
                  {truncate(p.node.label)}
                </text>
                {#if p.node.children.length}
                  <text
                    x={NODE_W - 14}
                    y="20"
                    fill="#fff"
                    font-size="11"
                    text-anchor="middle"
                  >
                    {collapsed.has(p.node.id) ? "+" : "−"}
                  </text>
                {/if}
              </g>
            {/each}
          </g>
        </svg>
      </div>
    </div>
    {#if selectedNode}
      <aside class="source-panel">
        <h3>{selectedNode.node.label}</h3>
        <div class="actions">
          <button onclick={() => runAction("expand")} disabled={actionBusy}>Expand</button>
          <button onclick={() => runAction("explain")} disabled={actionBusy}>Explain</button>
          <button onclick={() => runAction("evidence")} disabled={actionBusy}>Evidence</button>
          <button onclick={() => runAction("pdf")} disabled={actionBusy}>Open PDF</button>
        </div>
        {#if actionError}
          <p class="action-msg">{actionError}</p>
        {/if}
        {#if explanation}
          <p class="explanation">{explanation}</p>
          {#if relatedText}
            <p class="related"><strong>Related:</strong> {relatedText}</p>
          {/if}
        {/if}
        {#if evidenceText}
          <pre class="evidence">{evidenceText}</pre>
        {/if}
        <dl>
          <dt>Type</dt>
          <dd>{selectedNode.node.node_type}</dd>
          {#if selectedNode.node.source?.section_path?.length}
            <dt>Section</dt>
            <dd>{selectedNode.node.source.section_path.join(" / ")}</dd>
          {/if}
          {#if selectedNode.node.source?.pages?.length}
            <dt>Pages</dt>
            <dd>{selectedNode.node.source.pages.join(", ")}</dd>
          {/if}
          {#if selectedNode.node.source?.chunk_ids?.length}
            <dt>Evidence chunks</dt>
            <dd>{selectedNode.node.source.chunk_ids.length}</dd>
          {/if}
          {#if selectedNode.node.source?.is_inference}
            <dt>Note</dt>
            <dd>inference</dd>
          {/if}
        </dl>
      </aside>
    {/if}
    {#if showPdf}
      <div class="pdf-split">
        <div class="pdf-header">
          <strong>Source</strong>
          <button onclick={() => (showPdf = false)}>Close</button>
        </div>
        <PdfViewer
          documentId={documentId}
          jumpToPage={pdfPage}
          highlights={pdfHighlights}
          onAddSelection={handleSelection}
        />
        {#if selectionCandidates}
          <div class="selection-confirm">
            <p>Extracted concepts:</p>
            <ul>
              {#each selectionCandidates.candidates.nodes as node (node.id)}
                <li>{node.label}</li>
              {/each}
            </ul>
            <button onclick={confirmSelection} disabled={selectionBusy}>Add to mind map</button>
            <button onclick={() => (selectionCandidates = null)}>Cancel</button>
          </div>
        {/if}
      </div>
    {/if}
  {/if}
</div>

<style>
  .map-shell {
    display: flex;
    flex-direction: column;
    height: 100vh;
    font-family: system-ui, sans-serif;
  }
  header {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 0.6rem 1rem;
    background: #f5f5f5;
    border-bottom: 1px solid #e0e0e0;
  }
  header h1 {
    font-size: 1.1rem;
    margin: 0;
    flex: 1;
  }
  .controls {
    display: flex;
    gap: 0.4rem;
    align-items: center;
  }
  .controls input {
    padding: 0.3rem 0.5rem;
    border: 1px solid #ccc;
    border-radius: 4px;
  }
  button {
    padding: 0.3rem 0.7rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    background: #fff;
    cursor: pointer;
  }
  button:hover {
    background: #eef2f7;
  }
  button:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .canvas-wrap {
    flex: 1;
    overflow: auto;
  }
  .canvas {
    width: max-content;
    cursor: grab;
    background: #fafafa;
    min-height: 60vh;
  }
  .canvas:active {
    cursor: grabbing;
  }
  .map-svg {
    display: block;
  }
  .node {
    cursor: pointer;
  }
  .node rect {
    transition: stroke 0.1s;
  }
  .node.selected rect {
    stroke: #ff9800;
    stroke-width: 3;
  }
  .status {
    padding: 2rem;
    color: #666;
  }
  .error {
    color: #c62828;
  }
  .source-panel {
    position: fixed;
    right: 0.8rem;
    bottom: 0.8rem;
    width: 240px;
    padding: 0.8rem 1rem;
    background: #fff;
    border: 1px solid #ddd;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12);
  }
  .source-panel h3 {
    margin: 0 0 0.5rem;
    font-size: 0.95rem;
  }
  .actions {
    display: flex;
    gap: 0.3rem;
    flex-wrap: wrap;
    margin-bottom: 0.5rem;
  }
  .actions button {
    font-size: 0.78rem;
    padding: 0.2rem 0.5rem;
  }
  .action-msg {
    font-size: 0.78rem;
    color: #1565c0;
  }
  .explanation {
    font-size: 0.82rem;
    margin: 0.3rem 0;
  }
  .related {
    font-size: 0.8rem;
    color: #555;
  }
  .evidence {
    font-size: 0.75rem;
    white-space: pre-wrap;
    background: #f5f5f5;
    padding: 0.4rem;
    border-radius: 4px;
    max-height: 120px;
    overflow: auto;
  }
  .pdf-split {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    width: 48%;
    background: #eceff1;
    border-left: 1px solid #ccc;
    display: flex;
    flex-direction: column;
    z-index: 20;
  }
  .pdf-split :global(.viewer) {
    flex: 1;
    min-height: 0;
  }
  .pdf-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.4rem 0.8rem;
    background: #fff;
    border-bottom: 1px solid #ddd;
  }
  .pdf-header button {
    padding: 0.25rem 0.6rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    background: #fff;
    cursor: pointer;
  }
  .selection-confirm {
    position: absolute;
    bottom: 1rem;
    left: 1rem;
    right: 1rem;
    background: #fff;
    border: 1px solid #ddd;
    border-radius: 8px;
    padding: 0.8rem 1rem;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
    z-index: 30;
  }
  .selection-confirm ul {
    margin: 0.3rem 0;
  }
  .source-panel dl {
    margin: 0;
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 0.2rem 0.6rem;
    font-size: 0.8rem;
  }
  .source-panel dt {
    color: #777;
  }
  .source-panel dd {
    margin: 0;
  }
</style>
