from app.rag.ingest import prepare_chunks_from_pages


def make_pages():
    return [
        "Page one. " * 20,  # ~200 chars
        "Page two. " * 150,  # ~1500 chars, spans multiple chunks
        "Page three, the final page.",
    ]


def test_prepare_chunks_produces_at_least_one_chunk_per_document():
    chunks = prepare_chunks_from_pages(make_pages(), "doc1", "file.pdf", "Title", "it")
    assert len(chunks) > 0


def test_every_chunk_has_full_metadata():
    chunks = prepare_chunks_from_pages(make_pages(), "doc1", "file.pdf", "Title", "it")
    for c in chunks:
        assert c.metadata["doc_id"] == "doc1"
        assert c.metadata["source_file"] == "file.pdf"
        assert c.metadata["source_title"] == "Title"
        assert c.metadata["lang"] == "it"
        assert c.metadata["ingest_version"] == 2
        assert c.metadata["indexed_at"]
        assert c.metadata["content_hash"]
        assert c.metadata["page_start"] >= 1
        assert c.metadata["page_end"] >= c.metadata["page_start"]


def test_first_chunk_is_page_one():
    chunks = prepare_chunks_from_pages(make_pages(), "doc1", "file.pdf", "Title", "it")
    assert chunks[0].metadata["page_start"] == 1


def test_last_chunk_reaches_page_three():
    chunks = prepare_chunks_from_pages(make_pages(), "doc1", "file.pdf", "Title", "it")
    assert chunks[-1].metadata["page_end"] == 3


def test_chunk_ids_are_stable_across_runs():
    chunks_a = prepare_chunks_from_pages(make_pages(), "doc1", "file.pdf", "Title", "it")
    chunks_b = prepare_chunks_from_pages(make_pages(), "doc1", "file.pdf", "Title", "it")
    assert [c.id for c in chunks_a] == [c.id for c in chunks_b]


def test_chunk_ids_change_when_text_changes():
    pages_a = make_pages()
    pages_b = make_pages()
    pages_b[0] = "Completely different first page content here."
    chunks_a = prepare_chunks_from_pages(pages_a, "doc1", "file.pdf", "Title", "it")
    chunks_b = prepare_chunks_from_pages(pages_b, "doc1", "file.pdf", "Title", "it")
    assert chunks_a[0].id != chunks_b[0].id


def test_chunk_ids_differ_by_doc_id():
    pages = make_pages()
    chunks_a = prepare_chunks_from_pages(pages, "doc1", "file.pdf", "Title", "it")
    chunks_b = prepare_chunks_from_pages(pages, "doc2", "file.pdf", "Title", "it")
    assert chunks_a[0].id != chunks_b[0].id


def test_chunk_index_is_sequential():
    chunks = prepare_chunks_from_pages(make_pages(), "doc1", "file.pdf", "Title", "it")
    indices = [c.metadata["chunk_index"] for c in chunks]
    assert indices == list(range(len(chunks)))


def test_empty_pages_produces_no_chunks():
    assert prepare_chunks_from_pages([], "doc1", "file.pdf", "Title", "it") == []


def test_content_hash_matches_chunk_text():
    from app.rag.ids import content_hash

    chunks = prepare_chunks_from_pages(make_pages(), "doc1", "file.pdf", "Title", "it")
    for c in chunks:
        assert c.metadata["content_hash"] == content_hash(c.text)


def test_explicit_indexed_at_is_used_verbatim():
    chunks = prepare_chunks_from_pages(
        make_pages(), "doc1", "file.pdf", "Title", "it", indexed_at="2020-01-01T00:00:00+00:00"
    )
    assert all(c.metadata["indexed_at"] == "2020-01-01T00:00:00+00:00" for c in chunks)
