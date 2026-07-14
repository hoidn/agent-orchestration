"""Workflow loader and strict DSL validation per specs/dsl.md."""

import json
import math
import re
from copy import deepcopy
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Set
import yaml

from orchestrator.contracts.output_contract import OutputContractError, validate_contract_value
from orchestrator.exceptions import ValidationError, ValidationSubjectRef, WorkflowValidationError
from orchestrator.providers import (
    ProviderRegistry,
    ProviderSessionMetadataMode,
    ProviderSessionSupport,
    ProviderTemplate,
)
from orchestrator.workflow.assets import AssetResolutionError, WorkflowAssetResolver
from orchestrator.workflow.elaboration import elaborate_surface_workflow
from orchestrator.workflow.identity import STEP_ID_PATTERN
from orchestrator.workflow.loaded_bundle import (
    LoadedWorkflowBundle,
    workflow_input_contracts,
    workflow_managed_write_root_inputs,
    workflow_output_contracts,
)
from orchestrator.workflow.lowering import build_loaded_workflow_bundle
from orchestrator.workflow.predicates import (
    SCORE_PREDICATE_BOUND_KEYS,
    TYPED_PREDICATE_OPERATOR_KEYS,
    is_numeric_predicate_value,
    typed_predicate_operator_keys,
)
from orchestrator.workflow.references import ReferenceResolutionError, parse_structured_ref
from orchestrator.workflow.signatures import WORKFLOW_SIGNATURE_VERSION
from orchestrator.workflow.statements import (
    STRUCTURED_FINALLY_VERSION,
    STRUCTURED_IF_VERSION,
    STRUCTURED_MATCH_VERSION,
    STRUCTURED_REPEAT_UNTIL_VERSION,
    STRUCTURED_REPEAT_UNTIL_ON_EXHAUSTED_VERSION,
    branch_token,
    is_if_statement,
    is_match_statement,
    is_repeat_until_statement,
    match_case_token,
    normalize_match_case_block,
    normalize_branch_block,
    normalize_finally_block,
    normalize_repeat_until_block,
)


class PreservingLoader(yaml.SafeLoader):
    """Custom YAML loader that preserves string keys like 'on' instead of converting to bool."""
    pass


class WorkflowBoundaryValidationPolicy(str, Enum):
    """How strictly shared-loader boundary validation should gate bundle construction."""

    PUBLIC_CALLABLE = "public_callable"
    DEDICATED_RUNTIME_PROOF = "dedicated_runtime_proof"


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


