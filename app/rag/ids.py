"""Content-addressed vector IDs.

The old scheme (`chunk_id_counter = 1` reset inside `main()`, ids like
"id-1", "id-2", ...) meant every ingestion run overwrote whatever
previously occupied those positional IDs — a second run over a different
or reordered corpus left a spliced index with no way to tell which chunk
belonged to which document. An ID derived from (doc_id, chunk_index,
content hash) makes re-running on unchanged text idempotent (same ID,
same upsert, no-op) and makes edited text produce a new ID rather than
silently overwriting the old one's slot.
"""

from __future__ import annotations

import hashlib


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_id(doc_id: str, chunk_index: int, text: str) -> str:
    return f"{doc_id}:{chunk_index:05d}:{content_hash(text)[:12]}"
