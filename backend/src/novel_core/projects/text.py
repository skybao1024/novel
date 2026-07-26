"""Mechanical manuscript byte invariants."""

from __future__ import annotations

from hashlib import sha256


def manuscript_revision(content: bytes) -> str:
    """Return the content-addressed revision for exact manuscript bytes."""

    return f"sha256:{sha256(content).hexdigest()}"
