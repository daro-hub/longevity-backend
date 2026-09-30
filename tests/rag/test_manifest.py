import pytest

from app.rag.manifest import ManifestError, load_manifest, require_listed


def test_real_manifest_loads():
    manifest = load_manifest()
    assert "crea-linee-guida-2018.pdf" in manifest
    entry = manifest["crea-linee-guida-2018.pdf"]
    assert entry.doc_id == "crea-2018"
    assert entry.lang == "it"
    assert entry.year == 2018


def test_require_listed_returns_meta_for_known_file():
    manifest = load_manifest()
    meta = require_listed("crea-linee-guida-2018.pdf", manifest)
    assert meta.doc_id == "crea-2018"


def test_require_listed_raises_for_unknown_file():
    manifest = load_manifest()
    with pytest.raises(ManifestError, match="not listed"):
        require_listed("some-random-file.pdf", manifest)


def test_missing_manifest_file_raises(tmp_path):
    with pytest.raises(ManifestError, match="not found"):
        load_manifest(tmp_path / "does_not_exist.yaml")


def test_manifest_entry_missing_required_field(tmp_path):
    bad = tmp_path / "manifest.yaml"
    bad.write_text("some-file.pdf:\n  doc_id: x\n  title: y\n")
    with pytest.raises(ManifestError, match="missing fields"):
        load_manifest(bad)


def test_manifest_duplicate_doc_id_raises(tmp_path):
    bad = tmp_path / "manifest.yaml"
    bad.write_text(
        "file-a.pdf:\n"
        "  doc_id: dup\n  title: A\n  publisher: P\n  year: 2020\n  lang: it\n"
        "file-b.pdf:\n"
        "  doc_id: dup\n  title: B\n  publisher: P\n  year: 2021\n  lang: it\n"
    )
    with pytest.raises(ManifestError, match="duplicate doc_id"):
        load_manifest(bad)


def test_manifest_entry_url_is_optional(tmp_path):
    ok = tmp_path / "manifest.yaml"
    ok.write_text("file.pdf:\n  doc_id: x\n  title: y\n  publisher: p\n  year: 2020\n  lang: en\n")
    manifest = load_manifest(ok)
    assert manifest["file.pdf"].url is None


def test_empty_manifest_file_loads_as_empty_dict(tmp_path):
    empty = tmp_path / "manifest.yaml"
    empty.write_text("")
    assert load_manifest(empty) == {}
