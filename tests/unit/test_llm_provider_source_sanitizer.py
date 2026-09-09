from app.services.llm_provider import (
    clean_generated_answer,
    clean_stream_chunks,
)


def test_clean_generated_answer_removes_bracketed_source_reference():
    answer = (
        "Attention is useful. "
        "[attention_all_you_need.pdf, chunk 10]"
    )

    assert clean_generated_answer(answer) == "Attention is useful."


def test_clean_generated_answer_removes_unicode_source_reference():
    answer = (
        "Attention is useful. "
        "【attention_all_you_need.pdf, chunk 10】"
    )

    assert clean_generated_answer(answer) == "Attention is useful."


def test_clean_stream_chunks_removes_source_reference_split_across_chunks():
    chunks = [
        "Attention is useful ",
        "【attention_all_you_need.pdf, ",
        "chunk 10】",
        " for transformers.",
    ]

    result = "".join(clean_stream_chunks(iter(chunks)))

    assert result == "Attention is useful  for transformers."


def test_clean_stream_chunks_preserves_normal_square_brackets():
    chunks = [
        "The formula is ",
        "[QK^T / sqrt(d_k)]",
        ".",
    ]

    result = "".join(clean_stream_chunks(iter(chunks)))

    assert result == "The formula is [QK^T / sqrt(d_k)]."


def test_clean_stream_chunks_removes_multiple_source_references():
    chunks = [
        "Grounded answer "
        "[attention_all_you_need.pdf, chunk 10] "
        "【attention_all_you_need.pdf, chunk 6】"
    ]

    result = "".join(clean_stream_chunks(iter(chunks)))

    assert result == "Grounded answer  "
