"""Authored YAML parsing and recursive import facade."""

from copy import deepcopy
import logging
from pathlib import Path
from typing import Any, Dict, NamedTuple, Optional
import yaml

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


YAML_DEPRECATION_EVENT_CODE = "workflow_yaml_authoring_deprecated"
_YAML_DEPRECATION_LOGGER = logging.getLogger("orchestrator.loader.yaml_deprecation")


class PreservingLoader(yaml.SafeLoader):
    """Custom YAML loader that preserves string keys like 'on' instead of converting to bool."""

    def get_single_data(self):
        """Validate the composed workflow document before constructing its mapping."""
        document = self.get_single_node()
        if document is not None:
            duplicate_scan = _scan_duplicate_import_aliases(self, document)
            if duplicate_scan is not None and duplicate_scan.entries:
                message = "; ".join(
                    f"imports.{entry.alias}: duplicate import alias"
                    for entry in duplicate_scan.entries
                )
                raise yaml.constructor.ConstructorError(
                    "while constructing workflow imports",
                    duplicate_scan.entries[0].first_mark,
                    message,
                    duplicate_scan.entries[0].mark,
                )
            if (
                duplicate_scan is not None
                and duplicate_scan.duplicate_imports_mark is not None
            ):
                raise yaml.constructor.ConstructorError(
                    "while constructing workflow",
                    duplicate_scan.imports_key_mark,
                    "imports: duplicate top-level mapping",
                    duplicate_scan.duplicate_imports_mark,
                )
            return self.construct_document(document)
        return None


# Override the implicit resolver for boolean values to prevent 'on' from being converted to True
# This removes the implicit tag resolvers that convert strings like 'on', 'off', 'yes', 'no' to booleans
PreservingLoader.yaml_implicit_resolvers = dict(PreservingLoader.yaml_implicit_resolvers)
if 'o' in PreservingLoader.yaml_implicit_resolvers:
    # Remove resolvers that start with 'o' (which would catch 'on', 'off')
    PreservingLoader.yaml_implicit_resolvers['o'] = [
        (tag, regexp) for tag, regexp in PreservingLoader.yaml_implicit_resolvers['o']
        if tag != 'tag:yaml.org,2002:bool'
    ]
if 'O' in PreservingLoader.yaml_implicit_resolvers:
    PreservingLoader.yaml_implicit_resolvers['O'] = [
        (tag, regexp) for tag, regexp in PreservingLoader.yaml_implicit_resolvers['O']
        if tag != 'tag:yaml.org,2002:bool'
    ]


class _DuplicateImportAliasEntry(NamedTuple):
    alias: str
    first_mark: yaml.Mark
    mark: yaml.Mark


class _DuplicateImportAliasScan(NamedTuple):
    imports_key_mark: yaml.Mark
    entries: tuple[_DuplicateImportAliasEntry, ...]
    duplicate_imports_mark: Optional[yaml.Mark]


def _scan_duplicate_import_aliases(
    loader: PreservingLoader,
    document: yaml.Node,
) -> Optional[_DuplicateImportAliasScan]:
    """Return marked duplicate effective top-level imports and aliases."""
    if not isinstance(document, yaml.MappingNode):
        return None

    effective_document = deepcopy(document)
    loader.flatten_mapping(effective_document)

    imports_entries: list[tuple[yaml.ScalarNode, yaml.Node]] = []
    for key_node, value_node in effective_document.value:
        if isinstance(key_node, yaml.ScalarNode) and key_node.value == "imports":
            imports_entries.append((key_node, value_node))

    if not imports_entries:
        return None

    seen: dict[str, yaml.Mark] = {}
    duplicates: list[_DuplicateImportAliasEntry] = []
    first_imports_key = imports_entries[0][0]
    for _, imports_node in imports_entries:
        if not isinstance(imports_node, yaml.MappingNode):
            continue
        effective_imports = deepcopy(imports_node)
        loader.flatten_mapping(effective_imports)

        for key_node, _ in effective_imports.value:
            alias = loader.construct_object(key_node, deep=True)
            if not isinstance(alias, str):
                continue
            if alias in seen:
                if not any(entry.alias == alias for entry in duplicates):
                    duplicates.append(
                        _DuplicateImportAliasEntry(
                            alias,
                            seen[alias],
                            key_node.start_mark,
                        )
                    )
                continue
            seen[alias] = key_node.start_mark
    return _DuplicateImportAliasScan(
        imports_key_mark=first_imports_key.start_mark,
        entries=tuple(duplicates),
        duplicate_imports_mark=(
            imports_entries[1][0].start_mark
            if len(imports_entries) > 1
            else None
        ),
    )


