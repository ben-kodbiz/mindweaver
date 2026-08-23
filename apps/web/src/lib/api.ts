import type { DocumentInfo, MindMap } from "./types";

async function get<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

export function listDocuments(): Promise<{
  items: DocumentInfo[];
  total: number;
}> {
  return get("/api/v1/documents");
}

export async function deleteDocument(documentId: string): Promise<void> {
  const res = await fetch(`/api/v1/documents/${documentId}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.error?.message ?? `HTTP ${res.status}`);
  }
}

export function getMindMap(documentId: string): Promise<MindMap> {
  return get(`/api/v1/documents/${documentId}/mindmap`);
}

export function getPreferences(
  documentId: string,
): Promise<Record<string, unknown>> {
  return get(`/api/v1/documents/${documentId}/mindmap/preferences`);
}

export async function savePreferences(
  documentId: string,
  layout: Record<string, unknown>,
): Promise<void> {
  await fetch(`/api/v1/documents/${documentId}/mindmap/preferences`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(layout),
  });
}

export interface SourceRegion {
  page_number: number;
  bbox?: { left: number; top: number; right: number; bottom: number };
  text: string;
}

export function getChunkSource(
  documentId: string,
  chunkId: string,
): Promise<{ regions: SourceRegion[] }> {
  return get(
    `/api/v1/documents/${documentId}/chunks/${encodeURIComponent(chunkId)}/source`,
  );
}

export interface SelectionCandidates {
  candidates: { nodes: { id: string; label: string }[]; edges: unknown[] };
  added: boolean;
  warnings: string[];
}

export async function addSelection(
  documentId: string,
  text: string,
  pageNumber: number,
  confirm: boolean,
): Promise<SelectionCandidates> {
  const res = await fetch(`/api/v1/documents/${documentId}/mindmap/selection`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, page_number: pageNumber, confirm }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as SelectionCandidates;
}

export interface EvidenceChunk {
  chunk_id: string;
  page_start: number;
  page_end: number;
  section_path: string[];
  text: string;
}

export interface NodeEvidence {
  node_id: string;
  label: string;
  pages: number[];
  chunks: EvidenceChunk[];
}

export function getNodeEvidence(
  documentId: string,
  nodeId: string,
): Promise<NodeEvidence> {
  return get(
    `/api/v1/documents/${documentId}/mindmap/nodes/${encodeURIComponent(nodeId)}/evidence`,
  );
}

export interface RelatedItem {
  node_id: string;
  label: string;
  relation?: string | null;
  score?: number | null;
}

export function getRelatedNodes(
  documentId: string,
  nodeId: string,
): Promise<RelatedItem[]> {
  return get(
    `/api/v1/documents/${documentId}/mindmap/nodes/${encodeURIComponent(nodeId)}/related`,
  );
}

export interface ExplainResult {
  node_id: string;
  label: string;
  explanation: string;
  grounding: string;
  citations: {
    chunk_id: string;
    page_start: number;
    page_end: number;
    section?: string | null;
  }[];
  related_concepts: RelatedItem[];
}

export async function explainNode(
  documentId: string,
  nodeId: string,
): Promise<ExplainResult> {
  const res = await fetch(
    `/api/v1/documents/${documentId}/mindmap/nodes/${encodeURIComponent(nodeId)}/explain`,
    { method: "POST" },
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as ExplainResult;
}

export async function expandNode(
  documentId: string,
  nodeId: string,
): Promise<MindMap> {
  const res = await fetch(
    `/api/v1/documents/${documentId}/mindmap/nodes/${encodeURIComponent(nodeId)}/expand`,
    { method: "POST" },
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const body = await res.json();
  return body.mindmap as MindMap;
}

export interface GraphNodeData {
  id: string;
  label: string;
  type: string;
  definition: string;
  source_chunks: string[];
  page_numbers?: number[];
  note?: string;
  color?: string | null;
  tags?: string[];
  is_important?: boolean;
  is_bookmarked?: boolean;
  is_user_created: boolean;
}

export interface GraphEdgeData {
  source: string;
  target: string;
  relation: string;
  note: string;
  source_chunks: string[];
  is_inference: boolean;
}

export interface GraphData {
  document_id: string;
  version: number;
  nodes: GraphNodeData[];
  edges: GraphEdgeData[];
}

export function getGraph(
  documentId: string,
  options: {
    node_types?: string[];
    relations?: string[];
    focus_node_id?: string | null;
    limit?: number;
  } = {},
): Promise<GraphData> {
  const params = new URLSearchParams();
  for (const t of options.node_types ?? []) params.append("node_types", t);
  for (const r of options.relations ?? []) params.append("relations", r);
  if (options.focus_node_id) params.set("focus_node_id", options.focus_node_id);
  if (options.limit) params.set("limit", String(options.limit));
  const qs = params.toString();
  return get(`/api/v1/documents/${documentId}/graph${qs ? `?${qs}` : ""}`);
}

export async function post<T>(url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.error?.message ?? `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

export interface GraphNodeFull extends GraphNodeData {
  note: string;
  color: string | null;
  tags: string[];
  is_important: boolean;
  is_bookmarked: boolean;
}

export function createPersonalNode(
  documentId: string,
  payload: {
    label: string;
    node_type?: string;
    note?: string;
    color?: string | null;
    tags?: string[];
  },
): Promise<GraphNodeData> {
  return post(`/api/v1/documents/${documentId}/graph/nodes`, payload);
}

export async function updateGraphNode(
  documentId: string,
  nodeId: string,
  updates: Partial<
    Pick<GraphNodeData, "label"> & {
      note: string;
      color: string | null;
      tags: string[];
      is_important: boolean;
      is_bookmarked: boolean;
    }
  >,
): Promise<GraphNodeFull> {
  const res = await fetch(
    `/api/v1/documents/${documentId}/graph/nodes/${encodeURIComponent(nodeId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    },
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as GraphNodeFull;
}

export async function deleteGraphNode(
  documentId: string,
  nodeId: string,
): Promise<void> {
  await fetch(
    `/api/v1/documents/${documentId}/graph/nodes/${encodeURIComponent(nodeId)}`,
    { method: "DELETE" },
  );
}

export function createConnection(
  documentId: string,
  payload: { source: string; target: string; relation?: string; note?: string },
): Promise<unknown> {
  return post(`/api/v1/documents/${documentId}/graph/edges`, payload);
}

export async function removeConnection(
  documentId: string,
  payload: { source: string; target: string; relation: string },
): Promise<void> {
  await fetch(`/api/v1/documents/${documentId}/graph/edges`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function mergeNodes(
  documentId: string,
  nodeId: string,
  into: string,
): Promise<GraphNodeFull> {
  return post(
    `/api/v1/documents/${documentId}/graph/nodes/${encodeURIComponent(nodeId)}/merge`,
    { into },
  );
}

export function undoGraph(documentId: string): Promise<{ undone: string }> {
  return post(`/api/v1/documents/${documentId}/graph/undo`);
}

export function redoGraph(documentId: string): Promise<{ redone: string }> {
  return post(`/api/v1/documents/${documentId}/graph/redo`);
}

export interface IntelStatus {
  enabled: boolean;
  node_expansion: { enabled: boolean };
}

export function getIntelStatus(): Promise<IntelStatus> {
  return get("/api/v1/intelligence/status");
}

export interface IntelProposalChild {
  label: string;
  relationship: string;
  description: string;
  evidence: { chunk_id: string; page_number: number }[];
}

export async function aiExpandNode(
  documentId: string,
  nodeId: string,
): Promise<{
  proposal: {
    node_id: string;
    children: IntelProposalChild[];
    warnings: string[];
  };
}> {
  return post(
    `/api/v1/intelligence/mindmap/expand?document_id=${encodeURIComponent(documentId)}&node_id=${encodeURIComponent(nodeId)}`,
  );
}

export async function acceptAiProposal(
  documentId: string,
  nodeId: string,
  children: IntelProposalChild[],
): Promise<{
  accepted_count: number;
  created: { id: string; label: string }[];
  errors: string[];
}> {
  return post(
    `/api/v1/intelligence/mindmap/nodes/${encodeURIComponent(nodeId)}/accept?document_id=${encodeURIComponent(documentId)}`,
    { children },
  );
}