class WorkflowLoader:
    """Loads and validates workflow YAML with strict DSL enforcement."""

    SUPPORTED_VERSIONS = {
        "1.1", "1.1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8",
        "2.0", "2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "2.8", "2.9", "2.10", "2.11", "2.12", "2.13", "2.14", "2.15",
    }
    SUPPORTED_OUTPUT_TYPES = {"enum", "integer", "float", "bool", "relpath", "string"}
    PRIVATE_COLLECTION_OUTPUT_TYPES = {"optional", "list", "map"}
    STRING_CONTRACT_VERSION = "2.10"
    ENV_VAR_PATTERN = re.compile(r'\$\{env\.[^}]+\}')
    INPUT_REF_PATTERN = re.compile(r'\$\{inputs\.([A-Za-z0-9_-]+)\}')
    VERSION_ORDER = [
        "1.1", "1.1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8",
        "2.0", "2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "2.8", "2.9", "2.10", "2.11", "2.12", "2.13", "2.14",
        "2.15",
    ]

    def __init__(
        self,
        workspace: Path,
        *,
        boundary_validation_policy: "WorkflowBoundaryValidationPolicy" = None,
    ):
        """Initialize loader with workspace root."""
        if boundary_validation_policy is None:
            boundary_validation_policy = WorkflowBoundaryValidationPolicy.PUBLIC_CALLABLE
        self.workspace = workspace.resolve()
        self.errors: List[ValidationError] = []
        self._workflow_input_specs: Dict[str, Dict[str, Any]] = {}
        self._current_workflow_path: Optional[Path] = None
        self._current_source_root: Optional[Path] = None
        self._current_imports: Dict[str, Any] = {}
        self._load_stack: List[Path] = []
        self._provider_registry = ProviderRegistry()
        self._current_workflow_is_imported = False
        self._current_validation_workflow_name: Optional[str] = None
        self._allow_private_collection_output_schemas = False
        self._allow_generated_repeat_until_on_exhausted_refs = False
        self._boundary_validation_policy = boundary_validation_policy
        self._dedicated_runtime_proof_nested_structured_step_names: Set[str] = set()
        self._dedicated_runtime_proof_parent_ref_allowances: Set[tuple[str, str]] = set()
        self._generated_repeat_until_on_exhausted_refs: Dict[str, Dict[str, str]] = {}

    def load(self, workflow_path: Path) -> LoadedWorkflowBundle:
        """Load and validate workflow YAML into the typed bundle surface."""
        return self.load_bundle(workflow_path)

    def load_bundle(self, workflow_path: Path) -> LoadedWorkflowBundle:
        """Load and validate workflow YAML into the typed surface bundle."""
        self.errors = []
        self._workflow_input_specs = {}
        self._current_imports = {}
        self._provider_registry = ProviderRegistry()
        self._current_validation_workflow_name = None
        self._generated_repeat_until_on_exhausted_refs = {}
        workflow = self._load_workflow(Path(workflow_path).resolve())
        if self.errors:
            self._raise_validation_errors()
        return workflow

    def _load_workflow(
        self,
        workflow_path: Path,
        *,
        expected_version: Optional[str] = None,
    ) -> LoadedWorkflowBundle:
        """Load and validate one workflow file without clearing accumulated errors."""
        resolved_workflow_path = workflow_path.resolve()
        if resolved_workflow_path in self._load_stack:
            try:
                display_path = str(resolved_workflow_path.relative_to(self.workspace))
            except ValueError:
                display_path = str(resolved_workflow_path)
            self._add_error(f"Circular import detected while loading '{display_path}'")
            return {}

        previous_input_specs = self._workflow_input_specs
        previous_workflow_path = self._current_workflow_path
        previous_source_root = self._current_source_root
        previous_imports = self._current_imports
        previous_workflow_is_imported = self._current_workflow_is_imported

        self._load_stack.append(resolved_workflow_path)
        self._workflow_input_specs = {}
        self._current_workflow_path = resolved_workflow_path
        self._current_source_root = resolved_workflow_path.parent
        self._current_imports = {}
        self._current_workflow_is_imported = expected_version is not None

        try:
            try:
                with open(resolved_workflow_path, 'r') as f:
                    workflow = yaml.load(f, Loader=PreservingLoader)
            except Exception as e:
                self._add_error(f"Failed to load workflow: {e}")
                return {}

            if workflow is None or not isinstance(workflow, dict):
                self._add_error("Workflow must be a YAML object/dictionary")
                return {}

            assert isinstance(workflow, dict), "Type narrowing for workflow"
            version = workflow.get('version')
            if not version:
                self._add_error("'version' field is required")
                version = ""
            elif not isinstance(version, str):
                self._add_error(f"'version' field must be a string, got {type(version).__name__}")
                version = ""
            elif version not in self.SUPPORTED_VERSIONS:
                self._add_error(f"Unsupported version '{version}'. Supported: {self.SUPPORTED_VERSIONS}")

            if isinstance(version, str) and version:
                inputs = workflow.get("inputs")
                if isinstance(inputs, dict):
                    self._workflow_input_specs = {
                        str(name): spec
                        for name, spec in inputs.items()
                        if isinstance(name, str) and isinstance(spec, dict)
                    }
                self._normalize_v214_ergonomics(workflow, version)

            surface_source = deepcopy(workflow)

            if expected_version and isinstance(version, str) and version and version != expected_version:
                self._add_error(
                    f"Imported workflows must declare the same DSL version as their caller "
                    f"(expected '{expected_version}', found '{version}')"
                )

            imported_bundles = self._load_imports(workflow.get('imports'), version, resolved_workflow_path)
            self._current_imports = dict(imported_bundles)

            surface = elaborate_surface_workflow(
                surface_source,
                workflow_path=resolved_workflow_path,
                imported_bundles=imported_bundles,
                validation_backend=self,
                workflow_is_imported=expected_version is not None,
                allow_generated_step_kinds=(
                    self._boundary_validation_policy
                    is WorkflowBoundaryValidationPolicy.DEDICATED_RUNTIME_PROOF
                ),
            )
            if surface is None:
                return {}
            return build_loaded_workflow_bundle(surface, imports=imported_bundles)
        finally:
            self._load_stack.pop()
            self._workflow_input_specs = previous_input_specs
            self._current_workflow_path = previous_workflow_path
            self._current_source_root = previous_source_root
            self._current_imports = previous_imports
            self._current_workflow_is_imported = previous_workflow_is_imported

    def _normalize_v214_ergonomics(self, workflow: Dict[str, Any], version: str) -> None:
        """Expand narrow v2.14 ergonomics shorthands into existing runtime shapes."""
        if not self._version_at_least(version, "2.14"):
            return

        def normalize_steps(steps: Any) -> None:
            if not isinstance(steps, list):
                return
            for step in steps:
                if not isinstance(step, dict):
                    continue
                self._expand_materialize_input_values(step)
                if is_if_statement(step):
                    for branch_name in ("then", "else"):
                        branch = normalize_branch_block(step.get(branch_name), branch_name)
                        if isinstance(branch, dict):
                            normalize_steps(branch.get("steps"))
                if is_match_statement(step):
                    match_node = step.get("match")
                    cases = match_node.get("cases") if isinstance(match_node, dict) else None
                    if isinstance(cases, dict):
                        for case_name, authored_case in cases.items():
                            case_block = normalize_match_case_block(authored_case, str(case_name))
                            if isinstance(case_block, dict):
                                normalize_steps(case_block.get("steps"))
                repeat_until = normalize_repeat_until_block(step.get("repeat_until"))
                if isinstance(repeat_until, dict):
                    normalize_steps(repeat_until.get("steps"))
                for_each = step.get("for_each")
                if isinstance(for_each, dict):
                    normalize_steps(for_each.get("steps"))

        normalize_steps(workflow.get("steps"))
        finalization = normalize_finally_block(workflow.get("finally"))
        if isinstance(finalization, dict):
            normalize_steps(finalization.get("steps"))

    def _expand_materialize_input_values(self, step: Dict[str, Any]) -> None:
        """Expand materialize_artifacts.input_values into long-form values entries."""
        materialize_artifacts = step.get("materialize_artifacts")
        if not isinstance(materialize_artifacts, dict):
            return

        input_values = materialize_artifacts.get("input_values")
        if input_values is None:
            return

        step_name = step.get("name", "<unnamed>")
        context = f"Step '{step_name}': materialize_artifacts"
        if not isinstance(input_values, list):
            self._add_error(f"{context}.input_values must be a list")
            return

        existing_values = materialize_artifacts.get("values")
        expanded_values: List[Dict[str, Any]] = []
        seen_names: Set[str] = set()
        if isinstance(existing_values, list):
            for spec in existing_values:
                if isinstance(spec, dict) and isinstance(spec.get("name"), str) and spec["name"].strip():
                    seen_names.add(spec["name"])

        for group_index, group in enumerate(input_values):
            group_context = f"{context}.input_values[{group_index}]"
            if not isinstance(group, dict):
                self._add_error(f"{group_context} must be a dictionary")
                continue

            names = group.get("names")
            if not isinstance(names, list) or not names:
                self._add_error(f"{group_context}.names must be a non-empty list")
                continue

            contract_mode = group.get("contract")
            if contract_mode != "inherit":
                self._add_error(f"{group_context}.contract must be the literal 'inherit'")
                continue

            pointer_template = group.get("pointer_template")
            if not isinstance(pointer_template, str):
                self._add_error(f"{group_context}.pointer_template must be a string")
                continue
            if "{name}" not in pointer_template:
                self._add_error(f"{group_context}.pointer_template must contain '{{name}}'")
                continue

            for raw_name in names:
                if not isinstance(raw_name, str) or not raw_name.strip():
                    self._add_error(f"{group_context}.names entries must be non-empty strings")
                    continue
                name = raw_name.strip()
                if not isinstance(self._workflow_input_specs.get(name), dict):
                    self._add_error(f"{group_context}.names references unknown workflow input '{name}'")
                    continue
                if name in seen_names:
                    self._add_error(f"{group_context} expands duplicate materialized name '{name}'")
                    continue

                pointer_path = pointer_template.replace("{name}", name)
                self._validate_path_safety(pointer_path, f"{group_context}.pointer_template")

                expanded_values.append(
                    {
                        "name": name,
                        "source": {"input": name},
                        "contract": {"inherit": "source"},
                        "pointer": {"path": pointer_path},
                    }
                )
                seen_names.add(name)

        normalized = dict(materialize_artifacts)
        normalized_values = list(existing_values) if isinstance(existing_values, list) else []
        normalized_values.extend(expanded_values)
        normalized["values"] = normalized_values
        normalized.pop("input_values", None)
        step["materialize_artifacts"] = normalized

    def _validate_top_level(self, workflow: Dict[str, Any], version: str):
        """Validate top-level workflow fields."""
        workflow_name = workflow.get('name')
        self._current_validation_workflow_name = workflow_name if isinstance(workflow_name, str) else None

        # Known fields at version 1.1/1.1.1
        known_fields = {
            'version', 'name', 'strict_flow', 'context', 'providers', 'secrets',
            'inbox_dir', 'processed_dir', 'failed_dir', 'task_extension', 'steps',
            'artifacts', 'max_transitions', 'inputs', 'outputs', 'finally', 'imports'
        }
        if self._version_at_least(version, "2.15"):
            known_fields.add("result_guidance")

        # Strict unknown field rejection (skip if version is invalid/empty)
        if version:
            for key in workflow.keys():
                if key not in known_fields:
                    self._add_error(f"Unknown field '{key}' at version '{version}'")

        # Validate providers if present
        if 'providers' in workflow:
            self._validate_providers(workflow['providers'], version)

        # Validate secrets if present
        if 'secrets' in workflow:
            self._validate_secrets(workflow['secrets'])

        # Path safety for directories
        for dir_field in ['inbox_dir', 'processed_dir', 'failed_dir']:
            if dir_field in workflow:
                self._validate_path_safety(workflow[dir_field], dir_field)

        if 'artifacts' in workflow:
            if not self._version_at_least(version, "1.2"):
                self._add_error("artifacts requires version '1.2'")
            else:
                self._validate_artifacts_registry(workflow['artifacts'], version)

        if 'max_transitions' in workflow:
            if not self._version_at_least(version, "1.8"):
                self._add_error("max_transitions requires version '1.8'")
            else:
                self._validate_positive_integer(
                    workflow['max_transitions'],
                    "max_transitions",
                    allow_zero=False,
                )

        if 'inputs' in workflow:
            if not self._version_at_least(version, WORKFLOW_SIGNATURE_VERSION):
                self._add_error(f"inputs requires version '{WORKFLOW_SIGNATURE_VERSION}'")
            else:
                self._validate_workflow_inputs(workflow['inputs'], version)

        if 'outputs' in workflow and not self._version_at_least(version, WORKFLOW_SIGNATURE_VERSION):
            self._add_error(f"outputs requires version '{WORKFLOW_SIGNATURE_VERSION}'")

        if 'result_guidance' in workflow:
            if not self._version_at_least(version, "2.15"):
                self._add_error("result_guidance requires version '2.15'")
            else:
                outputs = workflow.get("outputs")
                if not isinstance(outputs, dict) or not outputs:
                    self._add_error("result_guidance requires at least one declared output")
                self._validate_guidance_payload(
                    workflow["result_guidance"],
                    context="result_guidance",
                    version=version,
                    allow_context=False,
                )

        if 'finally' in workflow and not self._version_at_least(version, STRUCTURED_FINALLY_VERSION):
            self._add_error(f"finally requires version '{STRUCTURED_FINALLY_VERSION}'")

        if 'imports' in workflow and not self._version_at_least(version, "2.5"):
            self._add_error("imports requires version '2.5'")

    def error_count(self) -> int:
        """Return the current number of accumulated validation errors."""
        return len(self.errors)

    def add_error(self, message: str) -> None:
        """Public validation hook used by the elaboration phase."""
        self._add_error(message)

    def version_at_least(self, version: str, minimum: str) -> bool:
        """Public version comparison hook used by the elaboration phase."""
        return self._version_at_least(version, minimum)

    def validate_top_level(self, workflow: Dict[str, Any], version: str) -> None:
        """Public validation hook used by the elaboration phase."""
        self._validate_top_level(workflow, version)

    def build_finalization_catalog_steps(
        self,
        finalization: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Public validation hook used by the elaboration phase."""
        return self._build_finalization_catalog_steps(finalization)

    def build_root_ref_catalog(
        self,
        steps: List[Any],
        artifacts_registry: Optional[Any],
    ) -> Dict[str, Any]:
        """Public validation hook used by the elaboration phase."""
        return self._build_root_ref_catalog(steps, artifacts_registry)

    def validate_steps(
        self,
        steps: List[Any],
        version: str,
        artifacts_registry: Optional[Any] = None,
        *,
        root_catalog: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Public validation hook used by the elaboration phase."""
        self._validate_steps(
            steps,
            version,
            artifacts_registry,
            root_catalog=root_catalog,
        )

    def validate_finally_block(
        self,
        finalization: Optional[Dict[str, Any]],
        version: str,
        artifacts_registry: Optional[Any],
        root_catalog: Dict[str, Any],
    ) -> None:
        """Public validation hook used by the elaboration phase."""
        self._validate_finally_block(finalization, version, artifacts_registry, root_catalog)

    def validate_dataflow_cross_references(
        self,
        steps: List[Dict[str, Any]],
        artifacts_registry: Optional[Any],
    ) -> None:
        """Public validation hook used by the elaboration phase."""
        self._validate_dataflow_cross_references(steps, artifacts_registry)

    def validate_workflow_outputs(
        self,
        outputs: Any,
        version: str,
        root_catalog: Dict[str, Any],
    ) -> None:
        """Public validation hook used by the elaboration phase."""
        self._validate_workflow_outputs(outputs, version, root_catalog)

    def validate_goto_targets(self, workflow: Dict[str, Any]) -> None:
        """Public validation hook used by the elaboration phase."""
        self._validate_goto_targets(workflow)

    def analyze_reusable_write_roots(self, workflow: Dict[str, Any]) -> tuple[Set[str], List[str]]:
        """Public validation hook used by the elaboration phase."""
        return self._analyze_reusable_write_roots(workflow)

    def validate_call_write_root_collisions(self, steps: Any, finally_block: Any) -> None:
        """Public validation hook used by the elaboration phase."""
        self._validate_call_write_root_collisions(steps, finally_block)

    def _load_imports(
        self,
        imports: Any,
        version: str,
        workflow_path: Path,
    ) -> Dict[str, LoadedWorkflowBundle]:
        """Load imported workflows relative to the authored workflow file."""
        if imports is None:
            return {}
        if not isinstance(imports, dict):
            self._add_error("'imports' must be a dictionary")
            return {}
        if not self._version_at_least(version, "2.5"):
            return {}

        imported_workflows: Dict[str, LoadedWorkflowBundle] = {}
        for alias, import_path in imports.items():
            context = f"imports.{alias}"
            if not isinstance(alias, str) or not alias.strip():
                self._add_error(f"{context}: import alias must be a non-empty string")
                continue
            if not isinstance(import_path, str) or not import_path.strip():
                self._add_error(f"{context}: import path must be a non-empty string")
                continue

            try:
                resolved_import_path = self._resolve_import_path(workflow_path, import_path)
            except ValueError as exc:
                self._add_error(f"{context}: {exc}")
                continue

            error_start = len(self.errors)
            imported_workflow = self._load_workflow(
                resolved_import_path,
                expected_version=version if self._version_at_least(version, "2.5") else None,
            )
            if len(self.errors) > error_start:
                for error in self.errors[error_start:]:
                    error.message = f"Import '{alias}': {error.message}"
                continue
            imported_workflows[alias] = imported_workflow

        return imported_workflows

    def _resolve_import_path(self, workflow_path: Path, import_path: str) -> Path:
        """Resolve an import path relative to the authored workflow while keeping it in WORKSPACE."""
        if not isinstance(import_path, str) or not import_path.strip():
            raise ValueError("import path must be a non-empty string")
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
                f"asset path traversal outside the workflow source tree is not allowed: {import_path}"
            ) from exc
        return resolved

    def _validate_workflow_inputs(self, inputs: Any, version: str) -> None:
        """Validate top-level workflow input contracts."""
        if not isinstance(inputs, dict):
            self._add_error("'inputs' must be a dictionary")
            return

        self._workflow_input_specs = {}
        for input_name, spec in inputs.items():
            context = f"inputs.{input_name}"
            if not isinstance(input_name, str) or not input_name.strip():
                self._add_error(f"{context}: input name must be a non-empty string")
                continue

            self._validate_workflow_signature_contract(
                spec,
                context,
                version,
                allow_from=False,
                subject_refs=self._workflow_subject_refs("generated_input", input_name),
            )
            if isinstance(spec, dict):
                self._workflow_input_specs[input_name] = spec

    def _validate_workflow_outputs(
        self,
        outputs: Any,
        version: str,
        root_catalog: Dict[str, Any],
    ) -> None:
        """Validate top-level workflow output contracts and export refs."""
        if not isinstance(outputs, dict):
            self._add_error("'outputs' must be a dictionary")
            return

        scope_artifacts = root_catalog.get('artifacts', {})
        scope_multi_visit = root_catalog.get('multi_visit', set())
        scope_non_step_results = root_catalog.get('non_step_results', set())

        for output_name, spec in outputs.items():
            context = f"outputs.{output_name}"
            if not isinstance(output_name, str) or not output_name.strip():
                self._add_error(f"{context}: output name must be a non-empty string")
                continue

            self._validate_workflow_signature_contract(
                spec,
                context,
                version,
                allow_from=True,
                subject_refs=self._workflow_subject_refs("generated_output", output_name),
            )
            if not isinstance(spec, dict):
                continue

            binding = spec.get('from')
            ref = binding.get('ref') if isinstance(binding, dict) else None
            if not isinstance(ref, str) or not ref:
                continue
            projection = spec.get('projection')
            projection_class = projection.get('projection_class') if isinstance(projection, dict) else None
            if projection_class == 'provider_bundle_path_projection':
                bundle_path_ref = projection.get('bundle_path_ref') if isinstance(projection, dict) else None
                if not isinstance(bundle_path_ref, str) or not bundle_path_ref:
                    self._add_error(
                        (
                            f"{context}.projection.bundle_path_ref must be a non-empty string "
                            "for provider bundle projections"
                        ),
                        subject_refs=self._workflow_subject_refs("generated_output", output_name),
                    )
                    continue
                if ref != bundle_path_ref:
                    self._add_error(
                        (
                            f"{context}.from must match projection.bundle_path_ref "
                            "for provider bundle projections"
                        ),
                        subject_refs=self._workflow_subject_refs("generated_output", output_name),
                    )
                    continue
                if not self._validate_provider_bundle_projection_contract(
                    spec,
                    projection,
                    context=context,
                    output_name=output_name,
                ):
                    continue
            allows_input_projection_ref = (
                projection_class == 'provider_bundle_path_projection'
                and ref.startswith('inputs.')
            )
            if not ref.startswith('root.steps.') and not allows_input_projection_ref:
                self._add_error(
                    (
                        f"{context}.from must reference root.steps.*"
                        if projection_class != 'provider_bundle_path_projection'
                        else f"{context}.from must reference root.steps.* or inputs.*"
                    ),
                    subject_refs=self._workflow_subject_refs("generated_output", output_name),
                )
                continue

            ref_type = self._validate_structured_ref(
                ref,
                f"workflow output '{output_name}'",
                version,
                root_catalog,
                scope_artifacts,
                scope_multi_visit,
                None,
                None,
                scope_non_step_results,
                None,
            )
            declared_type = spec.get('type')
            if ref_type == 'unknown' or not isinstance(declared_type, str):
                continue
            if declared_type == ref_type:
                continue
            if declared_type == 'float' and ref_type == 'integer':
                continue
            self._add_error(
                f"{context}.from resolves to '{ref_type}' but output declares '{declared_type}'",
                subject_refs=self._workflow_subject_refs("generated_output", output_name),
            )

    def _validate_provider_bundle_projection_contract(
        self,
        spec: dict[str, Any],
        projection: dict[str, Any],
        *,
        context: str,
        output_name: str,
    ) -> bool:
        subject_refs = self._workflow_subject_refs("generated_output", output_name)
        bundle_under = projection.get('bundle_under')
        if not isinstance(bundle_under, str) or not bundle_under:
            self._add_error(
                (
                    f"{context}.projection.bundle_under must be a non-empty string "
                    "for provider bundle projections"
                ),
                subject_refs=subject_refs,
            )
            return False
        bundle_must_exist_target = projection.get('bundle_must_exist_target')
        if not isinstance(bundle_must_exist_target, bool):
            self._add_error(
                (
                    f"{context}.projection.bundle_must_exist_target must be a boolean "
                    "for provider bundle projections"
                ),
                subject_refs=subject_refs,
            )
            return False

        declared_under = spec.get('under')
        if declared_under != bundle_under:
            self._add_error(
                (
                    f"{context} provider bundle projection must remain under `{bundle_under}`; "
                    f"got `{declared_under}`"
                ),
                subject_refs=subject_refs,
            )
            return False

        declared_must_exist_target = spec.get('must_exist_target')
        if bundle_must_exist_target and declared_must_exist_target is not True:
            self._add_error(
                (
                    f"{context} provider bundle projection must preserve "
                    "`must_exist_target: true` from the provider bundle authority"
                ),
                subject_refs=subject_refs,
            )
            return False
        return True

    def _validate_workflow_signature_contract(
        self,
        spec: Any,
        context: str,
        version: str,
        *,
        allow_from: bool,
        subject_refs: tuple[ValidationSubjectRef, ...] = (),
    ) -> None:
        """Validate one workflow-boundary input/output contract."""
        if not isinstance(spec, dict):
            self._add_error(f"{context} must be a dictionary", subject_refs=subject_refs)
            return

        allowed_fields = {
            'kind',
            'type',
            'allowed',
            'under',
            'must_exist_target',
            'description',
            'item',
            'items',
            'keys',
            'values',
            '__allow_unresolved_source',
        }
        if allow_from:
            allowed_fields.add('from')
            allowed_fields.add('projection')
        else:
            allowed_fields.update({'required', 'default'})

        for field_name in spec.keys():
            if field_name not in allowed_fields:
                self._add_error(f"{context}: unknown field '{field_name}'", subject_refs=subject_refs)

        kind = spec.get('kind', 'relpath')
        if not isinstance(kind, str):
            self._add_error(f"{context}.kind must be a string", subject_refs=subject_refs)
            kind = 'relpath'
        elif kind not in {'relpath', 'scalar', 'collection'}:
            self._add_error(f"{context}.kind invalid kind '{kind}'", subject_refs=subject_refs)

        output_type = spec.get('type')
        if output_type is None:
            self._add_error(f"{context} missing required 'type'", subject_refs=subject_refs)
        elif not isinstance(output_type, str):
            self._add_error(f"{context}.type must be a string", subject_refs=subject_refs)
        elif output_type not in self._supported_output_types(version):
            self._add_error(f"{context}.type invalid type '{output_type}'", subject_refs=subject_refs)

        if 'description' in spec and not isinstance(spec['description'], str):
            self._add_error(f"{context}.description must be a string", subject_refs=subject_refs)

        if not allow_from and 'required' in spec and not isinstance(spec['required'], bool):
            self._add_error(f"{context}.required must be a boolean", subject_refs=subject_refs)

        if kind == 'relpath':
            if output_type is not None and output_type != 'relpath':
                self._add_error(
                    f"{context}: kind 'relpath' requires type 'relpath'",
                    subject_refs=subject_refs,
                )
            if 'under' in spec:
                if not isinstance(spec['under'], str):
                    self._add_error(f"{context}.under must be a string", subject_refs=subject_refs)
                else:
                    self._validate_path_safety(spec['under'], f"{context}.under", subject_refs=subject_refs)
            if 'must_exist_target' in spec and not isinstance(spec['must_exist_target'], bool):
                self._add_error(
                    f"{context}.must_exist_target must be a boolean",
                    subject_refs=subject_refs,
                )
        elif kind == 'scalar':
            if output_type not in self._supported_scalar_types(version):
                self._add_error(
                    f"{context}: kind 'scalar' requires type one of {self._scalar_type_list(version)}",
                    subject_refs=subject_refs,
                )
            if 'under' in spec:
                self._add_error(f"{context}: kind 'scalar' forbids 'under'", subject_refs=subject_refs)
            if 'must_exist_target' in spec:
                self._add_error(
                    f"{context}: kind 'scalar' forbids 'must_exist_target'",
                    subject_refs=subject_refs,
                )
            for field_name in ('item', 'items', 'keys', 'values'):
                if field_name in spec:
                    self._add_error(
                        f"{context}: kind 'scalar' forbids '{field_name}'",
                        subject_refs=subject_refs,
                    )
        elif kind == 'collection':
            if output_type not in self.PRIVATE_COLLECTION_OUTPUT_TYPES:
                self._add_error(
                    f"{context}: kind 'collection' requires type one of optional|list|map",
                    subject_refs=subject_refs,
                )
            elif not (
                (
                    self._allow_private_collection_output_schemas
                    and self._version_at_least(version, "2.14")
                )
                or (allow_from and self._version_at_least(version, "2.15"))
            ):
                self._add_error(
                    f"{context}: kind 'collection' is only available for frontend-lowered workflows",
                    subject_refs=subject_refs,
                )
            if 'under' in spec:
                self._add_error(f"{context}: kind 'collection' forbids 'under'", subject_refs=subject_refs)
            if 'must_exist_target' in spec:
                self._add_error(
                    f"{context}: kind 'collection' forbids 'must_exist_target'",
                    subject_refs=subject_refs,
                )
            self._validate_output_schema_spec(
                spec,
                field_context=context,
                version=version,
                subject_refs=subject_refs,
                kind_label="workflow boundary",
                allow_guidance_keys=True,
            )

        if output_type == 'enum' and 'allowed' not in spec:
            self._add_error(f"{context} enum type requires 'allowed'", subject_refs=subject_refs)
        if 'allowed' in spec and not isinstance(spec['allowed'], list):
            self._add_error(f"{context}.allowed must be a list", subject_refs=subject_refs)

        if not allow_from and 'default' in spec:
            try:
                validate_contract_value(spec['default'], spec, workspace=self.workspace)
            except OutputContractError as exc:
                self._add_error(
                    f"{context}.default is invalid: {exc}",
                    subject_refs=subject_refs,
                )

        if allow_from:
            binding = spec.get('from')
            if binding is None:
                self._add_error(f"{context} missing required 'from'", subject_refs=subject_refs)
            elif not isinstance(binding, dict):
                self._add_error(f"{context}.from must be a dictionary", subject_refs=subject_refs)
            elif set(binding.keys()) != {'ref'}:
                self._add_error(f"{context}.from must be exactly {{ref: ...}}", subject_refs=subject_refs)
            elif not isinstance(binding.get('ref'), str) or not binding.get('ref'):
                self._add_error(
                    f"{context}.from.ref must be a non-empty string",
                    subject_refs=subject_refs,
                )

    def _validate_secrets(self, secrets: Any):
        """Validate secrets configuration."""
        if not isinstance(secrets, list):
            self._add_error("'secrets' must be a list of environment variable names")
            return

        for i, secret in enumerate(secrets):
            if not isinstance(secret, str):
                self._add_error(f"'secrets[{i}]' must be a string")
            elif not secret:
                self._add_error(f"'secrets[{i}]' cannot be empty")

    def _validate_providers(self, providers: Dict[str, Any], version: str):
        """Validate provider templates."""
        if not isinstance(providers, dict):
            self._add_error("'providers' must be a dictionary")
            return

        for name, config in providers.items():
            error_count = len(self.errors)
            if not isinstance(config, dict):
                self._add_error(f"Provider '{name}' must be a dictionary")
                continue

            if 'command' not in config:
                self._add_error(f"Provider '{name}' missing required 'command' field")
            elif not isinstance(config['command'], list):
                self._add_error(f"Provider '{name}' command must be a list")
            else:
                # AT-49: Check for ${PROMPT} in stdin mode
                input_mode = config.get('input_mode', 'argv')
                if input_mode == 'stdin':
                    command_str = ' '.join(str(token) for token in config['command'])
                    if '${PROMPT}' in command_str:
                        self._add_error(
                            f"Provider '{name}': ${{PROMPT}} not allowed in stdin mode"
                        )

            if 'input_mode' in config:
                if config['input_mode'] not in ['argv', 'stdin']:
                    self._add_error(f"Provider '{name}' input_mode must be 'argv' or 'stdin'")

            session_support_node = config.get("session_support")
            session_support: Optional[ProviderSessionSupport] = None
            if session_support_node is not None:
                if not self._version_at_least(version, self.STRING_CONTRACT_VERSION):
                    self._add_error(
                        f"Provider '{name}': session_support requires version '{self.STRING_CONTRACT_VERSION}'"
                    )
                elif not isinstance(session_support_node, dict):
                    self._add_error(f"Provider '{name}': session_support must be a dictionary")
                else:
                    metadata_mode = session_support_node.get("metadata_mode")
                    fresh_command = session_support_node.get("fresh_command")
                    resume_command = session_support_node.get("resume_command")
                    if not isinstance(metadata_mode, str) or not metadata_mode:
                        self._add_error(
                            f"Provider '{name}': session_support.metadata_mode must be a non-empty string"
                        )
                    elif metadata_mode != ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value:
                        self._add_error(
                            f"Provider '{name}': unsupported session_support.metadata_mode '{metadata_mode}'"
                        )
                    if not isinstance(fresh_command, list) or not fresh_command:
                        self._add_error(
                            f"Provider '{name}': session_support.fresh_command must be a non-empty list"
                        )
                    elif any(not isinstance(token, str) for token in fresh_command):
                        self._add_error(
                            f"Provider '{name}': session_support.fresh_command entries must be strings"
                        )
                    if resume_command is not None:
                        if not isinstance(resume_command, list) or not resume_command:
                            self._add_error(
                                f"Provider '{name}': session_support.resume_command must be a non-empty list"
                            )
                        elif any(not isinstance(token, str) for token in resume_command):
                            self._add_error(
                                f"Provider '{name}': session_support.resume_command entries must be strings"
                            )

                    if (
                        isinstance(metadata_mode, str)
                        and isinstance(fresh_command, list)
                        and (resume_command is None or isinstance(resume_command, list))
                    ):
                        session_support = ProviderSessionSupport(
                            metadata_mode=metadata_mode,
                            fresh_command=fresh_command,
                            resume_command=resume_command,
                        )

            if len(self.errors) != error_count:
                continue

            try:
                template = ProviderTemplate(
                    name=name,
                    command=config.get("command", []),
                    defaults=config.get("defaults", {}),
                    input_mode=config.get("input_mode", "argv"),
                    session_support=session_support,
                )
            except Exception as exc:
                self._add_error(f"Provider '{name}': {exc}")
                continue

            for error in template.validate():
                self._add_error(error)

            if len(self.errors) != error_count:
                continue

            try:
                self._provider_registry.register(template)
            except ValueError as exc:
                self._add_error(str(exc))

    def _validate_steps(
        self,
        steps: List[Any],
        version: str,
        artifacts_registry: Optional[Any] = None,
        root_catalog: Optional[Dict[str, Any]] = None,
        scope_artifacts: Optional[Dict[str, Any]] = None,
        parent_artifacts: Optional[Dict[str, Any]] = None,
        scope_multi_visit: Optional[Set[str]] = None,
        parent_multi_visit: Optional[Set[str]] = None,
        scope_non_step_results: Optional[Set[str]] = None,
        parent_non_step_results: Optional[Set[str]] = None,
        top_level: bool = True,
        allow_nested_structured: bool = False,
        proof_context: Optional[Dict[str, str]] = None,
    ):
        """Validate step definitions."""
        if not isinstance(steps, list):
            self._add_error("'steps' must be a list")
            return

        if root_catalog is None:
            root_catalog = self._build_root_ref_catalog(steps, artifacts_registry)
        if scope_artifacts is None:
            scope_artifacts = root_catalog.get('artifacts', {})
        if scope_multi_visit is None:
            scope_multi_visit = root_catalog.get('multi_visit', set())
        if scope_non_step_results is None:
            scope_non_step_results = root_catalog.get('non_step_results', set())

        step_names = set()
        authored_ids = set()

        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                self._add_error(f"Step {i} must be a dictionary")
                continue

            # Name is required and must be unique
            name = step.get('name')
            if not name:
                self._add_error(f"Step {i} missing required 'name' field")
                # Use fallback name for subsequent error messages
                name = f"<step_{i}>"
            elif not isinstance(name, str):
                self._add_error(f"Step {i} name must be a string, got {type(name).__name__}")
                name = f"<step_{i}>"
            elif name in step_names:
                self._add_error(f"Duplicate step name '{name}'")
            else:
                step_names.add(name)

            authored_id = step.get('id')
            if authored_id is not None:
                if not self._version_at_least(version, "2.0"):
                    self._add_error(f"Step '{name}': id requires version '2.0'")
                elif not isinstance(authored_id, str) or not STEP_ID_PATTERN.fullmatch(authored_id):
                    self._add_error(
                        f"Step '{name}': id must match {STEP_ID_PATTERN.pattern}"
                    )
                elif authored_id in authored_ids:
                    self._add_error(f"Duplicate step id '{authored_id}'")
                else:
                    authored_ids.add(authored_id)

            if is_if_statement(step) and is_match_statement(step):
                self._add_error(
                    f"Step '{name}': structured if/else cannot be combined with structured match"
                )
                continue
            if is_repeat_until_statement(step) and (is_if_statement(step) or is_match_statement(step)):
                self._add_error(
                    f"Step '{name}': repeat_until cannot be combined with other structured control fields"
                )
                continue

            if is_if_statement(step):
                self._validate_if_statement(
                    step=step,
                    step_name=name,
                    version=version,
                    artifacts_registry=artifacts_registry,
                    root_catalog=root_catalog,
                    scope_artifacts=scope_artifacts,
                    scope_multi_visit=scope_multi_visit,
                    parent_artifacts=parent_artifacts,
                    parent_multi_visit=parent_multi_visit,
                    scope_non_step_results=scope_non_step_results,
                    parent_non_step_results=parent_non_step_results,
                    top_level=top_level,
                    allow_nested=allow_nested_structured
                    or name in self._dedicated_runtime_proof_nested_structured_step_names,
                    proof_context=proof_context,
                )
                continue

            if is_match_statement(step):
                self._validate_match_statement(
                    step=step,
                    step_name=name,
                    version=version,
                    artifacts_registry=artifacts_registry,
                    root_catalog=root_catalog,
                    scope_artifacts=scope_artifacts,
                    scope_multi_visit=scope_multi_visit,
                    parent_artifacts=parent_artifacts,
                    parent_multi_visit=parent_multi_visit,
                    scope_non_step_results=scope_non_step_results,
                    parent_non_step_results=parent_non_step_results,
                    top_level=top_level,
                    allow_nested=allow_nested_structured
                    or name in self._dedicated_runtime_proof_nested_structured_step_names,
                    proof_context=proof_context,
                )
                continue

            if is_repeat_until_statement(step):
                self._validate_repeat_until_statement(
                    step=step,
                    step_name=name,
                    version=version,
                    artifacts_registry=artifacts_registry,
                    root_catalog=root_catalog,
                    scope_artifacts=scope_artifacts,
                    scope_multi_visit=scope_multi_visit,
                    parent_artifacts=parent_artifacts,
                    parent_multi_visit=parent_multi_visit,
                    scope_non_step_results=scope_non_step_results,
                    parent_non_step_results=parent_non_step_results,
                    top_level=top_level,
                    proof_context=proof_context,
                )
                continue

            # AT-10: Provider/Command exclusivity
            execution_fields = [
                'provider',
                'adjudicated_provider',
                'command',
                'wait_for',
                'assert',
                'set_scalar',
                'increment_scalar',
                'materialize_artifacts',
                'select_variant_output',
                'call',
            ]
            exec_count = sum(1 for f in execution_fields if f in step)

            if 'for_each' in step:
                # for_each is exclusive with execution fields
                if exec_count > 0:
                    self._add_error(f"Step '{name}': for_each cannot be combined with {execution_fields}")
                self._validate_for_each(
                    step['for_each'],
                    name,
                    version,
                    artifacts_registry,
                    root_catalog,
                    scope_artifacts,
                    scope_multi_visit,
                    scope_non_step_results,
                    proof_context=proof_context,
                )

            if 'max_visits' in step:
                if not top_level or 'for_each' in step:
                    self._add_error(
                        f"Step '{name}': max_visits is only supported on top-level steps before stable internal IDs land"
                    )
                elif not self._version_at_least(version, "1.8"):
                    self._add_error(f"Step '{name}': max_visits requires version '1.8'")
                else:
                    self._validate_positive_integer(
                        step['max_visits'],
                        f"Step '{name}': max_visits",
                        allow_zero=False,
                    )
            if exec_count > 1:
                # AT-10: Mutual exclusivity
                present = [f for f in execution_fields if f in step]
                if 'assert' in present:
                    self._add_error(f"Step '{name}': assert cannot be combined with {present}")
                else:
                    self._add_error(f"Step '{name}': mutually exclusive fields {present}")

            if 'assert' in step:
                if not self._version_at_least(version, "1.5"):
                    self._add_error(f"Step '{name}': assert requires version '1.5'")
                else:
                    self._validate_assert_condition(
                    step['assert'],
                    name,
                    version,
                    root_catalog,
                    scope_artifacts,
                    scope_multi_visit,
                    parent_artifacts,
                    parent_multi_visit,
                    scope_non_step_results,
                    parent_non_step_results,
                )

            if 'set_scalar' in step:
                if not self._version_at_least(version, "1.7"):
                    self._add_error(f"Step '{name}': set_scalar requires version '1.7'")
                else:
                    self._validate_scalar_bookkeeping(
                        step=step,
                        node=step['set_scalar'],
                        field_name='set_scalar',
                        step_name=name,
                        artifacts_registry=artifacts_registry,
                    )

            if 'increment_scalar' in step:
                if not self._version_at_least(version, "1.7"):
                    self._add_error(f"Step '{name}': increment_scalar requires version '1.7'")
                else:
                    self._validate_scalar_bookkeeping(
                        step=step,
                        node=step['increment_scalar'],
                        field_name='increment_scalar',
                        step_name=name,
                        artifacts_registry=artifacts_registry,
                    )

            if 'materialize_artifacts' in step and not self._version_at_least(version, "2.14"):
                self._add_error(f"Step '{name}': materialize_artifacts requires version '2.14'")

            if 'select_variant_output' in step and not self._version_at_least(version, "2.14"):
                self._add_error(f"Step '{name}': select_variant_output requires version '2.14'")

            if 'call' in step:
                self._validate_call_step(
                    step=step,
                    step_name=name,
                    version=version,
                    root_catalog=root_catalog,
                    scope_artifacts=scope_artifacts,
                    scope_multi_visit=scope_multi_visit,
                    parent_artifacts=parent_artifacts,
                    parent_multi_visit=parent_multi_visit,
                    scope_non_step_results=scope_non_step_results,
                    parent_non_step_results=parent_non_step_results,
                )

            if 'adjudicated_provider' in step:
                self._validate_adjudicated_provider(
                    step=step,
                    step_name=name,
                    version=version,
                    artifacts_registry=artifacts_registry,
                )

            if 'managed_jobs' in step:
                self._validate_managed_jobs(step, name, version)

            # AT-40: Reject deprecated command_override
            if 'command_override' in step:
                self._add_error(f"Step '{name}': deprecated 'command_override' not supported")

            # Validate dependencies (version-gated features)
            if 'depends_on' in step:
                self._validate_dependencies(step['depends_on'], name, version)

            if 'asset_file' in step:
                self._validate_asset_file(step, name, version)

            if 'asset_depends_on' in step:
                self._validate_asset_depends_on(step, name, version)

            # Validate variables in allowed fields
            self._validate_variables_usage(step, name)

            # Path safety for file fields
            for field in ['input_file', 'output_file']:
                if field in step:
                    self._validate_path_safety(
                        step[field],
                        f"step '{name}' {field}",
                        subject_refs=self._workflow_subject_refs("step_id", name),
                    )

            # Validate deterministic artifact contracts
            if 'expected_outputs' in step:
                self._validate_expected_outputs(
                    step['expected_outputs'],
                    name,
                    version,
                    subject_refs=self._workflow_subject_refs("step_id", name),
                )

            if 'output_bundle' in step:
                if not self._version_at_least(version, "1.3"):
                    self._add_error(f"Step '{name}': output_bundle requires version '1.3'")
                else:
                    self._validate_output_bundle(
                        step['output_bundle'],
                        name,
                        version,
                        subject_refs=self._workflow_subject_refs("step_id", name),
                    )

            if 'variant_output' in step:
                if not self._version_at_least(version, "2.14"):
                    self._add_error(f"Step '{name}': variant_output requires version '2.14'")
                else:
                    self._validate_variant_output(
                        step['variant_output'],
                        name,
                        version,
                        subject_refs=self._workflow_subject_refs("step_id", name),
                    )

            if 'pre_snapshot' in step and not self._version_at_least(version, "2.14"):
                self._add_error(f"Step '{name}': pre_snapshot requires version '2.14'")

            if 'requires_variant' in step and not self._version_at_least(version, "2.14"):
                self._add_error(f"Step '{name}': requires_variant requires version '2.14'")

            step_proof_context = dict(proof_context or {})
            if self._version_at_least(version, "2.14"):
                step_proof_context = self._extend_variant_proof_context(
                    step=step,
                    step_name=name,
                    root_catalog=root_catalog,
                    proof_context=step_proof_context,
                )
                if 'materialize_artifacts' in step:
                    self._validate_materialize_artifacts(
                        step['materialize_artifacts'],
                        name,
                        version,
                        root_catalog,
                        scope_artifacts,
                        scope_multi_visit,
                        parent_artifacts,
                        parent_multi_visit,
                        scope_non_step_results,
                        parent_non_step_results,
                        step_proof_context,
                    )
                    self._validate_materialize_published_pointer_authority(
                        step=step,
                        step_name=name,
                        artifacts_registry=artifacts_registry,
                    )
                if 'pre_snapshot' in step:
                    self._validate_pre_snapshot(
                        step['pre_snapshot'],
                        name,
                        version,
                        root_catalog,
                        scope_artifacts,
                        scope_multi_visit,
                        parent_artifacts,
                        parent_multi_visit,
                        scope_non_step_results,
                        parent_non_step_results,
                        step_proof_context,
                    )
                if 'select_variant_output' in step:
                    self._validate_select_variant_output(
                        step['select_variant_output'],
                        name,
                        version,
                        root_catalog,
                        scope_artifacts,
                        scope_multi_visit,
                        parent_artifacts,
                        parent_multi_visit,
                        scope_non_step_results,
                        parent_non_step_results,
                        step_proof_context,
                    )

            declared_output_contracts = [
                field_name
                for field_name in ('expected_outputs', 'output_bundle', 'variant_output', 'select_variant_output')
                if field_name in step
            ]
            if len(declared_output_contracts) > 1:
                if declared_output_contracts == ['expected_outputs', 'output_bundle']:
                    self._add_error(
                        f"Step '{name}': output_bundle is mutually exclusive with expected_outputs"
                    )
                else:
                    self._add_error(
                        f"Step '{name}': mutually exclusive output contract fields {declared_output_contracts}"
                    )

            if 'inject_output_contract' in step and not isinstance(step['inject_output_contract'], bool):
                self._add_error(f"Step '{name}': 'inject_output_contract' must be a boolean")

            if 'persist_artifacts_in_state' in step and not isinstance(step['persist_artifacts_in_state'], bool):
                self._add_error(f"Step '{name}': 'persist_artifacts_in_state' must be a boolean")

            if 'publishes' in step:
                if not self._version_at_least(version, "1.2"):
                    self._add_error(f"Step '{name}': publishes requires version '1.2'")
                else:
                    if step.get('persist_artifacts_in_state') is False:
                        self._add_error(
                            f"Step '{name}': publishes requires persist_artifacts_in_state to be true"
                        )
                    self._validate_publishes(step['publishes'], name)

            if 'consumes' in step:
                if not self._version_at_least(version, "1.2"):
                    self._add_error(f"Step '{name}': consumes requires version '1.2'")
                else:
                    self._validate_consumes(step['consumes'], name)

            if 'prompt_consumes' in step:
                if not self._version_at_least(version, "1.2"):
                    self._add_error(f"Step '{name}': prompt_consumes requires version '1.2'")
                else:
                    prompt_consumes = step['prompt_consumes']
                    if (
                        not isinstance(prompt_consumes, list)
                        or any(not isinstance(item, str) or not item.strip() for item in prompt_consumes)
                    ):
                        self._add_error(
                            f"Step '{name}': prompt_consumes must be a list of artifact names"
                        )

                    consumes = step.get('consumes')
                    if not isinstance(consumes, list) or not consumes:
                        self._add_error(f"Step '{name}': prompt_consumes requires consumes")
                    elif isinstance(prompt_consumes, list):
                        consumed_names = {
                            entry.get('artifact')
                            for entry in consumes
                            if isinstance(entry, dict) and isinstance(entry.get('artifact'), str)
                        }
                        for artifact_name in prompt_consumes:
                            if not isinstance(artifact_name, str) or not artifact_name.strip():
                                continue
                            if artifact_name not in consumed_names:
                                self._add_error(
                                    f"Step '{name}': prompt_consumes artifact '{artifact_name}' must appear in consumes"
                                )

            if 'inject_consumes' in step:
                if not self._version_at_least(version, "1.2"):
                    self._add_error(f"Step '{name}': inject_consumes requires version '1.2'")
                elif not isinstance(step['inject_consumes'], bool):
                    self._add_error(f"Step '{name}': 'inject_consumes' must be a boolean")

            if 'consumes_injection_position' in step:
                if not self._version_at_least(version, "1.2"):
                    self._add_error(f"Step '{name}': consumes_injection_position requires version '1.2'")
                else:
                    position = step['consumes_injection_position']
                    if not isinstance(position, str):
                        self._add_error(
                            f"Step '{name}': consumes_injection_position must be 'prepend' or 'append'"
                        )
                    elif position not in {'prepend', 'append'}:
                        self._add_error(
                            f"Step '{name}': consumes_injection_position must be 'prepend' or 'append'"
                        )

            if 'consume_bundle' in step:
                if not self._version_at_least(version, "1.3"):
                    self._add_error(f"Step '{name}': consume_bundle requires version '1.3'")
                else:
                    self._validate_consume_bundle(step['consume_bundle'], name, step.get('consumes'))

            if 'provider_session' in step:
                if 'adjudicated_provider' in step:
                    self._add_error(
                        f"Step '{name}': provider_session is invalid with adjudicated_provider"
                    )
                    continue
                self._validate_provider_session(
                    step=step,
                    step_name=name,
                    version=version,
                    artifacts_registry=artifacts_registry,
                    top_level=top_level,
                )

            # Validate wait_for exclusivity (AT-36)
            if 'wait_for' in step:
                self._validate_wait_for(step, name)

            # Validate when conditions
            if 'when' in step:
                self._validate_when_condition(
                    step['when'],
                    name,
                    version,
                    root_catalog,
                    scope_artifacts,
                    scope_multi_visit,
                    parent_artifacts,
                    parent_multi_visit,
                    scope_non_step_results,
                    parent_non_step_results,
                )

            # Validate control flow
            if 'on' in step:
                self._validate_on_handlers(step['on'], name)

    def _collect_all_steps(self, steps: List[Any]) -> List[Dict[str, Any]]:
        """Collect all step definitions from top-level and nested control-flow blocks."""
        collected: List[Dict[str, Any]] = []
        if not isinstance(steps, list):
            return collected

        for step in steps:
            if not isinstance(step, dict):
                continue
            collected.append(step)
            if is_if_statement(step):
                for branch_name in ('then', 'else'):
                    branch = normalize_branch_block(step.get(branch_name), branch_name)
                    nested = branch.get('steps') if isinstance(branch, dict) else None
                    if isinstance(nested, list):
                        collected.extend(self._collect_all_steps(nested))
            if is_match_statement(step):
                match = step.get('match')
                cases = match.get('cases') if isinstance(match, dict) else None
                if isinstance(cases, dict):
                    for case_name, authored_case in cases.items():
                        case_block = normalize_match_case_block(authored_case, str(case_name))
                        nested = case_block.get('steps') if isinstance(case_block, dict) else None
                        if isinstance(nested, list):
                            collected.extend(self._collect_all_steps(nested))
            for_each = step.get('for_each')
            if isinstance(for_each, dict):
                nested = for_each.get('steps')
                if isinstance(nested, list):
                    collected.extend(self._collect_all_steps(nested))
            repeat_until = step.get('repeat_until')
            if isinstance(repeat_until, dict):
                nested = repeat_until.get('steps')
                if isinstance(nested, list):
                    collected.extend(self._collect_all_steps(nested))

        return collected

    def _iter_call_sites(
        self,
        steps: Any,
        *,
        multi_visit_context: Optional[str] = None,
    ) -> List[tuple[Dict[str, Any], Optional[str]]]:
        """Collect call steps plus whether they execute inside a multi-visit loop."""
        call_sites: List[tuple[Dict[str, Any], Optional[str]]] = []
        if not isinstance(steps, list):
            return call_sites

        for step in steps:
            if not isinstance(step, dict):
                continue

            if 'call' in step:
                call_sites.append((step, multi_visit_context))

            if is_if_statement(step):
                for branch_name in ('then', 'else'):
                    branch = normalize_branch_block(step.get(branch_name), branch_name)
                    nested = branch.get('steps') if isinstance(branch, dict) else None
                    if isinstance(nested, list):
                        call_sites.extend(
                            self._iter_call_sites(nested, multi_visit_context=multi_visit_context)
                        )

            if is_match_statement(step):
                match = step.get('match')
                cases = match.get('cases') if isinstance(match, dict) else None
                if isinstance(cases, dict):
                    for case_name, authored_case in cases.items():
                        case_block = normalize_match_case_block(authored_case, str(case_name))
                        nested = case_block.get('steps') if isinstance(case_block, dict) else None
                        if isinstance(nested, list):
                            call_sites.extend(
                                self._iter_call_sites(nested, multi_visit_context=multi_visit_context)
                            )

            for_each = step.get('for_each')
            if isinstance(for_each, dict):
                nested = for_each.get('steps')
                if isinstance(nested, list):
                    nested_context = multi_visit_context
                    items = for_each.get('items')
                    if nested_context is None and (
                        'items_from' in for_each
                        or not isinstance(items, list)
                        or len(items) != 1
                    ):
                        nested_context = 'for_each'
                    call_sites.extend(
                        self._iter_call_sites(nested, multi_visit_context=nested_context)
                    )

            repeat_until = step.get('repeat_until')
            if isinstance(repeat_until, dict):
                nested = repeat_until.get('steps')
                if isinstance(nested, list):
                    nested_context = multi_visit_context
                    max_iterations = repeat_until.get('max_iterations')
                    if nested_context is None and not (
                        isinstance(max_iterations, int) and max_iterations == 1
                    ):
                        nested_context = 'repeat_until'
                    call_sites.extend(
                        self._iter_call_sites(nested, multi_visit_context=nested_context)
                    )

        return call_sites

    def _validate_for_each(
        self,
        for_each: Any,
        step_name: str,
        version: str,
        artifacts_registry: Optional[Any] = None,
        root_catalog: Optional[Dict[str, Any]] = None,
        parent_scope_artifacts: Optional[Dict[str, Any]] = None,
        parent_scope_multi_visit: Optional[Set[str]] = None,
        parent_scope_non_step_results: Optional[Set[str]] = None,
        proof_context: Optional[Dict[str, str]] = None,
    ):
        """Validate for_each loop configuration."""
        if not isinstance(for_each, dict):
            self._add_error(f"Step '{step_name}': for_each must be a dictionary")
            return

        # Must have items_from OR items, not both
        has_from = 'items_from' in for_each
        has_items = 'items' in for_each

        if not (has_from or has_items):
            self._add_error(f"Step '{step_name}': for_each requires 'items_from' or 'items'")
        elif has_from and has_items:
            self._add_error(f"Step '{step_name}': for_each cannot have both 'items_from' and 'items'")

        if 'steps' not in for_each:
            self._add_error(f"Step '{step_name}': for_each missing required 'steps'")
        else:
            nested_scope_artifacts = self._build_scope_artifact_catalog(
                for_each['steps'],
                artifacts_registry,
            )
            nested_scope_multi_visit = self._build_root_ref_catalog(
                for_each['steps'],
                artifacts_registry,
            ).get('multi_visit', set())
            nested_scope_non_step_results = self._build_scope_non_step_result_targets(
                for_each['steps']
            )
            # Recursively validate nested steps
            self._validate_steps(
                for_each['steps'],
                version,
                artifacts_registry,
                root_catalog,
                scope_artifacts=nested_scope_artifacts,
                parent_artifacts=parent_scope_artifacts,
                scope_multi_visit=nested_scope_multi_visit,
                parent_multi_visit=parent_scope_multi_visit,
                scope_non_step_results=nested_scope_non_step_results,
                parent_non_step_results=parent_scope_non_step_results,
                top_level=False,
                proof_context=proof_context,
            )

    def _validate_positive_integer(self, value: Any, context: str, allow_zero: bool = False) -> None:
        """Validate integer fields used for cycle guards."""
        if type(value) is not int:
            self._add_error(f"{context} must be an integer")
            return
        if value < 0 or (value == 0 and not allow_zero):
            comparator = ">= 0" if allow_zero else "> 0"
            self._add_error(f"{context} must be {comparator}")

    def _validate_if_statement(
        self,
        step: Dict[str, Any],
        step_name: str,
        version: str,
        artifacts_registry: Optional[Any],
        root_catalog: Dict[str, Any],
        scope_artifacts: Dict[str, Any],
        scope_multi_visit: Set[str],
        parent_artifacts: Optional[Dict[str, Any]],
        parent_multi_visit: Optional[Set[str]],
        scope_non_step_results: Set[str],
        parent_non_step_results: Optional[Set[str]],
        top_level: bool,
        allow_nested: bool = False,
        proof_context: Optional[Dict[str, str]] = None,
    ) -> None:
        """Validate one top-level structured if/else statement."""
        if not top_level and not allow_nested:
            self._add_error(
                f"Step '{step_name}': structured if/else is only supported on top-level steps in v{STRUCTURED_IF_VERSION}"
            )
            return
        if not self._version_at_least(version, STRUCTURED_IF_VERSION):
            self._add_error(f"Step '{step_name}': if/else requires version '{STRUCTURED_IF_VERSION}'")
            return

        allowed_fields = {'name', 'id', 'if', 'then', 'else', 'when'}
        for field_name in step.keys():
            if field_name not in allowed_fields:
                self._add_error(
                    f"Step '{step_name}': structured if/else does not allow field '{field_name}'"
                )

        if 'if' not in step:
            self._add_error(f"Step '{step_name}': structured if/else requires 'if'")
        else:
            self._validate_when_condition(
                step['if'],
                step_name,
                version,
                root_catalog,
                scope_artifacts,
                scope_multi_visit,
                parent_artifacts,
                parent_multi_visit,
                scope_non_step_results,
                parent_non_step_results,
            )
        if 'when' in step:
            self._validate_when_condition(
                step['when'],
                step_name,
                version,
                root_catalog,
                scope_artifacts,
                scope_multi_visit,
                parent_artifacts,
                parent_multi_visit,
                scope_non_step_results,
                parent_non_step_results,
            )

        if 'then' not in step:
            self._add_error(f"Step '{step_name}': structured if/else requires 'then'")
        if 'else' not in step:
            self._add_error(f"Step '{step_name}': structured if/else requires 'else'")

        then_block = normalize_branch_block(step.get('then'), 'then')
        else_block = normalize_branch_block(step.get('else'), 'else')

        branch_tokens: Dict[str, str] = {}
        for branch_name, branch in (('then', then_block), ('else', else_block)):
            if branch is None:
                continue
            token = branch_token(branch_name, branch)
            if token in branch_tokens:
                self._add_error(
                    f"Step '{step_name}': duplicate branch id '{token}'"
                )
            else:
                branch_tokens[token] = branch_name

        then_outputs = self._validate_if_branch(
            statement_name=step_name,
            branch_name='then',
            branch=then_block,
            version=version,
            artifacts_registry=artifacts_registry,
            root_catalog=root_catalog,
            parent_scope_artifacts=scope_artifacts,
            parent_scope_multi_visit=scope_multi_visit,
            parent_scope_non_step_results=scope_non_step_results,
            proof_context=proof_context,
        )
        else_outputs = self._validate_if_branch(
            statement_name=step_name,
            branch_name='else',
            branch=else_block,
            version=version,
            artifacts_registry=artifacts_registry,
            root_catalog=root_catalog,
            parent_scope_artifacts=scope_artifacts,
            parent_scope_multi_visit=scope_multi_visit,
            parent_scope_non_step_results=scope_non_step_results,
            proof_context=proof_context,
        )

        if then_outputs is None or else_outputs is None:
            return
        if set(then_outputs.keys()) != set(else_outputs.keys()):
            self._add_error(
                f"Step '{step_name}': then/else outputs must declare the same output names"
            )
            return
        for output_name in then_outputs.keys():
            left = {
                key: value
                for key, value in then_outputs[output_name].items()
                if key != 'from'
            }
            right = {
                key: value
                for key, value in else_outputs[output_name].items()
                if key != 'from'
            }
            if left != right:
                self._add_error(
                    f"Step '{step_name}': then/else output '{output_name}' must use matching contracts"
                )

    def _validate_if_branch(
        self,
        statement_name: str,
        branch_name: str,
        branch: Optional[Dict[str, Any]],
        version: str,
        artifacts_registry: Optional[Any],
        root_catalog: Dict[str, Any],
        parent_scope_artifacts: Dict[str, Any],
        parent_scope_multi_visit: Set[str],
        parent_scope_non_step_results: Set[str],
        proof_context: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict[str, Dict[str, Any]]]:
        """Validate one branch block of a structured if/else statement."""
        if branch is None:
            self._add_error(
                f"Step '{statement_name}': {branch_name} must be a list of steps or an object with steps"
            )
            return None

        branch_id = branch.get('id')
        if branch_id is not None:
            if not isinstance(branch_id, str) or not STEP_ID_PATTERN.fullmatch(branch_id):
                self._add_error(
                    f"Step '{statement_name}': {branch_name}.id must match {STEP_ID_PATTERN.pattern}"
                )

        branch_steps = branch.get('steps')
        if not isinstance(branch_steps, list) or not branch_steps:
            self._add_error(
                f"Step '{statement_name}': {branch_name}.steps must be a non-empty list"
            )
            return None

        if self._branch_contains_goto(branch_steps):
            self._add_error(
                f"Step '{statement_name}': structured if/else branches do not permit goto/_end routing in the first tranche"
            )

        branch_scope_artifacts = self._build_scope_artifact_catalog(branch_steps, artifacts_registry)
        branch_scope_multi_visit = self._build_root_ref_catalog(branch_steps, artifacts_registry).get('multi_visit', set())
        branch_scope_non_step_results = self._build_scope_non_step_result_targets(branch_steps)
        self._validate_steps(
            branch_steps,
            version,
            artifacts_registry,
            root_catalog,
            scope_artifacts=branch_scope_artifacts,
            parent_artifacts=parent_scope_artifacts,
            scope_multi_visit=branch_scope_multi_visit,
            parent_multi_visit=parent_scope_multi_visit,
            scope_non_step_results=branch_scope_non_step_results,
            parent_non_step_results=parent_scope_non_step_results,
            top_level=False,
            proof_context=proof_context,
        )

        outputs = branch.get('outputs', {})
        if not isinstance(outputs, dict):
            self._add_error(f"Step '{statement_name}': {branch_name}.outputs must be a dictionary")
            return None

        for output_name, spec in outputs.items():
            context = f"Step '{statement_name}': {branch_name}.outputs.{output_name}"
            self._validate_workflow_signature_contract(spec, context, version, allow_from=True)
            if not isinstance(spec, dict):
                continue

            binding = spec.get('from')
            ref = binding.get('ref') if isinstance(binding, dict) else None
            ref_type = self._validate_structured_ref(
                ref,
                f"{statement_name}.{branch_name}.outputs.{output_name}",
                version,
                root_catalog,
                branch_scope_artifacts,
                branch_scope_multi_visit,
                parent_scope_artifacts,
                parent_scope_multi_visit,
                branch_scope_non_step_results,
                parent_scope_non_step_results,
            )
            declared_type = spec.get('type')
            if ref_type == 'unknown' or not isinstance(declared_type, str):
                continue
            if declared_type == ref_type:
                continue
            if declared_type == 'float' and ref_type == 'integer':
                continue
            self._add_error(
                f"{context}.from resolves to '{ref_type}' but output declares '{declared_type}'"
            )

        return outputs

    def _validate_match_statement(
        self,
        step: Dict[str, Any],
        step_name: str,
        version: str,
        artifacts_registry: Optional[Any],
        root_catalog: Dict[str, Any],
        scope_artifacts: Dict[str, Any],
        scope_multi_visit: Set[str],
        parent_artifacts: Optional[Dict[str, Any]],
        parent_multi_visit: Optional[Set[str]],
        scope_non_step_results: Set[str],
        parent_non_step_results: Optional[Set[str]],
        top_level: bool,
        allow_nested: bool = False,
        proof_context: Optional[Dict[str, str]] = None,
    ) -> None:
        """Validate one top-level structured match statement."""
        if not top_level and not allow_nested:
            self._add_error(
                f"Step '{step_name}': structured match is only supported on top-level steps in v{STRUCTURED_MATCH_VERSION}"
            )
            return
        if not self._version_at_least(version, STRUCTURED_MATCH_VERSION):
            self._add_error(f"Step '{step_name}': match requires version '{STRUCTURED_MATCH_VERSION}'")
            return

        allowed_fields = {'name', 'id', 'match', 'when'}
        for field_name in step.keys():
            if field_name not in allowed_fields:
                self._add_error(
                    f"Step '{step_name}': structured match does not allow field '{field_name}'"
                )

        match_node = step.get('match')
        if not isinstance(match_node, dict):
            self._add_error(f"Step '{step_name}': match must be a dictionary")
            return
        if 'when' in step:
            self._validate_when_condition(
                step['when'],
                step_name,
                version,
                root_catalog,
                scope_artifacts,
                scope_multi_visit,
                parent_artifacts,
                parent_multi_visit,
                scope_non_step_results,
                parent_non_step_results,
            )

        ref_contract = self._resolve_structured_ref_contract(
            match_node.get('ref'),
            step_name,
            version,
            root_catalog,
            scope_artifacts,
            scope_multi_visit,
            parent_artifacts,
            parent_multi_visit,
            scope_non_step_results,
            parent_non_step_results,
        )
        allowed_values = ref_contract.get('allowed') if isinstance(ref_contract, dict) else None
        if not isinstance(ref_contract, dict) or ref_contract.get('type') != 'enum' or not isinstance(allowed_values, list):
            self._add_error(f"Step '{step_name}': match.ref must resolve to an enum artifact or input")

        cases = match_node.get('cases')
        if not isinstance(cases, dict) or not cases:
            self._add_error(f"Step '{step_name}': match.cases must be a non-empty dictionary")
            return

        case_tokens: Dict[str, str] = {}
        validated_case_names: List[str] = []
        case_outputs: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for case_name, authored_case in cases.items():
            if not isinstance(case_name, str) or not case_name:
                self._add_error(f"Step '{step_name}': match case names must be non-empty strings")
                continue
            validated_case_names.append(case_name)
            case_block = normalize_match_case_block(authored_case, case_name)
            token = match_case_token(case_name, case_block or {})
            if token in case_tokens:
                self._add_error(f"Step '{step_name}': duplicate case id '{token}'")
            else:
                case_tokens[token] = case_name
            case_proof_context = self._extend_match_case_variant_proof(
                step_name=step_name,
                case_name=case_name,
                ref_contract=ref_contract,
                proof_context=proof_context,
            )
            outputs = self._validate_match_case(
                statement_name=step_name,
                case_name=case_name,
                case_block=case_block,
                version=version,
                artifacts_registry=artifacts_registry,
                root_catalog=root_catalog,
                parent_scope_artifacts=scope_artifacts,
                parent_scope_multi_visit=scope_multi_visit,
                parent_scope_non_step_results=scope_non_step_results,
                proof_context=case_proof_context,
            )
            if outputs is not None:
                case_outputs[case_name] = outputs

        if isinstance(allowed_values, list):
            extra_cases = sorted(set(validated_case_names) - set(allowed_values))
            missing_cases = sorted(set(allowed_values) - set(validated_case_names))
            if extra_cases:
                self._add_error(
                    f"Step '{step_name}': match.cases contains undeclared enum values {extra_cases}"
                )
            if missing_cases:
                self._add_error(
                    f"Step '{step_name}': match.cases must cover every allowed enum value; missing {missing_cases}"
                )

        if not case_outputs:
            return

        first_outputs = next(iter(case_outputs.values()))
        for case_name, outputs in case_outputs.items():
            if set(outputs.keys()) != set(first_outputs.keys()):
                self._add_error(
                    f"Step '{step_name}': all match cases must declare the same output names"
                )
                return
            for output_name in first_outputs.keys():
                left = {
                    key: value
                    for key, value in first_outputs[output_name].items()
                    if key != 'from'
                }
                right = {
                    key: value
                    for key, value in outputs[output_name].items()
                    if key != 'from'
                }
                if left != right:
                    self._add_error(
                        f"Step '{step_name}': case '{case_name}' output '{output_name}' must use matching contracts"
                    )

    def _validate_match_case(
        self,
        statement_name: str,
        case_name: str,
        case_block: Optional[Dict[str, Any]],
        version: str,
        artifacts_registry: Optional[Any],
        root_catalog: Dict[str, Any],
        parent_scope_artifacts: Dict[str, Any],
        parent_scope_multi_visit: Set[str],
        parent_scope_non_step_results: Set[str],
        proof_context: Optional[Dict[str, str]] = None,
    ) -> Optional[Dict[str, Dict[str, Any]]]:
        """Validate one case block of a structured match statement."""
        if case_block is None:
            self._add_error(
                f"Step '{statement_name}': match.cases.{case_name} must be a list of steps or an object with steps"
            )
            return None

        case_id = case_block.get('id')
        if case_id is not None:
            if not isinstance(case_id, str) or not STEP_ID_PATTERN.fullmatch(case_id):
                self._add_error(
                    f"Step '{statement_name}': match.cases.{case_name}.id must match {STEP_ID_PATTERN.pattern}"
                )

        case_steps = case_block.get('steps')
        if not isinstance(case_steps, list) or not case_steps:
            self._add_error(
                f"Step '{statement_name}': match.cases.{case_name}.steps must be a non-empty list"
            )
            return None

        if self._branch_contains_goto(case_steps):
            self._add_error(
                f"Step '{statement_name}': structured match cases do not permit goto/_end routing in the first tranche"
            )

        case_scope_artifacts = self._build_scope_artifact_catalog(case_steps, artifacts_registry)
        case_scope_multi_visit = self._build_root_ref_catalog(case_steps, artifacts_registry).get('multi_visit', set())
        case_scope_non_step_results = self._build_scope_non_step_result_targets(case_steps)
        self._validate_steps(
            case_steps,
            version,
            artifacts_registry,
            root_catalog,
            scope_artifacts=case_scope_artifacts,
            parent_artifacts=parent_scope_artifacts,
            scope_multi_visit=case_scope_multi_visit,
            parent_multi_visit=parent_scope_multi_visit,
            scope_non_step_results=case_scope_non_step_results,
            parent_non_step_results=parent_scope_non_step_results,
            top_level=False,
            proof_context=proof_context,
        )

        outputs = case_block.get('outputs', {})
        if not isinstance(outputs, dict):
            self._add_error(f"Step '{statement_name}': match.cases.{case_name}.outputs must be a dictionary")
            return None

        for output_name, spec in outputs.items():
            context = f"Step '{statement_name}': match.cases.{case_name}.outputs.{output_name}"
            self._validate_workflow_signature_contract(spec, context, version, allow_from=True)
            if not isinstance(spec, dict):
                continue

            binding = spec.get('from')
            ref = binding.get('ref') if isinstance(binding, dict) else None
            ref_type = self._validate_structured_ref(
                ref,
                f"{statement_name}.match.cases.{case_name}.outputs.{output_name}",
                version,
                root_catalog,
                case_scope_artifacts,
                case_scope_multi_visit,
                parent_scope_artifacts,
                parent_scope_multi_visit,
                case_scope_non_step_results,
                parent_scope_non_step_results,
            )
            declared_type = spec.get('type')
            if ref_type == 'unknown' or not isinstance(declared_type, str):
                continue
            if declared_type == ref_type:
                continue
            if declared_type == 'float' and ref_type == 'integer':
                continue
            self._add_error(
                f"{context}.from resolves to '{ref_type}' but output declares '{declared_type}'"
            )

        return outputs

    def _validate_repeat_until_statement(
        self,
        step: Dict[str, Any],
        step_name: str,
        version: str,
        artifacts_registry: Optional[Any],
        root_catalog: Dict[str, Any],
        scope_artifacts: Dict[str, Any],
        scope_multi_visit: Set[str],
        parent_artifacts: Optional[Dict[str, Any]],
        parent_multi_visit: Optional[Set[str]],
        scope_non_step_results: Set[str],
        parent_non_step_results: Optional[Set[str]],
        top_level: bool,
        proof_context: Optional[Dict[str, str]] = None,
    ) -> None:
        """Validate one top-level post-test repeat_until statement."""
        if not top_level:
            self._add_error(
                f"Step '{step_name}': structured repeat_until is only supported on top-level steps in v{STRUCTURED_REPEAT_UNTIL_VERSION}"
            )
            return
        if not self._version_at_least(version, STRUCTURED_REPEAT_UNTIL_VERSION):
            self._add_error(
                f"Step '{step_name}': repeat_until requires version '{STRUCTURED_REPEAT_UNTIL_VERSION}'"
            )
            return

        allowed_fields = {'name', 'id', 'repeat_until', 'requires_variant', 'when'}
        for field_name in step.keys():
            if field_name not in allowed_fields:
                self._add_error(
                    f"Step '{step_name}': structured repeat_until does not allow field '{field_name}'"
                )

        block = normalize_repeat_until_block(step.get('repeat_until'))
        if block is None:
            self._add_error(f"Step '{step_name}': repeat_until must be a dictionary")
            return

        body_id = block.get('id')
        if body_id is not None:
            if not isinstance(body_id, str) or not STEP_ID_PATTERN.fullmatch(body_id):
                self._add_error(
                    f"Step '{step_name}': repeat_until.id must match {STEP_ID_PATTERN.pattern}"
                )

        max_iterations = block.get('max_iterations')
        self._validate_positive_integer(
            max_iterations,
            f"Step '{step_name}': repeat_until.max_iterations",
            allow_zero=False,
        )

        body_steps = block.get('steps')
        if not isinstance(body_steps, list) or not body_steps:
            self._add_error(
                f"Step '{step_name}': repeat_until.steps must be a non-empty list"
            )
            return

        if self._branch_contains_goto(body_steps):
            self._add_error(
                f"Step '{step_name}': repeat_until steps do not permit goto/_end routing in the first tranche"
            )

        for nested_step in body_steps:
            if not isinstance(nested_step, dict):
                continue
            nested_name = nested_step.get('name')
            if not isinstance(nested_name, str):
                continue
            if 'for_each' in nested_step:
                self._add_error(
                    f"Step '{step_name}': repeat_until body step '{nested_name}' does not support for_each in the first tranche"
                )
            if is_repeat_until_statement(nested_step):
                self._add_error(
                    f"Step '{step_name}': repeat_until body step '{nested_name}' does not support nested repeat_until in the first tranche"
                )

        body_scope_artifacts = self._build_scope_artifact_catalog(body_steps, artifacts_registry)
        body_scope_multi_visit = self._build_root_ref_catalog(body_steps, artifacts_registry).get('multi_visit', set())
        body_scope_non_step_results = self._build_scope_non_step_result_targets(body_steps)
        self._validate_steps(
            body_steps,
            version,
            artifacts_registry,
            root_catalog,
            scope_artifacts=body_scope_artifacts,
            parent_artifacts=scope_artifacts,
            scope_multi_visit=body_scope_multi_visit,
            parent_multi_visit=scope_multi_visit,
            scope_non_step_results=body_scope_non_step_results,
            parent_non_step_results=scope_non_step_results,
            top_level=False,
            allow_nested_structured=True,
            proof_context=proof_context,
        )

        outputs = block.get('outputs')
        if not isinstance(outputs, dict) or not outputs:
            self._add_error(f"Step '{step_name}': repeat_until.outputs must be a non-empty dictionary")
            return

        normalized_outputs: Dict[str, Dict[str, Any]] = {}
        for output_name, spec in outputs.items():
            context = f"Step '{step_name}': repeat_until.outputs.{output_name}"
            self._validate_workflow_signature_contract(spec, context, version, allow_from=True)
            if not isinstance(spec, dict):
                continue

            binding = spec.get('from')
            ref = binding.get('ref') if isinstance(binding, dict) else None
            ref_type = self._validate_structured_ref(
                ref,
                f"{step_name}.repeat_until.outputs.{output_name}",
                version,
                root_catalog,
                body_scope_artifacts,
                body_scope_multi_visit,
                scope_artifacts,
                scope_multi_visit,
                body_scope_non_step_results,
                scope_non_step_results,
            )
            declared_type = spec.get('type')
            if ref_type != 'unknown' and isinstance(declared_type, str):
                if declared_type != ref_type and not (declared_type == 'float' and ref_type == 'integer'):
                    self._add_error(
                        f"{context}.from resolves to '{ref_type}' but output declares '{declared_type}'"
                    )
            if isinstance(output_name, str) and isinstance(spec, dict):
                normalized_outputs[output_name] = spec

        on_exhausted = block.get('on_exhausted')
        if on_exhausted is not None:
            if not self._version_at_least(version, STRUCTURED_REPEAT_UNTIL_ON_EXHAUSTED_VERSION):
                self._add_error(
                    f"Step '{step_name}': repeat_until.on_exhausted requires version '{STRUCTURED_REPEAT_UNTIL_ON_EXHAUSTED_VERSION}'"
                )
            self._validate_repeat_until_on_exhausted(
                step_name=step_name,
                on_exhausted=on_exhausted,
                output_specs=normalized_outputs,
            )

        condition = block.get('condition')
        if not isinstance(condition, dict) or not self._is_typed_predicate_node(condition):
            self._add_error(f"Step '{step_name}': repeat_until.condition must be a typed predicate")
            return

        rewritten_condition = self._rewrite_repeat_until_condition_refs(
            condition,
            step_name=step_name,
            output_specs=normalized_outputs,
        )
        self._validate_typed_predicate(
            rewritten_condition,
            step_name,
            version,
            root_catalog,
            {},
            set(),
            None,
            None,
            set(),
            None,
        )
        block['condition'] = rewritten_condition
        step['repeat_until'] = block

    def _validate_repeat_until_on_exhausted(
        self,
        *,
        step_name: str,
        on_exhausted: Any,
        output_specs: Dict[str, Dict[str, Any]],
    ) -> None:
        context = f"Step '{step_name}': repeat_until.on_exhausted"
        if not isinstance(on_exhausted, dict):
            self._add_error(f"{context} must be a dictionary")
            return

        allowed_fields = {'outputs'}
        for field_name in on_exhausted.keys():
            if field_name not in allowed_fields:
                self._add_error(f"{context} does not allow field '{field_name}'")

        outputs = on_exhausted.get('outputs')
        if not isinstance(outputs, dict) or not outputs:
            self._add_error(f"{context}.outputs must be a non-empty dictionary")
            return

        for output_name, value in outputs.items():
            value_context = f"{context}.outputs.{output_name}"
            if output_name not in output_specs:
                self._add_error(f"{value_context} targets unknown repeat_until output")
                continue

            spec = output_specs[output_name]
            output_type = spec.get('type')
            if output_type == 'relpath' or spec.get('kind', 'relpath' if output_type == 'relpath' else 'scalar') == 'relpath':
                self._add_error(f"{value_context} may only override scalar repeat_until outputs")
                continue
            if self._is_generated_repeat_until_on_exhausted_ref(
                value,
                step_name=step_name,
                output_name=output_name,
            ):
                continue
            if isinstance(value, (dict, list)):
                self._add_error(f"{value_context} must be a scalar literal")
                continue
            try:
                validate_contract_value(value, spec, workspace=self.workspace)
            except OutputContractError as exc:
                self._add_error(f"{value_context} is invalid: {exc}")

    def _is_generated_repeat_until_on_exhausted_ref(
        self,
        value: Any,
        *,
        step_name: str,
        output_name: str,
    ) -> bool:
        """Allow only the exact compiler-emitted loop-frame state ref for this output."""

        if not self._allow_generated_repeat_until_on_exhausted_refs:
            return False
        if not (
            isinstance(value, dict)
            and set(value) == {'ref'}
            and isinstance(value.get('ref'), str)
        ):
            return False
        ref = value['ref'].strip()
        if not ref:
            return False
        expected_ref = (
            self._generated_repeat_until_on_exhausted_refs.get(step_name, {}).get(output_name)
        )
        return ref == expected_ref

    def _rewrite_repeat_until_condition_refs(
        self,
        node: Any,
        *,
        step_name: str,
        output_specs: Dict[str, Dict[str, Any]],
    ) -> Any:
        """Rewrite repeat_until condition refs onto loop-frame artifacts."""
        if isinstance(node, list):
            return [
                self._rewrite_repeat_until_condition_refs(
                    item,
                    step_name=step_name,
                    output_specs=output_specs,
                )
                for item in node
            ]
        if not isinstance(node, dict):
            return node

        if set(node.keys()) == {'ref'}:
            ref = node.get('ref')
            if isinstance(ref, str) and ref.startswith('self.outputs.'):
                output_name = ref[len('self.outputs.'):]
                if output_name not in output_specs:
                    self._add_error(
                        f"Step '{step_name}': repeat_until.condition ref '{ref}' targets unknown loop output '{output_name}'"
                    )
                    return {'ref': ref}
                return {'ref': f"root.steps.{step_name}.artifacts.{output_name}"}
            if isinstance(ref, str) and ref.startswith('self.steps.'):
                self._add_error(
                    f"Step '{step_name}': repeat_until.condition must read declared loop-frame outputs via self.outputs.*, not '{ref}'"
                )
            return {'ref': ref}

        rewritten: Dict[str, Any] = {}
        for key, value in node.items():
            rewritten[key] = self._rewrite_repeat_until_condition_refs(
                value,
                step_name=step_name,
                output_specs=output_specs,
            )
        return rewritten

    def _build_finalization_catalog_steps(
        self,
        finally_block: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Build presentation-prefixed finalization steps for validation catalogs."""
        if finally_block is None:
            return []
        steps = finally_block.get('steps')
        if not isinstance(steps, list):
            return []

        prefixed_steps = deepcopy(steps)
        for step in prefixed_steps:
            if not isinstance(step, dict):
                continue
            name = step.get('name')
            if isinstance(name, str) and name:
                step['name'] = f"finally.{name}"
        return prefixed_steps

    def _validate_finally_block(
        self,
        finally_block: Optional[Dict[str, Any]],
        version: str,
        artifacts_registry: Optional[Any],
        root_catalog: Dict[str, Any],
    ) -> None:
        """Validate a top-level workflow finalization block."""
        if finally_block is None:
            self._add_error("finally must be a list of steps or an object with steps")
            return

        block_id = finally_block.get('id')
        if block_id is not None:
            if not isinstance(block_id, str) or not STEP_ID_PATTERN.fullmatch(block_id):
                self._add_error(f"finally.id must match {STEP_ID_PATTERN.pattern}")

        prefixed_steps = self._build_finalization_catalog_steps(finally_block)
        if not prefixed_steps:
            self._add_error("finally.steps must be a non-empty list")
            return

        if self._branch_contains_goto(prefixed_steps):
            self._add_error(
                "finally steps do not permit goto/_end routing in the first tranche"
            )

        self._validate_steps(
            prefixed_steps,
            version,
            artifacts_registry,
            root_catalog,
            top_level=False,
        )

    def _branch_contains_goto(self, steps: List[Any]) -> bool:
        """Return True when any nested step declares an explicit goto handler."""
        for step in steps:
            if not isinstance(step, dict):
                continue
            on = step.get('on')
            if isinstance(on, dict):
                for handler in ('success', 'failure', 'always'):
                    target = on.get(handler, {}).get('goto') if isinstance(on.get(handler), dict) else None
                    if isinstance(target, str):
                        return True
            for_each = step.get('for_each')
            if isinstance(for_each, dict) and isinstance(for_each.get('steps'), list):
                if self._branch_contains_goto(for_each.get('steps', [])):
                    return True
        return False

    def _validate_dependencies(self, depends_on: Any, step_name: str, version: str):
        """Validate dependency configuration."""
        if not isinstance(depends_on, dict):
            self._add_error(f"Step '{step_name}': depends_on must be a dictionary")
            return

        # Validate inject feature (requires version 1.1.1)
        if 'inject' in depends_on:
            if not self._version_at_least(version, "1.1.1"):
                self._add_error(f"Step '{step_name}': depends_on.inject requires version '1.1.1'")

    def _validate_asset_file(self, step: Dict[str, Any], step_name: str, version: str) -> None:
        """Validate workflow-source-relative prompt assets."""
        if not self._version_at_least(version, "2.5"):
            self._add_error(f"Step '{step_name}': asset_file requires version '2.5'")
            return
        if 'provider' not in step and 'adjudicated_provider' not in step:
            self._add_error(f"Step '{step_name}': asset_file is only supported on provider steps")
            return
        if 'input_file' in step:
            self._add_error(f"Step '{step_name}': asset_file is mutually exclusive with input_file")
            return
        asset_file = step.get('asset_file')
        if not isinstance(asset_file, str):
            self._add_error(f"Step '{step_name}': asset_file must be a string")
            return
        self._validate_source_relative_asset_path(asset_file, f"Step '{step_name}': asset_file")

    def _validate_asset_depends_on(self, step: Dict[str, Any], step_name: str, version: str) -> None:
        """Validate workflow-source-relative dependency assets."""
        if not self._version_at_least(version, "2.5"):
            self._add_error(f"Step '{step_name}': asset_depends_on requires version '2.5'")
            return
        if 'provider' not in step and 'adjudicated_provider' not in step:
            self._add_error(f"Step '{step_name}': asset_depends_on is only supported on provider steps")
            return
        asset_depends_on = step.get('asset_depends_on')
        if not isinstance(asset_depends_on, list):
            self._add_error(f"Step '{step_name}': asset_depends_on must be a list")
            return
        for index, path in enumerate(asset_depends_on):
            if not isinstance(path, str):
                self._add_error(f"Step '{step_name}': asset_depends_on[{index}] must be a string")
                continue
            self._validate_source_relative_asset_path(
                path,
                f"Step '{step_name}': asset_depends_on[{index}]",
            )

    def _validate_adjudicated_provider(
        self,
        *,
        step: Dict[str, Any],
        step_name: str,
        version: str,
        artifacts_registry: Optional[Any] = None,
    ) -> None:
        """Validate the DSL 2.11 adjudicated provider step form."""
        context = f"Step '{step_name}': adjudicated_provider"
        if not self._version_at_least(version, "2.11"):
            self._add_error(f"{context} requires version '2.11'")

        node = step.get('adjudicated_provider')
        if not isinstance(node, dict):
            self._add_error(f"{context} must be a dictionary")
            return

        if 'provider_session' in step:
            self._add_error(f"Step '{step_name}': provider_session is invalid with adjudicated_provider")

        for forbidden in ('output_file', 'output_capture', 'allow_parse_error'):
            if forbidden in step:
                self._add_error(f"Step '{step_name}': {forbidden} is invalid with adjudicated_provider")

        declared_contracts = [
            field_name
            for field_name in ('expected_outputs', 'output_bundle', 'variant_output')
            if field_name in step
        ]
        if len(declared_contracts) != 1:
            self._add_error(
                f"{context} must declare exactly one of expected_outputs or output_bundle (variant_output also satisfies this requirement in v2.14)"
            )

        candidates = node.get('candidates')
        candidate_prompt_overrides = 0
        if not isinstance(candidates, list) or not candidates:
            self._add_error(f"{context}.candidates must be a non-empty list")
        else:
            seen_candidate_ids: Set[str] = set()
            for index, candidate in enumerate(candidates):
                candidate_context = f"{context}.candidates[{index}]"
                if not isinstance(candidate, dict):
                    self._add_error(f"{candidate_context} must be a dictionary")
                    continue
                candidate_id = candidate.get('id')
                if not isinstance(candidate_id, str) or not STEP_ID_PATTERN.fullmatch(candidate_id):
                    self._add_error(f"{candidate_context}: candidate id must match {STEP_ID_PATTERN.pattern}")
                elif candidate_id in seen_candidate_ids:
                    self._add_error(f"{candidate_context}: duplicate candidate id '{candidate_id}'")
                else:
                    seen_candidate_ids.add(candidate_id)

                provider_name = candidate.get('provider')
                if not isinstance(provider_name, str) or not provider_name.strip():
                    self._add_error(f"{candidate_context}.provider is required")
                elif self._provider_registry.get(provider_name) is None:
                    self._add_error(f"{candidate_context}: unknown candidate provider '{provider_name}'")

                if 'asset_file' in candidate and 'input_file' in candidate:
                    self._add_error(f"{candidate_context}: candidate prompt override may use only one of asset_file or input_file")
                if 'asset_file' in candidate or 'input_file' in candidate:
                    candidate_prompt_overrides += 1
                if 'asset_file' in candidate:
                    if not isinstance(candidate.get('asset_file'), str):
                        self._add_error(f"{candidate_context}.asset_file must be a string")
                    else:
                        self._validate_source_relative_asset_path(
                            candidate['asset_file'],
                            f"{candidate_context}.asset_file",
                        )
                if 'input_file' in candidate:
                    if not isinstance(candidate.get('input_file'), str):
                        self._add_error(f"{candidate_context}.input_file must be a string")
                    else:
                        self._validate_path_safety(candidate['input_file'], f"{candidate_context}.input_file")
                        self._validate_no_run_root_candidate_path(
                            candidate['input_file'],
                            f"{candidate_context}.input_file",
                        )

                for forbidden in (
                    'consumes',
                    'depends_on',
                    'publishes',
                    'expected_outputs',
                    'output_bundle',
                    'output_file',
                ):
                    if forbidden in candidate:
                        self._add_error(f"{candidate_context}: candidate field '{forbidden}' is not supported")

        has_step_prompt = ('asset_file' in step) ^ ('input_file' in step)
        if 'asset_file' in step and 'input_file' in step:
            self._add_error(f"Step '{step_name}': asset_file is mutually exclusive with input_file")
        if isinstance(candidates, list) and candidates:
            all_candidates_have_prompt = candidate_prompt_overrides == len(candidates)
        else:
            all_candidates_have_prompt = False
        if not has_step_prompt and not all_candidates_have_prompt:
            self._add_error(
                f"{context} must declare one base prompt source unless every candidate has a prompt override"
            )

        evaluator = node.get('evaluator')
        if not isinstance(evaluator, dict):
            self._add_error(f"{context}.evaluator must be a dictionary")
        else:
            evaluator_provider = evaluator.get('provider')
            if not isinstance(evaluator_provider, str) or not evaluator_provider.strip():
                self._add_error(f"{context}.evaluator.provider is required")
            elif self._provider_registry.get(evaluator_provider) is None:
                self._add_error(f"{context}.evaluator: unknown evaluator provider '{evaluator_provider}'")

            if 'asset_file' in evaluator and 'input_file' in evaluator:
                self._add_error(f"{context}.evaluator: evaluator prompt source may use only one of asset_file or input_file")
            if 'asset_file' not in evaluator and 'input_file' not in evaluator:
                self._add_error(f"{context}.evaluator must declare asset_file or input_file")
            if 'asset_file' in evaluator:
                if not isinstance(evaluator.get('asset_file'), str):
                    self._add_error(f"{context}.evaluator.asset_file must be a string")
                else:
                    self._validate_source_relative_asset_path(
                        evaluator['asset_file'],
                        f"{context}.evaluator.asset_file",
                    )
            if 'input_file' in evaluator:
                if not isinstance(evaluator.get('input_file'), str):
                    self._add_error(f"{context}.evaluator.input_file must be a string")
                else:
                    self._validate_path_safety(evaluator['input_file'], f"{context}.evaluator.input_file")

            if 'rubric_asset_file' in evaluator and 'rubric_input_file' in evaluator:
                self._add_error(f"{context}.evaluator: evaluator rubric source may use only one of rubric_asset_file or rubric_input_file")
            if 'rubric_asset_file' in evaluator:
                if not isinstance(evaluator.get('rubric_asset_file'), str):
                    self._add_error(f"{context}.evaluator.rubric_asset_file must be a string")
                else:
                    self._validate_source_relative_asset_path(
                        evaluator['rubric_asset_file'],
                        f"{context}.evaluator.rubric_asset_file",
                    )
            if 'rubric_input_file' in evaluator:
                if not isinstance(evaluator.get('rubric_input_file'), str):
                    self._add_error(f"{context}.evaluator.rubric_input_file must be a string")
                else:
                    self._validate_path_safety(
                        evaluator['rubric_input_file'],
                        f"{context}.evaluator.rubric_input_file",
                    )

            confidentiality = evaluator.get('evidence_confidentiality')
            if confidentiality is None:
                self._add_error(f"{context}.evaluator.evidence_confidentiality is required")
            elif confidentiality != 'same_trust_boundary':
                self._add_error(
                    f"{context}.evaluator.evidence_confidentiality must be same_trust_boundary"
                )

            limits = evaluator.get('evidence_limits')
            if limits is not None:
                self._validate_adjudicated_evidence_limits(limits, f"{context}.evaluator.evidence_limits")

        selection = node.get('selection')
        if selection is not None:
            if not isinstance(selection, dict):
                self._add_error(f"{context}.selection must be a dictionary")
            else:
                tie_break = selection.get('tie_break')
                if tie_break is not None and tie_break != 'candidate_order':
                    self._add_error(f"{context}.selection.tie_break must be candidate_order")
                require_score = selection.get('require_score_for_single_candidate')
                if require_score is not None and not isinstance(require_score, bool):
                    self._add_error(
                        f"{context}.selection.require_score_for_single_candidate must be boolean"
                    )

        ledger_path = node.get('score_ledger_path')
        if ledger_path is not None:
            if not isinstance(ledger_path, str):
                self._add_error(f"{context}.score_ledger_path must be a string")
            else:
                self._validate_score_ledger_path(ledger_path, step, context, artifacts_registry)

        for field_name in ('input_file',):
            path_value = step.get(field_name)
            if isinstance(path_value, str):
                self._validate_no_run_root_candidate_path(
                    path_value,
                    f"Step '{step_name}': {field_name}",
                )
        depends_on = step.get('depends_on')
        if isinstance(depends_on, dict):
            for dep_key in ('required', 'optional'):
                paths = depends_on.get(dep_key)
                if isinstance(paths, list):
                    for index, path_value in enumerate(paths):
                        if isinstance(path_value, str):
                            self._validate_no_run_root_candidate_path(
                                path_value,
                                f"Step '{step_name}': depends_on.{dep_key}[{index}]",
                            )
        consume_bundle = step.get('consume_bundle')
        if isinstance(consume_bundle, dict) and isinstance(consume_bundle.get('path'), str):
            self._validate_no_run_root_candidate_path(
                consume_bundle['path'],
                f"Step '{step_name}': consume_bundle.path",
            )
        if isinstance(step.get('expected_outputs'), list):
            for index, spec in enumerate(step['expected_outputs']):
                if isinstance(spec, dict) and isinstance(spec.get('path'), str):
                    self._validate_no_run_root_candidate_path(
                        spec['path'],
                        f"Step '{step_name}': expected_outputs[{index}].path",
                    )
        if isinstance(step.get('output_bundle'), dict) and isinstance(step['output_bundle'].get('path'), str):
            self._validate_no_run_root_candidate_path(
                step['output_bundle']['path'],
                f"Step '{step_name}': output_bundle.path",
            )

    def _validate_adjudicated_evidence_limits(self, limits: Any, context: str) -> None:
        if not isinstance(limits, dict):
            self._add_error(f"{context} must be a dictionary")
            return
        allowed = {'max_item_bytes', 'max_packet_bytes'}
        for key in limits:
            if key not in allowed:
                self._add_error(f"{context}.{key} is not supported")
        item = limits.get('max_item_bytes', 262144)
        packet = limits.get('max_packet_bytes', 1048576)
        for key, value in (('max_item_bytes', item), ('max_packet_bytes', packet)):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                self._add_error(f"{context}.{key} must be a literal positive integer")
        if (
            isinstance(item, int)
            and not isinstance(item, bool)
            and isinstance(packet, int)
            and not isinstance(packet, bool)
            and packet < item
        ):
            self._add_error(
                f"{context}.max_packet_bytes must be greater than or equal to max_item_bytes"
            )

    def _validate_score_ledger_path(
        self,
        path_value: str,
        step: Dict[str, Any],
        context: str,
        artifacts_registry: Optional[Any] = None,
    ) -> None:
        path = Path(path_value)
        normalized = path.as_posix()
        if path.is_absolute() or '..' in path.parts or not normalized.startswith('artifacts/'):
            self._add_error(f"{context}.score_ledger_path must be under artifacts/")
            return
        self._validate_path_safety(path_value, f"{context}.score_ledger_path")

        known_paths: Set[str] = set()
        expected_outputs = step.get('expected_outputs')
        if isinstance(expected_outputs, list):
            for spec in expected_outputs:
                if isinstance(spec, dict) and isinstance(spec.get('path'), str):
                    known_paths.add(Path(spec['path']).as_posix())
        output_bundle = step.get('output_bundle')
        if isinstance(output_bundle, dict) and isinstance(output_bundle.get('path'), str):
            known_paths.add(Path(output_bundle['path']).as_posix())
        publishes = step.get('publishes')
        if isinstance(publishes, list):
            registry = artifacts_registry if isinstance(artifacts_registry, dict) else {}
            expected_list = expected_outputs if isinstance(expected_outputs, list) else []
            for entry in publishes:
                if isinstance(entry, dict) and isinstance(entry.get('from'), str):
                    for spec in expected_list:
                        if isinstance(spec, dict) and spec.get('name') == entry['from'] and spec.get('type') == 'relpath':
                            if isinstance(spec.get('path'), str):
                                known_paths.add(Path(spec['path']).as_posix())
                    artifact_name = entry.get('artifact')
                    artifact_spec = registry.get(artifact_name) if isinstance(artifact_name, str) else None
                    if (
                        isinstance(artifact_spec, dict)
                        and artifact_spec.get('type') == 'relpath'
                        and isinstance(artifact_spec.get('pointer'), str)
                    ):
                        known_paths.add(Path(artifact_spec['pointer']).as_posix())
        if normalized in known_paths:
            self._add_error(f"{context}.score_ledger_path collides with a step-managed output path")

    def _validate_no_run_root_candidate_path(self, path_value: str, context: str) -> None:
        if '${run.root}' in path_value:
            self._add_error(f"{context} must not depend on ${{run.root}}")
            return
        if '.orchestrate/runs/' in path_value or path_value.startswith('.orchestrate/runs'):
            self._add_error(f"{context} must not name the parent run root")

    def _validate_source_relative_asset_path(self, path: str, context: str) -> None:
        """Validate one workflow-source-relative asset path against the current source tree."""
        if self._current_workflow_path is None:
            self._add_error(f"{context}: workflow source root is unavailable")
            return
        try:
            WorkflowAssetResolver(self._current_workflow_path).resolve(path)
        except AssetResolutionError as exc:
            self._add_error(f"{context}: {exc}")

    def _validate_scalar_bookkeeping(
        self,
        step: Dict[str, Any],
        node: Any,
        field_name: str,
        step_name: str,
        artifacts_registry: Optional[Any],
    ) -> None:
        context = f"Step '{step_name}': {field_name}"
        if not isinstance(node, dict):
            self._add_error(f"{context} must be a dictionary")
            return

        if step.get('persist_artifacts_in_state') is False:
            self._add_error(f"{context} requires persist_artifacts_in_state to be true")

        artifact_name = node.get('artifact')
        if not isinstance(artifact_name, str) or not artifact_name.strip():
            self._add_error(f"{context} 'artifact' must be a non-empty string")
            return

        registry = artifacts_registry if isinstance(artifacts_registry, dict) else {}
        artifact_spec = registry.get(artifact_name)
        if not isinstance(artifact_spec, dict) or artifact_spec.get('kind') != 'scalar':
            self._add_error(f"{context} must target a declared scalar artifact")
            return

        artifact_type = artifact_spec.get('type')
        if field_name == 'set_scalar':
            if 'value' not in node:
                self._add_error(f"{context} missing required 'value'")
            elif isinstance(node.get('value'), (dict, list)):
                self._add_error(f"{context} 'value' must be a scalar literal")
            return

        if 'by' not in node:
            self._add_error(f"{context} missing required 'by'")
            return
        by_value = node.get('by')
        if type(by_value) not in {int, float}:
            self._add_error(f"{context} 'by' must be a numeric literal")
        if artifact_type not in {'integer', 'float'}:
            self._add_error(f"{context} requires an integer or float artifact")

    def _validate_variables_usage(self, step: Dict[str, Any], name: str):
        """Validate variable usage and reject ${env.*} namespace (AT-7)."""
        # Fields that allow variable substitution
        variable_fields = ['command', 'input_file', 'output_file', 'provider', 'provider_params']

        for field in variable_fields:
            if field in step:
                value = step[field]
                self._check_env_variables(value, f"step '{name}' {field}")

        # Check when conditions
        if 'when' in step:
            self._validate_legacy_condition_variable_usage(step['when'], f"step '{name}' when")
        if 'assert' in step:
            self._validate_legacy_condition_variable_usage(step['assert'], f"step '{name}' assert")

    def _validate_call_step(
        self,
        step: Dict[str, Any],
        step_name: str,
        version: str,
        root_catalog: Dict[str, Any],
        scope_artifacts: Dict[str, Any],
        scope_multi_visit: Set[str],
        parent_artifacts: Optional[Dict[str, Any]],
        parent_multi_visit: Optional[Set[str]],
        scope_non_step_results: Set[str],
        parent_non_step_results: Optional[Set[str]],
    ) -> None:
        """Validate reusable-workflow call boundaries."""
        if not self._version_at_least(version, "2.5"):
            self._add_error(f"Step '{step_name}': call requires version '2.5'")
            return
        call_alias = step.get('call')
        if not isinstance(call_alias, str) or not call_alias:
            self._add_error(f"Step '{step_name}': call must name an imported workflow alias")
            return
        if not isinstance(step.get('id'), str) or not STEP_ID_PATTERN.fullmatch(step.get('id')):
            self._add_error(f"Step '{step_name}': call requires an authored stable 'id'")

        imported_workflow = self._current_imports.get(call_alias)
        if not isinstance(imported_workflow, LoadedWorkflowBundle):
            self._add_error(f"Step '{step_name}': unknown import alias '{call_alias}'")
            return
        callee_inputs = workflow_input_contracts(imported_workflow)

        bindings = step.get('with', {})
        if bindings is None:
            bindings = {}
        if not isinstance(bindings, dict):
            self._add_error(f"Step '{step_name}': with must be a dictionary")
            return

        for bound_name in bindings:
            if bound_name not in callee_inputs:
                self._add_error(
                    f"Step '{step_name}': call.with.{bound_name} does not match any declared callee input"
                )

        for input_name, input_spec in callee_inputs.items():
            if not isinstance(input_spec, Mapping):
                continue

            if input_name not in bindings:
                if "default" in input_spec or input_spec.get("required", True) is False:
                    continue
                self._add_error(
                    f"Step '{step_name}': call.with is missing required callee input '{input_name}'"
                )
                continue

            binding = bindings[input_name]
            if isinstance(binding, dict):
                if set(binding.keys()) != {'ref'}:
                    self._add_error(
                        f"Step '{step_name}': call.with.{input_name} must be a literal or {{ref: ...}}"
                    )
                    continue
                resolved_type = self._validate_structured_ref(
                    binding.get('ref'),
                    step_name,
                    version,
                    root_catalog,
                    scope_artifacts,
                    scope_multi_visit,
                    parent_artifacts,
                    parent_multi_visit,
                    scope_non_step_results,
                    parent_non_step_results,
                )
                declared_type = input_spec.get("type")
                if (
                    isinstance(declared_type, str)
                    and resolved_type != 'unknown'
                    and declared_type != resolved_type
                    and not (declared_type == 'float' and resolved_type == 'integer')
                ):
                    self._add_error(
                        f"Step '{step_name}': call.with.{input_name} resolves to '{resolved_type}' but callee input declares '{declared_type}'"
                    )
                continue

            try:
                validate_contract_value(binding, input_spec, workspace=self.workspace)
            except OutputContractError as exc:
                self._add_error(f"Step '{step_name}': call.with.{input_name} is invalid: {exc}")

        managed_inputs = workflow_managed_write_root_inputs(imported_workflow)
        if managed_inputs:
            callee_inputs = workflow_input_contracts(imported_workflow)
            for input_name in managed_inputs:
                if input_name in bindings:
                    continue
                input_spec = callee_inputs.get(input_name, {})
                if isinstance(input_spec, Mapping) and "default" in input_spec:
                    continue
                self._add_error(
                    f"Step '{step_name}': call is missing required write-root binding '{input_name}'"
                )

    def _analyze_reusable_write_roots(self, workflow: Dict[str, Any]) -> tuple[Set[str], List[str]]:
        """Return relpath inputs used for managed write roots and any contract violations."""
        managed_inputs: Set[str] = set()
        errors: List[str] = []
        input_specs = workflow.get('inputs', {})
        if not isinstance(input_specs, dict):
            input_specs = {}

        steps = list(workflow.get('steps', [])) if isinstance(workflow.get('steps'), list) else []
        finally_block = workflow.get('finally')
        if isinstance(finally_block, dict) and isinstance(finally_block.get('steps'), list):
            steps.extend(finally_block.get('steps', []))

        for step in self._collect_all_steps(steps):
            step_name = step.get('name', 'step')
            for field_label, candidate in self._iter_managed_write_paths(step):
                if not isinstance(candidate, str) or not candidate:
                    continue
                referenced_inputs = set(self.INPUT_REF_PATTERN.findall(candidate))
                relpath_inputs: Set[str] = set()
                for input_name in referenced_inputs:
                    spec = input_specs.get(input_name)
                    if not isinstance(spec, dict) or spec.get('type') != 'relpath':
                        errors.append(
                            f"Reusable workflow step '{step_name}' must use typed relpath inputs for "
                            f"{field_label}; input '{input_name}' is not declared as type 'relpath'"
                        )
                        continue
                    relpath_inputs.add(input_name)

                if relpath_inputs:
                    managed_inputs.update(relpath_inputs)
                    continue

                errors.append(
                    f"Reusable workflow step '{step_name}' hard-codes DSL-managed write roots in "
                    f"{field_label}; expose them as typed relpath inputs instead"
                )

        return managed_inputs, errors

    def _iter_managed_write_paths(self, step: Dict[str, Any]) -> List[tuple[str, Any]]:
        """Yield explicit DSL-managed write-path surfaces for reusable-call validation."""
        paths: List[tuple[str, Any]] = []
        if 'output_file' in step:
            paths.append(('output_file', step.get('output_file')))

        expected_outputs = step.get('expected_outputs')
        if isinstance(expected_outputs, list):
            for index, spec in enumerate(expected_outputs):
                if isinstance(spec, dict) and 'path' in spec:
                    paths.append((f"expected_outputs[{index}].path", spec.get('path')))

        output_bundle = step.get('output_bundle')
        if isinstance(output_bundle, dict) and 'path' in output_bundle:
            paths.append(('output_bundle.path', output_bundle.get('path')))

        variant_output = step.get('variant_output')
        if isinstance(variant_output, dict) and 'path' in variant_output:
            paths.append(('variant_output.path', variant_output.get('path')))

        consume_bundle = step.get('consume_bundle')
        if isinstance(consume_bundle, dict) and 'path' in consume_bundle:
            paths.append(('consume_bundle.path', consume_bundle.get('path')))

        return paths

    def _validate_call_write_root_collisions(self, steps: Any, finally_block: Any) -> None:
        """Reject call sites that bind the same managed write root more than once."""
        collected_steps: List[Any] = []
        if isinstance(steps, list):
            collected_steps.extend(steps)
        if isinstance(finally_block, dict) and isinstance(finally_block.get('steps'), list):
            collected_steps.extend(finally_block.get('steps', []))

        seen: Dict[Any, tuple[str, str]] = {}
        for step, multi_visit_context in self._iter_call_sites(collected_steps):
            if not isinstance(step, dict) or 'call' not in step:
                continue

            step_name = step.get('name', 'step')
            imported_workflow = self._current_imports.get(step.get('call'))
            if not isinstance(imported_workflow, LoadedWorkflowBundle):
                continue

            managed_inputs = workflow_managed_write_root_inputs(imported_workflow)
            if not managed_inputs:
                continue

            bindings = step.get('with', {})
            if not isinstance(bindings, dict):
                bindings = {}
            callee_inputs = workflow_input_contracts(imported_workflow)

            for input_name in managed_inputs:
                if input_name in bindings:
                    binding = bindings[input_name]
                else:
                    input_spec = callee_inputs.get(input_name, {})
                    if not isinstance(input_spec, Mapping) or 'default' not in input_spec:
                        continue
                    binding = input_spec['default']

                collision_key = self._call_write_root_collision_key(binding)
                if multi_visit_context is not None and self._loop_binding_is_invariant(binding):
                    self._add_error(
                        f"Step '{step_name}': call.with.{input_name} must vary per invocation inside "
                        f"{multi_visit_context} when binding a managed write root"
                    )
                    continue
                if collision_key is None:
                    continue

                prior = seen.get(collision_key)
                if prior is not None:
                    prior_step, prior_input = prior
                    self._add_error(
                        f"Step '{step_name}': colliding write-root bindings with step '{prior_step}' "
                        f"for inputs '{input_name}' and '{prior_input}'"
                    )
                else:
                    seen[collision_key] = (step_name, input_name)

    def _loop_binding_is_invariant(self, binding: Any) -> bool:
        """Return True when a managed write-root binding cannot vary across loop visits."""
        if isinstance(binding, dict) and set(binding.keys()) == {'ref'}:
            ref = binding.get('ref')
            return isinstance(ref, str) and (
                ref.startswith('root.')
                or ref.startswith('inputs.')
            )
        if isinstance(binding, str) and "${loop.index}" in binding:
            return False
        return self._call_write_root_collision_key(binding) is not None

    def _call_write_root_collision_key(self, binding: Any) -> Optional[Any]:
        """Return a deterministic comparable key for a call write-root binding."""
        if isinstance(binding, dict) and set(binding.keys()) == {'ref'}:
            return ('ref', binding.get('ref'))
        if isinstance(binding, str) and "${loop.index}" in binding:
            return None
        if isinstance(binding, (str, int, float, bool)):
            return ('literal', binding)
        return None

    def _validate_legacy_condition_variable_usage(self, condition: Any, context: str) -> None:
        """Apply ${env.*} validation to legacy conditional substitution surfaces."""
        if not isinstance(condition, dict):
            return

        if 'equals' in condition and isinstance(condition['equals'], dict):
            for key in ('left', 'right'):
                if key in condition['equals']:
                    self._check_env_variables(condition['equals'][key], f"{context}.equals.{key}")

        if 'exists' in condition:
            self._check_env_variables(condition['exists'], f"{context}.exists")
        if 'not_exists' in condition:
            self._check_env_variables(condition['not_exists'], f"{context}.not_exists")

    def _check_env_variables(self, value: Any, context: str):
        """Check for and reject ${env.*} variables (AT-7)."""
        if isinstance(value, str):
            if self.ENV_VAR_PATTERN.search(value):
                self._add_error(f"{context}: ${'{env.*}'} namespace not allowed in DSL")
        elif isinstance(value, list):
            for item in value:
                self._check_env_variables(item, context)
        elif isinstance(value, dict):
            for v in value.values():
                self._check_env_variables(v, context)

    def _validate_wait_for(self, step: Dict[str, Any], name: str):
        """Validate wait_for configuration (AT-36)."""
        wait_for = step['wait_for']

        if not isinstance(wait_for, dict):
            self._add_error(f"Step '{name}': wait_for must be a dictionary")
            return

        # wait_for is exclusive with other execution fields
        exclusive_fields = ['command', 'provider', 'for_each']
        conflicts = [f for f in exclusive_fields if f in step]
        if conflicts:
            self._add_error(f"Step '{name}': wait_for cannot be combined with {conflicts}")

    def _validate_expected_outputs(
        self,
        expected_outputs: Any,
        step_name: str,
        version: str,
        *,
        subject_refs: tuple[ValidationSubjectRef, ...] = (),
    ):
        """Validate expected_outputs contract entries."""
        if not isinstance(expected_outputs, list):
            self._add_error(f"Step '{step_name}': expected_outputs must be a list", subject_refs=subject_refs)
            return

        seen_names: Set[str] = set()
        for i, spec in enumerate(expected_outputs):
            context = f"Step '{step_name}': expected_outputs[{i}]"
            if not isinstance(spec, dict):
                self._add_error(f"{context} must be a dictionary", subject_refs=subject_refs)
                continue

            if 'name' not in spec:
                self._add_error(f"{context} missing required 'name'", subject_refs=subject_refs)
            elif not isinstance(spec['name'], str):
                self._add_error(f"{context} 'name' must be a string", subject_refs=subject_refs)
            elif not spec['name'].strip():
                self._add_error(f"{context} 'name' cannot be empty", subject_refs=subject_refs)
            elif spec['name'] in seen_names:
                self._add_error(f"{context} duplicate artifact name '{spec['name']}'", subject_refs=subject_refs)
            else:
                seen_names.add(spec['name'])

            if 'path' not in spec:
                self._add_error(f"{context} missing required 'path'", subject_refs=subject_refs)
            elif not isinstance(spec['path'], str):
                self._add_error(f"{context} 'path' must be a string", subject_refs=subject_refs)
            else:
                self._validate_path_safety(spec['path'], f"{context} path", subject_refs=subject_refs)

            if 'type' not in spec:
                self._add_error(f"{context} missing required 'type'", subject_refs=subject_refs)
            elif not isinstance(spec['type'], str):
                self._add_error(f"{context} 'type' must be a string", subject_refs=subject_refs)
            elif spec['type'] not in self._supported_expected_output_types(version):
                self._add_error(f"{context} invalid expected_outputs type '{spec['type']}'", subject_refs=subject_refs)

            if 'under' in spec:
                if not isinstance(spec['under'], str):
                    self._add_error(f"{context} 'under' must be a string", subject_refs=subject_refs)
                else:
                    self._validate_path_safety(spec['under'], f"{context} under", subject_refs=subject_refs)

            if 'allowed' in spec:
                if not isinstance(spec['allowed'], list):
                    self._add_error(f"{context} 'allowed' must be a list", subject_refs=subject_refs)

            if spec.get('type') == 'enum' and 'allowed' not in spec:
                self._add_error(f"{context} enum type requires 'allowed'", subject_refs=subject_refs)

            if 'must_exist_target' in spec and not isinstance(spec['must_exist_target'], bool):
                self._add_error(f"{context} 'must_exist_target' must be a boolean", subject_refs=subject_refs)

            if 'required' in spec and not isinstance(spec['required'], bool):
                self._add_error(f"{context} 'required' must be a boolean", subject_refs=subject_refs)

            for guidance_key in ('description', 'format_hint', 'example'):
                if guidance_key in spec and not isinstance(spec[guidance_key], str):
                    self._add_error(f"{context} '{guidance_key}' must be a string", subject_refs=subject_refs)

    def _validate_output_bundle(
        self,
        output_bundle: Any,
        step_name: str,
        version: str,
        *,
        subject_refs: tuple[ValidationSubjectRef, ...] = (),
    ):
        """Validate output_bundle contract entries (v1.3)."""
        context = f"Step '{step_name}': output_bundle"
        if not isinstance(output_bundle, dict):
            self._add_error(f"{context} must be a dictionary", subject_refs=subject_refs)
            return

        if 'path' not in output_bundle:
            self._add_error(f"{context} missing required 'path'", subject_refs=subject_refs)
        elif not isinstance(output_bundle['path'], str):
            self._add_error(f"{context} 'path' must be a string", subject_refs=subject_refs)
        else:
            self._validate_path_safety(output_bundle['path'], f"{context} path", subject_refs=subject_refs)

        if 'guidance' in output_bundle:
            if not self._version_at_least(version, "2.15"):
                self._add_error(
                    f"{context}.guidance requires version '2.15'",
                    subject_refs=subject_refs,
                )
            else:
                self._validate_guidance_payload(
                    output_bundle['guidance'],
                    context=f"{context}.guidance",
                    version=version,
                    allow_context=False,
                    subject_refs=subject_refs,
                )
        for misplaced_key in ('description', 'format_hint', 'example', 'guidance_context', 'guidance_by_variant'):
            if misplaced_key in output_bundle:
                self._add_error(
                    f"{context}.{misplaced_key} is not allowed at bundle level; use {context}.guidance",
                    subject_refs=subject_refs,
                )

        fields = output_bundle.get('fields')
        if not isinstance(fields, list) or not fields:
            self._add_error(f"{context}.fields must be a non-empty list", subject_refs=subject_refs)
            return

        seen_names: Set[str] = set()
        root_pointer_indexes: list[int] = []
        for i, spec in enumerate(fields):
            field_context = f"{context}.fields[{i}]"
            if not isinstance(spec, dict):
                self._add_error(f"{field_context} must be a dictionary", subject_refs=subject_refs)
                continue

            if 'name' not in spec:
                self._add_error(f"{field_context} missing required 'name'", subject_refs=subject_refs)
            elif not isinstance(spec['name'], str):
                self._add_error(f"{field_context} 'name' must be a string", subject_refs=subject_refs)
            elif not spec['name'].strip():
                self._add_error(f"{field_context} 'name' cannot be empty", subject_refs=subject_refs)
            elif spec['name'] in seen_names:
                self._add_error(f"{field_context} duplicate artifact name '{spec['name']}'", subject_refs=subject_refs)
            else:
                seen_names.add(spec['name'])

            if 'json_pointer' not in spec:
                self._add_error(f"{field_context} missing required 'json_pointer'", subject_refs=subject_refs)
            elif not isinstance(spec['json_pointer'], str):
                self._add_error(f"{field_context} 'json_pointer' must be a string", subject_refs=subject_refs)
            else:
                pointer = spec['json_pointer']
                if pointer and not pointer.startswith('/'):
                    self._add_error(f"{field_context} 'json_pointer' must be RFC 6901 pointer syntax", subject_refs=subject_refs)
                elif (
                    self._version_at_least(version, "2.15")
                    and self._decode_guidance_json_pointer(pointer) is None
                ):
                    self._add_error(f"{field_context} 'json_pointer' must be RFC 6901 pointer syntax", subject_refs=subject_refs)
                elif pointer == "":
                    root_pointer_indexes.append(i)

            self._validate_field_guidance(
                spec,
                context=field_context,
                version=version,
                subject_refs=subject_refs,
            )

            self._validate_output_schema_spec(
                spec,
                field_context=field_context,
                version=version,
                subject_refs=subject_refs,
                kind_label="output_bundle",
                allow_guidance_keys=True,
            )

        if self._version_at_least(version, "2.15") and len(fields) > 1 and root_pointer_indexes:
            self._add_error(
                f"{context}.fields root json_pointer cannot have sibling fields",
                subject_refs=subject_refs,
            )

    def _validate_variant_output(
        self,
        variant_output: Any,
        step_name: str,
        version: str,
        *,
        subject_refs: tuple[ValidationSubjectRef, ...] = (),
    ) -> None:
        """Validate tagged-union output contract entries (v2.14)."""
        context = f"Step '{step_name}': variant_output"
        if not isinstance(variant_output, dict):
            self._add_error(f"{context} must be a dictionary", subject_refs=subject_refs)
            return

        if 'path' not in variant_output:
            self._add_error(f"{context} missing required 'path'", subject_refs=subject_refs)
        elif not isinstance(variant_output['path'], str):
            self._add_error(f"{context} 'path' must be a string", subject_refs=subject_refs)
        else:
            self._validate_path_safety(variant_output['path'], f"{context} path", subject_refs=subject_refs)

        if 'guidance' in variant_output:
            if not self._version_at_least(version, "2.15"):
                self._add_error(
                    f"{context}.guidance requires version '2.15'",
                    subject_refs=subject_refs,
                )
            else:
                self._validate_guidance_payload(
                    variant_output['guidance'],
                    context=f"{context}.guidance",
                    version=version,
                    allow_context=False,
                    subject_refs=subject_refs,
                )
        for misplaced_key in ('description', 'format_hint', 'example', 'guidance_context', 'guidance_by_variant'):
            if misplaced_key in variant_output:
                self._add_error(
                    f"{context}.{misplaced_key} is not allowed at bundle level; use {context}.guidance",
                    subject_refs=subject_refs,
                )

        discriminant = variant_output.get('discriminant')
        if not isinstance(discriminant, dict):
            self._add_error(f"{context}.discriminant must be a dictionary", subject_refs=subject_refs)
            return

        shared_fields = variant_output.get('shared_fields', [])
        if shared_fields is None:
            shared_fields = []
        if not isinstance(shared_fields, list):
            self._add_error(f"{context}.shared_fields must be a list", subject_refs=subject_refs)
            shared_fields = []

        variants = variant_output.get('variants')
        if not isinstance(variants, dict) or not variants:
            self._add_error(f"{context}.variants must be a non-empty dictionary", subject_refs=subject_refs)
            return

        base_seen_names: Set[str] = set()
        base_seen_pointers: Set[str] = set()

        def validate_field_spec(
            spec: Any,
            field_context: str,
            *,
            seen_names: Set[str],
            seen_pointers: Set[str],
            guidance_role: str,
        ) -> None:
            if not isinstance(spec, dict):
                self._add_error(f"{field_context} must be a dictionary", subject_refs=subject_refs)
                return

            name = spec.get('name')
            if not isinstance(name, str):
                self._add_error(f"{field_context} 'name' must be a string", subject_refs=subject_refs)
            elif not name.strip():
                self._add_error(f"{field_context} 'name' cannot be empty", subject_refs=subject_refs)
            elif name in seen_names:
                self._add_error(
                    f"{field_context} duplicate artifact name '{name}' across discriminant/shared_fields/variants",
                    subject_refs=subject_refs,
                )
            else:
                seen_names.add(name)

            pointer = spec.get('json_pointer')
            if not isinstance(pointer, str):
                self._add_error(f"{field_context} 'json_pointer' must be a string", subject_refs=subject_refs)
            else:
                if pointer and not pointer.startswith('/'):
                    self._add_error(f"{field_context} 'json_pointer' must be RFC 6901 pointer syntax", subject_refs=subject_refs)
                elif (
                    self._version_at_least(version, "2.15")
                    and self._decode_guidance_json_pointer(pointer) is None
                ):
                    self._add_error(f"{field_context} 'json_pointer' must be RFC 6901 pointer syntax", subject_refs=subject_refs)
                elif pointer in seen_pointers:
                    self._add_error(
                        f"{field_context} duplicate json_pointer '{pointer}' across discriminant/shared_fields/variants",
                        subject_refs=subject_refs,
                    )
                else:
                    seen_pointers.add(pointer)

            self._validate_field_guidance(
                spec,
                context=field_context,
                version=version,
                allowed_variants=(
                    discriminant.get('allowed')
                    if guidance_role == "shared" and isinstance(discriminant.get('allowed'), list)
                    else None
                ),
                allow_guidance=guidance_role != "discriminant",
                allow_guidance_by_variant=guidance_role == "shared",
                subject_refs=subject_refs,
            )

            self._validate_output_schema_spec(
                spec,
                field_context=field_context,
                version=version,
                subject_refs=subject_refs,
                kind_label="variant_output",
                allow_guidance_keys=guidance_role != "discriminant",
            )

        validate_field_spec(
            discriminant,
            f"{context}.discriminant",
            seen_names=base_seen_names,
            seen_pointers=base_seen_pointers,
            guidance_role="discriminant",
        )

        for index, spec in enumerate(shared_fields):
            validate_field_spec(
                spec,
                f"{context}.shared_fields[{index}]",
                seen_names=base_seen_names,
                seen_pointers=base_seen_pointers,
                guidance_role="shared",
            )

        for variant_name, variant_spec in variants.items():
            variant_context = f"{context}.variants.{variant_name}"
            if not isinstance(variant_spec, dict):
                self._add_error(f"{variant_context} must be a dictionary", subject_refs=subject_refs)
                continue
            fields = variant_spec.get('fields')
            if not isinstance(fields, list):
                self._add_error(f"{variant_context}.fields must be a list", subject_refs=subject_refs)
                continue
            variant_seen_names = set(base_seen_names)
            variant_seen_pointers = set(base_seen_pointers)
            for index, spec in enumerate(fields):
                validate_field_spec(
                    spec,
                    f"{variant_context}.fields[{index}]",
                    seen_names=variant_seen_names,
                    seen_pointers=variant_seen_pointers,
                    guidance_role="variant",
                )

    def _validate_field_guidance(
        self,
        spec: Dict[str, Any],
        *,
        context: str,
        version: str,
        allowed_variants: Any = None,
        allow_guidance: bool = True,
        allow_guidance_by_variant: bool = False,
        subject_refs: tuple[ValidationSubjectRef, ...] = (),
    ) -> None:
        """Validate additive v2.15 guidance without changing value schemas."""
        direct_keys = ('description', 'format_hint', 'example', 'guidance_context')
        present_direct_keys = tuple(key for key in direct_keys if key in spec)
        has_by_variant = 'guidance_by_variant' in spec
        if not present_direct_keys and not has_by_variant:
            return

        if not self._version_at_least(version, "2.15"):
            self._add_error(
                f"{context} field guidance requires version '2.15'",
                subject_refs=subject_refs,
            )
            return

        if not allow_guidance:
            for key in (*present_direct_keys, *(() if not has_by_variant else ('guidance_by_variant',))):
                self._add_error(
                    f"{context}: guidance key '{key}' is not allowed on the discriminant",
                    subject_refs=subject_refs,
                )
            return

        if present_direct_keys:
            direct_payload = {key: spec[key] for key in present_direct_keys}
            self._validate_guidance_payload(
                direct_payload,
                context=context,
                version=version,
                allow_context=True,
                leaf_pointer=spec.get('json_pointer'),
                field_spec=spec,
                subject_refs=subject_refs,
            )

        if not has_by_variant:
            return
        if not allow_guidance_by_variant:
            self._add_error(
                f"{context}.guidance_by_variant is only allowed on shared variant fields",
                subject_refs=subject_refs,
            )
            return
        if present_direct_keys:
            self._add_error(
                f"{context}.guidance_by_variant is mutually exclusive with direct guidance",
                subject_refs=subject_refs,
            )

        payloads = spec['guidance_by_variant']
        if not isinstance(payloads, dict) or not payloads:
            self._add_error(
                f"{context}.guidance_by_variant must be a non-empty dictionary",
                subject_refs=subject_refs,
            )
            return

        canonical_variants = (
            [value for value in allowed_variants if isinstance(value, str)]
            if isinstance(allowed_variants, list)
            else []
        )
        payload_names = list(payloads)
        unknown_variants = [name for name in payload_names if name not in canonical_variants]
        if unknown_variants:
            self._add_error(
                f"{context}.guidance_by_variant has unknown variants {unknown_variants}",
                subject_refs=subject_refs,
            )
        expected_order = [name for name in canonical_variants if name in payloads]
        if not unknown_variants and payload_names != expected_order:
            self._add_error(
                f"{context}.guidance_by_variant keys must follow discriminant allowed order",
                subject_refs=subject_refs,
            )

        for variant_name, payload in payloads.items():
            self._validate_guidance_payload(
                payload,
                context=f"{context}.guidance_by_variant.{variant_name}",
                version=version,
                allow_context=True,
                leaf_pointer=spec.get('json_pointer'),
                field_spec=spec,
                subject_refs=subject_refs,
            )

    def _validate_guidance_payload(
        self,
        payload: Any,
        *,
        context: str,
        version: str,
        allow_context: bool,
        leaf_pointer: Any = None,
        field_spec: Optional[Mapping[str, Any]] = None,
        subject_refs: tuple[ValidationSubjectRef, ...] = (),
    ) -> None:
        """Validate one closed guidance payload independently of value-schema shape."""
        if not isinstance(payload, dict):
            self._add_error(f"{context} must be a dictionary", subject_refs=subject_refs)
            return

        allowed_keys = {'description', 'format_hint', 'example'}
        if allow_context:
            allowed_keys.add('guidance_context')
        for key in payload:
            if key not in allowed_keys:
                self._add_error(f"{context}: unknown guidance key '{key}'", subject_refs=subject_refs)

        if not payload:
            self._add_error(f"{context} must be a non-empty guidance payload", subject_refs=subject_refs)
            return

        for key in ('description', 'format_hint'):
            if key not in payload:
                continue
            value = payload[key]
            if not isinstance(value, str) or not value.strip():
                self._add_error(
                    f"{context}.{key} must be a non-empty string",
                    subject_refs=subject_refs,
                )

        if 'example' in payload:
            self._validate_json_compatible_guidance_value(
                payload['example'],
                context=f"{context}.example",
                subject_refs=subject_refs,
            )
            if field_spec is not None:
                self._validate_field_guidance_example(
                    payload['example'],
                    field_spec,
                    context=f"{context}.example",
                    subject_refs=subject_refs,
                )

        if 'guidance_context' not in payload:
            return
        rows = payload['guidance_context']
        if not isinstance(rows, list) or not rows:
            self._add_error(
                f"{context}.guidance_context must be a non-empty list",
                subject_refs=subject_refs,
            )
            return
        if leaf_pointer == "":
            self._add_error(
                f"{context} root field cannot declare guidance_context",
                subject_refs=subject_refs,
            )
            return
        leaf_parts = self._decode_guidance_json_pointer(leaf_pointer)
        if leaf_parts is None:
            return

        previous_depth = -1
        seen_pointers: set[str] = set()
        for index, row in enumerate(rows):
            row_context = f"{context}.guidance_context[{index}]"
            if not isinstance(row, dict):
                self._add_error(f"{row_context} must be a dictionary", subject_refs=subject_refs)
                continue
            row_pointer = row.get('json_pointer')
            if not isinstance(row_pointer, str) or not row_pointer:
                self._add_error(
                    f"{row_context}.json_pointer must be a non-empty RFC 6901 pointer",
                    subject_refs=subject_refs,
                )
                continue
            row_parts = self._decode_guidance_json_pointer(row_pointer)
            if row_parts is None:
                self._add_error(
                    f"{row_context}.json_pointer must use RFC 6901 pointer syntax",
                    subject_refs=subject_refs,
                )
                continue
            if row_pointer in seen_pointers:
                self._add_error(
                    f"{row_context}.json_pointer duplicates an earlier context pointer",
                    subject_refs=subject_refs,
                )
            seen_pointers.add(row_pointer)
            if len(row_parts) >= len(leaf_parts) or leaf_parts[:len(row_parts)] != row_parts:
                self._add_error(
                    f"{row_context}.json_pointer must be a proper prefix of the field pointer",
                    subject_refs=subject_refs,
                )
            if len(row_parts) <= previous_depth:
                self._add_error(
                    f"{context}.guidance_context must be ordered shallowest to deepest",
                    subject_refs=subject_refs,
                )
            previous_depth = len(row_parts)

            row_payload = {key: value for key, value in row.items() if key != 'json_pointer'}
            self._validate_guidance_payload(
                row_payload,
                context=row_context,
                version=version,
                allow_context=False,
                subject_refs=subject_refs,
            )

    def _validate_json_compatible_guidance_value(
        self,
        value: Any,
        *,
        context: str,
        subject_refs: tuple[ValidationSubjectRef, ...] = (),
    ) -> None:
        if not self._is_json_native_guidance_value(value):
            self._add_error(
                f"{context} must be JSON-compatible",
                subject_refs=subject_refs,
            )
            return
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError):
            self._add_error(
                f"{context} must be JSON-compatible",
                subject_refs=subject_refs,
            )

    @classmethod
    def _is_json_native_guidance_value(cls, value: Any) -> bool:
        if value is None or isinstance(value, (bool, str)):
            return True
        if type(value) is int:
            return True
        if isinstance(value, float):
            return math.isfinite(value)
        if isinstance(value, list):
            return all(cls._is_json_native_guidance_value(item) for item in value)
        if isinstance(value, dict):
            return all(
                isinstance(key, str) and cls._is_json_native_guidance_value(item)
                for key, item in value.items()
            )
        return False

    @staticmethod
    def _decode_guidance_json_pointer(pointer: Any) -> Optional[tuple[str, ...]]:
        if not isinstance(pointer, str) or (pointer and not pointer.startswith('/')):
            return None
        if pointer == "":
            return ()
        decoded: list[str] = []
        for raw_part in pointer[1:].split('/'):
            index = 0
            chars: list[str] = []
            while index < len(raw_part):
                char = raw_part[index]
                if char != '~':
                    chars.append(char)
                    index += 1
                    continue
                if index + 1 >= len(raw_part) or raw_part[index + 1] not in {'0', '1'}:
                    return None
                chars.append('~' if raw_part[index + 1] == '0' else '/')
                index += 2
            decoded.append(''.join(chars))
        return tuple(decoded)

    def _validate_field_guidance_example(
        self,
        example: Any,
        field_spec: Mapping[str, Any],
        *,
        context: str,
        subject_refs: tuple[ValidationSubjectRef, ...] = (),
    ) -> None:
        schema = self._guidance_example_schema(field_spec)
        if not self._guidance_example_has_json_type(example, schema):
            self._add_error(f"{context} is invalid for the field schema", subject_refs=subject_refs)
            return
        try:
            validate_contract_value(example, schema, workspace=self.workspace)
        except OutputContractError as exc:
            self._add_error(
                f"{context} is invalid for the field schema: {exc}",
                subject_refs=subject_refs,
            )

    @classmethod
    def _guidance_example_schema(cls, spec: Mapping[str, Any]) -> Dict[str, Any]:
        schema = deepcopy(dict(spec))
        schema.pop('description', None)
        schema.pop('format_hint', None)
        schema.pop('example', None)
        schema.pop('guidance_context', None)
        schema.pop('guidance_by_variant', None)
        if 'must_exist_target' in schema:
            schema['must_exist_target'] = False
        for key in ('item', 'items', 'keys', 'values'):
            child = schema.get(key)
            if isinstance(child, Mapping):
                schema[key] = cls._guidance_example_schema(child)
        return schema

    @classmethod
    def _guidance_example_has_json_type(cls, value: Any, spec: Mapping[str, Any]) -> bool:
        value_type = spec.get('type')
        if value_type == 'optional':
            return value is None or (
                isinstance(spec.get('item'), Mapping)
                and cls._guidance_example_has_json_type(value, spec['item'])
            )
        if value_type == 'list':
            return isinstance(value, list) and isinstance(spec.get('items'), Mapping) and all(
                cls._guidance_example_has_json_type(item, spec['items']) for item in value
            )
        if value_type == 'map':
            return isinstance(value, dict) and isinstance(spec.get('values'), Mapping) and all(
                isinstance(key, str) and cls._guidance_example_has_json_type(item, spec['values'])
                for key, item in value.items()
            )
        if value_type in {'string', 'enum', 'relpath'}:
            return isinstance(value, str)
        if value_type == 'integer':
            return type(value) is int
        if value_type == 'float':
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if value_type == 'bool':
            return isinstance(value, bool)
        return False

    def _validate_output_schema_spec(
        self,
        spec: Dict[str, Any],
        *,
        field_context: str,
        version: str,
        subject_refs: tuple[ValidationSubjectRef, ...] = (),
        kind_label: str,
        allow_guidance_keys: bool = False,
    ) -> None:
        if not allow_guidance_keys and self._version_at_least(version, "2.15"):
            for key in ('description', 'format_hint', 'example', 'guidance_context', 'guidance_by_variant'):
                if key in spec:
                    self._add_error(
                        f"{field_context}: guidance key '{key}' is not allowed in a nested schema",
                        subject_refs=subject_refs,
                    )
        if 'type' not in spec:
            self._add_error(f"{field_context} missing required 'type'", subject_refs=subject_refs)
            return
        output_type = spec['type']
        if not isinstance(output_type, str):
            self._add_error(f"{field_context} 'type' must be a string", subject_refs=subject_refs)
            return
        if output_type not in self._supported_output_types(version):
            self._add_error(
                f"{field_context} invalid {kind_label} field type '{output_type}'",
                subject_refs=subject_refs,
            )
            return

        if 'under' in spec:
            if not isinstance(spec['under'], str):
                self._add_error(f"{field_context} 'under' must be a string", subject_refs=subject_refs)
            else:
                self._validate_path_safety(spec['under'], f"{field_context} under", subject_refs=subject_refs)

        if 'allowed' in spec and not isinstance(spec['allowed'], list):
            self._add_error(f"{field_context} 'allowed' must be a list", subject_refs=subject_refs)

        if output_type == 'enum' and 'allowed' not in spec:
            self._add_error(f"{field_context} enum type requires 'allowed'", subject_refs=subject_refs)

        if 'must_exist_target' in spec and not isinstance(spec['must_exist_target'], bool):
            self._add_error(f"{field_context} 'must_exist_target' must be a boolean", subject_refs=subject_refs)

        if 'required' in spec and not isinstance(spec['required'], bool):
            self._add_error(f"{field_context} 'required' must be a boolean", subject_refs=subject_refs)

        if output_type == 'optional':
            item_spec = spec.get('item')
            if not isinstance(item_spec, dict):
                self._add_error(f"{field_context} optional type requires 'item' schema", subject_refs=subject_refs)
                return
            self._validate_output_schema_spec(
                item_spec,
                field_context=f"{field_context}.item",
                version=version,
                subject_refs=subject_refs,
                kind_label=kind_label,
            )
            return

        if output_type == 'list':
            item_spec = spec.get('items')
            if not isinstance(item_spec, dict):
                self._add_error(f"{field_context} list type requires 'items' schema", subject_refs=subject_refs)
                return
            self._validate_output_schema_spec(
                item_spec,
                field_context=f"{field_context}.items",
                version=version,
                subject_refs=subject_refs,
                kind_label=kind_label,
            )
            return

        if output_type == 'map':
            key_spec = spec.get('keys')
            value_spec = spec.get('values')
            if not isinstance(key_spec, dict):
                self._add_error(f"{field_context} map type requires 'keys' schema", subject_refs=subject_refs)
            else:
                self._validate_output_schema_spec(
                    key_spec,
                    field_context=f"{field_context}.keys",
                    version=version,
                    subject_refs=subject_refs,
                    kind_label=kind_label,
                )
                if key_spec.get('type') != 'string':
                    self._add_error(f"{field_context}.keys map key schema must use type 'string'", subject_refs=subject_refs)
            if not isinstance(value_spec, dict):
                self._add_error(f"{field_context} map type requires 'values' schema", subject_refs=subject_refs)
            else:
                self._validate_output_schema_spec(
                    value_spec,
                    field_context=f"{field_context}.values",
                    version=version,
                    subject_refs=subject_refs,
                    kind_label=kind_label,
                )

    def _extend_variant_proof_context(
        self,
        *,
        step: Dict[str, Any],
        step_name: str,
        root_catalog: Dict[str, Any],
        proof_context: Dict[str, str],
    ) -> Dict[str, str]:
        """Merge step-local requires_variant proof into the inherited proof context."""
        requires_variant = step.get('requires_variant')
        if not isinstance(requires_variant, dict):
            return proof_context

        producer_step = requires_variant.get('step')
        required_variant = requires_variant.get('value')
        if not isinstance(producer_step, str) or not producer_step or not isinstance(required_variant, str) or not required_variant:
            self._add_error(f"Step '{step_name}': requires_variant must declare non-empty step and value")
            return proof_context

        discriminant_spec = self._variant_discriminant_spec_for_step(root_catalog, producer_step)
        if not isinstance(discriminant_spec, dict):
            self._add_error(
                f"Step '{step_name}': requires_variant.step '{producer_step}' does not reference a variant-producing step"
            )
            return proof_context

        allowed = discriminant_spec.get('allowed')
        if isinstance(allowed, list) and required_variant not in allowed:
            self._add_error(
                f"Step '{step_name}': requires_variant.value '{required_variant}' is not allowed for step '{producer_step}'"
            )
            return proof_context

        merged = dict(proof_context)
        existing_variant = merged.get(producer_step)
        if existing_variant is not None and existing_variant != required_variant:
            self._add_error(
                f"Step '{step_name}': requires_variant for step '{producer_step}' contradicts active proof '{existing_variant}'"
            )
            return merged
        merged[producer_step] = required_variant
        return merged

    def _extend_match_case_variant_proof(
        self,
        *,
        step_name: str,
        case_name: str,
        ref_contract: Optional[Dict[str, Any]],
        proof_context: Optional[Dict[str, str]],
    ) -> Dict[str, str]:
        """Attach match-case proof when the selector is a variant discriminant."""
        merged = dict(proof_context or {})
        if not isinstance(ref_contract, dict):
            return merged
        if ref_contract.get('variant_role') != 'discriminant':
            return merged

        producer_step = ref_contract.get('variant_owner_step')
        if not isinstance(producer_step, str) or not producer_step:
            return merged

        existing_variant = merged.get(producer_step)
        if existing_variant is not None and existing_variant != case_name:
            self._add_error(
                f"Step '{step_name}': match case '{case_name}' contradicts active proof '{existing_variant}' for step '{producer_step}'"
            )
            return merged
        merged[producer_step] = case_name
        return merged

    def _variant_discriminant_spec_for_step(
        self,
        root_catalog: Dict[str, Any],
        producer_step: str,
    ) -> Optional[Dict[str, Any]]:
        """Return the discriminant artifact spec for one variant-producing step."""
        artifacts = root_catalog.get('artifacts', {})
        step_artifacts = artifacts.get(producer_step) if isinstance(artifacts, dict) else None
        if not isinstance(step_artifacts, dict):
            return None
        for artifact_spec in step_artifacts.values():
            if isinstance(artifact_spec, dict) and artifact_spec.get('variant_role') == 'discriminant':
                return artifact_spec
        return None

    def _validate_materialize_artifacts(
        self,
        materialize_artifacts: Any,
        step_name: str,
        version: str,
        root_catalog: Dict[str, Any],
        scope_artifacts: Dict[str, Any],
        scope_multi_visit: Set[str],
        parent_artifacts: Optional[Dict[str, Any]],
        parent_multi_visit: Optional[Set[str]],
        scope_non_step_results: Set[str],
        parent_non_step_results: Optional[Set[str]],
        proof_context: Dict[str, str],
    ) -> None:
        """Validate private v2.14 materialize_artifacts refs and pointers."""
        context = f"Step '{step_name}': materialize_artifacts"
        if not isinstance(materialize_artifacts, dict):
            self._add_error(f"{context} must be a dictionary")
            return

        values = materialize_artifacts.get('values')
        if not isinstance(values, list) or not values:
            self._add_error(f"{context}.values must be a non-empty list")
            return

        for index, spec in enumerate(values):
            value_context = f"{context}.values[{index}]"
            if not isinstance(spec, dict):
                self._add_error(f"{value_context} must be a dictionary")
                continue

            name = spec.get('name')
            if not isinstance(name, str) or not name.strip():
                self._add_error(f"{value_context}.name must be a non-empty string")

            source = spec.get('source')
            if not isinstance(source, dict):
                self._add_error(f"{value_context}.source must be a dictionary")
                continue

            source_fields = [field_name for field_name in ('input', 'ref', 'literal') if field_name in source]
            if len(source_fields) != 1:
                self._add_error(f"{value_context}.source must declare exactly one of input, ref, or literal")
                continue

            if 'input' in source:
                input_name = source.get('input')
                if not isinstance(input_name, str) or not input_name:
                    self._add_error(f"{value_context}.source.input must be a non-empty string")
                elif not isinstance(self._workflow_input_specs.get(input_name), dict):
                    self._add_error(f"{value_context}.source.input references unknown workflow input '{input_name}'")
            elif 'ref' in source:
                ref_type = self._validate_structured_ref(
                    source.get('ref'),
                    step_name,
                    version,
                    root_catalog,
                    scope_artifacts,
                    scope_multi_visit,
                    parent_artifacts,
                    parent_multi_visit,
                    scope_non_step_results,
                    parent_non_step_results,
                    proof_context=proof_context,
                )
                contract = spec.get('contract')
                declared_type = contract.get('type') if isinstance(contract, dict) else None
                if (
                    isinstance(declared_type, str)
                    and ref_type != 'unknown'
                    and declared_type != ref_type
                    and not (declared_type == 'float' and ref_type == 'integer')
                ):
                    self._add_error(
                        f"{value_context}.source.ref resolves to '{ref_type}' but contract declares '{declared_type}'"
                    )

            pointer = spec.get('pointer')
            if isinstance(pointer, dict) and 'path' in pointer:
                pointer_path = pointer.get('path')
                if not isinstance(pointer_path, str):
                    self._add_error(f"{value_context}.pointer.path must be a string")
                else:
                    self._validate_path_safety(pointer_path, f"{value_context}.pointer.path")

            if 'ensure_parent' in spec and not isinstance(spec['ensure_parent'], bool):
                self._add_error(f"{value_context}.ensure_parent must be a boolean")

    def _validate_pre_snapshot(
        self,
        pre_snapshot: Any,
        step_name: str,
        version: str,
        root_catalog: Dict[str, Any],
        scope_artifacts: Dict[str, Any],
        scope_multi_visit: Set[str],
        parent_artifacts: Optional[Dict[str, Any]],
        parent_multi_visit: Optional[Set[str]],
        scope_non_step_results: Set[str],
        parent_non_step_results: Optional[Set[str]],
        proof_context: Dict[str, str],
    ) -> None:
        """Validate private v2.14 pre_snapshot candidate refs."""
        context = f"Step '{step_name}': pre_snapshot"
        if not isinstance(pre_snapshot, dict):
            self._add_error(f"{context} must be a dictionary")
            return

        snapshot_name = pre_snapshot.get('name')
        if not isinstance(snapshot_name, str) or not snapshot_name:
            self._add_error(f"{context}.name must be a non-empty string")

        digest = pre_snapshot.get('digest')
        if not isinstance(digest, str) or not digest:
            self._add_error(f"{context}.digest must be a non-empty string")
        elif digest != "sha256":
            self._add_error(
                f"{context}.digest must be 'sha256' (snapshot_ref_not_snapshot_diff)"
            )

        candidates = pre_snapshot.get('candidates')
        if not isinstance(candidates, dict) or not candidates:
            self._add_error(f"{context}.candidates must be a non-empty dictionary")
            return

        for candidate_name, candidate in candidates.items():
            candidate_context = f"{context}.candidates.{candidate_name}"
            ref = candidate.get('ref') if isinstance(candidate, dict) else None
            ref_type = self._validate_structured_ref(
                ref,
                step_name,
                version,
                root_catalog,
                scope_artifacts,
                scope_multi_visit,
                parent_artifacts,
                parent_multi_visit,
                scope_non_step_results,
                parent_non_step_results,
                proof_context=proof_context,
            )
            if ref_type != 'unknown' and ref_type != 'relpath':
                self._add_error(f"{candidate_context}.ref must resolve to a relpath artifact")

    def _validate_select_variant_output(
        self,
        select_variant_output: Any,
        step_name: str,
        version: str,
        root_catalog: Dict[str, Any],
        scope_artifacts: Dict[str, Any],
        scope_multi_visit: Set[str],
        parent_artifacts: Optional[Dict[str, Any]],
        parent_multi_visit: Optional[Set[str]],
        scope_non_step_results: Set[str],
        parent_non_step_results: Optional[Set[str]],
        proof_context: Dict[str, str],
    ) -> None:
        """Validate private v2.14 select_variant_output snapshot evidence refs."""
        context = f"Step '{step_name}': select_variant_output"
        if not isinstance(select_variant_output, dict):
            self._add_error(f"{context} must be a dictionary")
            return

        bundle_path = select_variant_output.get('path')
        if not isinstance(bundle_path, str):
            self._add_error(f"{context}.path must be a string")
        else:
            self._validate_path_safety(bundle_path, f"{context}.path")

        evidence = select_variant_output.get('evidence')
        if not isinstance(evidence, dict):
            self._add_error(f"{context}.evidence must be a dictionary")
            return
        mode = evidence.get('mode')
        if not isinstance(mode, str):
            self._add_error(f"{context}.evidence.mode must be a string")
        elif mode != "snapshot_diff":
            self._add_error(
                f"{context}.evidence.mode must be 'snapshot_diff' (snapshot_ref_not_snapshot_diff)"
            )
        snapshot = evidence.get('snapshot')
        if not isinstance(snapshot, dict):
            self._add_error(f"{context}.evidence.snapshot must be a dictionary")
            return

        ref_type = self._validate_structured_ref(
            snapshot.get('ref'),
            step_name,
            version,
            root_catalog,
            scope_artifacts,
            scope_multi_visit,
            parent_artifacts,
            parent_multi_visit,
            scope_non_step_results,
            parent_non_step_results,
            proof_context=proof_context,
            allow_snapshot_ref=True,
        )
        if ref_type != 'unknown' and ref_type != 'snapshot':
            self._add_error(f"{context}.evidence.snapshot.ref must resolve to a snapshot ref")

    def _validate_materialize_published_pointer_authority(
        self,
        *,
        step: Dict[str, Any],
        step_name: str,
        artifacts_registry: Optional[Dict[str, Any]],
    ) -> None:
        """Enforce canonical top-level pointer ownership for published relpath materializations."""
        materialize_artifacts = step.get('materialize_artifacts')
        publishes = step.get('publishes')
        if not isinstance(materialize_artifacts, dict) or not isinstance(publishes, list):
            return

        values = materialize_artifacts.get('values')
        if not isinstance(values, list):
            return

        local_pointers: Dict[str, str] = {}
        for spec in values:
            if not isinstance(spec, dict):
                continue
            name = spec.get('name')
            pointer = spec.get('pointer')
            pointer_path = pointer.get('path') if isinstance(pointer, dict) else None
            if isinstance(name, str) and isinstance(pointer_path, str) and pointer_path:
                local_pointers[name] = pointer_path

        registry = artifacts_registry if isinstance(artifacts_registry, dict) else {}
        for publish in publishes:
            if not isinstance(publish, dict):
                continue
            artifact_name = publish.get('artifact')
            from_name = publish.get('from')
            if not isinstance(artifact_name, str) or not isinstance(from_name, str):
                continue
            local_pointer = local_pointers.get(from_name)
            if local_pointer is None:
                continue
            artifact_spec = registry.get(artifact_name)
            if not isinstance(artifact_spec, dict):
                continue
            if artifact_spec.get('kind', 'relpath') != 'relpath':
                continue
            canonical_pointer = artifact_spec.get('pointer')
            if isinstance(canonical_pointer, str) and canonical_pointer != local_pointer:
                self._add_error(
                    f"Step '{step_name}': pointer_authority_conflict for published artifact "
                    f"'{artifact_name}' (local pointer '{local_pointer}' != canonical pointer '{canonical_pointer}')"
                )

    def _validate_consume_bundle(self, consume_bundle: Any, step_name: str, consumes: Any):
        """Validate consume_bundle structure and consumes subset constraints (v1.3)."""
        context = f"Step '{step_name}': consume_bundle"
        if not isinstance(consume_bundle, dict):
            self._add_error(f"{context} must be a dictionary")
            return

        if 'path' not in consume_bundle:
            self._add_error(f"{context} missing required 'path'")
        elif not isinstance(consume_bundle['path'], str):
            self._add_error(f"{context} 'path' must be a string")
        else:
            self._validate_path_safety(consume_bundle['path'], f"{context} path")

        if not isinstance(consumes, list) or not consumes:
            self._add_error(f"Step '{step_name}': consume_bundle requires consumes")
            return

        consumed_names = {
            entry.get('artifact')
            for entry in consumes
            if isinstance(entry, dict) and isinstance(entry.get('artifact'), str)
        }

        if 'include' in consume_bundle:
            include = consume_bundle['include']
            if not isinstance(include, list):
                self._add_error(f"{context} 'include' must be a list")
            else:
                for name in include:
                    if not isinstance(name, str) or not name.strip():
                        self._add_error(f"{context} 'include' entries must be non-empty strings")
                        continue
                    if name not in consumed_names:
                        self._add_error(
                            f"Step '{step_name}': consume_bundle.include artifact '{name}' must appear in consumes"
                        )

    def _validate_provider_session(
        self,
        *,
        step: Dict[str, Any],
        step_name: str,
        version: str,
        artifacts_registry: Optional[Any],
        top_level: bool,
    ) -> None:
        """Validate the step-local provider_session contract."""
        context = f"Step '{step_name}': provider_session"
        if not self._version_at_least(version, self.STRING_CONTRACT_VERSION):
            self._add_error(f"{context} requires version '{self.STRING_CONTRACT_VERSION}'")
            return
        if not top_level or self._current_workflow_is_imported:
            self._add_error(
                f"{context} is only supported on provider steps authored directly under the root workflow steps list"
            )
            return
        if 'provider' not in step:
            self._add_error(f"{context} requires a provider step")
            return
        if 'retries' in step:
            self._add_error(f"{context} forbids retries")

        node = step.get('provider_session')
        if not isinstance(node, dict):
            self._add_error(f"{context} must be a dictionary")
            return

        mode = node.get('mode')
        if mode not in {'fresh', 'resume'}:
            self._add_error(f"{context}.mode must be 'fresh' or 'resume'")
            return

        provider_name = step.get('provider')
        if isinstance(provider_name, str) and "${" in provider_name:
            self._add_error(f"{context} requires a static provider template")
            return
        provider_template = self._provider_registry.get(provider_name) if isinstance(provider_name, str) else None
        if provider_template is None:
            self._add_error(f"{context} requires a known provider template")
            return
        if provider_template.session_support is None:
            self._add_error(f"{context} requires provider '{provider_name}' to declare session_support")
            return

        registry = artifacts_registry if isinstance(artifacts_registry, dict) else {}

        if mode == 'fresh':
            publish_artifact = node.get('publish_artifact')
            if not isinstance(publish_artifact, str) or not publish_artifact.strip():
                self._add_error(f"{context}.publish_artifact must be a non-empty string")
                return
            if 'session_id_from' in node:
                self._add_error(f"{context}.session_id_from is not allowed in fresh mode")
            if step.get('persist_artifacts_in_state') is False:
                self._add_error(f"{context} requires persist_artifacts_in_state to be true")
            self._validate_provider_session_artifact(registry, publish_artifact, context)
            self._validate_provider_session_publish_collisions(step, publish_artifact, context)
            return

        session_id_from = node.get('session_id_from')
        if not isinstance(session_id_from, str) or not session_id_from.strip():
            self._add_error(f"{context}.session_id_from must be a non-empty string")
            return
        if 'publish_artifact' in node:
            self._add_error(f"{context}.publish_artifact is not allowed in resume mode")
        if provider_template.session_support.resume_command is None:
            self._add_error(
                f"{context} requires provider '{provider_name}' to declare session_support.resume_command"
            )
        self._validate_provider_session_artifact(registry, session_id_from, context)

        consumes = step.get('consumes')
        matching_consumes = []
        if isinstance(consumes, list):
            matching_consumes = [
                consume for consume in consumes
                if isinstance(consume, dict) and consume.get('artifact') == session_id_from
            ]
        if len(matching_consumes) != 1:
            self._add_error(
                f"{context}.session_id_from must match exactly one consumes entry"
            )
        else:
            freshness = matching_consumes[0].get('freshness', 'any')
            if freshness == 'since_last_consume':
                self._add_error(
                    f"{context}.session_id_from consume must omit freshness or set freshness to 'any'"
                )

        prompt_consumes = step.get('prompt_consumes')
        if isinstance(prompt_consumes, list) and session_id_from in prompt_consumes:
            self._add_error(
                f"{context}.session_id_from consume cannot be re-included through prompt_consumes"
            )

        consume_bundle = step.get('consume_bundle')
        non_session_consumes = []
        if isinstance(consumes, list):
            non_session_consumes = [
                consume for consume in consumes
                if isinstance(consume, dict) and consume.get('artifact') != session_id_from
            ]
        if isinstance(consume_bundle, dict):
            include = consume_bundle.get('include')
            if isinstance(include, list) and session_id_from in include:
                self._add_error(
                    f"{context}.session_id_from consume cannot be re-included through consume_bundle.include"
                )
            if not non_session_consumes:
                self._add_error(
                    f"{context} requires at least one non-session consume when consume_bundle is declared"
                )

    def _validate_managed_jobs(self, step: Dict[str, Any], step_name: str, version: str) -> None:
        """Validate the step-local managed provider job contract."""
        context = f"Step '{step_name}': managed_jobs"
        if not self._version_at_least(version, "2.13"):
            self._add_error(f"{context} requires version '2.13'")
            return

        if 'adjudicated_provider' in step:
            self._add_error(f"{context} is invalid with adjudicated_provider")
            return
        if 'provider' not in step:
            self._add_error(f"{context} is valid only on provider steps")
            return
        if 'retries' in step:
            self._add_error(f"{context} cannot be combined with provider retries")
        if 'on' in step:
            self._add_error(f"{context} cannot be combined with ordinary on handlers")

        node = step.get('managed_jobs')
        if not isinstance(node, dict):
            self._add_error(f"{context} must be a dictionary")
            return

        policy = node.get('policy')
        if not isinstance(policy, str) or not policy.strip():
            self._add_error(f"{context}.policy is required")
        else:
            self._validate_path_safety(policy, f"{context}.policy")

        watch_roots = node.get('watch_roots')
        if not isinstance(watch_roots, list) or not watch_roots:
            self._add_error(f"{context}.watch_roots must be a non-empty list")
        elif isinstance(watch_roots, list):
            for index, watch_root in enumerate(watch_roots):
                item_context = f"{context}.watch_roots[{index}]"
                if not isinstance(watch_root, str) or not watch_root.strip():
                    self._add_error(f"{item_context} must be a non-empty string")
                    continue
                self._validate_path_safety(watch_root, item_context)

        backend = node.get('backend', 'auto')
        if backend not in {'auto', 'local', 'slurm'}:
            self._add_error(f"{context}.backend must be one of 'auto', 'local', or 'slurm'")

        poll_budget_sec = node.get('poll_budget_sec')
        if type(poll_budget_sec) is not int or poll_budget_sec <= 0:
            self._add_error(f"{context}.poll_budget_sec must be a positive integer")
        else:
            timeout_sec = step.get('timeout_sec')
            if isinstance(timeout_sec, (int, float)) and poll_budget_sec > timeout_sec:
                self._add_error(f"{context}.poll_budget_sec cannot exceed timeout_sec")

        routes = node.get('on')
        if not isinstance(routes, dict):
            self._add_error(f"{context}.on must be a dictionary")
            return
        for route_name in ('complete', 'failed', 'invalid', 'outstanding'):
            if route_name not in routes:
                self._add_error(f"{context}.on.{route_name} is required")
        for route_name in ('complete', 'failed', 'invalid'):
            if route_name not in routes:
                continue
            target = routes.get(route_name)
            if not isinstance(target, str) or not target.strip():
                self._add_error(f"{context}.on.{route_name} must be a non-empty step name")
        if 'outstanding' in routes and routes.get('outstanding') != 'fail_resumable':
            self._add_error(f"{context}.on.outstanding must be 'fail_resumable'")

    def _validate_provider_session_artifact(
        self,
        registry: Dict[str, Any],
        artifact_name: str,
        context: str,
    ) -> None:
        """Validate that one provider-session artifact is a declared string scalar."""
        artifact_spec = registry.get(artifact_name)
        if not isinstance(artifact_spec, dict):
            self._add_error(f"{context} references unknown artifact '{artifact_name}'")
            return
        if artifact_spec.get('kind') != 'scalar' or artifact_spec.get('type') != 'string':
            self._add_error(
                f"{context} artifact '{artifact_name}' must be declared as kind 'scalar' with type 'string'"
            )

    def _validate_provider_session_publish_collisions(
        self,
        step: Dict[str, Any],
        publish_artifact: str,
        context: str,
    ) -> None:
        """Reject authored surfaces that collide with a runtime-owned publish_artifact key."""
        expected_outputs = step.get('expected_outputs')
        if isinstance(expected_outputs, list):
            for spec in expected_outputs:
                if isinstance(spec, dict) and spec.get('name') == publish_artifact:
                    self._add_error(
                        f"{context}.publish_artifact '{publish_artifact}' collides with expected_outputs"
                    )

        output_bundle = step.get('output_bundle')
        if isinstance(output_bundle, dict):
            for spec in output_bundle.get('fields', []):
                if isinstance(spec, dict) and spec.get('name') == publish_artifact:
                    self._add_error(
                        f"{context}.publish_artifact '{publish_artifact}' collides with output_bundle.fields"
                    )

        publishes = step.get('publishes')
        if isinstance(publishes, list):
            for publish in publishes:
                if not isinstance(publish, dict):
                    continue
                if publish.get('artifact') == publish_artifact or publish.get('from') == publish_artifact:
                    self._add_error(
                        f"{context}.publish_artifact '{publish_artifact}' is runtime-owned and cannot be reused by publishes"
                    )

    def _validate_when_condition(
        self,
        when: Any,
        step_name: str,
        version: str,
        root_catalog: Dict[str, Any],
        scope_artifacts: Dict[str, Any],
        scope_multi_visit: Set[str],
        parent_artifacts: Optional[Dict[str, Any]],
        parent_multi_visit: Optional[Set[str]],
        scope_non_step_results: Set[str],
        parent_non_step_results: Optional[Set[str]],
    ):
        """Validate when condition structure."""
        if not isinstance(when, dict):
            self._add_error(f"Step '{step_name}': when must be a dictionary")
            return

        if self._is_typed_predicate_node(when):
            if not self._version_at_least(version, "1.6"):
                self._add_error(f"Step '{step_name}': typed predicates require version '1.6'")
                return
            self._validate_typed_predicate(
                when,
                step_name,
                version,
                root_catalog,
                scope_artifacts,
                scope_multi_visit,
                parent_artifacts,
                parent_multi_visit,
                scope_non_step_results,
                parent_non_step_results,
            )
            return

        condition_types = ['equals', 'exists', 'not_exists']
        present = [t for t in condition_types if t in when]

        if len(present) == 0:
            self._add_error(f"Step '{step_name}': when requires one of {condition_types}")
        elif len(present) > 1:
            self._add_error(f"Step '{step_name}': when can only have one condition type, found {present}")

    def _validate_assert_condition(
        self,
        assertion: Any,
        step_name: str,
        version: str,
        root_catalog: Dict[str, Any],
        scope_artifacts: Dict[str, Any],
        scope_multi_visit: Set[str],
        parent_artifacts: Optional[Dict[str, Any]],
        parent_multi_visit: Optional[Set[str]],
        scope_non_step_results: Set[str],
        parent_non_step_results: Optional[Set[str]],
    ) -> None:
        if not isinstance(assertion, dict):
            self._add_error(f"Step '{step_name}': assert must be a dictionary")
            return
        if self._is_typed_predicate_node(assertion):
            if not self._version_at_least(version, "1.6"):
                self._add_error(f"Step '{step_name}': typed assert predicates require version '1.6'")
                return
            self._validate_typed_predicate(
                assertion,
                step_name,
                version,
                root_catalog,
                scope_artifacts,
                scope_multi_visit,
                parent_artifacts,
                parent_multi_visit,
                scope_non_step_results,
                parent_non_step_results,
            )
            return

        condition_types = ['equals', 'exists', 'not_exists']
        present = [t for t in condition_types if t in assertion]
        if len(present) == 0:
            self._add_error(f"Step '{step_name}': assert requires one of {condition_types}")
        elif len(present) > 1:
            self._add_error(f"Step '{step_name}': assert can only have one condition type, found {present}")

    def _is_typed_predicate_node(self, node: Any) -> bool:
        return isinstance(node, dict) and any(
            key in node for key in TYPED_PREDICATE_OPERATOR_KEYS
        )

    def _version_at_least(self, version: str, minimum: str) -> bool:
        if version not in self.VERSION_ORDER or minimum not in self.VERSION_ORDER:
            return False
        return self.VERSION_ORDER.index(version) >= self.VERSION_ORDER.index(minimum)

    def _build_root_ref_catalog(
        self,
        steps: List[Any],
        artifacts_registry: Optional[Any] = None,
    ) -> Dict[str, Any]:
        artifact_map: Dict[str, Dict[str, Any]] = self._build_scope_artifact_catalog(steps, artifacts_registry)
        all_steps = self._collect_all_steps(steps)
        all_artifact_map = self._build_scope_artifact_catalog(all_steps, artifacts_registry)
        step_names: List[str] = []

        for step in steps:
            if not isinstance(step, dict):
                continue
            name = step.get('name')
            if not isinstance(name, str):
                continue
            step_names.append(name)

        edges: Dict[str, Set[str]] = {name: set() for name in step_names}
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                continue
            name = step.get('name')
            if not isinstance(name, str):
                continue

            if index + 1 < len(steps):
                next_name = steps[index + 1].get('name') if isinstance(steps[index + 1], dict) else None
                if isinstance(next_name, str):
                    edges[name].add(next_name)

            on = step.get('on')
            if isinstance(on, dict):
                for handler in ('success', 'failure', 'always'):
                    target = on.get(handler, {}).get('goto') if isinstance(on.get(handler), dict) else None
                    if isinstance(target, str) and target != '_end':
                        edges[name].add(target)

        return {
            'artifacts': artifact_map,
            'all_artifacts': all_artifact_map,
            'multi_visit': self._detect_multi_visit_steps(edges),
            'non_step_results': self._build_scope_non_step_result_targets(steps),
            'all_non_step_results': self._build_scope_non_step_result_targets(all_steps),
        }

    def _build_scope_artifact_catalog(
        self,
        steps: List[Any],
        artifacts_registry: Optional[Any] = None,
    ) -> Dict[str, Dict[str, Any]]:
        artifact_map: Dict[str, Dict[str, Any]] = {}
        registry = artifacts_registry if isinstance(artifacts_registry, dict) else {}

        for step in steps:
            if not isinstance(step, dict):
                continue
            name = step.get('name')
            if not isinstance(name, str):
                continue

            outputs: Dict[str, Any] = {}
            if is_if_statement(step):
                outputs = self._collect_if_statement_outputs(step)
                artifact_map[name] = outputs
                continue
            if is_match_statement(step):
                outputs = self._collect_match_statement_outputs(step)
                artifact_map[name] = outputs
                continue
            if is_repeat_until_statement(step):
                outputs = self._collect_repeat_until_outputs(step)
                artifact_map[name] = outputs
                continue

            expected_outputs = step.get('expected_outputs')
            if isinstance(expected_outputs, list):
                for spec in expected_outputs:
                    if isinstance(spec, dict):
                        artifact_name = spec.get('name')
                        if isinstance(artifact_name, str):
                            outputs[artifact_name] = self._normalize_output_contract_artifact_spec(
                                spec,
                                persisted=step.get('persist_artifacts_in_state', True) is not False,
                                owner_step_name=name,
                            )

            output_bundle = step.get('output_bundle')
            if isinstance(output_bundle, dict):
                for spec in output_bundle.get('fields', []):
                    if isinstance(spec, dict):
                        artifact_name = spec.get('name')
                        if isinstance(artifact_name, str):
                            outputs[artifact_name] = self._normalize_output_contract_artifact_spec(
                                spec,
                                persisted=step.get('persist_artifacts_in_state', True) is not False,
                                owner_step_name=name,
                            )

            variant_output = step.get('variant_output')
            if isinstance(variant_output, dict):
                discriminant = variant_output.get('discriminant')
                if isinstance(discriminant, dict):
                    artifact_name = discriminant.get('name')
                    if isinstance(artifact_name, str):
                        outputs[artifact_name] = {
                            **self._normalize_output_contract_artifact_spec(
                                discriminant,
                                persisted=step.get('persist_artifacts_in_state', True) is not False,
                            ),
                            'variant_owner_step': name,
                            'variant_role': 'discriminant',
                        }
                shared_fields = variant_output.get('shared_fields')
                if isinstance(shared_fields, list):
                    for spec in shared_fields:
                        if not isinstance(spec, dict):
                            continue
                        artifact_name = spec.get('name')
                        if isinstance(artifact_name, str):
                            outputs[artifact_name] = {
                                **self._normalize_output_contract_artifact_spec(
                                    spec,
                                    persisted=step.get('persist_artifacts_in_state', True) is not False,
                                ),
                                'variant_owner_step': name,
                                'variant_role': 'shared',
                            }
                variants = variant_output.get('variants')
                if isinstance(variants, dict):
                    for variant_name, variant_spec in variants.items():
                        if not isinstance(variant_spec, dict):
                            continue
                        fields = variant_spec.get('fields')
                        if not isinstance(fields, list):
                            continue
                        for spec in fields:
                            if not isinstance(spec, dict):
                                continue
                            artifact_name = spec.get('name')
                            if isinstance(artifact_name, str):
                                outputs[artifact_name] = {
                                    **self._normalize_output_contract_artifact_spec(
                                        spec,
                                        persisted=step.get('persist_artifacts_in_state', True) is not False,
                                    ),
                                    'variant_owner_step': name,
                                    'variant_role': 'field',
                                    'variant_required': variant_name,
                                }
            select_variant_output = step.get('select_variant_output')
            if isinstance(select_variant_output, dict):
                discriminant = select_variant_output.get('discriminant')
                if isinstance(discriminant, dict):
                    artifact_name = discriminant.get('name')
                    if isinstance(artifact_name, str):
                        outputs[artifact_name] = {
                            **self._normalize_output_contract_artifact_spec(
                                discriminant,
                                persisted=step.get('persist_artifacts_in_state', True) is not False,
                            ),
                            'variant_owner_step': name,
                            'variant_role': 'discriminant',
                        }
                variants = select_variant_output.get('variants')
                if isinstance(variants, dict):
                    for variant_name, variant_spec in variants.items():
                        if not isinstance(variant_spec, dict):
                            continue
                        fields = variant_spec.get('fields')
                        if not isinstance(fields, list):
                            continue
                        for spec in fields:
                            if not isinstance(spec, dict):
                                continue
                            artifact_name = spec.get('name')
                            if isinstance(artifact_name, str):
                                outputs[artifact_name] = {
                                    **self._normalize_output_contract_artifact_spec(
                                        spec,
                                        persisted=step.get('persist_artifacts_in_state', True) is not False,
                                    ),
                                    'variant_owner_step': name,
                                    'variant_role': 'field',
                                    'variant_required': variant_name,
                                }

            materialize_artifacts = step.get('materialize_artifacts')
            if isinstance(materialize_artifacts, dict):
                values = materialize_artifacts.get('values')
                if isinstance(values, list):
                    for spec in values:
                        if not isinstance(spec, dict):
                            continue
                        artifact_name = spec.get('name')
                        contract = self._resolve_materialize_catalog_contract(
                            spec,
                            artifact_map=artifact_map,
                        )
                        if isinstance(artifact_name, str) and isinstance(contract, dict):
                            outputs[artifact_name] = {
                                'type': contract.get('type'),
                                'persisted': step.get('persist_artifacts_in_state', True) is not False,
                                'allowed': deepcopy(contract.get('allowed')) if isinstance(contract.get('allowed'), list) else None,
                            }

            materialize_view = step.get('materialize_view')
            if isinstance(materialize_view, dict):
                output_contracts = materialize_view.get('output_contracts')
                if isinstance(output_contracts, dict):
                    for artifact_name, spec in output_contracts.items():
                        if not isinstance(artifact_name, str) or not isinstance(spec, dict):
                            continue
                        outputs[artifact_name] = self._normalize_output_contract_artifact_spec(
                            spec,
                            persisted=step.get('persist_artifacts_in_state', True) is not False,
                            owner_step_name=name,
                        )

            for field_name in ('set_scalar', 'increment_scalar'):
                node = step.get(field_name)
                if not isinstance(node, dict):
                    continue
                artifact_name = node.get('artifact')
                artifact_spec = registry.get(artifact_name) if isinstance(artifact_name, str) else None
                artifact_type = artifact_spec.get('type') if isinstance(artifact_spec, dict) else None
                if isinstance(artifact_name, str) and isinstance(artifact_type, str):
                    outputs[artifact_name] = {
                        'type': artifact_type,
                        'persisted': True,
                        'allowed': deepcopy(artifact_spec.get('allowed')) if isinstance(artifact_spec.get('allowed'), list) else None,
                    }

            provider_session = step.get('provider_session')
            if isinstance(provider_session, dict) and provider_session.get('mode') == 'fresh':
                artifact_name = provider_session.get('publish_artifact')
                if isinstance(artifact_name, str):
                    outputs[artifact_name] = {
                        'type': 'string',
                        'persisted': step.get('persist_artifacts_in_state', True) is not False,
                        'allowed': None,
                    }

            if 'call' in step:
                imported_workflow = self._current_imports.get(step.get('call'))
                if not isinstance(imported_workflow, LoadedWorkflowBundle):
                    continue
                imported_outputs = workflow_output_contracts(imported_workflow)
                if isinstance(imported_outputs, Mapping):
                    for artifact_name, output_spec in imported_outputs.items():
                        if not isinstance(artifact_name, str) or not isinstance(output_spec, Mapping):
                            continue
                        outputs[artifact_name] = self._normalize_output_contract_artifact_spec(
                            output_spec,
                            persisted=True,
                            owner_step_name=name,
                        )

            artifact_map[name] = outputs

        return artifact_map

    def _resolve_materialize_catalog_contract(
        self,
        spec: Dict[str, Any],
        *,
        artifact_map: Dict[str, Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Resolve materialize_artifacts contract metadata for authored-shape catalogs."""
        contract = spec.get("contract")
        if isinstance(contract, dict) and isinstance(contract.get("type"), str):
            return contract

        if not (isinstance(contract, dict) and contract.get("inherit") == "source"):
            return contract if isinstance(contract, dict) else None

        source = spec.get("source")
        if not isinstance(source, dict):
            return None

        if "input" in source and isinstance(source.get("input"), str):
            input_spec = self._workflow_input_specs.get(source["input"])
            return input_spec if isinstance(input_spec, dict) else None

        if source.get("runtime") == "now_ns":
            return {"kind": "scalar", "type": "integer"}

        if "ref" in source and isinstance(source.get("ref"), str) and ".artifacts." in source["ref"]:
            try:
                target = parse_structured_ref(source["ref"], artifact_map.keys())
            except ReferenceResolutionError:
                return None
            step_artifacts = artifact_map.get(target.step_name)
            if not isinstance(step_artifacts, dict) or not isinstance(target.member, str):
                return None
            resolved = step_artifacts.get(target.member)
            return resolved if isinstance(resolved, dict) else None

        return None

    def _collect_if_statement_outputs(self, step: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Collect block outputs exposed by a structured if/else statement."""
        outputs: Dict[str, Dict[str, Any]] = {}
        then_block = normalize_branch_block(step.get('then'), 'then')
        if then_block is None:
            return outputs

        then_outputs = then_block.get('outputs')
        if not isinstance(then_outputs, dict):
            return outputs

        for output_name, spec in then_outputs.items():
            if not isinstance(output_name, str) or not isinstance(spec, dict):
                continue
            outputs[output_name] = self._normalize_output_contract_artifact_spec(
                spec,
                persisted=True,
                owner_step_name=step.get('name') if isinstance(step.get('name'), str) else None,
            )
        return outputs

    def _collect_match_statement_outputs(self, step: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Collect block outputs exposed by a structured match statement."""
        match = step.get('match')
        cases = match.get('cases') if isinstance(match, dict) else None
        if not isinstance(cases, dict):
            return {}

        for case_name, authored_case in cases.items():
            case_block = normalize_match_case_block(authored_case, str(case_name))
            if not isinstance(case_block, dict):
                continue
            outputs = case_block.get('outputs')
            if not isinstance(outputs, dict):
                continue
            collected: Dict[str, Dict[str, Any]] = {}
            for output_name, spec in outputs.items():
                if not isinstance(output_name, str) or not isinstance(spec, dict):
                    continue
                collected[output_name] = self._normalize_output_contract_artifact_spec(
                    spec,
                    persisted=True,
                    owner_step_name=step.get('name') if isinstance(step.get('name'), str) else None,
                )
            return collected

        return {}

    def _collect_repeat_until_outputs(self, step: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Collect loop-frame outputs exposed by a repeat_until statement."""
        block = normalize_repeat_until_block(step.get('repeat_until'))
        if not isinstance(block, dict):
            return {}

        outputs = block.get('outputs')
        if not isinstance(outputs, dict):
            return {}

        collected: Dict[str, Dict[str, Any]] = {}
        for output_name, spec in outputs.items():
            if not isinstance(output_name, str) or not isinstance(spec, dict):
                continue
            collected[output_name] = self._normalize_output_contract_artifact_spec(
                spec,
                persisted=True,
                owner_step_name=step.get('name') if isinstance(step.get('name'), str) else None,
            )
        return collected

    def _normalize_output_contract_artifact_spec(
        self,
        spec: Dict[str, Any],
        *,
        persisted: bool,
        owner_step_name: str | None = None,
    ) -> Dict[str, Any]:
        """Project one output contract into structured-ref metadata."""
        normalized = {
            'type': spec.get('type'),
            'persisted': persisted,
            'allowed': deepcopy(spec.get('allowed')) if isinstance(spec.get('allowed'), list) else None,
        }
        projection = spec.get('projection')
        if (
            owner_step_name is not None
            and isinstance(projection, dict)
            and projection.get('projection_class') == 'union_workflow_boundary'
        ):
            field_role = projection.get('field_role')
            active_variants = projection.get('active_variants')
            if field_role == 'discriminant':
                normalized['variant_owner_step'] = owner_step_name
                normalized['variant_role'] = 'discriminant'
            elif field_role == 'shared':
                normalized['variant_owner_step'] = owner_step_name
                normalized['variant_role'] = 'shared'
            elif field_role == 'variant':
                normalized['variant_owner_step'] = owner_step_name
                normalized['variant_role'] = 'field'
                if (
                    isinstance(active_variants, list)
                    and len(active_variants) == 1
                    and isinstance(active_variants[0], str)
                ):
                    normalized['variant_required'] = active_variants[0]
        return normalized

    def _build_scope_non_step_result_targets(self, steps: List[Any]) -> Set[str]:
        non_step_results: Set[str] = set()

        for step in steps:
            if not isinstance(step, dict):
                continue
            name = step.get('name')
            if isinstance(name, str) and 'for_each' in step:
                non_step_results.add(name)

        return non_step_results

    def _detect_multi_visit_steps(self, edges: Dict[str, Set[str]]) -> Set[str]:
        index = 0
        indices: Dict[str, int] = {}
        lowlinks: Dict[str, int] = {}
        stack: List[str] = []
        on_stack: Set[str] = set()
        multi_visit: Set[str] = set()

        def strongconnect(node: str) -> None:
            nonlocal index
            indices[node] = index
            lowlinks[node] = index
            index += 1
            stack.append(node)
            on_stack.add(node)

            for neighbor in edges.get(node, set()):
                if neighbor not in edges:
                    continue
                if neighbor not in indices:
                    strongconnect(neighbor)
                    lowlinks[node] = min(lowlinks[node], lowlinks[neighbor])
                elif neighbor in on_stack:
                    lowlinks[node] = min(lowlinks[node], indices[neighbor])

            if lowlinks[node] != indices[node]:
                return

            component: List[str] = []
            while stack:
                current = stack.pop()
                on_stack.remove(current)
                component.append(current)
                if current == node:
                    break

            if len(component) > 1:
                multi_visit.update(component)
            elif component and component[0] in edges.get(component[0], set()):
                multi_visit.add(component[0])

        for node in edges:
            if node not in indices:
                strongconnect(node)

        return multi_visit

    def _validate_typed_predicate(
        self,
        predicate: Any,
        step_name: str,
        version: str,
        root_catalog: Dict[str, Any],
        scope_artifacts: Dict[str, Any],
        scope_multi_visit: Set[str],
        parent_artifacts: Optional[Dict[str, Any]],
        parent_multi_visit: Optional[Set[str]],
        scope_non_step_results: Set[str],
        parent_non_step_results: Optional[Set[str]],
    ) -> None:
        if not isinstance(predicate, dict):
            self._add_error(f"Step '{step_name}': typed predicate must be a dictionary")
            return

        present_keys = typed_predicate_operator_keys(predicate)
        if len(present_keys) != 1:
            self._add_error(
                f"Step '{step_name}': typed predicate nodes must declare exactly one typed predicate operator"
            )
            return

        if 'artifact_bool' in predicate:
            node = predicate['artifact_bool']
            if not isinstance(node, dict):
                self._add_error(f"Step '{step_name}': artifact_bool must be a dictionary")
                return
            ref_type = self._validate_structured_ref(
                node.get('ref'),
                step_name,
                version,
                root_catalog,
                scope_artifacts,
                scope_multi_visit,
                parent_artifacts,
                parent_multi_visit,
                scope_non_step_results,
                parent_non_step_results,
            )
            if ref_type != 'bool':
                self._add_error(f"Step '{step_name}': artifact_bool requires a bool artifact ref")
            return

        if 'compare' in predicate:
            node = predicate['compare']
            if not isinstance(node, dict):
                self._add_error(f"Step '{step_name}': compare must be a dictionary")
                return
            left_type = self._validate_compare_operand(
                node.get('left'),
                step_name,
                version,
                root_catalog,
                scope_artifacts,
                scope_multi_visit,
                parent_artifacts,
                parent_multi_visit,
                scope_non_step_results,
                parent_non_step_results,
            )
            right_type = self._validate_compare_operand(
                node.get('right'),
                step_name,
                version,
                root_catalog,
                scope_artifacts,
                scope_multi_visit,
                parent_artifacts,
                parent_multi_visit,
                scope_non_step_results,
                parent_non_step_results,
            )
            op = node.get('op')
            if op not in {'eq', 'ne', 'lt', 'lte', 'gt', 'gte'}:
                self._add_error(f"Step '{step_name}': compare.op must be one of eq|ne|lt|lte|gt|gte")
                return
            if op in {'lt', 'lte', 'gt', 'gte'} and (
                left_type not in {'integer', 'float'} or right_type not in {'integer', 'float'}
            ):
                self._add_error(
                    f"Step '{step_name}': ordered compare operators require numeric operands"
                )
            return

        if 'score' in predicate:
            if not self._version_at_least(version, "2.8"):
                self._add_error(f"Step '{step_name}': score predicates require version '2.8'")
                return

            node = predicate['score']
            if not isinstance(node, dict):
                self._add_error(f"Step '{step_name}': score must be a dictionary")
                return

            allowed_keys = {'ref', *SCORE_PREDICATE_BOUND_KEYS}
            unexpected_keys = sorted(set(node.keys()) - allowed_keys)
            if unexpected_keys:
                joined = ", ".join(unexpected_keys)
                self._add_error(
                    f"Step '{step_name}': score only supports ref, gt, gte, lt, and lte (unexpected: {joined})"
                )

            ref_type = self._validate_structured_ref(
                node.get('ref'),
                step_name,
                version,
                root_catalog,
                scope_artifacts,
                scope_multi_visit,
                parent_artifacts,
                parent_multi_visit,
                scope_non_step_results,
                parent_non_step_results,
            )
            if ref_type not in {'integer', 'float'}:
                self._add_error(f"Step '{step_name}': score requires a numeric ref")

            bounds = {key: node.get(key) for key in SCORE_PREDICATE_BOUND_KEYS if key in node}
            if not bounds:
                self._add_error(f"Step '{step_name}': score requires at least one bound")
                return

            if 'gt' in node and 'gte' in node:
                self._add_error(f"Step '{step_name}': score cannot declare both gt and gte")
            if 'lt' in node and 'lte' in node:
                self._add_error(f"Step '{step_name}': score cannot declare both lt and lte")

            for key, value in bounds.items():
                if not is_numeric_predicate_value(value):
                    self._add_error(f"Step '{step_name}': score bound '{key}' must be numeric")

            self._validate_score_predicate_bounds(node, step_name)
            return

        if 'all_of' in predicate:
            items = predicate['all_of']
            if not isinstance(items, list) or not items:
                self._add_error(f"Step '{step_name}': all_of must be a non-empty list")
                return
            for item in items:
                self._validate_typed_predicate(
                    item,
                    step_name,
                    version,
                    root_catalog,
                    scope_artifacts,
                    scope_multi_visit,
                    parent_artifacts,
                    parent_multi_visit,
                    scope_non_step_results,
                    parent_non_step_results,
                )
            return

        if 'any_of' in predicate:
            items = predicate['any_of']
            if not isinstance(items, list) or not items:
                self._add_error(f"Step '{step_name}': any_of must be a non-empty list")
                return
            for item in items:
                self._validate_typed_predicate(
                    item,
                    step_name,
                    version,
                    root_catalog,
                    scope_artifacts,
                    scope_multi_visit,
                    parent_artifacts,
                    parent_multi_visit,
                    scope_non_step_results,
                    parent_non_step_results,
                )
            return

        if 'not' in predicate:
            self._validate_typed_predicate(
                predicate['not'],
                step_name,
                version,
                root_catalog,
                scope_artifacts,
                scope_multi_visit,
                parent_artifacts,
                parent_multi_visit,
                scope_non_step_results,
                parent_non_step_results,
            )
            return

        self._add_error(f"Step '{step_name}': unsupported typed predicate")

    def _validate_compare_operand(
        self,
        operand: Any,
        step_name: str,
        version: str,
        root_catalog: Dict[str, Any],
        scope_artifacts: Dict[str, Any],
        scope_multi_visit: Set[str],
        parent_artifacts: Optional[Dict[str, Any]],
        parent_multi_visit: Optional[Set[str]],
        scope_non_step_results: Set[str],
        parent_non_step_results: Optional[Set[str]],
    ) -> str:
        if isinstance(operand, dict):
            if set(operand.keys()) != {'ref'}:
                self._add_error(f"Step '{step_name}': compare operands must be literals or {{ref: ...}}")
                return 'unknown'
            return self._validate_structured_ref(
                operand.get('ref'),
                step_name,
                version,
                root_catalog,
                scope_artifacts,
                scope_multi_visit,
                parent_artifacts,
                parent_multi_visit,
                scope_non_step_results,
                parent_non_step_results,
            )
        if isinstance(operand, bool):
            return 'bool'
        if type(operand) is int:
            return 'integer'
        if isinstance(operand, float):
            return 'float'
        if isinstance(operand, str):
            return 'string'
        self._add_error(
            f"Step '{step_name}': unsupported compare operand type '{type(operand).__name__}'"
        )
        return 'unknown'

    def _validate_score_predicate_bounds(self, node: Dict[str, Any], step_name: str) -> None:
        lower_bound = None
        upper_bound = None

        for key in ('gt', 'gte'):
            value = node.get(key)
            if is_numeric_predicate_value(value):
                lower_bound = (key, value)
                break

        for key in ('lt', 'lte'):
            value = node.get(key)
            if is_numeric_predicate_value(value):
                upper_bound = (key, value)
                break

        if lower_bound is None or upper_bound is None:
            return

        lower_key, lower_value = lower_bound
        upper_key, upper_value = upper_bound
        if lower_value > upper_value:
            self._add_error(f"Step '{step_name}': score bounds describe an empty range")
            return
        if lower_value == upper_value and (lower_key == 'gt' or upper_key == 'lt'):
            self._add_error(f"Step '{step_name}': score bounds describe an empty range")

    def _supported_output_types(self, version: str) -> Set[str]:
        """Return the output contract types available at one DSL version."""
        supported_types = set(self.SUPPORTED_OUTPUT_TYPES)
        if not self._version_at_least(version, self.STRING_CONTRACT_VERSION):
            supported_types.discard("string")
        if self._allow_private_collection_output_schemas and self._version_at_least(version, "2.14"):
            supported_types.update(self.PRIVATE_COLLECTION_OUTPUT_TYPES)
        if self._version_at_least(version, "2.15"):
            supported_types.update(self.PRIVATE_COLLECTION_OUTPUT_TYPES)
        return supported_types

    def _supported_scalar_types(self, version: str) -> Set[str]:
        """Return the scalar contract types available at one DSL version."""
        scalar_types = {"enum", "integer", "float", "bool"}
        if self._version_at_least(version, self.STRING_CONTRACT_VERSION):
            scalar_types.add("string")
        return scalar_types

    def _supported_expected_output_types(self, version: str) -> Set[str]:
        """Return types supported by the legacy file-backed result channel."""
        return self._supported_output_types(version) - self.PRIVATE_COLLECTION_OUTPUT_TYPES

    def _scalar_type_list(self, version: str) -> str:
        """Render a deterministic scalar-type list for validation errors."""
        order = ("enum", "integer", "float", "bool", "string")
        return "|".join(type_name for type_name in order if type_name in self._supported_scalar_types(version))

    def _validate_structured_ref(
        self,
        ref: Any,
        step_name: str,
        version: str,
        root_catalog: Dict[str, Any],
        scope_artifacts: Dict[str, Any],
        scope_multi_visit: Set[str],
        parent_artifacts: Optional[Dict[str, Any]],
        parent_multi_visit: Optional[Set[str]],
        scope_non_step_results: Set[str],
        parent_non_step_results: Optional[Set[str]],
        proof_context: Optional[Dict[str, str]] = None,
        allow_snapshot_ref: bool = False,
    ) -> str:
        contract = self._resolve_structured_ref_contract(
            ref,
            step_name,
            version,
            root_catalog,
            scope_artifacts,
            scope_multi_visit,
            parent_artifacts,
            parent_multi_visit,
            scope_non_step_results,
            parent_non_step_results,
            proof_context=proof_context,
            allow_snapshot_ref=allow_snapshot_ref,
        )
        if not isinstance(contract, dict):
            return 'unknown'
        return contract.get('type', 'unknown')

    def _resolve_structured_ref_contract(
        self,
        ref: Any,
        step_name: str,
        version: str,
        root_catalog: Dict[str, Any],
        scope_artifacts: Dict[str, Any],
        scope_multi_visit: Set[str],
        parent_artifacts: Optional[Dict[str, Any]],
        parent_multi_visit: Optional[Set[str]],
        scope_non_step_results: Set[str],
        parent_non_step_results: Optional[Set[str]],
        proof_context: Optional[Dict[str, str]] = None,
        allow_snapshot_ref: bool = False,
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(ref, str) or not ref:
            self._add_error(f"Step '{step_name}': structured refs must be non-empty strings")
            return None
        if ref.startswith('inputs.'):
            if not self._version_at_least(version, WORKFLOW_SIGNATURE_VERSION):
                self._add_error(
                    f"Step '{step_name}': inputs refs are not available before workflow signatures land"
                )
                return None
            input_name = ref[len('inputs.'):]
            if not input_name:
                self._add_error(f"Step '{step_name}': invalid structured ref '{ref}'")
                return None
            spec = self._workflow_input_specs.get(input_name)
            if not isinstance(spec, dict):
                self._add_error(
                    f"Step '{step_name}': structured ref '{ref}' targets unknown input '{input_name}'"
                )
                return None
            return {
                'type': spec.get('type', 'unknown'),
                'allowed': deepcopy(spec.get('allowed')) if isinstance(spec.get('allowed'), list) else None,
            }
        if ref.startswith('steps.'):
            self._add_error(
                f"Step '{step_name}': bare 'steps.' refs are invalid in structured predicates"
            )
            return None
        if ref.startswith('context.'):
            self._add_error(f"Step '{step_name}': structured refs cannot read untyped context values")
            return None

        scope_name = ref.split('.', 1)[0]
        resolved_scope_name = scope_name
        if self._version_at_least(version, "2.0"):
            if scope_name == 'root':
                if not ref.startswith('root.steps.'):
                    self._add_error(f"Step '{step_name}': invalid structured ref '{ref}'")
                    return None
                artifacts_catalog = root_catalog.get('artifacts', {})
            elif scope_name == 'self':
                if not ref.startswith('self.steps.'):
                    self._add_error(f"Step '{step_name}': invalid structured ref '{ref}'")
                    return None
                artifacts_catalog = scope_artifacts
            elif scope_name == 'parent':
                if not ref.startswith('parent.steps.'):
                    self._add_error(f"Step '{step_name}': invalid structured ref '{ref}'")
                    return None
                if parent_artifacts is None:
                    self._add_error(f"Step '{step_name}': parent refs are unavailable in the root scope")
                    return None
                artifacts_catalog = parent_artifacts
            else:
                self._add_error(
                    f"Step '{step_name}': structured refs must start with root.steps., self.steps., or parent.steps."
                )
                return None
        else:
            if ref.startswith('self.') or ref.startswith('parent.'):
                scope = ref.split('.', 1)[0]
                self._add_error(
                    f"Step '{step_name}': {scope}. refs are not available before scoped refs land"
                )
                return None
            if not ref.startswith('root.steps.'):
                self._add_error(f"Step '{step_name}': structured refs must start with 'root.steps.'")
                return None
            artifacts_catalog = root_catalog.get('artifacts', {})

        try:
            parsed_ref = parse_structured_ref(ref, artifacts_catalog.keys())
        except ReferenceResolutionError:
            self._add_error(f"Step '{step_name}': invalid structured ref '{ref}'")
            return None

        target_step = parsed_ref.step_name
        if (
            scope_name == 'parent'
            and target_step not in artifacts_catalog
            and self._boundary_validation_policy is WorkflowBoundaryValidationPolicy.DEDICATED_RUNTIME_PROOF
            and (step_name, ref) in self._dedicated_runtime_proof_parent_ref_allowances
        ):
            nested_artifacts = root_catalog.get('all_artifacts', {})
            if isinstance(nested_artifacts, dict) and target_step in nested_artifacts:
                artifacts_catalog = nested_artifacts
                resolved_scope_name = 'all'

        if resolved_scope_name == 'root':
            multi_visit = root_catalog.get('multi_visit', set())
            non_step_results = root_catalog.get('non_step_results', set())
        elif resolved_scope_name == 'parent':
            multi_visit = parent_multi_visit or set()
            non_step_results = parent_non_step_results or set()
        elif resolved_scope_name == 'all':
            multi_visit = (
                root_catalog.get('multi_visit', set())
                | (parent_multi_visit or set())
                | scope_multi_visit
            )
            non_step_results = root_catalog.get('all_non_step_results', set())
        else:
            multi_visit = scope_multi_visit
            non_step_results = scope_non_step_results

        if target_step in non_step_results:
            self._add_error(
                f"Step '{step_name}': structured ref '{ref}' targets for_each summary step '{target_step}', which does not expose step-result fields"
            )
            return None

        if target_step in multi_visit:
            self._add_error(
                f"Step '{step_name}': structured ref '{ref}' targets multi-visit step '{target_step}'"
            )
            return None

        if target_step not in artifacts_catalog:
            self._add_error(
                f"Step '{step_name}': structured ref '{ref}' targets unknown step '{target_step}'"
            )
            return None

        if parsed_ref.field == 'exit_code':
            return {'type': 'integer'}
        if parsed_ref.field == 'outcome':
            outcome_types = {
                'status': 'string',
                'phase': 'string',
                'class': 'string',
                'retryable': 'bool',
            }
            outcome_type = outcome_types.get(parsed_ref.member)
            if outcome_type is None:
                self._add_error(
                    f"Step '{step_name}': structured ref '{ref}' targets invalid outcome field '{parsed_ref.member}'"
                )
                return None
            return {'type': outcome_type}
        if parsed_ref.field == 'artifacts':
            artifact_name = parsed_ref.member
            artifacts = artifacts_catalog.get(target_step, {})
            artifact_spec = artifacts.get(artifact_name)
            if artifact_spec is None:
                self._add_error(f"Step '{step_name}': structured ref '{ref}' targets unknown artifact")
                return None
            if not artifact_spec.get('persisted', True):
                self._add_error(
                    f"Step '{step_name}': structured ref '{ref}' targets a non-persisted artifact"
                )
                return None
            required_variant = artifact_spec.get('variant_required') if isinstance(artifact_spec, dict) else None
            if isinstance(required_variant, str) and proof_context is not None:
                variant_owner = artifact_spec.get('variant_owner_step', target_step)
                proven_variant = proof_context.get(variant_owner)
                if proven_variant != required_variant:
                    if proven_variant is None:
                        self._add_error(
                            f"Step '{step_name}': structured ref '{ref}' targets variant-specific artifact '{artifact_name}' without required author-time variant proof"
                        )
                    else:
                        self._add_error(
                            f"Step '{step_name}': structured ref '{ref}' requires variant proof '{required_variant}' but active proof is '{proven_variant}'"
                        )
                    return None
            return artifact_spec
        if parsed_ref.field == 'snapshots':
            if not allow_snapshot_ref:
                self._add_error(
                    f"Step '{step_name}': structured ref '{ref}' targets a snapshot; snapshot refs are only allowed in select_variant_output.evidence.snapshot.ref"
                )
                return None
            return {'type': 'snapshot'}

        self._add_error(f"Step '{step_name}': invalid structured ref '{ref}'")
        return None

    def _validate_on_handlers(self, on: Any, step_name: str):
        """Validate on success/failure/always handlers."""
        if not isinstance(on, dict):
            self._add_error(f"Step '{step_name}': on must be a dictionary")
            return

        valid_handlers = ['success', 'failure', 'always']
        for handler in on.keys():
            if handler not in valid_handlers:
                self._add_error(f"Step '{step_name}': unknown on handler '{handler}'")

    def _validate_goto_targets(self, workflow: Dict[str, Any]):
        """Validate that all goto targets exist (AT-55 in spec)."""
        # Collect all step names
        step_names = set()
        self._collect_step_names(workflow.get('steps', []), step_names)
        step_names.add('_end')  # Reserved target

        # Check all goto references
        self._check_goto_references(workflow.get('steps', []), step_names)

    def _collect_step_names(self, steps: List[Any], names: Set[str]):
        """Recursively collect all step names."""
        for step in steps:
            if isinstance(step, dict):
                if 'name' in step:
                    names.add(step['name'])
                if 'for_each' in step and 'steps' in step['for_each']:
                    self._collect_step_names(step['for_each']['steps'], names)

    def _check_goto_references(self, steps: List[Any], valid_names: Set[str]):
        """Check that all goto references are valid."""
        for step in steps:
            if not isinstance(step, dict):
                continue

            name = step.get('name', '<unnamed>')

            if 'on' in step and isinstance(step['on'], dict):
                for handler in ['success', 'failure', 'always']:
                    if handler in step['on'] and 'goto' in step['on'][handler]:
                        target = step['on'][handler]['goto']
                        if target not in valid_names:
                            self._add_error(f"Step '{name}' on.{handler}.goto references unknown target '{target}'")

            managed_jobs = step.get('managed_jobs')
            if isinstance(managed_jobs, dict):
                routes = managed_jobs.get('on')
                if isinstance(routes, dict):
                    for handler in ['complete', 'failed', 'invalid']:
                        target = routes.get(handler)
                        if isinstance(target, str) and target not in valid_names:
                            self._add_error(
                                f"Step '{name}' managed_jobs.on.{handler} references unknown target '{target}'"
                            )

            if 'for_each' in step and 'steps' in step['for_each']:
                self._check_goto_references(step['for_each']['steps'], valid_names)

    def _validate_path_safety(
        self,
        path: str,
        context: str,
        *,
        subject_refs: tuple[ValidationSubjectRef, ...] = (),
    ):
        """Validate path safety (AT-38, AT-39)."""
        # Skip variable placeholders for now (validated at runtime)
        if '${' in path:
            return

        # Reject absolute paths
        if Path(path).is_absolute():
            self._add_error(f"{context}: absolute paths not allowed", subject_refs=subject_refs)

        # Reject parent directory traversal
        if '..' in Path(path).parts:
            self._add_error(
                f"{context}: parent directory traversal ('..') not allowed",
                subject_refs=subject_refs,
            )

    def _validate_artifacts_registry(self, artifacts: Any, version: str):
        """Validate top-level artifacts registry (v1.2)."""
        if not isinstance(artifacts, dict):
            self._add_error("'artifacts' must be a dictionary")
            return

        for artifact_name, spec in artifacts.items():
            context = f"artifacts.{artifact_name}"
            if not isinstance(artifact_name, str) or not artifact_name.strip():
                self._add_error(f"{context}: artifact name must be a non-empty string")
                continue

            if not isinstance(spec, dict):
                self._add_error(f"{context} must be a dictionary")
                continue

            kind = spec.get('kind', 'relpath')
            if not isinstance(kind, str):
                self._add_error(f"{context} 'kind' must be a string")
                kind = 'relpath'
            elif kind not in {'relpath', 'scalar', 'collection'}:
                self._add_error(f"{context} invalid kind '{kind}'")

            output_type = spec.get('type')
            if output_type is None:
                self._add_error(f"{context} missing required 'type'")
            elif not isinstance(output_type, str):
                self._add_error(f"{context} 'type' must be a string")
            elif output_type not in self._supported_output_types(version):
                self._add_error(f"{context} invalid type '{output_type}'")

            if kind == 'relpath':
                pointer = spec.get('pointer')
                if pointer is None:
                    self._add_error(f"{context}: kind 'relpath' requires 'pointer'")
                elif not isinstance(pointer, str):
                    self._add_error(f"{context} 'pointer' must be a string")
                else:
                    self._validate_path_safety(pointer, f"{context}.pointer")

                if output_type is not None and output_type != 'relpath':
                    self._add_error(f"{context}: kind 'relpath' requires type 'relpath'")

                if 'under' in spec:
                    if not isinstance(spec['under'], str):
                        self._add_error(f"{context} 'under' must be a string")
                    else:
                        self._validate_path_safety(spec['under'], f"{context}.under")

                if 'must_exist_target' in spec and not isinstance(spec['must_exist_target'], bool):
                    self._add_error(f"{context} 'must_exist_target' must be a boolean")

            elif kind == 'scalar':
                if output_type not in self._supported_scalar_types(version):
                    self._add_error(
                        f"{context}: kind 'scalar' requires type one of {self._scalar_type_list(version)}"
                    )
                if 'pointer' in spec:
                    self._add_error(f"{context}: kind 'scalar' forbids 'pointer'")
                if 'under' in spec:
                    self._add_error(f"{context}: kind 'scalar' forbids 'under'")
                if 'must_exist_target' in spec:
                    self._add_error(f"{context}: kind 'scalar' forbids 'must_exist_target'")
                for field_name in ('item', 'items', 'keys', 'values'):
                    if field_name in spec:
                        self._add_error(f"{context}: kind 'scalar' forbids '{field_name}'")

            elif kind == 'collection':
                if output_type not in self.PRIVATE_COLLECTION_OUTPUT_TYPES:
                    self._add_error(f"{context}: kind 'collection' requires type one of optional|list|map")
                elif not (
                    self._allow_private_collection_output_schemas
                    and self._version_at_least(version, "2.14")
                ):
                    self._add_error(
                        f"{context}: kind 'collection' is only available for frontend-lowered workflows"
                    )
                if 'pointer' in spec:
                    self._add_error(f"{context}: kind 'collection' forbids 'pointer'")
                if 'under' in spec:
                    self._add_error(f"{context}: kind 'collection' forbids 'under'")
                if 'must_exist_target' in spec:
                    self._add_error(f"{context}: kind 'collection' forbids 'must_exist_target'")
                self._validate_output_schema_spec(
                    spec,
                    field_context=context,
                    version=version,
                    kind_label="artifact",
                    allow_guidance_keys=True,
                )

            if output_type == 'enum' and 'allowed' not in spec:
                self._add_error(f"{context} enum type requires 'allowed'")
            if 'allowed' in spec and not isinstance(spec['allowed'], list):
                self._add_error(f"{context} 'allowed' must be a list")

    def _validate_publishes(self, publishes: Any, step_name: str):
        """Validate step publishes list (v1.2)."""
        if not isinstance(publishes, list):
            self._add_error(f"Step '{step_name}': publishes must be a list")
            return

        for i, entry in enumerate(publishes):
            context = f"Step '{step_name}': publishes[{i}]"
            if not isinstance(entry, dict):
                self._add_error(f"{context} must be a dictionary")
                continue

            artifact = entry.get('artifact')
            if artifact is None:
                self._add_error(f"{context} missing required 'artifact'")
            elif not isinstance(artifact, str) or not artifact.strip():
                self._add_error(f"{context} 'artifact' must be a non-empty string")

            output_name = entry.get('from')
            if output_name is None:
                self._add_error(f"{context} missing required 'from'")
            elif not isinstance(output_name, str) or not output_name.strip():
                self._add_error(f"{context} 'from' must be a non-empty string")

    def _validate_consumes(self, consumes: Any, step_name: str):
        """Validate step consumes list (v1.2)."""
        if not isinstance(consumes, list):
            self._add_error(f"Step '{step_name}': consumes must be a list")
            return

        allowed_policies = {'latest_successful'}
        allowed_freshness = {'any', 'since_last_consume'}

        for i, entry in enumerate(consumes):
            context = f"Step '{step_name}': consumes[{i}]"
            if not isinstance(entry, dict):
                self._add_error(f"{context} must be a dictionary")
                continue

            artifact = entry.get('artifact')
            if artifact is None:
                self._add_error(f"{context} missing required 'artifact'")
            elif not isinstance(artifact, str) or not artifact.strip():
                self._add_error(f"{context} 'artifact' must be a non-empty string")

            if 'producers' in entry:
                producers = entry['producers']
                if not isinstance(producers, list):
                    self._add_error(f"{context} 'producers' must be a list")
                else:
                    for producer in producers:
                        if not isinstance(producer, str) or not producer.strip():
                            self._add_error(f"{context} 'producers' entries must be non-empty strings")

            if 'policy' in entry:
                policy = entry['policy']
                if not isinstance(policy, str):
                    self._add_error(f"{context} 'policy' must be a string")
                elif policy not in allowed_policies:
                    self._add_error(f"{context} unsupported policy '{policy}'")

            if 'freshness' in entry:
                freshness = entry['freshness']
                if not isinstance(freshness, str):
                    self._add_error(f"{context} 'freshness' must be a string")
                elif freshness not in allowed_freshness:
                    self._add_error(f"{context} unsupported freshness '{freshness}'")

            for guidance_key in ('description', 'format_hint', 'example'):
                if guidance_key in entry and not isinstance(entry[guidance_key], str):
                    self._add_error(f"{context} '{guidance_key}' must be a string")

            if 'prompt' in entry:
                prompt = entry['prompt']
                if not isinstance(prompt, dict):
                    self._add_error(f"{context} consume prompt metadata must be a mapping")
                else:
                    mode = prompt.get('mode')
                    if mode is not None:
                        if not isinstance(mode, str):
                            self._add_error(f"{context} consume prompt mode must be one of: content, reference, none")
                        elif mode not in {'content', 'reference', 'none'}:
                            self._add_error(f"{context} consume prompt mode must be one of: content, reference, none")
                    for prompt_key in ('label', 'description', 'format_hint', 'example', 'role'):
                        if prompt_key in prompt and not isinstance(prompt[prompt_key], str):
                            self._add_error(f"{context} consume prompt '{prompt_key}' must be a string")

    def _get_publish_source_map(
        self,
        step: Dict[str, Any],
        artifacts_registry: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Index publish sources by name for cross-reference checks."""
        out: Dict[str, Dict[str, Any]] = {}
        expected_outputs = step.get('expected_outputs', [])
        if not isinstance(expected_outputs, list):
            expected_outputs = []

        for spec in expected_outputs:
            if not isinstance(spec, dict) or not isinstance(spec.get('name'), str):
                continue
            out[spec['name']] = {
                "source": "expected_outputs",
                "type": spec.get('type'),
                "path": spec.get('path'),
            }

        output_bundle = step.get('output_bundle')
        if isinstance(output_bundle, dict):
            fields = output_bundle.get('fields', [])
            if isinstance(fields, list):
                for spec in fields:
                    if not isinstance(spec, dict) or not isinstance(spec.get('name'), str):
                        continue
                    out[spec['name']] = {
                        "source": "output_bundle",
                        "type": spec.get('type'),
                        "path": None,
                    }

        variant_output = step.get('variant_output')
        if isinstance(variant_output, dict):
            discriminant = variant_output.get('discriminant')
            if isinstance(discriminant, dict) and isinstance(discriminant.get('name'), str):
                out[discriminant['name']] = {
                    "source": "variant_output.discriminant",
                    "type": discriminant.get('type'),
                    "path": None,
                }
            shared_fields = variant_output.get('shared_fields', [])
            if isinstance(shared_fields, list):
                for spec in shared_fields:
                    if not isinstance(spec, dict) or not isinstance(spec.get('name'), str):
                        continue
                    out[spec['name']] = {
                        "source": "variant_output",
                        "type": spec.get('type'),
                        "path": None,
                    }
            variants = variant_output.get('variants', {})
            if isinstance(variants, dict):
                for variant_spec in variants.values():
                    if not isinstance(variant_spec, dict):
                        continue
                    fields = variant_spec.get('fields', [])
                    if not isinstance(fields, list):
                        continue
                    for spec in fields:
                        if not isinstance(spec, dict) or not isinstance(spec.get('name'), str):
                            continue
                        out[spec['name']] = {
                            "source": "variant_output",
                            "type": spec.get('type'),
                            "path": None,
                        }

        materialize_artifacts = step.get('materialize_artifacts')
        if isinstance(materialize_artifacts, dict):
            values = materialize_artifacts.get('values', [])
            if isinstance(values, list):
                for spec in values:
                    if not isinstance(spec, dict) or not isinstance(spec.get('name'), str):
                        continue
                    contract = spec.get('contract')
                    pointer = spec.get('pointer')
                    pointer_path = pointer.get('path') if isinstance(pointer, dict) else None
                    out[spec['name']] = {
                        "source": "materialize_artifacts",
                        "type": contract.get('type') if isinstance(contract, dict) else None,
                        "path": pointer_path,
                    }

        registry = artifacts_registry if isinstance(artifacts_registry, dict) else {}
        for field_name in ('set_scalar', 'increment_scalar'):
            node = step.get(field_name)
            if not isinstance(node, dict):
                continue
            artifact_name = node.get('artifact')
            if not isinstance(artifact_name, str):
                continue
            artifact_spec = registry.get(artifact_name)
            if not isinstance(artifact_spec, dict):
                continue
            out[artifact_name] = {
                "source": field_name,
                "type": artifact_spec.get('type'),
                "path": None,
            }
        return out

    def _validate_dataflow_cross_references(self, steps: List[Dict[str, Any]], artifacts_registry: Optional[Any]):
        """Validate v1.2 publishes/consumes cross references."""
        registry = artifacts_registry if isinstance(artifacts_registry, dict) else {}

        publishes_by_step: Dict[str, Set[str]] = {}

        for step in steps:
            if not isinstance(step, dict):
                continue
            step_name = step.get('name')
            if not isinstance(step_name, str):
                continue

            published_artifacts: Set[str] = set()

            publish_sources_by_name = self._get_publish_source_map(step, registry)
            publishes = step.get('publishes', [])
            if isinstance(publishes, list):
                for entry in publishes:
                    if not isinstance(entry, dict):
                        continue
                    artifact_name = entry.get('artifact')
                    from_name = entry.get('from')
                    if not isinstance(artifact_name, str) or not isinstance(from_name, str):
                        continue

                    if artifact_name not in registry:
                        self._add_error(
                            f"Step '{step_name}': publishes unknown artifact '{artifact_name}'"
                        )
                        continue

                    source_spec = publish_sources_by_name.get(from_name)
                    if source_spec is None:
                        self._add_error(
                            f"Step '{step_name}': publishes.from '{from_name}' not found in expected_outputs, output_bundle.fields, or scalar bookkeeping output"
                        )
                        continue

                    registry_spec = registry[artifact_name]
                    registry_kind = registry_spec.get('kind', 'relpath')
                    source_path = source_spec.get('path')
                    if registry_kind == 'relpath' and isinstance(source_path, str):
                        pointer = registry_spec.get('pointer')
                        if source_path != pointer:
                            if source_spec.get('source') == 'materialize_artifacts':
                                self._add_error(
                                    f"Step '{step_name}': pointer_authority_conflict for published artifact "
                                    f"'{artifact_name}' (local pointer '{source_path}' != canonical pointer '{pointer}')"
                                )
                            else:
                                self._add_error(
                                    f"Step '{step_name}': publishes pointer mismatch for artifact '{artifact_name}'"
                                )
                            continue

                    if (
                        source_spec.get('type') is not None
                        and source_spec.get('type') != registry_spec.get('type')
                    ):
                        self._add_error(
                            f"Step '{step_name}': publishes type mismatch for artifact '{artifact_name}'"
                        )
                        continue

                    published_artifacts.add(artifact_name)

            existing = publishes_by_step.setdefault(step_name, set())
            existing.update(published_artifacts)

        for step in steps:
            if not isinstance(step, dict):
                continue
            step_name = step.get('name')
            if not isinstance(step_name, str):
                continue

            consumes = step.get('consumes', [])
            if not isinstance(consumes, list):
                continue

            for entry in consumes:
                if not isinstance(entry, dict):
                    continue
                artifact_name = entry.get('artifact')
                if not isinstance(artifact_name, str):
                    continue

                if artifact_name not in registry:
                    self._add_error(
                        f"Step '{step_name}': consumes unknown artifact '{artifact_name}'"
                    )
                    continue

                producers = entry.get('producers', [])
                if not isinstance(producers, list):
                    continue

                for producer_name in producers:
                    if not isinstance(producer_name, str):
                        continue
                    if artifact_name not in publishes_by_step.get(producer_name, set()):
                        self._add_error(
                            f"Step '{step_name}': consumes producer '{producer_name}' does not publish artifact '{artifact_name}'"
                        )

    def _workflow_subject_refs(
        self,
        subject_kind: str,
        subject_name: str,
    ) -> tuple[ValidationSubjectRef, ...]:
        if not isinstance(subject_name, str) or not subject_name.strip():
            return ()
        return (
            ValidationSubjectRef(
                subject_kind=subject_kind,
                subject_name=subject_name,
                workflow_name=self._current_validation_workflow_name,
            ),
        )

    def _add_error(
        self,
        message: str,
        path: str = "",
        exit_code: int = 2,
        *,
        subject_refs: tuple[ValidationSubjectRef, ...] = (),
    ):
        """Add validation error."""
        self.errors.append(ValidationError(message, path, exit_code, subject_refs))

    def _raise_validation_errors(self):
        """Raise WorkflowValidationError with accumulated errors."""
        raise WorkflowValidationError(self.errors)
