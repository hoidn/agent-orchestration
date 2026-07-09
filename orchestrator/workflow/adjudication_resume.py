"""Resume reconciliation for adjudicated provider execution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from .adjudication import (
    AdjudicationVisitPaths,
    BASELINE_COPY_POLICY,
    adjudication_sidecars_exist,
    adjudication_visit_paths,
    candidate_metadata_path,
    candidate_paths,
    load_baseline_manifest,
    load_candidate_metadata,
    load_score_ledger_rows,
    load_scorer_resolution_failure,
    load_scorer_snapshot,
)
from .adjudication_bindings import AdjudicationExecution
from .adjudication_runtime import AdjudicationRuntime


class AdjudicationResumeMixin:
    def _reconcile_adjudication_resume(
        self: AdjudicationRuntime,
        execution: AdjudicationExecution,
    ) -> Optional[Dict[str, Any]]:
        """Reconcile visit identity and load reusable sidecars when present."""
        candidate_roots = [
            candidate_paths(
                execution.run_root,
                execution.frame_scope,
                execution.step_id,
                int(execution.visit_count or 1),
                str(candidate_config.get("id")),
            ).candidate_root
            for candidate_config in execution.candidates_config
            if isinstance(candidate_config, dict)
        ]
        sidecars_exist = adjudication_sidecars_exist(
            visit_paths=execution.visit_paths,
            candidate_roots=candidate_roots,
        )
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
                execution.visit_count = previous_visit_count
                step_visits = execution.state.get("step_visits", {})
                if isinstance(step_visits, dict):
                    step_visits[execution.step_name] = previous_visit_count
                    self._persist_control_flow_state(execution.state)
                execution.visit_paths = previous_visit_paths
                sidecars_exist = True

        if sidecars_exist:
            if not self.resume_mode:
                return self._adjudication_failure_result(
                    "adjudication_resume_mismatch",
                    "existing adjudication sidecars require resume reconciliation before rerun",
                    visit_paths=execution.visit_paths,
                )
            resume_state = self._load_adjudication_resume_state(
                candidates_config=execution.candidates_config,
                evaluator_config=execution.evaluator_config,
                context=execution.context,
                state=execution.state,
                run_root=execution.run_root,
                frame_scope=execution.frame_scope,
                step_id=execution.step_id,
                visit_count=int(execution.visit_count or 1),
                visit_paths=execution.visit_paths,
            )
            if isinstance(resume_state.get("error"), dict):
                return resume_state["error"]
            execution.resume_state = resume_state
            execution.baseline_manifest = resume_state["baseline_manifest"]
            execution.candidates = resume_state["candidates"]
            execution.scorer = resume_state.get("scorer")
            execution.evaluator_prompt = str(resume_state.get("evaluator_prompt") or "")
            execution.scorer_failure = resume_state.get("scorer_failure")
            execution.resume_baseline_only = bool(resume_state.get("baseline_only"))
            execution.resume_loaded = not execution.resume_baseline_only

        if sidecars_exist and not execution.resume_loaded and not execution.resume_baseline_only:
            return self._adjudication_failure_result(
                "adjudication_resume_mismatch",
                "existing adjudication sidecars require resume reconciliation before rerun",
                visit_paths=execution.visit_paths,
            )
        return None

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
