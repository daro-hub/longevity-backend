from fastapi import APIRouter

from app.domain.references import REFERENCES

router = APIRouter()


@router.get("/v1/references")
async def get_references():
    """Exposes every numeric constant used by the domain engine, with its
    citation. This is the difference between "trust me" and "audit me":
    every one of these entries has a matching enforcement test in
    tests/domain/test_references.py.
    """
    return {
        name: {"citation": r.citation, "url": r.url, "note": r.note}
        for name, r in sorted(REFERENCES.items())
    }
