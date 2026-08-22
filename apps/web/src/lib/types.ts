export interface NodeSourceInfo {
  graph_node_id?: string | null;
  chunk_ids: string[];
  pages: number[];
  section_path: string[];
  is_inference?: boolean | null;
}

export interface MindMapNode {
  id: string;
  label: string;
  node_type: string;
  depth: number;
  children: MindMapNode[];
  source?: NodeSourceInfo | null;
  meta: Record<string, unknown>;
}

export interface MindMap {
  document_id: string;
  root: MindMapNode;
  total_nodes: number;
  max_depth: number;
}

export interface DocumentInfo {
  id: string;
  title: string;
  original_filename: string;
  status: string;
  page_count: number | null;
  created_at: string;
}
