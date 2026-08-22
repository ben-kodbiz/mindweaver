<script lang="ts">
  import { onMount } from "svelte";
  import { SvelteSet } from "svelte/reactivity";
  import cytoscape from "cytoscape";
  import type { Core, ElementDefinition } from "cytoscape";
  import {
    createConnection,
    createPersonalNode,
    deleteGraphNode,
    getGraph,
    mergeNodes,
    redoGraph,
    removeConnection as removeConnectionFn,
    undoGraph,
    updateGraphNode,
    type GraphData,
  } from "../lib/api";

  let { documentId }: { documentId: string } = $props();

  const ALL_NODE_TYPES = ["concept", "claim", "event", "person", "topic"];
  const ALL_RELATIONS = [
    "explains",
    "causes",
    "affects",
    "supports",
    "contradicts",
    "part_of",
    "related_to",
    "precedes",
    "follows",
    "example_of",
  ];

  const TYPE_COLORS: Record<string, string> = {
    concept: "#6a1b9a",
    topic: "#1565c0",
    claim: "#2e7d32",
    event: "#ef6c00",
    person: "#455a64",
  };

  const RELATION_COLORS: Record<string, string> = {
    supports: "#2e7d32",
    contradicts: "#c62828",
    causes: "#d84315",
    affects: "#f9a825",
    explains: "#1565c0",
    part_of: "#616161",
    related_to: "#9e9e9e",
    precedes: "#00838f",
    follows: "#00838f",
    example_of: "#7b1fa2",
  };

  let containerEl = $state<HTMLDivElement>();
  let cy: Core | null = null;
  let graph = $state<GraphData | null>(null);
  let totalNodes = $state(0);
  let loading = $state(true);
  let error = $state<string | null>(null);

  let noteDraft = $state("");
  let tagsDraft = $state("");
  let connectMode = $state(false);
  let connectSource = $state<string | null>(null);
  let actionMsg = $state<string | null>(null);
  let actionError = $state<string | null>(null);

  let selectedNodeTypes = $state<string[]>([...ALL_NODE_TYPES]);
  let selectedRelations = $state<string[]>([...ALL_RELATIONS]);
  let focusNodeId = $state<string | null>(null);
  let search = $state("");
  let selectedLabel = $state<string | null>(null);

  onMount(() => {
    load();
  });

  $effect(() => {
    // re-run when filters change
    void JSON.stringify([selectedNodeTypes, selectedRelations]);
    if (cy) load();
  });

  async function load() {
    try {
      graph = await getGraph(documentId, {
        node_types: selectedNodeTypes,
        relations: selectedRelations,
        focus_node_id: focusNodeId,
        limit: 200,
      });
      totalNodes = graph.nodes.length;
      render();
      error = null;
    } catch {
      error = "Could not load the graph.";
    } finally {
      loading = false;
    }
  }

  function render() {
    if (!graph || !containerEl) return;
    const elements: ElementDefinition[] = [
      ...graph.nodes.map((node) => ({
        data: {
          id: node.id,
          label: node.label,
          type: node.type,
          degree: graph!.edges.filter(
            (e) => e.source === node.id || e.target === node.id,
          ).length,
        },
      })),
      ...graph.edges.map((edge) => ({
        data: {
          id: `${edge.source}->${edge.target}:${edge.relation}`,
          source: edge.source,
          target: edge.target,
          relation: edge.relation,
          inference: edge.is_inference,
        },
      })),
    ];

    if (cy) {
      cy.destroy();
      cy = null;
    }
    cy = cytoscape({
      container: containerEl,
      elements,
      style: [
        {
          selector: "node",
          style: {
            label: "data(label)",
            "background-color": (ele: cytoscape.NodeSingular) =>
              TYPE_COLORS[ele.data("type")] ?? "#616161",
            color: "#fff",
            "text-valign": "center",
            "text-halign": "center",
            width: (ele: cytoscape.NodeSingular) =>
              24 + Number(ele.data("degree")) * 6,
            height: (ele: cytoscape.NodeSingular) =>
              24 + Number(ele.data("degree")) * 6,
            "font-size": 9,
            "border-width": 1.5,
            "border-color": "#263238",
          },
        },
        {
          selector: "edge",
          style: {
            label: "data(relation)",
            "curve-style": "bezier",
            "target-arrow-shape": "triangle",
            "arrow-scale": 0.8,
            width: 1.5,
            "line-color": (ele: cytoscape.EdgeSingular) =>
              RELATION_COLORS[ele.data("relation")] ?? "#9e9e9e",
            "target-arrow-color": (ele: cytoscape.EdgeSingular) =>
              RELATION_COLORS[ele.data("relation")] ?? "#9e9e9e",
            "line-style": (ele: cytoscape.EdgeSingular) =>
              ele.data("inference") ? "dashed" : "solid",
            "font-size": 7,
            color: "#777",
            "text-background-color": "#fff",
            "text-background-opacity": 0.85,
            opacity: (ele: cytoscape.EdgeSingular) =>
              ele.data("inference") ? 0.55 : 1,
          },
        },
        {
          selector: "node.dimmed, edge.dimmed",
          style: { opacity: 0.12 },
        },
        {
          selector: "node.highlighted",
          style: { "border-width": 4, "border-color": "#ff9800" },
        },
      ],
      layout: { name: "cose", animate: false, padding: 30 },
      wheelSensitivity: 0.25,
    });

    cy.on("tap", "node", (event) => {
      const id = event.target.id();
      selectedLabel = event.target.data("label");
      if (connectMode && connectSource && connectSource !== id) {
        void doConnect(connectSource, id);
        connectMode = false;
        connectSource = null;
        return;
      }
      const node = graph?.nodes.find((n) => n.id === id);
      noteDraft = node?.note ?? "";
      tagsDraft = (node?.tags ?? []).join(", ");
      dimToNeighborhood(id);
    });
    cy.on("tap", (event) => {
      if (event.target === cy) {
        clearDim();
        selectedLabel = null;
      }
    });
  }

  function dimToNeighborhood(id: string) {
    if (!cy) return;
    const keep = new SvelteSet<string>([id]);
    cy.getElementById(id)
      .neighborhood()
      .forEach((ele) => {
        keep.add(ele.id());
      });
    cy.nodes().forEach((node) => {
      if (!keep.has(node.id())) node.addClass("dimmed");
      else node.removeClass("dimmed");
    });
    cy.edges().forEach((edge) => {
      const inside =
        keep.has(edge.source().id()) && keep.has(edge.target().id());
      if (!inside) edge.addClass("dimmed");
      else edge.removeClass("dimmed");
    });
    cy.getElementById(id).addClass("highlighted");
  }

  function clearDim() {
    if (!cy) return;
    cy.elements().removeClass("dimmed highlighted");
  }

  function focusNeighborhood() {
    if (!selectedLabel || !graph) return;
    const target = selectedLabel;
    const match = graph.nodes.find(
      (n) => n.label.toLowerCase() === target.toLowerCase(),
    );
    if (!match) return;
    focusNodeId = match.id; // progressive: backend returns only the neighbourhood
    load();
  }

  function clearFocus() {
    focusNodeId = null;
    selectedLabel = null;
    load();
  }

  function runSearch() {
    const term = search.trim().toLowerCase();
    if (!cy) return;
    clearDim();
    if (!term) return;
    const matched = cy
      .nodes()
      .filter((node) => node.data("label").toLowerCase().includes(term));
    matched.addClass("highlighted");
    if (matched.length) {
      cy.animate({ center: { eles: matched }, zoom: 1.3 }, { duration: 250 });
      selectedLabel = matched[0].data("label");
    }
  }

  async function refresh() {
    await load();
  }

  function selectedId(): string | null {
    if (!selectedLabel || !graph) return null;
    const match = graph.nodes.find(
      (n) => n.label.toLowerCase() === selectedLabel!.toLowerCase(),
    );
    return match?.id ?? null;
  }

  async function saveNote() {
    const id = selectedId();
    if (!id) return;
    try {
      await updateGraphNode(documentId, id, {
        note: noteDraft,
        tags: tagsDraft
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean),
      });
      actionMsg = "Saved.";
      await refresh();
    } catch {
      actionError = "Could not save.";
    }
  }

  async function toggleFlag(flag: "is_important" | "is_bookmarked") {
    const id = selectedId();
    const node = graph?.nodes.find((n) => n.id === id);
    if (!id || !node) return;
    try {
      await updateGraphNode(documentId, id, { [flag]: !node[flag] });
      await refresh();
    } catch {
      actionError = "Could not update.";
    }
  }

  async function renameNode() {
    const id = selectedId();
    if (!id) return;
    const label = window.prompt("New label:");
    if (!label) return;
    try {
      await updateGraphNode(documentId, id, { label });
      await refresh();
    } catch {
      actionError = "Could not rename.";
    }
  }

  async function addPersonalNode() {
    const label = window.prompt("New personal node label:");
    if (!label) return;
    try {
      await createPersonalNode(documentId, { label });
      actionMsg = `Added ${label}.`;
      await load();
    } catch (e) {
      actionError = e instanceof Error ? e.message : "Could not add node.";
    }
  }

  async function doConnect(source: string, target: string) {
    try {
      await createConnection(documentId, { source, target });
      actionMsg = "Connection created.";
      await load();
    } catch (e) {
      actionError = e instanceof Error ? e.message : "Could not connect.";
    }
  }

  function startConnect() {
    const id = selectedId();
    if (!id) {
      actionError = "Select a source node first.";
      return;
    }
    connectSource = id;
    connectMode = true;
    actionMsg = `Click the target node to connect from ${id}…`;
  }

  async function removeSelectedEdge() {
    // removes the first edge of the focused/selected pair via prompt
    const source = window.prompt("Remove connection - source id:");
    const target = window.prompt("target id:");
    const relation = window.prompt("relation:");
    if (!source || !target || !relation) return;
    try {
      await removeConnectionFn(documentId, { source, target, relation });
      actionMsg = "Connection removed.";
      await load();
    } catch {
      actionError = "Could not remove connection.";
    }
  }

  async function mergeInto() {
    const id = selectedId();
    if (!id) return;
    const into = window.prompt(`Merge "${id}" into which node id?`);
    if (!into) return;
    try {
      await mergeNodes(documentId, id, into);
      actionMsg = "Merged.";
      selectedLabel = null;
      await load();
    } catch (e) {
      actionError = e instanceof Error ? e.message : "Could not merge.";
    }
  }

  async function deleteSelected() {
    const id = selectedId();
    if (!id) return;
    try {
      await deleteGraphNode(documentId, id);
      selectedLabel = null;
      actionMsg = "Node deleted.";
      await load();
    } catch {
      actionError = "Could not delete.";
    }
  }

  async function doUndo() {
    try {
      const result = await undoGraph(documentId);
      actionMsg = `Undid: ${result.undone}`;
      await load();
    } catch (e) {
      actionError = e instanceof Error ? e.message : "Nothing to undo.";
    }
  }

  async function doRedo() {
    try {
      const result = await redoGraph(documentId);
      actionMsg = `Redid: ${result.redone}`;
      await load();
    } catch (e) {
      actionError = e instanceof Error ? e.message : "Nothing to redo.";
    }
  }

  function truncate(label: string): string {
    return label.length > 18 ? label.slice(0, 17) + "…" : label;
  }
