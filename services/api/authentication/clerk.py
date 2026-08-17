"""Shared Clerk authentication configuration types."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ClerkVerificationConfiguration:
    """Offline trust material and allowed parties for Clerk session verification."""

    jwt_key: str = field(repr=False)
    authorized_parties: tuple[str, ...]
