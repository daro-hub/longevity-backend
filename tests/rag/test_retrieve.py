from types import SimpleNamespace

from app.rag.retrieve import filter_by_threshold, retrieve


def match(score, text="some text", extra=None):
    metadata = {"text": text}
    if extra:
        metadata.update(extra)
    return SimpleNamespace(score=score, metadata=metadata)


def test_keeps_matches_above_threshold():
    matches = [match(0.8), match(0.6), match(0.5)]
    kept = filter_by_threshold(matches, min_score=0.4, keep_above_threshold=4)
    assert len(kept) == 3


def test_stops_at_first_below_threshold_since_sorted_descending():
    matches = [match(0.8), match(0.3), match(0.9)]  # deliberately out of order after index 1
    kept = filter_by_threshold(matches, min_score=0.4, keep_above_threshold=4)
    # Only the first match clears the bar; the function trusts the sorted
    # contract and stops at the first failure rather than scanning on.
    assert len(kept) == 1


def test_nothing_above_threshold_returns_empty():
    matches = [match(0.2), match(0.1)]
    kept = filter_by_threshold(matches, min_score=0.4)
    assert kept == []


def test_respects_keep_above_threshold_cap():
    matches = [match(0.9), match(0.8), match(0.7), match(0.6), match(0.5)]
    kept = filter_by_threshold(matches, min_score=0.1, keep_above_threshold=2)
    assert len(kept) == 2
    assert kept[0].score == 0.9
    assert kept[1].score == 0.8


def test_skips_matches_with_no_text_metadata():
    matches = [match(0.9, text=None), match(0.8)]
    kept = filter_by_threshold(matches, min_score=0.1)
    assert len(kept) == 1
    assert kept[0].score == 0.8


def test_empty_matches_list():
    assert filter_by_threshold([]) == []


def test_metadata_is_preserved_on_kept_chunks():
    matches = [match(0.9, extra={"doc_id": "crea-2018", "page_start": 12})]
    kept = filter_by_threshold(matches, min_score=0.1)
    assert kept[0].metadata["doc_id"] == "crea-2018"
    assert kept[0].metadata["page_start"] == 12


def test_retrieve_calls_index_query_and_filters():
    fake_index = SimpleNamespace(
        query=lambda vector, top_k, include_metadata, namespace: SimpleNamespace(
            matches=[match(0.9), match(0.2)]
        )
    )
    kept = retrieve(fake_index, [0.1, 0.2, 0.3], min_score=0.5)
    assert len(kept) == 1
    assert kept[0].score == 0.9
