"""Resolves a character offset in a document's concatenated text back to
the page(s) it came from.

The old index_docs.py joined every page into one string
(`"\\n\\n".join(doc.page_content for doc in loaded_docs)`) before chunking
— which is exactly where page numbers got destroyed, and why citations
were impossible before. The fix here keeps that same concatenation (it's
strictly better than splitting per-page: chunks aren't artificially cut at
page boundaries) but builds a page map alongside it, so any character
offset in the concatenated text can be resolved back to a page number.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PageMap:
    """page_lengths[i] is the length, in characters, of page i+1's text as
    it appears in the concatenated document (including the separator that
    follows it, except for the last page).
    """

    page_lengths: tuple[int, ...]
    separator_len: int

    @classmethod
    def from_pages(cls, pages: list[str], separator: str = "\n\n") -> PageMap:
        return cls(page_lengths=tuple(len(p) for p in pages), separator_len=len(separator))

    def page_for_offset(self, char_offset: int) -> int:
        """Returns the 1-indexed page number containing char_offset."""
        if char_offset < 0:
            raise ValueError("char_offset must be >= 0")
        cursor = 0
        for i, length in enumerate(self.page_lengths):
            page_end = cursor + length
            if char_offset < page_end:
                return i + 1
            cursor = page_end + self.separator_len
        # Offset past the end (e.g. exactly at the document's final
        # character, or a chunk boundary rounding to the last index) --
        # clamp to the last page rather than raising.
        return len(self.page_lengths)

    def page_range_for_span(self, start: int, end: int) -> tuple[int, int]:
        """Returns (page_start, page_end) for a [start, end) character span."""
        page_start = self.page_for_offset(start)
        page_end = self.page_for_offset(max(start, end - 1))
        return page_start, page_end

    def concatenated_text(self, pages: list[str], separator: str = "\n\n") -> str:
        return separator.join(pages)
