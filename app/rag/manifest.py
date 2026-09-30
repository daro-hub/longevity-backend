"""Loads data/manifest.yaml and enforces the one rule that makes citations
possible: ingestion refuses to index any source file not listed here.
Filenames alone are terrible citations ("crea-linee-guida-2018.pdf, p. 42"
means nothing to a reader) — the manifest is what turns that into
"Linee Guida per una Sana Alimentazione — Revisione 2018, CREA, p. 42".
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_MANIFEST_PATH = Path(__file__).parent.parent.parent / "data" / "manifest.yaml"


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class DocMeta:
    filename: str
    doc_id: str
    title: str
    publisher: str
    year: int
    lang: str
    url: str | None = None


_REQUIRED_FIELDS = ("doc_id", "title", "publisher", "year", "lang")


def load_manifest(path: Path | None = None) -> dict[str, DocMeta]:
    manifest_path = path or DEFAULT_MANIFEST_PATH
    if not manifest_path.exists():
        raise ManifestError(f"manifest not found at {manifest_path}")

    with open(manifest_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    entries: dict[str, DocMeta] = {}
    doc_ids_seen: set[str] = set()
    for filename, fields in raw.items():
        missing = [f for f in _REQUIRED_FIELDS if f not in fields]
        if missing:
            raise ManifestError(f"manifest entry '{filename}' missing fields: {missing}")
        doc_id = fields["doc_id"]
        if doc_id in doc_ids_seen:
            raise ManifestError(f"duplicate doc_id in manifest: {doc_id}")
        doc_ids_seen.add(doc_id)
        entries[filename] = DocMeta(
            filename=filename,
            doc_id=doc_id,
            title=fields["title"],
            publisher=fields["publisher"],
            year=fields["year"],
            lang=fields["lang"],
            url=fields.get("url"),
        )
    return entries


def require_listed(filename: str, manifest: dict[str, DocMeta]) -> DocMeta:
    """Raises if filename isn't in the manifest -- this is the actual
    enforcement point, called by the ingest pipeline for every file it's
    about to index. --allow-unlisted on the CLI is the only sanctioned
    bypass, and it's opt-in per the ingest script, not the default.
    """
    meta = manifest.get(filename)
    if meta is None:
        raise ManifestError(
            f"'{filename}' is not listed in the manifest — refusing to index an "
            "unlisted file (every indexed chunk must be citable). Add it to "
            "data/manifest.yaml, or pass --allow-unlisted to override."
        )
    return meta
