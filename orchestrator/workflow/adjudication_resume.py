"""Resume reconciliation for adjudicated provider execution."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Literal, Mapping, Optional

from .adjudication import (
    AdjudicationVisitPaths,
    BASELINE_COPY_POLICY,
    BaselineManifest,
    LOCAL_SECRET_DENYLIST,
    PromotionConflictError,
    SCORE_ROW_SCHEMA,
    adjudication_sidecars_exist,
    adjudication_visit_paths,
    candidate_metadata_path,
    candidate_paths,
    candidate_visit_root,
    load_baseline_manifest,
    load_candidate_metadata,
    load_score_ledger_rows,
    load_scorer_resolution_failure,
    load_scorer_snapshot,
)
from .adjudication.promotion import (
    derive_promotion_rollback_authority,
    discard_partial_promotion_visit,
)
from .adjudication.utils import _require_canonical_child, _stable_hash
from .adjudication_bindings import AdjudicationExecution
from .adjudication_runtime import AdjudicationRuntime


@dataclass(frozen=True)
class AdjudicationResumeScope:
    """Canonical run-owned coordinates for one adjudication visit."""

    run_root: Path
    frame_scope: str
    step_id: str
    visit_count: int
    visit_paths: AdjudicationVisitPaths


@dataclass(frozen=True)
class AdjudicationResumeDecision:
    """Closed classification of adjudication resume reconciliation."""

    kind: Literal["reuse", "rerun_exact_scope", "integrity_error"]
    scope: AdjudicationResumeScope | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if self.kind == "reuse":
            if self.scope is not None or self.message is not None:
                raise ValueError("reuse decisions cannot carry cleanup state")
            return
        if self.kind == "rerun_exact_scope":
            if self.scope is None or not self.message:
                raise ValueError("exact-scope rerun decisions require scope and message")
            return
        if self.kind == "integrity_error":
            if self.scope is not None or not self.message:
                raise ValueError("integrity decisions require only a message")
            return
        raise ValueError(f"unsupported adjudication resume decision: {self.kind}")

    @classmethod
    def reuse(cls) -> "AdjudicationResumeDecision":
        return cls(kind="reuse")

    @classmethod
    def integrity_error(cls, message: str) -> "AdjudicationResumeDecision":
        return cls(kind="integrity_error", message=message)

    @classmethod
    def rerun_exact_scope(
        cls,
        *,
        scope: AdjudicationResumeScope,
        message: str,
    ) -> "AdjudicationResumeDecision":
        return cls(kind="rerun_exact_scope", scope=scope, message=message)


def classify_adjudication_resume_mismatch(
    *,
    run_root: Path,
    frame_scope: object,
    step_id: object,
    visit_count: object,
    visit_paths: object,
    message: str,
) -> AdjudicationResumeDecision:
    """Return an exact rerun scope only when every owned path is canonical."""

    integrity_message = "adjudication resume scope is not provably canonical"
    if (
        not isinstance(run_root, Path)
        or not isinstance(frame_scope, str)
        or not frame_scope
        or not isinstance(step_id, str)
        or not step_id
        or not isinstance(visit_count, int)
        or isinstance(visit_count, bool)
        or visit_count <= 0
        or not isinstance(visit_paths, AdjudicationVisitPaths)
    ):
        return AdjudicationResumeDecision.integrity_error(integrity_message)

    try:
        expected_paths = adjudication_visit_paths(
            run_root,
            frame_scope,
            step_id,
            visit_count,
        )
        if visit_paths != expected_paths:
            raise ValueError("adjudication visit paths are not canonical")

        for owned_path in expected_paths.__dict__.values():
            _require_canonical_child(owned_path, run_root)
    except (OSError, RuntimeError, TypeError, ValueError):
        return AdjudicationResumeDecision.integrity_error(integrity_message)

    return AdjudicationResumeDecision.rerun_exact_scope(
        scope=AdjudicationResumeScope(
            run_root=run_root,
            frame_scope=frame_scope,
            step_id=step_id,
            visit_count=visit_count,
            visit_paths=expected_paths,
        ),
        message=message,
    )


class AdjudicationResumeMixin:
    def _discard_exact_adjudication_visit(
        self: AdjudicationRuntime,
        execution: AdjudicationExecution,
        scope: AdjudicationResumeScope,
    ) -> str | None:
        """Discard only one independently authorized partial visit."""

        revalidated = classify_adjudication_resume_mismatch(
            run_root=scope.run_root,
            frame_scope=scope.frame_scope,
            step_id=scope.step_id,
            visit_count=scope.visit_count,
            visit_paths=scope.visit_paths,
            message="adjudication visit requires exact-scope cleanup",
        )
        if revalidated.kind != "rerun_exact_scope" or revalidated.scope != scope:
            return "adjudication cleanup scope is not provably canonical"

        expected_paths = adjudication_visit_paths(
            scope.run_root,
            scope.frame_scope,
            scope.step_id,
            scope.visit_count,
        )
        candidate_root = candidate_visit_root(
            scope.run_root,
            scope.frame_scope,
            scope.step_id,
            scope.visit_count,
        )
        promotion_root = expected_paths.promotion_manifest_path.parent
        owned_roots = (
            expected_paths.adjudication_root,
            candidate_root,
            promotion_root,
        )
        try:
            for owned_root in owned_roots:
                _require_canonical_child(owned_root, scope.run_root)
                if owned_root.exists() and not owned_root.is_dir():
                    raise ValueError("owned adjudication visit root is not a directory")

            expected_rollback: Mapping[str, Any] = {
                "selected_candidate_id": None,
                "files": [],
            }
            if promotion_root.exists():
                baseline_manifest = self._validated_cleanup_baseline(
                    execution,
                    scope,
                )
                selected_candidate_id = self._cleanup_selected_candidate_id(
                    execution,
                    scope,
                )
                selected_workspace = candidate_paths(
                    scope.run_root,
                    scope.frame_scope,
                    scope.step_id,
                    scope.visit_count,
                    selected_candidate_id,
                ).workspace
                expected_rollback = derive_promotion_rollback_authority(
                    expected_outputs=execution.resolved_expected_outputs,
                    output_bundle=execution.resolved_output_bundle,
                    candidate_workspace=selected_workspace,
                    parent_workspace=self.workspace,
                    baseline_manifest=baseline_manifest,
                    selected_candidate_id=selected_candidate_id,
                )

            discard_partial_promotion_visit(
                parent_workspace=self.workspace,
                promotion_manifest_path=expected_paths.promotion_manifest_path,
                expected_rollback=expected_rollback,
            )
            for owned_root in (
                candidate_root,
                expected_paths.adjudication_root,
            ):
                if owned_root.exists():
                    shutil.rmtree(owned_root)
        except (OSError, PromotionConflictError, RuntimeError, TypeError, ValueError):
            return "adjudication cleanup failed before a fresh provider attempt"
        return None

    def _validated_cleanup_baseline(
        self: AdjudicationRuntime,
        execution: AdjudicationExecution,
        scope: AdjudicationResumeScope,
    ) -> BaselineManifest:
        manifest = load_baseline_manifest(
            scope.visit_paths.baseline_manifest_path
        )
        payload = {
            "copy_policy": manifest.copy_policy,
            "local_secret_denylist": manifest.local_secret_denylist,
            "workflow_checksum": manifest.workflow_checksum,
            "parent_workspace": manifest.parent_workspace,
            "baseline_workspace": manifest.baseline_workspace,
            "resolved_consumes": manifest.resolved_consumes,
            "included": [asdict(entry) for entry in manifest.included],
            "excluded": [asdict(entry) for entry in manifest.excluded],
            "null_path_results": manifest.null_path_results,
        }
        if (
            manifest.copy_policy != BASELINE_COPY_POLICY
            or manifest.local_secret_denylist != LOCAL_SECRET_DENYLIST
            or manifest.workflow_checksum
            != execution.state.get("workflow_checksum", "")
            or Path(manifest.parent_workspace).resolve()
            != self.workspace.resolve()
            or Path(manifest.baseline_workspace).resolve()
            != scope.visit_paths.baseline_workspace.resolve()
            or _stable_hash(payload) != manifest.baseline_digest
        ):
            raise ValueError(
                "adjudication cleanup baseline is not independently valid"
            )
        return manifest

    def _cleanup_selected_candidate_id(
        self: AdjudicationRuntime,
        execution: AdjudicationExecution,
        scope: AdjudicationResumeScope,
    ) -> str:
        candidates: list[dict[str, Any]] = []
        candidate_configs: dict[str, tuple[int, dict[str, Any]]] = {}
        for index, candidate_config in enumerate(execution.candidates_config):
            if not isinstance(candidate_config, dict):
                raise ValueError("adjudication candidate config is invalid")
            candidate_id = candidate_config.get("id")
            if not isinstance(candidate_id, str) or not candidate_id:
                raise ValueError("adjudication candidate id is invalid")
            if candidate_id in candidate_configs:
                raise ValueError("adjudication candidate id is ambiguous")
            candidate_configs[candidate_id] = (index, candidate_config)
            paths = candidate_paths(
                scope.run_root,
                scope.frame_scope,
                scope.step_id,
                scope.visit_count,
                candidate_id,
            )
            candidate = load_candidate_metadata(paths)
            if (
                candidate.get("candidate_id") != candidate_id
                or candidate.get("candidate_index") != index
                or candidate.get("candidate_config_hash")
                != self._stable_runtime_hash(candidate_config)
            ):
                raise ValueError(
                    "adjudication candidate metadata is not authoritative"
                )
            candidates.append(candidate)

        selection = self._bindings.select_candidate(
            candidates,
            require_score_for_single_candidate=bool(
                execution.selection_config.get(
                    "require_score_for_single_candidate"
                )
                is True
            ),
        )
        selected_candidate_id = selection.selected_candidate_id
        if selection.error_type is not None or not isinstance(
            selected_candidate_id, str
        ):
            raise ValueError("adjudication cleanup selection is not unique")

        rows = load_score_ledger_rows(
            scope.visit_paths.run_score_ledger_path
        )
        if len(rows) != len(candidates):
            raise ValueError("adjudication cleanup ledger is incomplete")
        rows_by_candidate: dict[str, dict[str, Any]] = {}
        for row in rows:
            candidate_id = row.get("candidate_id")
            if (
                not isinstance(candidate_id, str)
                or candidate_id in rows_by_candidate
                or candidate_id not in candidate_configs
            ):
                raise ValueError("adjudication cleanup ledger is ambiguous")
            rows_by_candidate[candidate_id] = row

        selected_rows = [
            row for row in rows if row.get("selected") is True
        ]
        if (
            len(selected_rows) != 1
            or selected_rows[0].get("candidate_id")
            != selected_candidate_id
        ):
            raise ValueError(
                "adjudication cleanup ledger selection does not match"
            )
        for candidate in candidates:
            candidate_id = str(candidate["candidate_id"])
            index, candidate_config = candidate_configs[candidate_id]
            row = rows_by_candidate[candidate_id]
            expected_fields = {
                "row_schema": SCORE_ROW_SCHEMA,
                "run_id": execution.state.get("run_id"),
                "workflow_file": execution.state.get("workflow_file"),
                "workflow_checksum": execution.state.get(
                    "workflow_checksum"
                ),
                "execution_frame_id": execution.execution_frame_id,
                "call_frame_id": execution.call_frame_id,
                "step_id": scope.step_id,
                "step_name": execution.step_name,
                "visit_count": scope.visit_count,
                "candidate_id": candidate_id,
                "candidate_index": index,
                "candidate_config_hash": self._stable_runtime_hash(
                    candidate_config
                ),
                "candidate_status": candidate.get("candidate_status"),
                "score_status": candidate.get("score_status"),
                "score": candidate.get("score"),
                "selected": candidate_id == selected_candidate_id,
            }
            if any(
                row.get(field) != value
                for field, value in expected_fields.items()
            ):
                raise ValueError(
                    "adjudication cleanup ledger is not authoritative"
                )
        return selected_candidate_id

    def _reconcile_adjudication_resume(
        self: AdjudicationRuntime,
        execution: AdjudicationExecution,
    ) -> AdjudicationResumeDecision:
        """Reconcile visit identity and load reusable sidecars when present."""
        resume_visit_count = int(execution.visit_count or 1)
        resume_visit_paths = execution.visit_paths
        resume_candidate_roots = [
            candidate_paths(
                execution.run_root,
                execution.frame_scope,
                execution.step_id,
                resume_visit_count,
                str(candidate_config.get("id")),
            ).candidate_root
            for candidate_config in execution.candidates_config
            if isinstance(candidate_config, dict)
        ]
        sidecars_exist = adjudication_sidecars_exist(
            visit_paths=resume_visit_paths,
            candidate_roots=resume_candidate_roots,
        )
        using_previous_visit = False
        if (
            not sidecars_exist
            and self.resume_mode
            and isinstance(execution.visit_count, int)
            and execution.visit_count > 1
        ):
            previous_visit_count = execution.visit_count - 1
            previous_visit_paths = adjudication_visit_paths(
                execution.run_root,
                execution.frame_scope,
                execution.step_id,
                previous_visit_count,
            )
            previous_candidate_roots = [
                candidate_paths(
                    execution.run_root,
                    execution.frame_scope,
                    execution.step_id,
                    previous_visit_count,
                    str(candidate_config.get("id")),
                ).candidate_root
                for candidate_config in execution.candidates_config
                if isinstance(candidate_config, dict)
            ]
            if adjudication_sidecars_exist(
                visit_paths=previous_visit_paths,
                candidate_roots=previous_candidate_roots,
            ):
                previous_scope = classify_adjudication_resume_mismatch(
                    run_root=execution.run_root,
                    frame_scope=execution.frame_scope,
                    step_id=execution.step_id,
                    visit_count=previous_visit_count,
                    visit_paths=previous_visit_paths,
                    message="previous adjudication visit scope is not canonical",
                )
                if previous_scope.kind == "integrity_error":
                    return previous_scope
                resume_visit_count = previous_visit_count
                resume_visit_paths = previous_visit_paths
                resume_candidate_roots = previous_candidate_roots
                sidecars_exist = True
                using_previous_visit = True

        if sidecars_exist:
            if not self.resume_mode:
                return AdjudicationResumeDecision.integrity_error(
                    "existing adjudication sidecars require resume reconciliation before rerun",
                )
            resume_state = self._load_adjudication_resume_state(
                candidates_config=execution.candidates_config,
                evaluator_config=execution.evaluator_config,
                context=execution.context,
                state=execution.state,
                run_root=execution.run_root,
                frame_scope=execution.frame_scope,
                step_id=execution.step_id,
                visit_count=resume_visit_count,
                visit_paths=resume_visit_paths,
            )
            if isinstance(resume_state.get("error"), dict):
                failure = resume_state["error"]
                error = failure.get("error", {})
                message = (
                    error.get("message")
                    if isinstance(error, dict) and isinstance(error.get("message"), str)
                    else "adjudication resume state does not match its sidecars"
                )
                return classify_adjudication_resume_mismatch(
                    run_root=execution.run_root,
                    frame_scope=execution.frame_scope,
                    step_id=execution.step_id,
                    visit_count=resume_visit_count,
                    visit_paths=resume_visit_paths,
                    message=message,
                )
            execution.visit_count = resume_visit_count
            execution.visit_paths = resume_visit_paths
            if using_previous_visit:
                step_visits = execution.state.get("step_visits", {})
                if isinstance(step_visits, dict):
                    step_visits[execution.step_name] = resume_visit_count
                    self._persist_control_flow_state(execution.state)
            execution.resume_state = resume_state
            execution.baseline_manifest = resume_state["baseline_manifest"]
            execution.candidates = resume_state["candidates"]
            execution.scorer = resume_state.get("scorer")
            execution.evaluator_prompt = str(resume_state.get("evaluator_prompt") or "")
            execution.scorer_failure = resume_state.get("scorer_failure")
            execution.resume_baseline_only = bool(resume_state.get("baseline_only"))
            execution.resume_loaded = not execution.resume_baseline_only

        if sidecars_exist and not execution.resume_loaded and not execution.resume_baseline_only:
            return classify_adjudication_resume_mismatch(
                run_root=execution.run_root,
                frame_scope=execution.frame_scope,
                step_id=execution.step_id,
                visit_count=execution.visit_count,
                visit_paths=execution.visit_paths,
                message="existing adjudication sidecars require resume reconciliation before rerun",
            )
        return AdjudicationResumeDecision.reuse()

    def _load_adjudication_resume_state(
            self: AdjudicationRuntime,
            *,
            candidates_config: list[Any],
            evaluator_config: Mapping[str, Any],
            context: Dict[str, Any],
            state: Dict[str, Any],
            run_root: Path,
            frame_scope: str,
            step_id: str,
            visit_count: int,
        visit_paths: AdjudicationVisitPaths,
        ) -> dict[str, Any]:
            if not visit_paths.baseline_manifest_path.exists() or not visit_paths.baseline_workspace.exists():
                return {
                    "error": self._resume_mismatch(
                        "baseline manifest or workspace is missing for adjudication resume",
                        visit_paths=visit_paths,
                    )
                }
            try:
                baseline_manifest = load_baseline_manifest(visit_paths.baseline_manifest_path)
            except Exception as exc:
                return {
                    "error": self._resume_mismatch(
                        f"baseline manifest cannot be loaded for adjudication resume: {exc}",
                        visit_paths=visit_paths,
                    )
                }
            if baseline_manifest.workflow_checksum != state.get("workflow_checksum", ""):
                return {
                    "error": self._resume_mismatch(
                        "baseline workflow checksum does not match current resume state",
                        visit_paths=visit_paths,
                    )
                }
            if baseline_manifest.copy_policy != BASELINE_COPY_POLICY:
                return {
                    "error": self._resume_mismatch(
                        "baseline copy policy does not match the adjudication runtime",
                        visit_paths=visit_paths,
                    )
                }

            try:
                ledger_rows = load_score_ledger_rows(visit_paths.run_score_ledger_path)
            except Exception as exc:
                return {
                    "error": self._resume_mismatch(
                        f"score ledger cannot be loaded for adjudication resume: {exc}",
                        visit_paths=visit_paths,
                    )
                }
            ledger_by_candidate = {
                str(row.get("candidate_id")): row
                for row in ledger_rows
                if isinstance(row.get("candidate_id"), str)
            }

            candidate_sidecars_exist = False
            for candidate_config in candidates_config:
                if not isinstance(candidate_config, dict):
                    continue
                paths = candidate_paths(run_root, frame_scope, step_id, visit_count, str(candidate_config.get("id")))
                if paths.candidate_root.exists():
                    candidate_sidecars_exist = True
                    break
            if (
                not ledger_rows
                and not candidate_sidecars_exist
                and not visit_paths.scorer_root.exists()
                and not visit_paths.promotion_manifest_path.exists()
            ):
                return {
                    "baseline_manifest": baseline_manifest,
                    "candidates": [],
                    "scorer": None,
                    "evaluator_prompt": "",
                    "scorer_failure": None,
                    "baseline_only": True,
                }

            candidates: list[dict[str, Any]] = []
            pending_candidate_configs: list[tuple[int, dict[str, Any]]] = []
            for index, candidate_config in enumerate(candidates_config):
                if not isinstance(candidate_config, dict):
                    continue
                candidate_id = str(candidate_config.get("id"))
                paths = candidate_paths(run_root, frame_scope, step_id, visit_count, candidate_id)
                metadata_file = candidate_metadata_path(paths)
                if not metadata_file.exists():
                    if paths.candidate_root.exists() or candidate_id in ledger_by_candidate:
                        return {
                            "error": self._resume_mismatch(
                                f"candidate metadata missing for adjudication resume candidate '{candidate_id}'",
                                visit_paths=visit_paths,
                                candidates=candidates,
                            )
                        }
                    pending_candidate_configs.append((index, candidate_config))
                    continue
                try:
                    candidate = load_candidate_metadata(paths)
                except Exception as exc:
                    return {
                        "error": self._resume_mismatch(
                            f"candidate metadata cannot be loaded for adjudication resume candidate '{candidate_id}': {exc}",
                            visit_paths=visit_paths,
                            candidates=candidates,
                        )
                    }
                if candidate.get("candidate_id") != candidate_id:
                    return {
                        "error": self._resume_mismatch(
                            f"candidate metadata id mismatch for adjudication resume candidate '{candidate_id}'",
                            visit_paths=visit_paths,
                            candidates=candidates,
                        )
                    }
                if candidate.get("candidate_index") != index:
                    return {
                        "error": self._resume_mismatch(
                            f"candidate order mismatch for adjudication resume candidate '{candidate_id}'",
                            visit_paths=visit_paths,
                            candidates=candidates,
                        )
                    }
                expected_config_hash = self._stable_runtime_hash(candidate_config)
                if candidate.get("candidate_config_hash") != expected_config_hash:
                    return {
                        "error": self._resume_mismatch(
                            f"candidate config hash mismatch for adjudication resume candidate '{candidate_id}'",
                            visit_paths=visit_paths,
                            candidates=candidates,
                        )
                    }
                if paths.prompt_path.exists() and isinstance(candidate.get("composed_prompt_hash"), str):
                    prompt_hash = self._text_hash(paths.prompt_path.read_text(encoding="utf-8"))
                    if candidate.get("composed_prompt_hash") != prompt_hash:
                        return {
                            "error": self._resume_mismatch(
                                f"composed prompt hash mismatch for adjudication resume candidate '{candidate_id}'",
                                visit_paths=visit_paths,
                                candidates=candidates,
                            )
                        }
                row = ledger_by_candidate.get(candidate_id)
                if row is not None:
                    for key in ("candidate_run_key", "score_run_key"):
                        if isinstance(row.get(key), str):
                            candidate[key] = row[key]
                candidates.append(candidate)

            packet_candidates = []
            for candidate in candidates:
                paths = candidate_paths(run_root, frame_scope, step_id, visit_count, str(candidate.get("candidate_id")))
                if paths.evaluation_packet_path.exists():
                    packet_candidates.append((candidate, paths.evaluation_packet_path))

            scored_or_evaluation_failed = [
                candidate
                for candidate in candidates
                if candidate.get("score_status") in {"scored", "evaluation_failed"}
            ]
            scorer_unavailable = [
                candidate
                for candidate in candidates
                if candidate.get("score_status") == "scorer_unavailable"
            ]

            scorer: dict[str, Any] | None = None
            evaluator_prompt = ""
            scorer_failure: dict[str, Any] | None = None
            if scored_or_evaluation_failed or packet_candidates:
                try:
                    scorer = load_scorer_snapshot(visit_paths.scorer_root)
                except Exception as exc:
                    return {
                        "error": self._resume_mismatch(
                            f"scorer snapshot cannot be loaded for adjudication resume: {exc}",
                            visit_paths=visit_paths,
                            candidates=candidates,
                        )
                    }
                if scorer is None:
                    return {
                        "error": self._resume_mismatch(
                            "scorer snapshot missing for terminal score metadata during adjudication resume",
                            visit_paths=visit_paths,
                            candidates=candidates,
                        )
                    }
                current_scorer, current_prompt, current_failure = self._resolve_adjudication_scorer(
                    evaluator_config,
                    context,
                    state,
                    visit_paths=visit_paths,
                    persist=False,
                )
                if current_failure is not None or current_scorer is None:
                    return {
                        "error": self._resume_mismatch(
                            "scorer identity no longer resolves during adjudication resume",
                            visit_paths=visit_paths,
                            candidates=candidates,
                        )
                    }
                if current_scorer.get("scorer_identity_hash") != scorer.get("scorer_identity_hash"):
                    return {
                        "error": self._resume_mismatch(
                            "scorer identity hash mismatch during adjudication resume",
                            visit_paths=visit_paths,
                            candidates=candidates,
                        )
                    }
                evaluator_prompt = (
                    scorer.get("evaluator_prompt_content")
                    if isinstance(scorer.get("evaluator_prompt_content"), str)
                    else current_prompt
                )
                for candidate in scored_or_evaluation_failed:
                    if candidate.get("scorer_identity_hash") != scorer.get("scorer_identity_hash"):
                        return {
                            "error": self._resume_mismatch(
                                f"candidate scorer identity mismatch for adjudication resume candidate '{candidate.get('candidate_id')}'",
                                visit_paths=visit_paths,
                                candidates=candidates,
                            )
                        }
                for candidate, packet_path in packet_candidates:
                    try:
                        packet = json.loads(packet_path.read_text(encoding="utf-8"))
                    except Exception as exc:
                        return {
                            "error": self._resume_mismatch(
                                f"evaluation packet cannot be loaded for adjudication resume candidate '{candidate.get('candidate_id')}': {exc}",
                                visit_paths=visit_paths,
                                candidates=candidates,
                            )
                        }
                    if packet.get("scorer_identity_hash") != scorer.get("scorer_identity_hash"):
                        return {
                            "error": self._resume_mismatch(
                                f"evaluation packet scorer identity mismatch for adjudication resume candidate '{candidate.get('candidate_id')}'",
                                visit_paths=visit_paths,
                                candidates=candidates,
                            )
                        }
                    if (
                        isinstance(candidate.get("evaluation_packet_hash"), str)
                        and packet.get("evaluation_packet_hash") != candidate.get("evaluation_packet_hash")
                    ):
                        return {
                            "error": self._resume_mismatch(
                                f"evaluation packet hash mismatch for adjudication resume candidate '{candidate.get('candidate_id')}'",
                                visit_paths=visit_paths,
                                candidates=candidates,
                            )
                        }

            if scorer_unavailable:
                try:
                    scorer_failure = load_scorer_resolution_failure(visit_paths.scorer_root)
                except Exception as exc:
                    return {
                        "error": self._resume_mismatch(
                            f"scorer resolution failure cannot be loaded for adjudication resume: {exc}",
                            visit_paths=visit_paths,
                            candidates=candidates,
                        )
                    }
                if scorer_failure is None:
                    return {
                        "error": self._resume_mismatch(
                            "scorer resolution failure metadata missing for scorer_unavailable ledger rows during adjudication resume",
                            visit_paths=visit_paths,
                            candidates=candidates,
                        )
                    }
                current_scorer, _current_prompt, current_failure = self._resolve_adjudication_scorer(
                    evaluator_config,
                    context,
                    state,
                    visit_paths=visit_paths,
                    persist=False,
                )
                if current_scorer is not None or current_failure is None:
                    return {
                        "error": self._resume_mismatch(
                            "scorer resolution no longer fails during adjudication resume",
                            visit_paths=visit_paths,
                            candidates=candidates,
                        )
                    }
                if current_failure.get("scorer_resolution_failure_key") != scorer_failure.get("scorer_resolution_failure_key"):
                    return {
                        "error": self._resume_mismatch(
                            "scorer resolution failure key mismatch during adjudication resume",
                            visit_paths=visit_paths,
                            candidates=candidates,
                        )
                    }
                for candidate in scorer_unavailable:
                    if candidate.get("scorer_resolution_failure_key") != scorer_failure.get("scorer_resolution_failure_key"):
                        return {
                            "error": self._resume_mismatch(
                                f"candidate scorer resolution key mismatch for adjudication resume candidate '{candidate.get('candidate_id')}'",
                                visit_paths=visit_paths,
                                candidates=candidates,
                            )
                        }

            for row in ledger_rows:
                score_status = row.get("score_status")
                if score_status in {"scored", "evaluation_failed"} and scorer is None:
                    return {
                        "error": self._resume_mismatch(
                            "scorer snapshot missing for terminal score ledger rows during adjudication resume",
                            visit_paths=visit_paths,
                            candidates=candidates,
                        )
                    }
                if score_status == "scorer_unavailable" and scorer_failure is None:
                    return {
                        "error": self._resume_mismatch(
                            "scorer resolution failure metadata missing for scorer_unavailable ledger rows during adjudication resume",
                            visit_paths=visit_paths,
                            candidates=candidates,
                        )
                    }

            return {
                "baseline_manifest": baseline_manifest,
                "candidates": candidates,
                "scorer": scorer,
                "evaluator_prompt": evaluator_prompt,
                "scorer_failure": scorer_failure,
                "pending_candidate_configs": pending_candidate_configs,
            }

    def _resume_mismatch(
            self: AdjudicationRuntime,
            message: str,
            *,
        visit_paths: AdjudicationVisitPaths,
            candidates: Optional[list[dict[str, Any]]] = None,
        ) -> Dict[str, Any]:
            return self._adjudication_failure_result(
                "adjudication_resume_mismatch",
                message,
                candidates=candidates,
                visit_paths=visit_paths,
            )
