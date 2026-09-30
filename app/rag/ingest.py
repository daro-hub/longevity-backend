"""Prepares chunks for indexing: manifest-checked, page-accurate, content-
addressed. Kept separate from the actual network calls (embeddings,
Pinecone upsert) so the assembly logic is testable without either.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from app.rag.chunking import chunk_text
from app.rag.ids import chunk_id, content_hash
from app.rag.manifest import DocMeta, require_listed
from app.rag.paging import PageMap

INGEST_VERSION = 2


@dataclass(frozen=True)
class PreparedChunk:
    id: str
    text: str
    metadata: dict


def prepare_chunks_from_pages(
    pages: list[str],
    doc_id: str,
    source_file: str,
    source_title: str,
    lang: str,
    indexed_at: str | None = None,
) -> list[PreparedChunk]:
    """Pure assembly logic: given a document already split into pages,
    concatenates them (preserving the offset->page mapping), chunks the
    result, and resolves each chunk's page span. No I/O.
    """
    if not pages:
        return []

    page_map = PageMap.from_pages(pages)
    full_text = page_map.concatenated_text(pages)
    spans = chunk_text(full_text)
    timestamp = indexed_at or dt.datetime.now(dt.UTC).isoformat()

    prepared = []
    for span in spans:
        page_start, page_end = page_map.page_range_for_span(
            span.start_offset, span.start_offset + len(span.text)
        )
        cid = chunk_id(doc_id, span.chunk_index, span.text)
        prepared.append(
            PreparedChunk(
                id=cid,
                text=span.text,
                metadata={
                    "text": span.text,
                    "doc_id": doc_id,
                    "source_file": source_file,
                    "source_title": source_title,
                    "page_start": page_start,
                    "page_end": page_end,
                    "chunk_index": span.chunk_index,
                    "char_start": span.start_offset,
                    "lang": lang,
                    "content_hash": content_hash(span.text),
                    "ingest_version": INGEST_VERSION,
                    "indexed_at": timestamp,
                },
            )
        )
    return prepared


def load_pdf_pages(path: Path) -> list[str]:
    """Thin wrapper around PyPDFLoader -- not unit-tested against a real
    PDF (the corpus files are gitignored, not committed, so CI can't rely
    on one being present). prepare_chunks_from_pages above is where the
    actual logic lives and is tested with synthetic pages.
    """
    from langchain_community.document_loaders import PyPDFLoader

    loader = PyPDFLoader(str(path))
    docs = loader.load()
    return [d.page_content for d in docs]


def prepare_document(path: Path, manifest: dict[str, DocMeta]) -> list[PreparedChunk]:
    meta = require_listed(path.name, manifest)
    pages = load_pdf_pages(path)
    return prepare_chunks_from_pages(pages, meta.doc_id, path.name, meta.title, meta.lang)
