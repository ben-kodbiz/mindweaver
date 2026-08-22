"""Cross-document notebooks.

A notebook groups documents so retrieval, the knowledge graph, and concept
comparison can work across books. Source labels keep provenance visible:
every result and every merged node knows which document it came from.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from mindweaver.config import Settings
from mindweaver.graph.types import GraphRead
from mindweaver.models import Document, Notebook, NotebookDocument
from mindweaver.search.service import search


class NotebookError(Exception):
    pass


def create_notebook(session: Session, *, title: str, description: str = "") -> Notebook:
    if not title.strip():
        raise NotebookError("title must not be empty")
    notebook = Notebook(title=title.strip(), description=description)
    session.add(notebook)
    session.flush()
    return notebook


def get_notebook(session: Session, notebook_id: str) -> Notebook | None:
    return session.get(Notebook, notebook_id)


def list_notebooks(session: Session) -> list[dict[str, Any]]:
    rows = session.execute(
        select(
            Notebook,
            func.count(NotebookDocument.document_id).label("document_count"),
        )
        .outerjoin(NotebookDocument, NotebookDocument.notebook_id == Notebook.id)
        .group_by(Notebook.id)
        .order_by(Notebook.updated_at.desc())
    ).all()
    return [
        {
            "id": notebook.id,
            "title": notebook.title,
            "description": notebook.description,
            "document_count": count or 0,
            "created_at": notebook.created_at.isoformat(),
            "updated_at": notebook.updated_at.isoformat(),
        }
        for notebook, count in rows
    ]


def delete_notebook(session: Session, notebook: Notebook) -> None:
    session.delete(notebook)


def add_document(session: Session, notebook: Notebook, document_id: str) -> None:
    document = session.get(Document, document_id)
    if document is None:
        raise NotebookError(f"document not found: {document_id}")
    exists = session.scalar(
        select(NotebookDocument).where(
            NotebookDocument.notebook_id == notebook.id,
            NotebookDocument.document_id == document_id,
        )
    )
    if exists is not None:
        raise NotebookError("document already in notebook")
    session.add(NotebookDocument(notebook_id=notebook.id, document_id=document_id))
    session.flush()


def remove_document(session: Session, notebook: Notebook, document_id: str) -> None:
    session.execute(
        delete(NotebookDocument).where(
            NotebookDocument.notebook_id == notebook.id,
            NotebookDocument.document_id == document_id,
        )
    )
    session.flush()


def list_documents(session: Session, notebook_id: str) -> list[Document]:
    return list(
        session.scalars(
            select(Document)
            .join(NotebookDocument, NotebookDocument.document_id == Document.id)
            .where(NotebookDocument.notebook_id == notebook_id)
            .order_by(Document.created_at)
        ).all()
    )


def _document_graphs(session: Session, notebook: Notebook) -> dict[str, GraphRead]:
    graphs: dict[str, GraphRead] = {}
    for document in list_documents(session, notebook.id):
        from mindweaver.graph.service import get_graph

        graph = get_graph(session, document.id)
        if graph is not None:
            graphs[document.id] = graph
    return graphs


def search_notebook(
    session: Session,
    settings: Settings,
    notebook: Notebook,
    query: str,
    *,
    limit: int | None = None,
) -> dict[str, Any]:
    """Hybrid retrieval across every document in the notebook."""
    document_ids = [doc.id for doc in list_documents(session, notebook.id)]
    if not document_ids:
        return {"query": query, "total": 0, "results": [], "documents": []}
    response = search(
        session,
        settings,
        query,
        document_ids=document_ids,
        with_labels=True,
        limit=limit,
    )
    return {
        "query": response.query,
        "total": response.total,
        "results": [hit.model_dump() for hit in response.results],
        "documents": document_ids,
    }


def _relation_polarity(relation: str) -> str | None:
    """Any claim other than CONTRADICTS takes a positive stance on the pair;
    a CONTRADICTS edge from another document therefore reads as a conflict."""
    if relation == "contradicts":
        return "negative"
    return "positive"


def find_common_concepts(graphs: dict[str, GraphRead]) -> list[dict[str, Any]]:
    presence: dict[str, dict[str, Any]] = {}
    for doc_id, graph in graphs.items():
        for node in graph.nodes:
            entry = presence.setdefault(
                node.id,
                {"node_id": node.id, "label": node.label, "type": node.type.value, "documents": []},
            )
            entry["documents"].append(doc_id)
    return [entry for entry in presence.values() if len(set(entry["documents"])) >= 2]


def find_conflicts(graphs: dict[str, GraphRead]) -> list[dict[str, Any]]:
    """Contradictory claims between documents over the same node pair."""
    conflicts: list[dict[str, Any]] = []
    doc_ids = sorted(graphs.keys())
    seen: set[tuple[str, ...]] = set()
    for i, doc_a in enumerate(doc_ids):
        for doc_b in doc_ids[i + 1 :]:
            for edge_a in graphs[doc_a].edges:
                polarity_a = _relation_polarity(edge_a.relation.value)
                pair_a = frozenset({edge_a.source, edge_a.target})
                for edge_b in graphs[doc_b].edges:
                    polarity_b = _relation_polarity(edge_b.relation.value)
                    if polarity_a is None or polarity_b is None:
                        continue
                    pair_b = frozenset({edge_b.source, edge_b.target})
                    if pair_a != pair_b or pair_a == frozenset():
                        continue
                    if polarity_a != polarity_b:
                        key = tuple(
                            sorted([doc_a + edge_a.relation.value + doc_b + edge_b.relation.value])
                        )
                        if key in seen:
                            continue
                        seen.add(key)
                        conflicts.append(
                            {
                                "document_a": doc_a,
                                "document_b": doc_b,
                                "nodes": sorted(pair_a),
                                "claim_a": edge_a.relation.value,
                                "claim_b": edge_b.relation.value,
                            }
                        )
    return conflicts


def compare_documents(session: Session, notebook: Notebook) -> dict[str, Any]:
    """Common concepts, per-document uniques, and conflicting relations."""
    graphs = _document_graphs(session, notebook)

    presence: dict[str, set[str]] = {}
    labels: dict[str, str] = {}
    for doc_id, graph in graphs.items():
        for node in graph.nodes:
            presence.setdefault(node.id, set()).add(doc_id)
            labels[node.id] = node.label

    common = [
        {"node_id": node_id, "label": label, "documents": sorted(docs)}
        for node_id, docs in presence.items()
        if len(docs) >= 2
        for label in [labels[node_id]]
    ]
    common.sort(key=lambda item: (-len(item["documents"]), item["label"]))

    unique_by_document: dict[str, list[str]] = {}
    for doc_id, graph in graphs.items():
        unique_by_document[doc_id] = [
            node.label for node in graph.nodes if len(presence.get(node.id, set())) <= 1
        ]

    conflicts = find_conflicts(graphs)
    for conflict in conflicts:
        conflict["nodes"] = [labels.get(node_id, node_id) for node_id in conflict["nodes"]]

    shared_edges: list[dict[str, Any]] = []
    pair_seen: set[frozenset[str]] = set()
    for _doc_id, graph in graphs.items():
        for edge in graph.edges:
            pair = frozenset({edge.source, edge.target})
            if (
                len(presence.get(edge.source, set())) >= 2
                and len(presence.get(edge.target, set())) >= 2
                and pair not in pair_seen
            ):
                pair_seen.add(pair)
                shared_edges.append(
                    {
                        "source": labels.get(edge.source, edge.source),
                        "target": labels.get(edge.target, edge.target),
                        "relation": edge.relation.value,
                        "is_inference": edge.is_inference,
                    }
                )

    return {
        "notebook_id": notebook.id,
        "document_count": len(graphs),
        "common_concepts": common,
        "unique_by_document": unique_by_document,
        "conflicts": conflicts,
        "shared_relations": shared_edges,
    }


def notebook_graph(session: Session, notebook: Notebook) -> dict[str, Any]:
    """Merge every document graph into one cross-document view.

    Node ids are stable slugs, so the same concept in two books collapses into
    a single node that lists its source documents.
    """
    documents = list_documents(session, notebook.id)
    titles = {doc.id: doc.title or doc.original_filename for doc in documents}
    graphs = _document_graphs(session, notebook)

    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[tuple[str, str, str], dict[str, Any]] = {}

    def _track(item: dict[str, Any], doc_id: str) -> None:
        # Deduplicate by document ID - titles are not unique across books.
        if doc_id not in item["documents"]:
            item["documents"].append(doc_id)

    for doc_id, graph in graphs.items():
        for node in graph.nodes:
            existing = nodes.get(node.id)
            if existing is None:
                nodes[node.id] = {
                    "id": node.id,
                    "label": node.label,
                    "type": node.type.value,
                    "definition": node.definition,
                    "source_chunks": list(node.source_chunks),
                    "documents": [doc_id],
                }
            else:
                existing["source_chunks"] = sorted(
                    set(existing["source_chunks"]) | set(node.source_chunks)
                )
                _track(existing, doc_id)
        for edge in graph.edges:
            key = (edge.source, edge.target, edge.relation.value)
            existing = edges.get(key)
            if existing is None:
                edges[key] = {
                    "source": edge.source,
                    "target": edge.target,
                    "relation": edge.relation.value,
                    "note": edge.note,
                    "is_inference": edge.is_inference,
                    "source_chunks": list(edge.source_chunks),
                    "documents": [doc_id],
                }
            else:
                existing["source_chunks"] = sorted(
                    set(existing["source_chunks"]) | set(edge.source_chunks)
                )
                _track(existing, doc_id)

    return {
        "notebook_id": notebook.id,
        "document_count": len(graphs),
        "document_titles": titles,
        "nodes": list(nodes.values()),
        "edges": list(edges.values()),
    }
