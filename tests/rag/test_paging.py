import pytest

from app.rag.paging import PageMap

PAGES = [
    "Page one text.",
    "Page two is a bit longer than page one.",
    "Page three.",
]
SEPARATOR = "\n\n"


def make_map():
    return PageMap.from_pages(PAGES, separator=SEPARATOR)


def test_offset_at_start_of_page_one():
    pm = make_map()
    assert pm.page_for_offset(0) == 1


def test_offset_within_page_one():
    pm = make_map()
    concatenated = SEPARATOR.join(PAGES)
    offset = concatenated.index("one text")
    assert pm.page_for_offset(offset) == 1


def test_offset_within_page_two():
    pm = make_map()
    concatenated = SEPARATOR.join(PAGES)
    offset = concatenated.index("bit longer")
    assert pm.page_for_offset(offset) == 2


def test_offset_within_page_three():
    pm = make_map()
    concatenated = SEPARATOR.join(PAGES)
    offset = concatenated.index("Page three")
    assert pm.page_for_offset(offset) == 3


def test_offset_at_last_character():
    pm = make_map()
    concatenated = SEPARATOR.join(PAGES)
    assert pm.page_for_offset(len(concatenated) - 1) == 3


def test_offset_past_end_clamps_to_last_page():
    pm = make_map()
    concatenated = SEPARATOR.join(PAGES)
    assert pm.page_for_offset(len(concatenated) + 100) == 3


def test_negative_offset_raises():
    pm = make_map()
    with pytest.raises(ValueError):
        pm.page_for_offset(-1)


def test_span_crossing_a_page_boundary():
    pm = make_map()
    concatenated = SEPARATOR.join(PAGES)
    # A span that starts in page one and ends in page two.
    start = concatenated.index("text.")
    end = concatenated.index("bit longer") + len("bit longer")
    page_start, page_end = pm.page_range_for_span(start, end)
    assert page_start == 1
    assert page_end == 2


def test_span_within_a_single_page():
    pm = make_map()
    concatenated = SEPARATOR.join(PAGES)
    start = concatenated.index("bit longer")
    end = start + len("bit longer")
    page_start, page_end = pm.page_range_for_span(start, end)
    assert page_start == page_end == 2


def test_concatenated_text_matches_manual_join():
    pm = make_map()
    assert pm.concatenated_text(PAGES, SEPARATOR) == SEPARATOR.join(PAGES)


def test_single_page_document():
    pm = PageMap.from_pages(["Only one page here."])
    assert pm.page_for_offset(0) == 1
    assert pm.page_for_offset(5) == 1


def test_custom_separator():
    pm = PageMap.from_pages(PAGES, separator="---")
    concatenated = "---".join(PAGES)
    offset = concatenated.index("Page three")
    assert pm.page_for_offset(offset) == 3