</script>

<div class="graph-shell">
  <div class="filters">
    <fieldset>
      <legend>Node types</legend>
      {#each ALL_NODE_TYPES as type (type)}
        <label class="chip">
          <input
            type="checkbox"
            checked={selectedNodeTypes.includes(type)}
            onchange={() =>
              (selectedNodeTypes = selectedNodeTypes.includes(type)
                ? selectedNodeTypes.filter((t) => t !== type)
                : [...selectedNodeTypes, type])}
          />
          <span class="dot" style={`background: ${TYPE_COLORS[type]}`}
          ></span>{truncate(type)}
        </label>
      {/each}
    </fieldset>
    <fieldset>
      <legend>Relations</legend>
      <select multiple size="4" bind:value={selectedRelations}>
        {#each ALL_RELATIONS as relation (relation)}
          <option value={relation}>{truncate(relation)}</option>
        {/each}
      </select>
    </fieldset>
    <fieldset>
      <legend>Search</legend>
      <input
        type="search"
        placeholder="Find a concept…"
        bind:value={search}
        oninput={runSearch}
      />
      <button onclick={focusNeighborhood} disabled={!selectedLabel}
        >Focus</button
      >
      <button onclick={clearFocus} disabled={!focusNodeId}>Reset focus</button>
      <button onclick={() => addPersonalNode()}>+ Node</button>
      <button onclick={startConnect}>Connect…</button>
      <button onclick={removeSelectedEdge}>Remove link</button>
      <button onclick={doUndo}>Undo</button>
      <button onclick={doRedo}>Redo</button>
    </fieldset>
  </div>

  <p class="counts">
    {graph
      ? `${totalNodes} nodes · ${graph.edges.length} edges`
      : ""}{focusNodeId ? ` · focused on ${focusNodeId}` : ""}
  </p>

  {#if loading}
    <p class="status">Loading graph…</p>
  {:else if error}
    <p class="status error">{error}</p>
  {:else}
    <div class="canvas" role="application" aria-label="Knowledge graph canvas">
      <div class="cy-container" bind:this={containerEl}></div>
      {#if selectedLabel}
        <div class="edit-panel">
          <h4>{selectedLabel}</h4>
          {#if actionMsg}<p class="msg">{actionMsg}</p>{/if}
          <label>
            Note
            <textarea rows="3" bind:value={noteDraft}></textarea>
          </label>
          <label>
            Tags (comma separated)
            <input bind:value={tagsDraft} />
          </label>
          <div class="row">
            <button onclick={saveNote}>Save</button>
            <button onclick={() => toggleFlag("is_important")}
              >★ Important</button
            >
            <button onclick={() => toggleFlag("is_bookmarked")}
              >🔖 Bookmark</button
            >
          </div>
          <div class="row">
            <button onclick={renameNode}>Rename</button>
            <button onclick={mergeInto}>Merge into…</button>
            <button onclick={deleteSelected} class="danger">Delete</button>
          </div>
        </div>
        {#if actionError}
          <div class="info error">{actionError}</div>
        {:else if actionMsg}
          <div class="info">{actionMsg}</div>
        {/if}
      {/if}
    </div>
  {/if}
</div>

<style>
  .graph-shell {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
  }
  .filters {
    display: flex;
    gap: 1rem;
    padding: 0.5rem 1rem;
    background: #f5f5f5;
    border-bottom: 1px solid #e0e0e0;
    align-items: flex-start;
    flex-wrap: wrap;
  }
  fieldset {
    border: 1px solid #ddd;
    border-radius: 6px;
    padding: 0.3rem 0.6rem;
    display: flex;
    gap: 0.5rem;
    align-items: center;
  }
  legend {
    font-size: 0.72rem;
    color: #666;
    padding: 0 0.3rem;
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    font-size: 0.75rem;
    cursor: pointer;
  }
  .dot {
    width: 0.6rem;
    height: 0.6rem;
    border-radius: 50%;
    display: inline-block;
  }
  select {
    font-size: 0.75rem;
  }
  input[type="search"] {
    padding: 0.25rem 0.45rem;
    border: 1px solid #ccc;
    border-radius: 4px;
  }
  button {
    padding: 0.25rem 0.6rem;
    border: 1px solid #ccc;
    border-radius: 4px;
    background: #fff;
    cursor: pointer;
    font-size: 0.78rem;
  }
  button:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .counts {
    margin: 0;
    padding: 0.25rem 1rem;
    font-size: 0.75rem;
    color: #888;
  }
  .canvas {
    flex: 1;
    min-height: 0;
    position: relative;
    background: #fafafa;
  }
  .cy-container {
    position: absolute;
    inset: 0;
  }
  .info {
    position: absolute;
    left: 0.8rem;
    bottom: 0.8rem;
    background: #fff;
    border: 1px solid #ddd;
    border-radius: 6px;
    padding: 0.35rem 0.6rem;
    font-size: 0.8rem;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  }
  .edit-panel {
    position: absolute;
    right: 0.8rem;
    top: 0.8rem;
    width: 250px;
    background: #fff;
    border: 1px solid #ddd;
    border-radius: 8px;
    padding: 0.7rem 0.9rem;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.12);
    display: flex;
    flex-direction: column;
    gap: 0.45rem;
  }
  .edit-panel h4 {
    margin: 0;
    font-size: 0.9rem;
  }
  .edit-panel label {
    font-size: 0.72rem;
    color: #666;
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
  }
  .edit-panel textarea,
  .edit-panel input {
    font-size: 0.78rem;
    padding: 0.25rem 0.4rem;
    border: 1px solid #ccc;
    border-radius: 4px;
  }
  .row {
    display: flex;
    gap: 0.3rem;
    flex-wrap: wrap;
  }
  .row button {
    flex: none;
  }
  .danger {
    color: #c62828;
    border-color: #e57373;
  }
  .msg {
    margin: 0;
    font-size: 0.75rem;
    color: #1565c0;
  }
  .info.error {
    color: #c62828;
  }
  .status {
    padding: 2rem;
    color: #666;
  }
  .error {
    color: #c62828;
  }
</style>
