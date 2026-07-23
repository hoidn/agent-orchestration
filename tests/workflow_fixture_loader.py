"""Test-only JSON fixture adapter for shared workflow mapping validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from orchestrator.exceptions import ValidationError, WorkflowValidationError
from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle
from orchestrator.workflow.validation import (
    DEFAULT_ENV_VAR_PATTERN,
    DEFAULT_INPUT_REF_PATTERN,
    DEFAULT_PRIVATE_COLLECTION_OUTPUT_TYPES,
    DEFAULT_STRING_CONTRACT_VERSION,
    DEFAULT_SUPPORTED_OUTPUT_TYPES,
    DEFAULT_SUPPORTED_VERSIONS,
    DEFAULT_VERSION_ORDER,
    WorkflowBoundaryValidationPolicy,
    WorkflowImportResolutionResult,
    WorkflowMappingBuildRequest,
    WorkflowMappingValidationResult,
    WorkflowMappingValidationOptions,
    validate_workflow_mapping,
)


class WorkflowFixtureLoader:
    """Build typed bundles from JSON test fixtures through shared validation."""

    SUPPORTED_VERSIONS = set(DEFAULT_SUPPORTED_VERSIONS)
    SUPPORTED_OUTPUT_TYPES = set(DEFAULT_SUPPORTED_OUTPUT_TYPES)
    PRIVATE_COLLECTION_OUTPUT_TYPES = set(DEFAULT_PRIVATE_COLLECTION_OUTPUT_TYPES)
    STRING_CONTRACT_VERSION = DEFAULT_STRING_CONTRACT_VERSION
    ENV_VAR_PATTERN = DEFAULT_ENV_VAR_PATTERN
    INPUT_REF_PATTERN = DEFAULT_INPUT_REF_PATTERN
    VERSION_ORDER = list(DEFAULT_VERSION_ORDER)

    def __init__(
        self,
        workspace: Path,
        *,
        boundary_validation_policy: WorkflowBoundaryValidationPolicy | None = None,
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self._boundary_validation_policy = (
            WorkflowBoundaryValidationPolicy.PUBLIC_CALLABLE
            if boundary_validation_policy is None
            else boundary_validation_policy
        )
        self._load_stack: list[Path] = []

    def load(self, workflow_path: Path) -> LoadedWorkflowBundle:
        return self.load_bundle(workflow_path)

    def load_bundle(self, workflow_path: Path) -> LoadedWorkflowBundle:
        result = self._load_workflow(Path(workflow_path).resolve())
        if result.errors:
            raise WorkflowValidationError(list(result.errors))
        assert result.bundle is not None
        return result.bundle

    def load_mapping(
        self,
        authored_mapping: dict[str, Any],
        *,
        workflow_path: Path | None = None,
    ) -> LoadedWorkflowBundle:
        """Validate one in-memory mapping without granting production file I/O."""
        result = validate_workflow_mapping(
            WorkflowMappingBuildRequest(
                authored_mapping=authored_mapping,
                workflow_path=(
                    Path(workflow_path).resolve()
                    if workflow_path is not None
                    else self.workspace / "workflow.fixture.json"
                ),
                import_resolver=self._load_imports,
            ),
            options=self._validation_options(),
        )
        if result.errors:
            raise WorkflowValidationError(list(result.errors))
        assert result.bundle is not None
        return result.bundle

    def _load_workflow(
        self,
        workflow_path: Path,
        *,
        expected_version: str | None = None,
    ) -> WorkflowMappingValidationResult:
        resolved_workflow_path = workflow_path.resolve()
        if resolved_workflow_path in self._load_stack:
            try:
                display_path = str(resolved_workflow_path.relative_to(self.workspace))
            except ValueError:
                display_path = str(resolved_workflow_path)
            return WorkflowMappingValidationResult(
                None,
                (
                    ValidationError(
                        f"Circular import detected while loading '{display_path}'"
                    ),
                ),
            )

        self._load_stack.append(resolved_workflow_path)
        try:
            try:
                workflow = json.loads(
                    resolved_workflow_path.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as exc:
                return WorkflowMappingValidationResult(
                    None,
                    (ValidationError(f"Failed to load JSON workflow fixture: {exc}"),),
                )

            if not isinstance(workflow, dict):
                return WorkflowMappingValidationResult(
                    None,
                    (ValidationError("Workflow fixture must be a JSON object"),),
                )

            return validate_workflow_mapping(
                WorkflowMappingBuildRequest(
                    authored_mapping=workflow,
                    workflow_path=resolved_workflow_path,
                    import_resolver=self._load_imports,
                    expected_version=expected_version,
                    workflow_is_imported=expected_version is not None,
                ),
                options=self._validation_options(),
            )
        finally:
            self._load_stack.pop()

    def _validation_options(self) -> WorkflowMappingValidationOptions:
        return WorkflowMappingValidationOptions(
            workspace_root=self.workspace,
            boundary_validation_policy=self._boundary_validation_policy,
            supported_versions=frozenset(self.SUPPORTED_VERSIONS),
            version_order=tuple(self.VERSION_ORDER),
            supported_output_types=frozenset(self.SUPPORTED_OUTPUT_TYPES),
            private_collection_output_types=frozenset(
                self.PRIVATE_COLLECTION_OUTPUT_TYPES
            ),
            string_contract_version=self.STRING_CONTRACT_VERSION,
            env_var_pattern=self.ENV_VAR_PATTERN,
            input_ref_pattern=self.INPUT_REF_PATTERN,
        )

    def _load_imports(
        self,
        imports: Any,
        *,
        version: str,
        workflow_path: Path,
    ) -> WorkflowImportResolutionResult:
        if imports is None:
            return WorkflowImportResolutionResult({})
        if not isinstance(imports, dict):
            return WorkflowImportResolutionResult(
                {},
                (ValidationError("'imports' must be a dictionary"),),
            )
        if not self._version_at_least(version, "2.5"):
            return WorkflowImportResolutionResult({})

        imported_workflows: dict[str, LoadedWorkflowBundle] = {}
        errors: list[ValidationError] = []
        for alias, import_path in imports.items():
            context = f"imports.{alias}"
            if not isinstance(alias, str) or not alias.strip():
                errors.append(
                    ValidationError(
                        f"{context}: import alias must be a non-empty string"
                    )
                )
                continue
            if not isinstance(import_path, str) or not import_path.strip():
                errors.append(
                    ValidationError(
                        f"{context}: import path must be a non-empty string"
                    )
                )
                continue
            try:
                resolved_import_path = self._resolve_import_path(
                    workflow_path,
                    import_path,
                )
            except ValueError as exc:
                errors.append(ValidationError(f"{context}: {exc}"))
                continue

            child = self._load_workflow(
                resolved_import_path,
                expected_version=version,
            )
            if child.errors:
                errors.extend(
                    ValidationError(
                        f"Import '{alias}': {error.message}",
                        error.path,
                        error.exit_code,
                        error.subject_refs,
                    )
                    for error in child.errors
                )
                continue
            assert child.bundle is not None
            imported_workflows[alias] = child.bundle
        return WorkflowImportResolutionResult(imported_workflows, tuple(errors))

    def _resolve_import_path(self, workflow_path: Path, import_path: str) -> Path:
        if "${" in import_path:
            raise ValueError(
                "import paths must be literal workflow-relative strings"
            )
        candidate = Path(import_path)
        if candidate.is_absolute():
            raise ValueError(f"absolute import paths are not allowed: {import_path}")
        resolved = (workflow_path.parent / candidate).resolve()
        try:
            resolved.relative_to(self.workspace)
        except ValueError as exc:
            raise ValueError(
                "asset path traversal outside the workflow source tree is not "
                f"allowed: {import_path}"
            ) from exc
        return resolved

    def _version_at_least(self, version: str, minimum: str) -> bool:
        if version not in self.VERSION_ORDER or minimum not in self.VERSION_ORDER:
            return False
        return self.VERSION_ORDER.index(version) >= self.VERSION_ORDER.index(minimum)


# Keep legacy test call sites compact while making the adapter's scope explicit.
WorkflowLoader = WorkflowFixtureLoader

