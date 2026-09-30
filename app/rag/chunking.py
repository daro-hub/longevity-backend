"""Text splitting with character offsets preserved, so each chunk can be
resolved back to a page via app.rag.paging.PageMap.
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200


@dataclass(frozen=True)
class ChunkSpan:
    text: str
    start_offset: int  # character offset into the concatenated document text
    chunk_index: int


def chunk_text(
    text: str, chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP
) -> list[ChunkSpan]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
        add_start_index=True,
    )
    # create_documents (rather than split_text) is what actually populates
    # metadata["start_index"] -- split_text alone discards offsets.
    docs = splitter.create_documents([text])
    return [
        ChunkSpan(text=doc.page_content, start_offset=doc.metadata["start_index"], chunk_index=i)
        for i, doc in enumerate(docs)
    ]
