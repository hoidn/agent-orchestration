"""Workflow loader and strict DSL validation per specs/dsl.md."""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import yaml

from orchestrator.exceptions import ValidationError, WorkflowValidationError


class PreservingLoader(yaml.SafeLoader):
    """Custom YAML loader that preserves string keys like 'on' instead of converting to bool."""
    pass


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

    SUPPORTED_VERSIONS = {"1.1", "1.1.1", "1.2", "1.3", "1.4", "1.5", "1.6"}
    SUPPORTED_OUTPUT_TYPES = {"enum", "integer", "float", "bool", "relpath"}
    ENV_VAR_PATTERN = re.compile(r'\$\{env\.[^}]+\}')
    VERSION_ORDER = ["1.1", "1.1.1", "1.2", "1.3", "1.4", "1.5", "1.6"]

    def __init__(self, workspace: Path):
        """Initialize loader with workspace root."""
        self.workspace = workspace.resolve()
        self.errors: List[ValidationError] = []

    def load(self, workflow_path: Path) -> Dict[str, Any]:
        """Load and validate workflow YAML."""
        try:
            with open(workflow_path, 'r') as f:
                workflow = yaml.load(f, Loader=PreservingLoader)
        except Exception as e:
            self._add_error(f"Failed to load workflow: {e}")
            self._raise_validation_errors()

        if workflow is None or not isinstance(workflow, dict):
            self._add_error("Workflow must be a YAML object/dictionary")
            self._raise_validation_errors()

        # Type narrowing: at this point workflow is definitely Dict[str, Any]
        assert isinstance(workflow, dict), "Type narrowing for workflow"

        # Version validation and feature gating
        version = workflow.get('version')
        if not version:
            self._add_error("'version' field is required")
            # Use empty string as fallback to avoid None type issues
            version = ""
        elif not isinstance(version, str):
            self._add_error(f"'version' field must be a string, got {type(version).__name__}")
            version = ""
        elif version not in self.SUPPORTED_VERSIONS:
            self._add_error(f"Unsupported version '{version}'. Supported: {self.SUPPORTED_VERSIONS}")

        # Validate top-level schema
        self._validate_top_level(workflow, version)

        # Validate steps
        steps = workflow.get('steps', [])
        if not steps:
            self._add_error("'steps' field is required and must not be empty")
        else:
            self._validate_steps(steps, version, workflow.get('artifacts'))
            if version == "1.2":
                all_steps = self._collect_all_steps(steps)
                self._validate_dataflow_cross_references(all_steps, workflow.get('artifacts'))

        # Validate goto targets
        self._validate_goto_targets(workflow)

        if self.errors:
            self._raise_validation_errors()

        return workflow

    def _validate_top_level(self, workflow: Dict[str, Any], version: str):
        """Validate top-level workflow fields."""
        # Known fields at version 1.1/1.1.1
        known_fields = {
            'version', 'name', 'strict_flow', 'context', 'providers', 'secrets',
            'inbox_dir', 'processed_dir', 'failed_dir', 'task_extension', 'steps',
            'artifacts'
        }

        # Strict unknown field rejection (skip if version is invalid/empty)
        if version:
            for key in workflow.keys():
                if key not in known_fields:
                    self._add_error(f"Unknown field '{key}' at version '{version}'")

        # Validate providers if present
        if 'providers' in workflow:
            self._validate_providers(workflow['providers'])

        # Validate secrets if present
        if 'secrets' in workflow:
            self._validate_secrets(workflow['secrets'])

        # Path safety for directories
        for dir_field in ['inbox_dir', 'processed_dir', 'failed_dir']:
            if dir_field in workflow:
                self._validate_path_safety(workflow[dir_field], dir_field)

        if 'artifacts' in workflow:
            if version not in {"1.2", "1.3", "1.4", "1.5", "1.6"}:
                self._add_error("artifacts requires version '1.2'")
            else:
                self._validate_artifacts_registry(workflow['artifacts'])

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

    def _validate_providers(self, providers: Dict[str, Any]):
        """Validate provider templates."""
        if not isinstance(providers, dict):
            self._add_error("'providers' must be a dictionary")
            return

        for name, config in providers.items():
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

    def _validate_steps(
        self,
        steps: List[Any],
        version: str,
        artifacts_registry: Optional[Any] = None,
        root_catalog: Optional[Dict[str, Any]] = None,
    ):
        """Validate step definitions."""
        if not isinstance(steps, list):
            self._add_error("'steps' must be a list")
            return

        if root_catalog is None:
            root_catalog = self._build_root_ref_catalog(steps)

        step_names = set()

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

            # AT-10: Provider/Command exclusivity
            execution_fields = ['provider', 'command', 'wait_for', 'assert']
            exec_count = sum(1 for f in execution_fields if f in step)

            if 'for_each' in step:
                # for_each is exclusive with execution fields
                if exec_count > 0:
                    self._add_error(f"Step '{name}': for_each cannot be combined with {execution_fields}")
                self._validate_for_each(step['for_each'], name, version, artifacts_registry, root_catalog)
            elif exec_count > 1:
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
                    self._validate_assert_condition(step['assert'], name, version, root_catalog)

            # AT-40: Reject deprecated command_override
            if 'command_override' in step:
                self._add_error(f"Step '{name}': deprecated 'command_override' not supported")

            # Validate dependencies (version-gated features)
            if 'depends_on' in step:
                self._validate_dependencies(step['depends_on'], name, version)

            # Validate variables in allowed fields
            self._validate_variables_usage(step, name)

            # Path safety for file fields
            for field in ['input_file', 'output_file']:
                if field in step:
                    self._validate_path_safety(step[field], f"step '{name}' {field}")

            # Validate deterministic artifact contracts
            if 'expected_outputs' in step:
                self._validate_expected_outputs(step['expected_outputs'], name)

            if 'output_bundle' in step:
                if version not in {"1.3", "1.4", "1.5", "1.6"}:
                    self._add_error(f"Step '{name}': output_bundle requires version '1.3'")
                else:
                    self._validate_output_bundle(step['output_bundle'], name)

            if 'expected_outputs' in step and 'output_bundle' in step:
                self._add_error(
                    f"Step '{name}': output_bundle is mutually exclusive with expected_outputs"
                )

            if 'inject_output_contract' in step and not isinstance(step['inject_output_contract'], bool):
                self._add_error(f"Step '{name}': 'inject_output_contract' must be a boolean")

            if 'persist_artifacts_in_state' in step and not isinstance(step['persist_artifacts_in_state'], bool):
                self._add_error(f"Step '{name}': 'persist_artifacts_in_state' must be a boolean")

            if 'publishes' in step:
                if version not in {"1.2", "1.3", "1.4", "1.5", "1.6"}:
                    self._add_error(f"Step '{name}': publishes requires version '1.2'")
                else:
                    if step.get('persist_artifacts_in_state') is False:
                        self._add_error(
                            f"Step '{name}': publishes requires persist_artifacts_in_state to be true"
                        )
                    self._validate_publishes(step['publishes'], name)

            if 'consumes' in step:
                if version not in {"1.2", "1.3", "1.4", "1.5", "1.6"}:
                    self._add_error(f"Step '{name}': consumes requires version '1.2'")
                else:
                    self._validate_consumes(step['consumes'], name)

            if 'prompt_consumes' in step:
                if version not in {"1.2", "1.3", "1.4", "1.5", "1.6"}:
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
                if version not in {"1.2", "1.3", "1.4", "1.5", "1.6"}:
                    self._add_error(f"Step '{name}': inject_consumes requires version '1.2'")
                elif not isinstance(step['inject_consumes'], bool):
                    self._add_error(f"Step '{name}': 'inject_consumes' must be a boolean")

            if 'consumes_injection_position' in step:
                if version not in {"1.2", "1.3", "1.4", "1.5", "1.6"}:
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
                if version not in {"1.3", "1.4", "1.5", "1.6"}:
                    self._add_error(f"Step '{name}': consume_bundle requires version '1.3'")
                else:
                    self._validate_consume_bundle(step['consume_bundle'], name, step.get('consumes'))

            # Validate wait_for exclusivity (AT-36)
            if 'wait_for' in step:
                self._validate_wait_for(step, name)

            # Validate when conditions
            if 'when' in step:
                self._validate_when_condition(step['when'], name, version, root_catalog)

            # Validate control flow
            if 'on' in step:
                self._validate_on_handlers(step['on'], name)

    def _collect_all_steps(self, steps: List[Any]) -> List[Dict[str, Any]]:
        """Collect all step definitions from top-level and nested for_each blocks."""
        collected: List[Dict[str, Any]] = []
        if not isinstance(steps, list):
            return collected

        for step in steps:
            if not isinstance(step, dict):
                continue
            collected.append(step)
            for_each = step.get('for_each')
            if isinstance(for_each, dict):
                nested = for_each.get('steps')
                if isinstance(nested, list):
                    collected.extend(self._collect_all_steps(nested))

        return collected

    def _validate_for_each(
        self,
        for_each: Any,
        step_name: str,
        version: str,
        artifacts_registry: Optional[Any] = None,
        root_catalog: Optional[Dict[str, Any]] = None,
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
            # Recursively validate nested steps
            self._validate_steps(for_each['steps'], version, artifacts_registry, root_catalog)

    def _validate_dependencies(self, depends_on: Any, step_name: str, version: str):
        """Validate dependency configuration."""
        if not isinstance(depends_on, dict):
            self._add_error(f"Step '{step_name}': depends_on must be a dictionary")
            return

        # Validate inject feature (requires version 1.1.1)
        if 'inject' in depends_on:
            if version != "1.1.1":
                self._add_error(f"Step '{step_name}': depends_on.inject requires version '1.1.1'")

    def _validate_variables_usage(self, step: Dict[str, Any], name: str):
        """Validate variable usage and reject ${env.*} namespace (AT-7)."""
        # Fields that allow variable substitution
        variable_fields = ['command', 'input_file', 'output_file', 'provider_params']

        for field in variable_fields:
            if field in step:
                value = step[field]
                self._check_env_variables(value, f"step '{name}' {field}")

        # Check when conditions
        if 'when' in step and 'equals' in step['when']:
            equals = step['when']['equals']
            if isinstance(equals, dict):
                for key in ['left', 'right']:
                    if key in equals:
                        self._check_env_variables(equals[key], f"step '{name}' when.equals.{key}")

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

    def _validate_expected_outputs(self, expected_outputs: Any, step_name: str):
        """Validate expected_outputs contract entries."""
        if not isinstance(expected_outputs, list):
            self._add_error(f"Step '{step_name}': expected_outputs must be a list")
            return

        seen_names: Set[str] = set()
        for i, spec in enumerate(expected_outputs):
            context = f"Step '{step_name}': expected_outputs[{i}]"
            if not isinstance(spec, dict):
                self._add_error(f"{context} must be a dictionary")
                continue

            if 'name' not in spec:
                self._add_error(f"{context} missing required 'name'")
            elif not isinstance(spec['name'], str):
                self._add_error(f"{context} 'name' must be a string")
            elif not spec['name'].strip():
                self._add_error(f"{context} 'name' cannot be empty")
            elif spec['name'] in seen_names:
                self._add_error(f"{context} duplicate artifact name '{spec['name']}'")
            else:
                seen_names.add(spec['name'])

            if 'path' not in spec:
                self._add_error(f"{context} missing required 'path'")
            elif not isinstance(spec['path'], str):
                self._add_error(f"{context} 'path' must be a string")
            else:
                self._validate_path_safety(spec['path'], f"{context} path")

            if 'type' not in spec:
                self._add_error(f"{context} missing required 'type'")
            elif not isinstance(spec['type'], str):
                self._add_error(f"{context} 'type' must be a string")
            elif spec['type'] not in self.SUPPORTED_OUTPUT_TYPES:
                self._add_error(
                    f"{context} invalid expected_outputs type '{spec['type']}'"
                )

            if 'under' in spec:
                if not isinstance(spec['under'], str):
                    self._add_error(f"{context} 'under' must be a string")
                else:
                    self._validate_path_safety(spec['under'], f"{context} under")

            if 'allowed' in spec:
                if not isinstance(spec['allowed'], list):
                    self._add_error(f"{context} 'allowed' must be a list")

            if spec.get('type') == 'enum' and 'allowed' not in spec:
                self._add_error(f"{context} enum type requires 'allowed'")

            if 'must_exist_target' in spec and not isinstance(spec['must_exist_target'], bool):
                self._add_error(f"{context} 'must_exist_target' must be a boolean")

            if 'required' in spec and not isinstance(spec['required'], bool):
                self._add_error(f"{context} 'required' must be a boolean")

            for guidance_key in ('description', 'format_hint', 'example'):
                if guidance_key in spec and not isinstance(spec[guidance_key], str):
                    self._add_error(f"{context} '{guidance_key}' must be a string")

    def _validate_output_bundle(self, output_bundle: Any, step_name: str):
        """Validate output_bundle contract entries (v1.3)."""
        context = f"Step '{step_name}': output_bundle"
        if not isinstance(output_bundle, dict):
            self._add_error(f"{context} must be a dictionary")
            return

        if 'path' not in output_bundle:
            self._add_error(f"{context} missing required 'path'")
        elif not isinstance(output_bundle['path'], str):
            self._add_error(f"{context} 'path' must be a string")
        else:
            self._validate_path_safety(output_bundle['path'], f"{context} path")

        fields = output_bundle.get('fields')
        if not isinstance(fields, list) or not fields:
            self._add_error(f"{context}.fields must be a non-empty list")
            return

        seen_names: Set[str] = set()
        for i, spec in enumerate(fields):
            field_context = f"{context}.fields[{i}]"
            if not isinstance(spec, dict):
                self._add_error(f"{field_context} must be a dictionary")
                continue

            if 'name' not in spec:
                self._add_error(f"{field_context} missing required 'name'")
            elif not isinstance(spec['name'], str):
                self._add_error(f"{field_context} 'name' must be a string")
            elif not spec['name'].strip():
                self._add_error(f"{field_context} 'name' cannot be empty")
            elif spec['name'] in seen_names:
                self._add_error(f"{field_context} duplicate artifact name '{spec['name']}'")
            else:
                seen_names.add(spec['name'])

            if 'json_pointer' not in spec:
                self._add_error(f"{field_context} missing required 'json_pointer'")
            elif not isinstance(spec['json_pointer'], str):
                self._add_error(f"{field_context} 'json_pointer' must be a string")
            else:
                pointer = spec['json_pointer']
                if pointer and not pointer.startswith('/'):
                    self._add_error(f"{field_context} 'json_pointer' must be RFC 6901 pointer syntax")

            if 'type' not in spec:
                self._add_error(f"{field_context} missing required 'type'")
            elif not isinstance(spec['type'], str):
                self._add_error(f"{field_context} 'type' must be a string")
            elif spec['type'] not in self.SUPPORTED_OUTPUT_TYPES:
                self._add_error(
                    f"{field_context} invalid output_bundle field type '{spec['type']}'"
                )

            if 'under' in spec:
                if not isinstance(spec['under'], str):
                    self._add_error(f"{field_context} 'under' must be a string")
                else:
                    self._validate_path_safety(spec['under'], f"{field_context} under")

            if 'allowed' in spec and not isinstance(spec['allowed'], list):
                self._add_error(f"{field_context} 'allowed' must be a list")

            if spec.get('type') == 'enum' and 'allowed' not in spec:
                self._add_error(f"{field_context} enum type requires 'allowed'")

            if 'must_exist_target' in spec and not isinstance(spec['must_exist_target'], bool):
                self._add_error(f"{field_context} 'must_exist_target' must be a boolean")

            if 'required' in spec and not isinstance(spec['required'], bool):
                self._add_error(f"{field_context} 'required' must be a boolean")

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

    def _validate_when_condition(
        self,
        when: Any,
        step_name: str,
        version: str,
        root_catalog: Dict[str, Any],
    ):
        """Validate when condition structure."""
        if not isinstance(when, dict):
            self._add_error(f"Step '{step_name}': when must be a dictionary")
            return

        if self._is_typed_predicate_node(when):
            if not self._version_at_least(version, "1.6"):
                self._add_error(f"Step '{step_name}': typed predicates require version '1.6'")
                return
            self._validate_typed_predicate(when, step_name, root_catalog)
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
    ) -> None:
        if not isinstance(assertion, dict):
            self._add_error(f"Step '{step_name}': assert must be a dictionary")
            return
        if self._is_typed_predicate_node(assertion):
            if not self._version_at_least(version, "1.6"):
                self._add_error(f"Step '{step_name}': typed assert predicates require version '1.6'")
                return
            self._validate_typed_predicate(assertion, step_name, root_catalog)
            return

        condition_types = ['equals', 'exists', 'not_exists']
        present = [t for t in condition_types if t in assertion]
        if len(present) == 0:
            self._add_error(f"Step '{step_name}': assert requires one of {condition_types}")
        elif len(present) > 1:
            self._add_error(f"Step '{step_name}': assert can only have one condition type, found {present}")

    def _is_typed_predicate_node(self, node: Any) -> bool:
        return isinstance(node, dict) and any(
            key in node for key in ('artifact_bool', 'compare', 'all_of', 'any_of', 'not')
        )

    def _version_at_least(self, version: str, minimum: str) -> bool:
        if version not in self.VERSION_ORDER or minimum not in self.VERSION_ORDER:
            return False
        return self.VERSION_ORDER.index(version) >= self.VERSION_ORDER.index(minimum)

    def _build_root_ref_catalog(self, steps: List[Any]) -> Dict[str, Any]:
        artifact_map: Dict[str, Dict[str, Any]] = {}
        step_names: List[str] = []

        for step in steps:
            if not isinstance(step, dict):
                continue
            name = step.get('name')
            if not isinstance(name, str):
                continue
            step_names.append(name)
            outputs: Dict[str, Any] = {}

            expected_outputs = step.get('expected_outputs')
            if isinstance(expected_outputs, list):
                for spec in expected_outputs:
                    if isinstance(spec, dict):
                        artifact_name = spec.get('name')
                        artifact_type = spec.get('type')
                        if isinstance(artifact_name, str) and isinstance(artifact_type, str):
                            outputs[artifact_name] = {
                                'type': artifact_type,
                                'persisted': step.get('persist_artifacts_in_state', True) is not False,
                            }

            output_bundle = step.get('output_bundle')
            if isinstance(output_bundle, dict):
                for spec in output_bundle.get('fields', []):
                    if isinstance(spec, dict):
                        artifact_name = spec.get('name')
                        artifact_type = spec.get('type')
                        if isinstance(artifact_name, str) and isinstance(artifact_type, str):
                            outputs[artifact_name] = {
                                'type': artifact_type,
                                'persisted': step.get('persist_artifacts_in_state', True) is not False,
                            }

            artifact_map[name] = outputs

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
            'multi_visit': self._detect_multi_visit_steps(edges),
        }

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
        root_catalog: Dict[str, Any],
    ) -> None:
        if not isinstance(predicate, dict):
            self._add_error(f"Step '{step_name}': typed predicate must be a dictionary")
            return

        if 'artifact_bool' in predicate:
            node = predicate['artifact_bool']
            if not isinstance(node, dict):
                self._add_error(f"Step '{step_name}': artifact_bool must be a dictionary")
                return
            ref_type = self._validate_structured_ref(node.get('ref'), step_name, root_catalog)
            if ref_type != 'bool':
                self._add_error(f"Step '{step_name}': artifact_bool requires a bool artifact ref")
            return

        if 'compare' in predicate:
            node = predicate['compare']
            if not isinstance(node, dict):
                self._add_error(f"Step '{step_name}': compare must be a dictionary")
                return
            left_type = self._validate_compare_operand(node.get('left'), step_name, root_catalog)
            right_type = self._validate_compare_operand(node.get('right'), step_name, root_catalog)
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

        if 'all_of' in predicate:
            items = predicate['all_of']
            if not isinstance(items, list) or not items:
                self._add_error(f"Step '{step_name}': all_of must be a non-empty list")
                return
            for item in items:
                self._validate_typed_predicate(item, step_name, root_catalog)
            return

        if 'any_of' in predicate:
            items = predicate['any_of']
            if not isinstance(items, list) or not items:
                self._add_error(f"Step '{step_name}': any_of must be a non-empty list")
                return
            for item in items:
                self._validate_typed_predicate(item, step_name, root_catalog)
            return

        if 'not' in predicate:
            self._validate_typed_predicate(predicate['not'], step_name, root_catalog)
            return

        self._add_error(f"Step '{step_name}': unsupported typed predicate")

    def _validate_compare_operand(
        self,
        operand: Any,
        step_name: str,
        root_catalog: Dict[str, Any],
    ) -> str:
        if isinstance(operand, dict):
            if set(operand.keys()) != {'ref'}:
                self._add_error(f"Step '{step_name}': compare operands must be literals or {{ref: ...}}")
                return 'unknown'
            return self._validate_structured_ref(operand.get('ref'), step_name, root_catalog)
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

    def _validate_structured_ref(
        self,
        ref: Any,
        step_name: str,
        root_catalog: Dict[str, Any],
    ) -> str:
        if not isinstance(ref, str) or not ref:
            self._add_error(f"Step '{step_name}': structured refs must be non-empty strings")
            return 'unknown'
        if ref.startswith('steps.'):
            self._add_error(
                f"Step '{step_name}': bare 'steps.' refs are invalid in structured predicates"
            )
            return 'unknown'
        if ref.startswith('self.') or ref.startswith('parent.'):
            scope = ref.split('.', 1)[0]
            self._add_error(
                f"Step '{step_name}': {scope}. refs are not available before scoped refs land"
            )
            return 'unknown'
        if ref.startswith('context.'):
            self._add_error(f"Step '{step_name}': structured refs cannot read untyped context values")
            return 'unknown'
        if not ref.startswith('root.steps.'):
            self._add_error(f"Step '{step_name}': structured refs must start with 'root.steps.'")
            return 'unknown'

        parts = ref.split('.')
        if len(parts) < 4:
            self._add_error(f"Step '{step_name}': invalid structured ref '{ref}'")
            return 'unknown'

        target_step = parts[2]
        if target_step in root_catalog.get('multi_visit', set()):
            self._add_error(
                f"Step '{step_name}': structured ref '{ref}' targets multi-visit step '{target_step}'"
            )
            return 'unknown'

        tail = parts[3:]
        if tail == ['exit_code']:
            return 'integer'
        if len(tail) == 2 and tail[0] == 'outcome':
            return {
                'status': 'string',
                'phase': 'string',
                'class': 'string',
                'retryable': 'bool',
            }.get(tail[1], 'unknown')
        if len(tail) == 2 and tail[0] == 'artifacts':
            artifact_name = tail[1]
            artifacts = root_catalog.get('artifacts', {}).get(target_step, {})
            artifact_spec = artifacts.get(artifact_name)
            if artifact_spec is None:
                self._add_error(f"Step '{step_name}': structured ref '{ref}' targets unknown artifact")
                return 'unknown'
            if not artifact_spec.get('persisted', True):
                self._add_error(
                    f"Step '{step_name}': structured ref '{ref}' targets a non-persisted artifact"
                )
                return 'unknown'
            return artifact_spec.get('type', 'unknown')

        self._add_error(f"Step '{step_name}': invalid structured ref '{ref}'")
        return 'unknown'

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

            if 'for_each' in step and 'steps' in step['for_each']:
                self._check_goto_references(step['for_each']['steps'], valid_names)

    def _validate_path_safety(self, path: str, context: str):
        """Validate path safety (AT-38, AT-39)."""
        # Skip variable placeholders for now (validated at runtime)
        if '${' in path:
            return

        # Reject absolute paths
        if Path(path).is_absolute():
            self._add_error(f"{context}: absolute paths not allowed")

        # Reject parent directory traversal
        if '..' in Path(path).parts:
            self._add_error(f"{context}: parent directory traversal ('..') not allowed")

    def _validate_artifacts_registry(self, artifacts: Any):
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
            elif kind not in {'relpath', 'scalar'}:
                self._add_error(f"{context} invalid kind '{kind}'")

            output_type = spec.get('type')
            if output_type is None:
                self._add_error(f"{context} missing required 'type'")
            elif not isinstance(output_type, str):
                self._add_error(f"{context} 'type' must be a string")
            elif output_type not in self.SUPPORTED_OUTPUT_TYPES:
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
                if output_type not in {'enum', 'integer', 'float', 'bool'}:
                    self._add_error(
                        f"{context}: kind 'scalar' requires type one of enum|integer|float|bool"
                    )
                if 'pointer' in spec:
                    self._add_error(f"{context}: kind 'scalar' forbids 'pointer'")
                if 'under' in spec:
                    self._add_error(f"{context}: kind 'scalar' forbids 'under'")
                if 'must_exist_target' in spec:
                    self._add_error(f"{context}: kind 'scalar' forbids 'must_exist_target'")

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

    def _get_publish_source_map(self, step: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
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

            publish_sources_by_name = self._get_publish_source_map(step)
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
                            f"Step '{step_name}': publishes.from '{from_name}' not found in expected_outputs or output_bundle.fields"
                        )
                        continue

                    registry_spec = registry[artifact_name]
                    registry_kind = registry_spec.get('kind', 'relpath')
                    source_path = source_spec.get('path')
                    if registry_kind == 'relpath' and isinstance(source_path, str):
                        pointer = registry_spec.get('pointer')
                        if source_path != pointer:
                            self._add_error(
                                f"Step '{step_name}': publishes pointer mismatch for artifact '{artifact_name}'"
                            )
                            continue

                    if source_spec.get('type') != registry_spec.get('type'):
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

    def _add_error(self, message: str, path: str = "", exit_code: int = 2):
        """Add validation error."""
        self.errors.append(ValidationError(message, path, exit_code))

    def _raise_validation_errors(self):
        """Raise WorkflowValidationError with accumulated errors."""
        raise WorkflowValidationError(self.errors)
