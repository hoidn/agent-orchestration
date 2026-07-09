"""Structural runtime contract for workflow step interpreters."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Protocol

from ..executor_runtime import RuntimeStepInput


class StepRuntime(Protocol):
    """Structural executor surface used by step-kind interpreters.

    The members are the exact executor surface measured for the current step
    interpreter entry points. ``WorkflowExecutor`` satisfies this protocol
    structurally; interpreter modules never import the executor. This contract
    supports the executor decomposition plan.
    """

    workspace: Path
    workflow_artifacts: Dict[str, Any]
    state_manager: Any

    def _atomic_write_bytes(self, target: Path, content: bytes) -> None: ...

    def _atomic_write_text(self, target: Path, content: str) -> None: ...

    def _bounded_private_runtime_bundle_path(
        self,
        bundle_path: Path,
        *,
        namespace: str,
    ) -> Path: ...

    @staticmethod
    def _capture_existing_file_bytes(path: Path) -> bytes | None: ...

    def _contract_violation_result(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]: ...

    def _materialize_view_artifacts(
        self,
        target_path: str,
        *,
        output_contracts: Any,
    ) -> Dict[str, Any]: ...

    def _materialize_view_evidence_path(self, target_path: Path) -> Path: ...

    def _normalize_resource_transition_paths(
        self,
        resource: Dict[str, Any],
    ) -> Dict[str, Any]: ...

    def _prepare_runtime_output_bundle_parent(
        self,
        resolved_output_bundle: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]: ...

    def _pure_projection_artifacts(
        self,
        result_value: Any,
        *,
        output_contracts: Any,
    ) -> Dict[str, Any]: ...

    def _resolve_materialize_view_target_value(
        self,
        value: Any,
        state: Dict[str, Any],
        *,
        scope: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> tuple[Any, Optional[Dict[str, Any]]]: ...

    def _resolve_materialize_view_value(
        self,
        value: Any,
        state: Dict[str, Any],
        *,
        scope: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> tuple[Any, Optional[Dict[str, Any]]]: ...

    def _resolve_output_contract_paths(
        self,
        step: RuntimeStepInput,
        state: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> tuple[
        Optional[List[Dict[str, Any]]],
        Optional[Dict[str, Any]],
        Optional[Dict[str, Any]],
    ]: ...

    def _resolve_pure_projection_bindings(
        self,
        value: Any,
        state: Dict[str, Any],
        *,
        scope: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> tuple[Any, Optional[Dict[str, Any]]]: ...

    def _resolve_resource_transition_bindings(
        self,
        value: Any,
        state: Dict[str, Any],
        *,
        scope: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> tuple[Any, Optional[Dict[str, Any]]]: ...

    def _resolve_workspace_path(self, relative_path: str) -> Optional[Path]: ...

    def _resource_transition_artifacts(
        self,
        step: RuntimeStepInput,
        *,
        transition_result: Mapping[str, Any],
    ) -> Dict[str, Any]: ...

    @staticmethod
    def _restore_file_bytes(path: Path, previous_bytes: bytes | None) -> None: ...

    def _reuse_materialized_view(
        self,
        *,
        target_path: Path,
        evidence_path: Path,
        renderer_id: str,
        renderer_version: int,
        renderer_schema_version: int,
        evidence_key: str,
        rendered_digest: str,
    ) -> tuple[Dict[str, Any] | None, Optional[Dict[str, Any]]]: ...

    def _reuse_pure_projection_bundle(
        self,
        *,
        bundle_path: Path,
        payload: Mapping[str, Any],
        payload_digest: str,
        bindings_digest: str,
    ) -> tuple[Any | None, Optional[Dict[str, Any]]]: ...

    def _v214_failure_result(
        self,
        error_type: str,
        message: str,
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]: ...

    def _validate_scalar_value(
        self,
        artifact_name: Any,
        artifact_spec: Any,
        candidate_value: Any,
    ) -> Any: ...

    def _workspace_relative_path(self, path: Path) -> str: ...
