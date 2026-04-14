from app.services.rag_graph import (
    MAX_RETRIES,
    SIMILARITY_THRESHOLD,
    _extract_json,
    _route_after_evaluation,
)


def test_route_good_chunks():
    state = {
        "retrieved_chunks": [{"similarity": 0.8, "content": "text"}],
        "retry_count": 0,
    }
    assert _route_after_evaluation(state) == "rerank"


def test_route_no_chunks():
    state = {"retrieved_chunks": [], "retry_count": 0}
    assert _route_after_evaluation(state) == "reformulate"


def test_route_low_similarity():
    state = {
        "retrieved_chunks": [{"similarity": SIMILARITY_THRESHOLD - 0.1, "content": "text"}],
        "retry_count": 0,
    }
    assert _route_after_evaluation(state) == "reformulate"


def test_route_max_retries_forces_rerank():
    state = {
        "retrieved_chunks": [],
        "retry_count": MAX_RETRIES,
    }
    assert _route_after_evaluation(state) == "rerank"


def test_route_max_retries_with_low_similarity():
    state = {
        "retrieved_chunks": [{"similarity": 0.1, "content": "text"}],
        "retry_count": MAX_RETRIES,
    }
    assert _route_after_evaluation(state) == "rerank"


def test_extract_json_strips_code_fences():
    raw = '```json\n{"key": "value"}\n```'
    result = _extract_json(raw)
    assert result == '{"key": "value"}'


def test_extract_json_plain_text():
    raw = '{"key": "value"}'
    assert _extract_json(raw) == '{"key": "value"}'


def test_extract_json_strips_whitespace():
    raw = '  \n {"key": "value"}  \n '
    assert _extract_json(raw) == '{"key": "value"}'
