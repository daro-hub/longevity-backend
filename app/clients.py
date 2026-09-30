"""Lazily-constructed OpenAI / Pinecone clients.

The old main.py built both clients at *import* time and `raise ValueError`
if a key was missing — on Render that's a boot loop with no diagnosable
startup error. These are built on first use instead, so the process starts
cleanly even with incomplete config, and the /ask route can return a clean
503 with a clear message instead of the whole app failing to boot.
"""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings


@lru_cache
def get_openai_client():
    from openai import OpenAI

    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    return OpenAI(api_key=settings.openai_api_key)


@lru_cache
def get_pinecone_index():
    from pinecone import Pinecone

    settings = get_settings()
    if not settings.pinecone_api_key or not settings.pinecone_index_name:
        raise RuntimeError("PINECONE_API_KEY / PINECONE_INDEX_NAME are not configured")
    pc = Pinecone(api_key=settings.pinecone_api_key)
    # Constructed once and cached, rather than main.py's old behavior of
    # calling pc.Index(...) fresh inside every request handler.
    return pc.Index(settings.pinecone_index_name)
