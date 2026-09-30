from app.rag.citations import build_citations, build_context_blocks, strip_invalid_markers
from app.rag.retrieve import RetrievedChunk


def make_chunk(text, doc_id="crea-2018", title="Linee Guida", page_start=12, page_end=12, score=0.7):
    return RetrievedChunk(
        text=text,
        metadata={
            "doc_id": doc_id,
            "source_title": title,
            "page_start": page_start,
            "page_end": page_end,
            "url": "https://example.org",
        },
        score=score,
    )


def test_build_context_blocks_numbers_from_one():
    chunks = [make_chunk("first"), make_chunk("second")]
    blocks = build_context_blocks(chunks)
    assert "[1] first" in blocks
    assert "[2] second" in blocks


def test_build_context_blocks_empty_list():
    assert build_context_blocks([]) == ""


def test_build_citations_basic_fields():
    chunks = [make_chunk("text", doc_id="crea-2018", page_start=42, page_end=42, score=0.512345)]
    citations = build_citations(chunks)
    assert citations[0]["n"] == 1
    assert citations[0]["doc_id"] == "crea-2018"
    assert citations[0]["page"] == "42"
    assert citations[0]["score"] == 0.512


def test_build_citations_page_range_when_spanning_pages():
    chunks = [make_chunk("text", page_start=42, page_end=43)]
    citations = build_citations(chunks)
    assert citations[0]["page"] == "42-43"


def test_build_citations_snippet_truncated():
    long_text = "x" * 500
    chunks = [make_chunk(long_text)]
    citations = build_citations(chunks)
    assert len(citations[0]["snippet"]) == 200


def test_strip_invalid_markers_keeps_valid_ones():
    answer = "Il fabbisogno proteico è descritto in [1] e [2]."
    result = strip_invalid_markers(answer, num_citations=2)
    assert result == answer


def test_strip_invalid_markers_removes_out_of_range():
    answer = "Vedi [1] e [5] per dettagli."
    result = strip_invalid_markers(answer, num_citations=1)
    assert "[1]" in result
    assert "[5]" not in result


def test_strip_invalid_markers_removes_all_when_zero_citations():
    answer = "Nessuna fonte ma cito [1] comunque."
    result = strip_invalid_markers(answer, num_citations=0)
    assert "[1]" not in result


def test_strip_invalid_markers_no_markers_present():
    answer = "Risposta senza citazioni."
    assert strip_invalid_markers(answer, num_citations=3) == answer


def test_strip_invalid_markers_marker_zero_is_invalid():
    answer = "Riferimento [0] non valido."
    result = strip_invalid_markers(answer, num_citations=3)
    assert "[0]" not in result
