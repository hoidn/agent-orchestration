"""Resume and persisted-sidecar helpers for adjudicated-provider steps."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .models import AdjudicationVisitPaths, CandidateRuntimePaths
from .paths import candidate_metadata_path
from .utils import _atomic_write_text, _canonical_json

def persist_candidate_metadata(candidate: Mapping[str, Any], paths: CandidateRuntimePaths) -> Path:
    """Persist one candidate's terminal/runtime metadata for resume reconciliation."""
    path = candidate_metadata_path(paths)
    _atomic_write_text(path, _canonical_json(dict(candidate)) + "\n")
    return path


def load_candidate_metadata(paths: CandidateRuntimePaths) -> dict[str, Any]:
    path = candidate_metadata_path(paths)
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("candidate metadata must be a JSON object")
    return document


def adjudication_sidecars_exist(
    *,
    visit_paths: AdjudicationVisitPaths,
    candidate_roots: Sequence[Path],
) -> bool:
    """Return true when a prior adjudication attempt left runtime-owned state."""
    paths = [
        visit_paths.baseline_root,
        visit_paths.run_score_ledger_path,
        visit_paths.scorer_root,
        visit_paths.promotion_manifest_path,
        *candidate_roots,
    ]
    return any(path.exists() for path in paths)

def load_scorer_snapshot(scorer_root: Path) -> dict[str, Any] | None:
    path = scorer_root / "metadata.json"
    if not path.exists():
        return None
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("scorer snapshot must be a JSON object")
    return document


def load_scorer_resolution_failure(scorer_root: Path) -> dict[str, Any] | None:
    path = scorer_root / "resolution_failure.json"
    if not path.exists():
        return None
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("scorer resolution failure must be a JSON object")
    return document
