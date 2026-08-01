"""Command-line selection for the run-reference runtime root."""

from __future__ import annotations

from pathlib import Path


def resolve_run_ref_root(raw_root: str | None) -> Path:
    """Return the canonical default or validate one explicit absolute root."""

    if raw_root is None:
        return (
            Path.home() / ".local" / "state" / "orchestrator" / "run-ref"
        ).resolve(strict=False)

    candidate = Path(raw_root)
    resolved = candidate.resolve(strict=False)
    if not candidate.is_absolute() or candidate != resolved:
        raise ValueError("--run-ref-root must be a canonical absolute path")
    return resolved
