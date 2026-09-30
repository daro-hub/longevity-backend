#!/usr/bin/env python3
"""Ingests documents from data/corpus/ into Pinecone.

Thin CLI wrapper around app.rag.ingest — all the actual logic (manifest
enforcement, page-accurate chunking, content-addressed ids) lives there
and is unit-tested. This script is the I/O shell: file discovery,
embeddings, and the Pinecone upsert.

Replaces the old root-level index_docs.py, which:
  - joined every page into one string before chunking, destroying page
    numbers (this is why citations were impossible before)
  - reset a plain integer counter (`id-1`, `id-2`, ...) on every run, so a
    second run over a different corpus silently overwrote whatever
    occupied those same positional ids
  - printed "Operazione completata" even when a batch failed partway
    through, indistinguishable from a clean run
  - called `pc.create_index(...)` with no `spec=`, a dead code path

Usage:
    python scripts/index_docs.py --namespace v2
    python scripts/index_docs.py --namespace v2 --yes-really --delete-existing
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import get_settings  # noqa: E402
from app.rag.ingest import prepare_document  # noqa: E402
from app.rag.manifest import ManifestError, load_manifest  # noqa: E402

DATA_DIR = Path(__file__).parent.parent / "data" / "corpus"
EMBEDDING_BATCH_SIZE = 50


def discover_files(data_dir: Path) -> list[Path]:
    if not data_dir.exists():
        raise FileNotFoundError(
            f"{data_dir} does not exist. Create it and add source documents "
            f"listed in data/manifest.yaml."
        )
    return sorted(data_dir.glob("*.pdf")) + sorted(data_dir.glob("*.txt"))


def ensure_index_dimension(pc, index_name: str, expected_dim: int) -> None:
    stats = pc.describe_index(index_name)
    actual_dim = stats.dimension
    if actual_dim != expected_dim:
        raise ValueError(
            f"Index '{index_name}' has dimension {actual_dim}, but "
            f"OPENAI_EMBEDDING_DIMENSIONS is {expected_dim}. A mismatch here "
            f"surfaces as a confusing Pinecone error much later -- fix the "
            f"config or the index before ingesting."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--namespace",
        required=True,
        help="Pinecone namespace to write into. No default on purpose -- "
        "accidentally overwriting the default namespace is how the corpus "
        "got corrupted before.",
    )
    parser.add_argument(
        "--allow-unlisted",
        action="store_true",
        help="Index files not present in data/manifest.yaml. Off by default: "
        "an unlisted file can't be cited properly.",
    )
    parser.add_argument(
        "--delete-existing",
        action="store_true",
        help="Delete all vectors in the target namespace before ingesting.",
    )
    parser.add_argument(
        "--yes-really",
        action="store_true",
        help="Required alongside --delete-existing. Confirms you understand "
        "this is destructive for that namespace.",
    )
    args = parser.parse_args()

    if args.delete_existing and not args.yes_really:
        print("[ERRORE] --delete-existing richiede anche --yes-really.", file=sys.stderr)
        return 1

    settings = get_settings()
    if not settings.openai_api_key or not settings.pinecone_api_key or not settings.pinecone_index_name:
        print("[ERRORE] OPENAI_API_KEY / PINECONE_API_KEY / PINECONE_INDEX_NAME mancanti.", file=sys.stderr)
        return 1

    from openai import OpenAI
    from pinecone import Pinecone

    openai_client = OpenAI(api_key=settings.openai_api_key)
    pc = Pinecone(api_key=settings.pinecone_api_key)

    try:
        ensure_index_dimension(pc, settings.pinecone_index_name, settings.openai_embedding_dimensions)
    except Exception as e:
        print(f"[ERRORE] {e}", file=sys.stderr)
        return 1

    index = pc.Index(settings.pinecone_index_name)

    try:
        manifest = load_manifest()
    except ManifestError as e:
        print(f"[ERRORE] {e}", file=sys.stderr)
        return 1

    try:
        files = discover_files(DATA_DIR)
    except FileNotFoundError as e:
        print(f"[ERRORE] {e}", file=sys.stderr)
        return 1

    if not files:
        print(f"[!] Nessun file trovato in {DATA_DIR}.")
        return 0

    if args.delete_existing:
        print(f"[>] Cancellazione di tutti i vettori nel namespace '{args.namespace}'...")
        index.delete(delete_all=True, namespace=args.namespace)

    print(f"[*] Trovati {len(files)} file. Namespace di destinazione: '{args.namespace}'\n")

    all_chunks = []
    for path in files:
        print(f"   [*] Preparazione: {path.name}")
        try:
            if args.allow_unlisted and path.name not in manifest:
                # Bypass the manifest check by faking a minimal DocMeta --
                # only reachable with the explicit flag.
                from app.rag.manifest import DocMeta

                meta = DocMeta(
                    filename=path.name, doc_id=path.stem, title=path.stem, publisher="unknown", year=0, lang="it"
                )
                from app.rag.ingest import load_pdf_pages, prepare_chunks_from_pages

                pages = load_pdf_pages(path)
                chunks = prepare_chunks_from_pages(pages, meta.doc_id, path.name, meta.title, meta.lang)
            else:
                chunks = prepare_document(path, manifest)
        except Exception as e:
            print(f"   [ERRORE] {path.name}: {e}", file=sys.stderr)
            continue
        print(f"      -> {len(chunks)} chunk")
        all_chunks.extend(chunks)

    if not all_chunks:
        print("\n[!] Nessun chunk generato.")
        return 1

    print(f"\n[*] Totale chunk: {len(all_chunks)}. Creazione embedding e upsert...\n")

    total_uploaded = 0
    total_failed_batches = 0
    for i in range(0, len(all_chunks), EMBEDDING_BATCH_SIZE):
        batch = all_chunks[i : i + EMBEDDING_BATCH_SIZE]
        batch_num = i // EMBEDDING_BATCH_SIZE + 1
        total_batches = (len(all_chunks) + EMBEDDING_BATCH_SIZE - 1) // EMBEDDING_BATCH_SIZE
        try:
            response = openai_client.embeddings.create(
                model=settings.openai_embedding_model,
                input=[c.text for c in batch],
                dimensions=settings.openai_embedding_dimensions,
            )
            vectors = [
                {"id": c.id, "values": emb.embedding, "metadata": c.metadata}
                for c, emb in zip(batch, response.data, strict=True)
            ]
            index.upsert(vectors=vectors, namespace=args.namespace)
            total_uploaded += len(vectors)
            print(f"   [OK] Batch {batch_num}/{total_batches}: {len(vectors)} chunk")
        except Exception as e:
            total_failed_batches += 1
            print(f"   [ERRORE] Batch {batch_num}/{total_batches}: {e}", file=sys.stderr)

    print(f"\n[*] Caricati {total_uploaded}/{len(all_chunks)} chunk nel namespace '{args.namespace}'.")

    if total_failed_batches > 0:
        print(
            f"[ERRORE] {total_failed_batches} batch falliti su "
            f"{(len(all_chunks) + EMBEDDING_BATCH_SIZE - 1) // EMBEDDING_BATCH_SIZE} — "
            "run parziale, NON completata con successo.",
            file=sys.stderr,
        )
        return 1

    print("[OK] Operazione completata.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
