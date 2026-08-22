from fixtures.pdf import make_search_book_pdf
from mindweaver.database import make_session_factory, session_scope
from mindweaver.search.evaluation import (
    EVALUATION_SUITE,
    EvalQuestion,
    run_evaluation,
)


def _upload(client):
    resp = client.post(
        "/api/v1/documents",
        files={"file": ("searchbook.pdf", make_search_book_pdf(), "application/pdf")},
    )
    assert resp.status_code == 201
    return resp.json()


def test_evaluation_recall_and_mrr(client, app_settings):
    _upload(client)
    with session_scope(make_session_factory(client.app.state.engine)) as session:
        report = run_evaluation(session, app_settings, EVALUATION_SUITE, k=5)
    assert report.total == len(EVALUATION_SUITE) == 5
    assert report.recall_at_k >= 0.8
    assert report.mrr >= 0.6


def test_evaluation_negative_question_has_no_hits(client, app_settings):
    _upload(client)
    question = EvalQuestion(
        question="How do whales photosynthesise underwater?",
        expected_document="",
        expected_pages=[],
        expected_concepts=[],
        category="negative",
    )
    with session_scope(make_session_factory(client.app.state.engine)) as session:
        report = run_evaluation(session, app_settings, [question])
    result = report.results[0]
    assert result.relevant is True  # correctly returning no results
    assert result.hit_count == 0


def test_evaluation_exact_question_rank_one(client, app_settings):
    _upload(client)
    question = next(q for q in EVALUATION_SUITE if q.category == "exact")
    with session_scope(make_session_factory(client.app.state.engine)) as session:
        report = run_evaluation(session, app_settings, [question])
    result = report.results[0]
    assert result.relevant is True
    assert result.rank == 1
