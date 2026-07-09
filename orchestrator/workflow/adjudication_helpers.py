"""Small runner-owned adjudication helpers."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from ..exec.retry import RetryPolicy
from .adjudication import (
    AdjudicationDeadline,
    AdjudicationVisitPaths,
    PathSurface,
    candidate_paths,
    persist_candidate_metadata,
)
from .call_frame_state import _path_safe_frame_scope_token
from .adjudication_runtime import AdjudicationFrameContext, AdjudicationRuntime


class AdjudicationHelpersMixin:
    def _adjudication_frame_context(
        self: AdjudicationRuntime,
    ) -> AdjudicationFrameContext:
            """Return canonical run-root and current execution-frame identity."""
            manager: Any = self.state_manager
            call_frame_id = getattr(manager, "frame_id", None)
            root_manager = manager
            while hasattr(root_manager, "parent_manager"):
                root_manager = getattr(root_manager, "parent_manager")
            run_root = Path(getattr(root_manager, "run_root", self.state_manager.run_root))
            if isinstance(call_frame_id, str) and call_frame_id:
                return {
                    "run_root": run_root,
                    "frame_scope": self._path_safe_frame_scope(call_frame_id),
                    "execution_frame_id": call_frame_id,
                    "call_frame_id": call_frame_id,
                }
            return {
                "run_root": run_root,
                "frame_scope": "root",
                "execution_frame_id": "root",
                "call_frame_id": None,
            }

    def _path_safe_frame_scope(self: AdjudicationRuntime, frame_id: str) -> str:
            return _path_safe_frame_scope_token(frame_id)

    def _adjudication_timeout_value(self: AdjudicationRuntime, raw_timeout: Any) -> float | None:
            if isinstance(raw_timeout, (int, float)):
                return float(raw_timeout)
            return None

    def _adjudication_retry_policy(self: AdjudicationRuntime, step: Mapping[str, Any]) -> RetryPolicy:
            if "retries" in step:
                return RetryPolicy.for_command(step.get("retries"))
            return RetryPolicy.for_provider(max_retries=self.max_retries, delay_ms=self.retry_delay_ms)

    def _wait_for_adjudication_retry(
            self: AdjudicationRuntime,
            retry_policy: RetryPolicy,
            deadline: AdjudicationDeadline,
        ) -> None:
            delay_sec = max(0.0, float(retry_policy.delay_ms or 0) / 1000.0)
            if delay_sec <= 0:
                deadline.require_time_remaining("retry")
                return
            remaining = deadline.remaining_timeout_sec()
            if remaining is not None and remaining <= delay_sec:
                raise TimeoutError("adjudicated provider deadline expired before retry delay")
            time.sleep(delay_sec)
            deadline.require_time_remaining("retry")

    def _adjudication_deadline_expired(self: AdjudicationRuntime, deadline: AdjudicationDeadline) -> bool:
            remaining = deadline.remaining_timeout_sec()
            return remaining is not None and remaining <= 0

    def _adjudication_required_path_surfaces(self: AdjudicationRuntime, step: Dict[str, Any]) -> list[PathSurface]:
            surfaces: list[PathSurface] = []
            input_file = step.get("input_file")
            if isinstance(input_file, str):
                surfaces.append(PathSurface("input_file", Path(input_file)))
            depends_on = step.get("depends_on")
            if isinstance(depends_on, dict):
                for key in ("required",):
                    values = depends_on.get(key)
                    if isinstance(values, list):
                        for index, value in enumerate(values):
                            if isinstance(value, str):
                                surfaces.append(PathSurface(f"depends_on.{key}[{index}]", Path(value)))
            consume_bundle = step.get("consume_bundle")
            if isinstance(consume_bundle, dict) and isinstance(consume_bundle.get("path"), str):
                surfaces.append(PathSurface("consume_bundle.path", Path(consume_bundle["path"])))
            for index, spec in enumerate(step.get("expected_outputs", []) if isinstance(step.get("expected_outputs"), list) else []):
                if isinstance(spec, dict) and isinstance(spec.get("path"), str):
                    surfaces.append(PathSurface(f"expected_outputs[{index}].path", Path(spec["path"])))
            output_bundle = step.get("output_bundle")
            if isinstance(output_bundle, dict) and isinstance(output_bundle.get("path"), str):
                surfaces.append(PathSurface("output_bundle.path", Path(output_bundle["path"])))
            return surfaces

    def _adjudication_optional_path_surfaces(self: AdjudicationRuntime, step: Dict[str, Any]) -> list[PathSurface]:
            surfaces: list[PathSurface] = []
            depends_on = step.get("depends_on")
            if isinstance(depends_on, dict):
                values = depends_on.get("optional")
                if isinstance(values, list):
                    for index, value in enumerate(values):
                        if isinstance(value, str):
                            surfaces.append(PathSurface(f"depends_on.optional[{index}]", Path(value)))
            return surfaces

    def _resolve_adjudication_score_ledger_path(
            self: AdjudicationRuntime,
            adjudicated: dict[str, Any],
            state: Dict[str, Any],
            context: Dict[str, Any],
            *,
            step_name: str,
        visit_paths: AdjudicationVisitPaths,
        ) -> Optional[Dict[str, Any]]:
            ledger_path = adjudicated.get("score_ledger_path")
            if not isinstance(ledger_path, str):
                return None
            resolved_path, path_error = self._substitute_path_template(
                ledger_path,
                state,
                step_name=step_name,
                field_name="adjudicated_provider.score_ledger_path",
                context=context,
            )
            if path_error is not None:
                return path_error
            if not isinstance(resolved_path, str):
                return self._adjudication_failure_result(
                    "ledger_path_collision",
                    "score_ledger_path must resolve to a workspace-relative artifacts path",
                    visit_paths=visit_paths,
                )

            path = Path(resolved_path)
            normalized = path.as_posix()
            if path.is_absolute() or ".." in path.parts or not normalized.startswith("artifacts/"):
                return self._adjudication_failure_result(
                    "ledger_path_collision",
                    "score_ledger_path must resolve under artifacts/",
                    visit_paths=visit_paths,
                )
            ledger_abs = (self.workspace / path).resolve()
            workspace_root = self.workspace.resolve()
            if not self._path_under(ledger_abs, workspace_root):
                return self._adjudication_failure_result(
                    "ledger_path_collision",
                    "score_ledger_path must not escape the parent workspace",
                    visit_paths=visit_paths,
                )
            artifacts_root = (self.workspace / "artifacts").resolve()
            if not self._path_under(ledger_abs, artifacts_root):
                return self._adjudication_failure_result(
                    "ledger_path_collision",
                    "score_ledger_path must not escape artifacts/",
                    visit_paths=visit_paths,
                )
            adjudicated["score_ledger_path"] = normalized
            return None

    def _candidate_step_from_adjudicated_step(
            self: AdjudicationRuntime,
            step: Dict[str, Any],
            candidate_config: Mapping[str, Any],
        ) -> Dict[str, Any]:
            candidate_step = dict(step)
            candidate_step.pop("adjudicated_provider", None)
            candidate_step["provider"] = candidate_config.get("provider")
            if "provider_params" in candidate_config:
                candidate_step["provider_params"] = candidate_config.get("provider_params")
            else:
                candidate_step.pop("provider_params", None)
            if "asset_file" in candidate_config:
                candidate_step["asset_file"] = candidate_config["asset_file"]
                candidate_step.pop("input_file", None)
            elif "input_file" in candidate_config:
                candidate_step["input_file"] = candidate_config["input_file"]
                candidate_step.pop("asset_file", None)
            return candidate_step

    def _candidate_state_map(self: AdjudicationRuntime, candidates: list[dict[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for candidate in candidates:
                candidate_id = str(candidate.get("candidate_id"))
                result[candidate_id] = {
                    "candidate_status": candidate.get("candidate_status"),
                    "score_status": candidate.get("score_status"),
                    "score": candidate.get("score"),
                    "selected": bool(candidate.get("selected", False)),
                    "promotion_status": candidate.get("promotion_status", "not_selected"),
                    "candidate_root": candidate.get("candidate_root"),
                    "candidate_run_key": candidate.get("candidate_run_key"),
                    "score_run_key": candidate.get("score_run_key"),
                    "provider_exit_code": candidate.get("provider_exit_code"),
                    "attempt_count": candidate.get("attempt_count"),
                    "evaluator_attempt_count": candidate.get("evaluator_attempt_count"),
                    "failure_type": candidate.get("failure_type"),
                    "failure_message": candidate.get("failure_message"),
                    "scorer_resolution_failure_key": candidate.get("scorer_resolution_failure_key"),
                    "evaluation_packet_hash": candidate.get("evaluation_packet_hash"),
                }
            return result

    def _persist_adjudication_candidates(
            self: AdjudicationRuntime,
            *,
            run_root: Path,
            frame_scope: str,
            step_id: str,
            visit_count: int,
            candidates: list[dict[str, Any]],
        ) -> None:
            for candidate in candidates:
                candidate_id = candidate.get("candidate_id")
                if not isinstance(candidate_id, str) or not candidate_id:
                    continue
                paths = candidate_paths(run_root, frame_scope, step_id, visit_count, candidate_id)
                persist_candidate_metadata(candidate, paths)

    def _output_paths_from_contract(self: AdjudicationRuntime, step: Dict[str, Any]) -> dict[str, str]:
            paths: dict[str, str] = {}
            for spec in step.get("expected_outputs", []) if isinstance(step.get("expected_outputs"), list) else []:
                if isinstance(spec, dict) and isinstance(spec.get("name"), str) and isinstance(spec.get("path"), str):
                    paths[spec["name"]] = spec["path"]
            output_bundle = step.get("output_bundle")
            if isinstance(output_bundle, dict) and isinstance(output_bundle.get("path"), str):
                paths["output_bundle"] = output_bundle["path"]
            return paths

    def _promotion_destination_paths(self: AdjudicationRuntime, step: Dict[str, Any], artifacts: Mapping[str, Any]) -> set[Path]:
            paths: set[Path] = set()
            for spec in step.get("expected_outputs", []) if isinstance(step.get("expected_outputs"), list) else []:
                if not isinstance(spec, dict):
                    continue
                if isinstance(spec.get("path"), str):
                    paths.add((self.workspace / spec["path"]).resolve())
                if spec.get("type") == "relpath" and spec.get("must_exist_target") and isinstance(spec.get("name"), str):
                    value = artifacts.get(spec["name"])
                    if isinstance(value, str):
                        paths.add((self.workspace / value).resolve())
            output_bundle = step.get("output_bundle")
            if isinstance(output_bundle, dict) and isinstance(output_bundle.get("path"), str):
                paths.add((self.workspace / output_bundle["path"]).resolve())
                fields = output_bundle.get("fields")
                if isinstance(fields, list):
                    for field_spec in fields:
                        if not isinstance(field_spec, dict):
                            continue
                        if field_spec.get("type") == "relpath" and field_spec.get("must_exist_target") and isinstance(field_spec.get("name"), str):
                            value = artifacts.get(field_spec["name"])
                            if isinstance(value, str):
                                paths.add((self.workspace / value).resolve())
            return paths

    def _workflow_secret_values(self: AdjudicationRuntime, step: Dict[str, Any]) -> list[str]:
            secret_names = []
            secret_names.extend(self.global_secrets)
            step_secrets = step.get("secrets")
            if isinstance(step_secrets, list):
                secret_names.extend(name for name in step_secrets if isinstance(name, str))
            values: list[str] = []
            for name in secret_names:
                value = os.environ.get(name)
                if value:
                    values.append(value)
            return values

    def _provider_model(self: AdjudicationRuntime, params: Any) -> Optional[str]:
            if isinstance(params, Mapping):
                model = params.get("model") or params.get("reasoning_model")
                return model if isinstance(model, str) else None
            return None

    def _prompt_source_metadata(self: AdjudicationRuntime, step: Mapping[str, Any]) -> tuple[Optional[str], Optional[str]]:
            if isinstance(step.get("asset_file"), str):
                return "asset_file", step.get("asset_file")
            if isinstance(step.get("input_file"), str):
                return "input_file", step.get("input_file")
            return None, None

    def _stable_runtime_hash(self: AdjudicationRuntime, payload: Any) -> str:
            encoded = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
            from hashlib import sha256

            return f"sha256:{sha256(encoded).hexdigest()}"

    def _text_hash(self: AdjudicationRuntime, text: str) -> str:
            from hashlib import sha256

            return f"sha256:{sha256(text.encode('utf-8')).hexdigest()}"

    def _path_under(self: AdjudicationRuntime, path: Path, root: Path) -> bool:
            try:
                path.resolve().relative_to(root.resolve())
                return True
            except ValueError:
                return False
