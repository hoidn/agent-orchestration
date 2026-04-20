"""Adjudicated-provider runtime helpers.

The package owns deterministic sidecar paths, baseline snapshots, evidence
packet construction, selection, ledgers, resume sidecars, and selected-output
promotion. Public names are re-exported here to preserve the original
``orchestrator.workflow.adjudication`` import path while keeping implementation
responsibilities split by runtime concern.
"""

from __future__ import annotations

from .models import time as time
from .baseline import create_baseline_snapshot, load_baseline_manifest, prepare_candidate_workspace_from_baseline
from .evidence import build_evaluation_packet
from .ledger import generate_score_ledger_rows, load_score_ledger_rows, materialize_run_score_ledger, materialize_score_ledger_mirror
from .models import (
    BASELINE_COPY_POLICY,
    EVALUATION_PACKET_SCHEMA,
    EVALUATOR_JSON_CONTRACT,
    LOCAL_SECRET_DENYLIST,
    SCORE_ROW_SCHEMA,
    SECRET_DETECTION_POLICY,
    AdjudicationDeadline,
    AdjudicationVisitPaths,
    BaselineExcludedPathError,
    BaselineManifest,
    CandidateRuntimePaths,
    EvaluatorOutputError,
    EvidencePacketError,
    LedgerConflictError,
    ManifestEntry,
    PathSurface,
    PromotionConflictError,
    PromotionResult,
    SelectionResult,
    adjudication_outcome,
)
from .paths import adjudication_visit_paths, candidate_metadata_path, candidate_paths
from . import promotion as _promotion_module
from .promotion import _validate_promotion_parent, _validate_promotion_staging
from .resume import (
    adjudication_sidecars_exist,
    load_candidate_metadata,
    load_scorer_resolution_failure,
    load_scorer_snapshot,
    persist_candidate_metadata,
)
from .scoring import (
    parse_evaluator_output,
    persist_scorer_resolution_failure,
    persist_scorer_snapshot,
    scorer_identity_hash,
    select_candidate,
)


def promote_candidate_outputs(*args, **kwargs):
    """Promote selected outputs while preserving legacy root monkeypatch hooks."""
    _promotion_module._validate_promotion_parent = _validate_promotion_parent
    _promotion_module._validate_promotion_staging = _validate_promotion_staging
    return _promotion_module.promote_candidate_outputs(*args, **kwargs)


__all__ = [
    "BASELINE_COPY_POLICY",
    "EVALUATION_PACKET_SCHEMA",
    "EVALUATOR_JSON_CONTRACT",
    "LOCAL_SECRET_DENYLIST",
    "SCORE_ROW_SCHEMA",
    "SECRET_DETECTION_POLICY",
    "AdjudicationDeadline",
    "AdjudicationVisitPaths",
    "BaselineExcludedPathError",
    "BaselineManifest",
    "CandidateRuntimePaths",
    "EvaluatorOutputError",
    "EvidencePacketError",
    "LedgerConflictError",
    "ManifestEntry",
    "PathSurface",
    "PromotionConflictError",
    "PromotionResult",
    "SelectionResult",
    "adjudication_outcome",
    "adjudication_sidecars_exist",
    "adjudication_visit_paths",
    "build_evaluation_packet",
    "candidate_metadata_path",
    "candidate_paths",
    "create_baseline_snapshot",
    "generate_score_ledger_rows",
    "load_baseline_manifest",
    "load_candidate_metadata",
    "load_score_ledger_rows",
    "load_scorer_resolution_failure",
    "load_scorer_snapshot",
    "materialize_run_score_ledger",
    "materialize_score_ledger_mirror",
    "parse_evaluator_output",
    "persist_candidate_metadata",
    "persist_scorer_resolution_failure",
    "persist_scorer_snapshot",
    "prepare_candidate_workspace_from_baseline",
    "promote_candidate_outputs",
    "scorer_identity_hash",
    "select_candidate",
]
