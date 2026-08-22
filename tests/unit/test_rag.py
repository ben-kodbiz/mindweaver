from mindweaver.chat.rag import _extract_json, build_messages
from mindweaver.config import DatabaseConfig, Settings
from mindweaver.database import build_engine, init_database, make_session_factory, session_scope
from mindweaver.models import ChunkRecord, Document
from mindweaver.search.base import SearchHit


def _settings(tmp_path, *, stub: bool = True) -> Settings:
    settings = Settings(
        database=DatabaseConfig(url=f"sqlite:///{tmp_path}/chat.db"),
    )
    if stub:
        settings.llm.provider = "stub"
    return settings


def _indexed_chunks(session, settings) -> None:
    from mindweaver.search.indexing import index_document_chunks

    session.add(
        Document(
            id="doc_1", title="Search Book", original_filename="b.pdf", sha256="a" * 64, file_size=1
        )
    )
    session.flush()
    records = [
        ChunkRecord(
            chunk_id="c1",
            document_id="doc_1",
            position=0,
            page_start=1,
            page_end=1,
            chapter="Chapter 1: Foundations",
            section="Section 1.1 The Problem",
            subsection=None,
            section_path='["Chapter 1: Foundations", "Section 1.1 The Problem"]',
            text=(
                "Memory is the faculty by which information is encoded, stored, "
                "and retrieved in the human brain."
            ),
            token_count=15,
            parent_chunk_id=None,
        ),
        ChunkRecord(
            chunk_id="c2",
            document_id="doc_1",
            position=1,
            page_start=3,
            page_end=3,
            chapter="Chapter 2: Advanced Topics",
            section="Section 2.1 Consolidation",
            subsection=None,
            section_path='["Chapter 2: Advanced Topics", "Section 2.1 Consolidation"]',
            text="Consolidation stabilises memories over time.",
            token_count=6,
            parent_chunk_id=None,
        ),
    ]
    session.add_all(records)
    session.flush()
    index_document_chunks(session, settings, session.get(Document, "doc_1"), records)


def test_build_messages_includes_evidence_source():
    hit = SearchHit(
        chunk_id="c1",
        document_id="doc_1",
        page_start=1,
        page_end=1,
        chapter="Chapter 1",
        section="Section 1.1",
        section_path=["Chapter 1", "Section 1.1"],
        text="The memory paragraph.",
        retrieval_score=0.5,
    )
    messages = build_messages("What is memory?", [hit])
    assert messages[0].role == "system"
    assert "not_found" in messages[0].content
    assert "[1] (document=doc_1" in messages[1].content
    assert "pages=1-1" in messages[1].content
    assert "The memory paragraph." in messages[1].content


def test_extract_json_plain_and_fenced():
    assert (
        _extract_json('{"answer": "hi", "grounding": "supported_by_source", "citations": [1]}')[
            "answer"
        ]
        == "hi"
    )
    assert (
        _extract_json('```json\n{"answer": "hi", "grounding": "inference", "citations": []}\n```')[
            "grounding"
        ]
        == "inference"
    )
    assert _extract_json("no json here") is None


def test_answer_supported_by_source(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    with session_scope(make_session_factory(engine)) as session:
        settings = _settings(tmp_path)
        _indexed_chunks(session, settings)
        from mindweaver.chat.rag import answer_question

        result = answer_question(
            session, settings, "What is the faculty by which information is encoded?"
        )
    assert result.grounding == "supported_by_source"
    assert result.citations
    assert result.citations[0].page_start == 1
    assert result.citations[0].section == "Section 1.1 The Problem"


def test_answer_not_found_when_no_evidence(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    with session_scope(make_session_factory(engine)) as session:
        settings = _settings(tmp_path)
        _indexed_chunks(session, settings)
        from mindweaver.chat.rag import answer_question

        result = answer_question(session, settings, "How do whales photosynthesise underwater?")
    assert result.grounding == "not_found"
    assert result.answer == "I don't know from the provided sources."
    assert result.citations == []


def test_answer_absent_without_calling_llm(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    with session_scope(make_session_factory(engine)) as session:
        settings = _settings(tmp_path)
        _indexed_chunks(session, settings)
        from mindweaver.chat.rag import answer_question
        from mindweaver.llm.stub import StubLLMProvider

        calls: list[int] = []

        class CountingStub(StubLLMProvider):
            def complete(self, messages, **kwargs):
                calls.append(1)
                return super().complete(messages, **kwargs)

        from mindweaver.chat import rag as rag_module

        original = rag_module.get_llm_provider
        rag_module.get_llm_provider = lambda settings: CountingStub()  # type: ignore[assignment]
        try:
            answer_question(session, settings, "Whales photosynthesise underwater?")
        finally:
            rag_module.get_llm_provider = original
    assert calls == []


def test_misleading_question_is_inference(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    with session_scope(make_session_factory(engine)) as session:
        settings = _settings(tmp_path)
        _indexed_chunks(session, settings)
        from mindweaver.chat.rag import answer_question

        result = answer_question(
            session, settings, "This question is misleading: is the sky made of cheese?"
        )
    assert result.grounding == "inference"


def test_invalid_llm_json_falls_back(tmp_path):
    engine = build_engine(_settings(tmp_path))
    init_database(engine)
    with session_scope(make_session_factory(engine)) as session:
        settings = _settings(tmp_path)
        _indexed_chunks(session, settings)
        from mindweaver.chat.rag import answer_question
        from mindweaver.llm.stub import StubLLMProvider

        class BrokenStub(StubLLMProvider):
            def complete(self, messages, **kwargs):
                return "not json at all"

        from mindweaver.chat import rag as rag_module

        original = rag_module.get_llm_provider
        rag_module.get_llm_provider = lambda settings: BrokenStub()  # type: ignore[assignment]
        try:
            result = answer_question(session, settings, "What is memory?")
        finally:
            rag_module.get_llm_provider = original
    assert result.grounding == "inference"
    assert result.answer == "not json at all"
    assert result.citations == []
