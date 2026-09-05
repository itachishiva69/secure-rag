from app.api.query import parse_retrieved_chunk


def valid_payload():
    return {
        "document_id": 1,
        "filename": "finance-policy.txt",
        "chunk_index": 0,
        "department_ids": [10],
        "text": "Finance department policy information.",
    }


def test_parse_retrieved_chunk_accepts_valid_payload():
    chunk = parse_retrieved_chunk(
        valid_payload()
    )

    assert chunk is not None
    assert chunk.document_id == 1
    assert chunk.filename == "finance-policy.txt"
    assert chunk.chunk_index == 0
    assert chunk.department_ids == [10]
    assert chunk.text == (
        "Finance department policy information."
    )


def test_parse_retrieved_chunk_rejects_missing_document_id():
    payload = valid_payload()
    del payload["document_id"]

    assert parse_retrieved_chunk(payload) is None


def test_parse_retrieved_chunk_rejects_invalid_document_id_type():
    payload = valid_payload()
    payload["document_id"] = "1"

    assert parse_retrieved_chunk(payload) is None


def test_parse_retrieved_chunk_rejects_missing_text():
    payload = valid_payload()
    del payload["text"]

    assert parse_retrieved_chunk(payload) is None


def test_parse_retrieved_chunk_rejects_empty_text():
    payload = valid_payload()
    payload["text"] = ""

    assert parse_retrieved_chunk(payload) is None


def test_parse_retrieved_chunk_rejects_invalid_department_ids():
    payload = valid_payload()
    payload["department_ids"] = ["10"]

    assert parse_retrieved_chunk(payload) is None


def test_parse_retrieved_chunk_rejects_empty_department_ids():
    payload = valid_payload()
    payload["department_ids"] = []

    assert parse_retrieved_chunk(payload) is None


def test_parse_retrieved_chunk_rejects_negative_chunk_index():
    payload = valid_payload()
    payload["chunk_index"] = -1

    assert parse_retrieved_chunk(payload) is None


def test_parse_retrieved_chunk_rejects_empty_filename():
    payload = valid_payload()
    payload["filename"] = ""

    assert parse_retrieved_chunk(payload) is None


def test_parse_retrieved_chunk_rejects_extra_fields():
    payload = valid_payload()
    payload["unexpected"] = "should not be accepted"

    assert parse_retrieved_chunk(payload) is None