def _duplicate_import_aliases(
    loader: PreservingLoader,
    document: yaml.Node,
) -> tuple[str, ...]:
    """Return duplicate effective aliases from the top-level imports mapping."""
    duplicate_scan = _scan_duplicate_import_aliases(loader, document)
    if duplicate_scan is None:
        return ()
    return tuple(
        entry.alias
        for entry in duplicate_scan.entries
    )


class WorkflowLoader:
    """Parse authored YAML and compose it with request-scoped shared validation."""

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
        emit_yaml_deprecation_warning: bool = True,
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self._boundary_validation_policy = (
            WorkflowBoundaryValidationPolicy.PUBLIC_CALLABLE
            if boundary_validation_policy is None
            else boundary_validation_policy
        )
        self._emit_yaml_deprecation_warning = bool(emit_yaml_deprecation_warning)
        self._load_stack: list[Path] = []

    def load(self, workflow_path: Path) -> LoadedWorkflowBundle:
        """Load and validate workflow YAML into the typed bundle surface."""
        return self.load_bundle(workflow_path)

    def load_bundle(self, workflow_path: Path) -> LoadedWorkflowBundle:
        """Load one authored YAML graph and raise its structured diagnostics."""
        requested_path = Path(workflow_path)
        if (
            self._emit_yaml_deprecation_warning
            and requested_path.suffix.lower() in {".yaml", ".yml"}
        ):
            _YAML_DEPRECATION_LOGGER.warning(
                "Authored YAML workflow loading is deprecated",
                extra={
                    "workflow_deprecation_code": YAML_DEPRECATION_EVENT_CODE,
                    "workflow_deprecation_path": str(
                        requested_path.resolve(strict=False)
                    ),
                    "workflow_deprecation_format": "yaml",
                },
            )
        result = self._load_workflow(requested_path.resolve())
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
                (ValidationError(f"Circular import detected while loading '{display_path}'"),),
            )

        self._load_stack.append(resolved_workflow_path)
        try:
            try:
                with open(resolved_workflow_path, "r") as handle:
                    workflow = yaml.load(handle, Loader=PreservingLoader)
            except Exception as exc:
                return WorkflowMappingValidationResult(
                    None,
                    (ValidationError(f"Failed to load workflow: {exc}"),),
                )

            if workflow is None or not isinstance(workflow, dict):
                return WorkflowMappingValidationResult(
                    None,
                    (ValidationError("Workflow must be a YAML object/dictionary"),),
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

        imported_workflows: Dict[str, LoadedWorkflowBundle] = {}
        errors: list[ValidationError] = []
        for alias, import_path in imports.items():
            context = f"imports.{alias}"
            if not isinstance(alias, str) or not alias.strip():
                errors.append(
                    ValidationError(f"{context}: import alias must be a non-empty string")
                )
                continue
            if not isinstance(import_path, str) or not import_path.strip():
                errors.append(
                    ValidationError(f"{context}: import path must be a non-empty string")
                )
                continue
            try:
                resolved_import_path = self._resolve_import_path(workflow_path, import_path)
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
            raise ValueError("import paths must be literal workflow-relative strings")
        candidate = Path(import_path)
        if candidate.is_absolute():
            raise ValueError(f"absolute import paths are not allowed: {import_path}")
        resolved = (workflow_path.parent / candidate).resolve()
        try:
            resolved.relative_to(self.workspace)
        except ValueError as exc:
            raise ValueError(
                "asset path traversal outside the workflow source tree is not allowed: "
                f"{import_path}"
            ) from exc
        return resolved

    def _version_at_least(self, version: str, minimum: str) -> bool:
        if version not in self.VERSION_ORDER or minimum not in self.VERSION_ORDER:
            return False
        return self.VERSION_ORDER.index(version) >= self.VERSION_ORDER.index(minimum)
