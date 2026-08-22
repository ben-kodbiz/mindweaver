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
  layout: Record<string, unknown>
): Promise<void> {
  await fetch(`/api/v1/documents/${documentId}/mindmap/preferences`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(layout),
  });
}

export interface SourceRegion {
  page_number: number;
  bbox?: { left: number; top: number; right: number; bottom: number };
  text: string;
}

export function getChunkSource(documentId: string, chunkId: string): Promise<{ regions: SourceRegion[] }> {
  return get(`/api/v1/documents/${documentId}/chunks/${encodeURIComponent(chunkId)}/source`);
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
  confirm: boolean
): Promise<SelectionCandidates> {
  const res = await fetch(
    `/api/v1/documents/${documentId}/mindmap/selection`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, page_number: pageNumber, confirm }),
    }
  );
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

export function getNodeEvidence(documentId: string, nodeId: string): Promise<NodeEvidence> {
  return get(`/api/v1/documents/${documentId}/mindmap/nodes/${encodeURIComponent(nodeId)}/evidence`);
}

export interface RelatedItem {
  node_id: string;
  label: string;
  relation?: string | null;
  score?: number | null;
}

export function getRelatedNodes(documentId: string, nodeId: string): Promise<RelatedItem[]> {
  return get(`/api/v1/documents/${documentId}/mindmap/nodes/${encodeURIComponent(nodeId)}/related`);
}

export interface ExplainResult {
  node_id: string;
  label: string;
  explanation: string;
  grounding: string;
  citations: { chunk_id: string; page_start: number; page_end: number; section?: string | null }[];
  related_concepts: RelatedItem[];
}

export async function explainNode(
  documentId: string,
  nodeId: string
): Promise<ExplainResult> {
  const res = await fetch(
    `/api/v1/documents/${documentId}/mindmap/nodes/${encodeURIComponent(nodeId)}/explain`,
    { method: 'POST' }
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as ExplainResult;
}

export async function expandNode(
  documentId: string,
  nodeId: string
): Promise<MindMap> {
  const res = await fetch(
    `/api/v1/documents/${documentId}/mindmap/nodes/${encodeURIComponent(nodeId)}/expand`,
    { method: 'POST' }
  );
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const body = await res.json();
  return body.mindmap as MindMap;
}
