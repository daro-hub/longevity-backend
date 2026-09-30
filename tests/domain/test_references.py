"""Enforces that every numeric constant exported by references.py has a
citation. This is the mechanism, not discipline: a new magic number with no
matching entry in REFERENCES fails this test.
"""

from __future__ import annotations

from app.domain import references as ref


def _exported_numeric_names() -> set[str]:
    names = set()
    for name, value in vars(ref).items():
        if name.startswith("_") or name.isupper() is False:
            continue
        if name in ("Reference",):
            continue
        if isinstance(value, (int, float)):
            names.add(name)
        elif isinstance(value, dict) and value:
            # dict of enum -> number, e.g. ACTIVITY_MULTIPLIERS
            if all(isinstance(v, (int, float)) for v in value.values()):
                names.add(name)
        elif isinstance(value, tuple) and value and all(isinstance(v, (int, float, str)) for v in value):
            names.add(name)
    return names


def test_every_numeric_constant_has_a_source():
    numeric_names = _exported_numeric_names()
    missing = sorted(numeric_names - set(ref.REFERENCES.keys()))
    assert not missing, f"Numeric constants missing a REFERENCES entry: {missing}"


def test_no_stale_reference_entries():
    numeric_names = _exported_numeric_names()
    stale = sorted(set(ref.REFERENCES.keys()) - numeric_names)
    assert not stale, f"REFERENCES entries for names that no longer exist: {stale}"


def test_every_reference_has_a_citation_string():
    for name, reference in ref.REFERENCES.items():
        assert reference.citation, f"{name} has an empty citation"
