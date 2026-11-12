"""Helper records for currently supported phase/context library forms."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReusableArtifactRequirement:
    """One compiler-derived reusable artifact existence requirement."""

    field_path: tuple[str, ...]
    under: str


