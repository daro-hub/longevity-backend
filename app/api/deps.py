"""Request-scoped dependencies.

Auth is intentionally NOT implemented here yet — it needs a Supabase
project that does not exist yet (the personal one this app requires,
never AmuseUp's). ``current_user`` below is a placeholder that always
returns an anonymous stand-in so routes can be wired up now and switched to
real JWT verification later (Phase 4 of the project plan) without changing
route signatures. Do not build any authorization decision on top of this
stub — it is not a security boundary.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Request


def request_id(request: Request) -> str:
    existing = request.headers.get("x-request-id")
    return existing or str(uuid.uuid4())


@dataclass(frozen=True)
class CurrentUser:
    id: str
    is_anonymous: bool


def current_user_stub() -> CurrentUser:
    """Placeholder until Supabase JWT verification lands (Phase 4).
    Returns a fixed anonymous identity — every request is treated as the
    same anonymous user, which is fine for the stateless /v1/targets route
    but MUST NOT be used to gate anything sensitive.
    """
    return CurrentUser(id="anonymous-stub", is_anonymous=True)
