"""Workflow loader and strict DSL validation per specs/dsl.md."""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union
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

    SUPPORTED_VERSIONS = {"1.1", "1.1.1"}
    ENV_VAR_PATTERN = re.compile(r'\$\{env\.[^}]+\}')

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
            self._validate_steps(steps, version)

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
            'inbox_dir', 'processed_dir', 'failed_dir', 'task_extension', 'steps'
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

    def _validate_steps(self, steps: List[Any], version: str):
        """Validate step definitions."""
        if not isinstance(steps, list):
            self._add_error("'steps' must be a list")
            return

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
            execution_fields = ['provider', 'command', 'wait_for']
            exec_count = sum(1 for f in execution_fields if f in step)

            if 'for_each' in step:
                # for_each is exclusive with execution fields
                if exec_count > 0:
                    self._add_error(f"Step '{name}': for_each cannot be combined with {execution_fields}")
                self._validate_for_each(step['for_each'], name, version)
            elif exec_count > 1:
                # AT-10: Mutual exclusivity
                present = [f for f in execution_fields if f in step]
                self._add_error(f"Step '{name}': mutually exclusive fields {present}")

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

            # Validate wait_for exclusivity (AT-36)
            if 'wait_for' in step:
                self._validate_wait_for(step, name)

            # Validate when conditions
            if 'when' in step:
                self._validate_when_condition(step['when'], name)

            # Validate control flow
            if 'on' in step:
                self._validate_on_handlers(step['on'], name)

    def _validate_for_each(self, for_each: Any, step_name: str, version: str):
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
            self._validate_steps(for_each['steps'], version)

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

    def _validate_when_condition(self, when: Any, step_name: str):
        """Validate when condition structure."""
        if not isinstance(when, dict):
            self._add_error(f"Step '{step_name}': when must be a dictionary")
            return

        # Must have exactly one condition type
        condition_types = ['equals', 'exists', 'not_exists']
        present = [t for t in condition_types if t in when]

        if len(present) == 0:
            self._add_error(f"Step '{step_name}': when requires one of {condition_types}")
        elif len(present) > 1:
            self._add_error(f"Step '{step_name}': when can only have one condition type, found {present}")

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

    def _add_error(self, message: str, path: str = "", exit_code: int = 2):
        """Add validation error."""
        self.errors.append(ValidationError(message, path, exit_code))

    def _raise_validation_errors(self):
        """Raise WorkflowValidationError with accumulated errors."""
        raise WorkflowValidationError(self.errors)