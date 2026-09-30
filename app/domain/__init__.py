"""Pure domain logic: no I/O, no network calls, no clock reads, no LLM calls.

Every function in this package is deterministic and unit-testable without
mocks. This is the part of the system that computes real numbers instead of
asking a language model to guess them.
"""
