"""Workflow YAML loader with strict validation"""

import hashlib
import os
from pathlib import Path
from typing import Any, Dict, List, Set, Optional

import yaml

from .types import (
    WorkflowSpec, Step, ProviderTemplate, DependsOnConfig, DependsOnInjection,
    WaitForConfig, ForEachBlock, Condition, ConditionEquals, OnHandlers,
    GotoTarget, RetryConfig, DSLVersion, OutputCapture, InputMode,
    JsonOutputRequirement
)


class ValidationError(Exception):
    """Workflow validation error"""
    pass


class WorkflowLoader:
    """Load and validate workflow YAML files with strict schema enforcement"""

    # Fields allowed at each version
    V1_1_WORKFLOW_FIELDS = {
        'version', 'name', 'strict_flow', 'providers', 'context',
        'inbox_dir', 'processed_dir', 'failed_dir', 'task_extension', 'steps'
    }

    V1_1_STEP_FIELDS = {
        'name', 'agent', 'provider', 'provider_params', 'command', 'wait_for',
        'for_each', 'input_file', 'output_file', 'output_capture',
        'allow_parse_error', 'env', 'secrets', 'depends_on', 'timeout_sec',
        'retries', 'when', 'on'
    }

    V1_1_1_DEPENDS_ON_FIELDS = {'required', 'optional', 'inject'}
    V1_1_INJECTION_FIELDS = {'mode', 'instruction', 'position'}

    V1_3_STEP_FIELDS = V1_1_STEP_FIELDS | {'output_schema', 'output_require'}

    def __init__(self, workspace: Path = None):
        """Initialize loader with workspace root"""
        self.workspace = workspace or Path.cwd()

    def load(self, workflow_path: Path) -> WorkflowSpec:
        """Load and validate workflow from YAML file"""
        with open(workflow_path, 'r') as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValidationError("Workflow must be a YAML object")

        # Parse version first to determine validation rules
        version_str = data.get('version')
        if not version_str:
            raise ValidationError("Workflow must specify 'version' field")

        try:
            dsl_version = DSLVersion.from_string(version_str)
        except ValueError as e:
            raise ValidationError(str(e))

        # Validate top-level fields based on version
        self._validate_workflow_fields(data, dsl_version)

        # Parse workflow spec
        workflow = self._parse_workflow(data, dsl_version)

        # Validate the parsed workflow
        self._validate_workflow(workflow)

        return workflow

    def _validate_workflow_fields(self, data: Dict[str, Any], version: DSLVersion):
        """Validate that only allowed fields are present"""
        allowed_fields = self.V1_1_WORKFLOW_FIELDS

        unknown_fields = set(data.keys()) - allowed_fields
        if unknown_fields:
            raise ValidationError(
                f"Unknown fields in workflow (version {version.value}): {unknown_fields}"
            )

    def _parse_workflow(self, data: Dict[str, Any], version: DSLVersion) -> WorkflowSpec:
        """Parse workflow data into typed structure"""
        # Parse providers
        providers = {}
        if 'providers' in data:
            for name, provider_data in data['providers'].items():
                providers[name] = self._parse_provider(name, provider_data)

        # Parse steps
        steps_data = data.get('steps', [])
        if not steps_data:
            raise ValidationError("Workflow must have at least one step")

        steps = []
        for step_data in steps_data:
            step = self._parse_step(step_data, version)
            steps.append(step)

        # Create workflow spec
        workflow = WorkflowSpec(
            version=data['version'],
            name=data.get('name'),
            strict_flow=data.get('strict_flow', True),
            providers=providers,
            context=data.get('context', {}),
            inbox_dir=data.get('inbox_dir', 'inbox'),
            processed_dir=data.get('processed_dir', 'processed'),
            failed_dir=data.get('failed_dir', 'failed'),
            task_extension=data.get('task_extension', '.task'),
            steps=steps
        )

        return workflow

    def _parse_provider(self, name: str, data: Dict[str, Any]) -> ProviderTemplate:
        """Parse provider template"""
        if 'command' not in data:
            raise ValidationError(f"Provider '{name}' must specify 'command'")

        input_mode = InputMode.ARGV
        if 'input_mode' in data:
            try:
                input_mode = InputMode(data['input_mode'])
            except ValueError:
                raise ValidationError(
                    f"Provider '{name}' has invalid input_mode: {data['input_mode']}"
                )

        return ProviderTemplate(
            name=name,
            command=data['command'],
            defaults=data.get('defaults', {}),
            input_mode=input_mode
        )

    def _parse_step(self, data: Dict[str, Any], version: DSLVersion) -> Step:
        """Parse and validate a single step"""
        if 'name' not in data:
            raise ValidationError("Step must have 'name' field")

        # Check for deprecated fields first
        if 'command_override' in data:
            raise ValidationError(
                f"Step '{data['name']}' uses deprecated 'command_override' field"
            )

        # Validate allowed fields based on version
        allowed_fields = self.V1_1_STEP_FIELDS
        if version == DSLVersion.V1_3:
            allowed_fields = self.V1_3_STEP_FIELDS

        unknown_fields = set(data.keys()) - allowed_fields
        if unknown_fields:
            # Special case for v1.3 fields used in earlier versions
            if 'output_require' in unknown_fields and version != DSLVersion.V1_3:
                raise ValidationError(
                    f"Step '{data['name']}' uses 'output_require' which requires version 1.3 or higher"
                )
            raise ValidationError(
                f"Unknown fields in step '{data['name']}' (version {version.value}): {unknown_fields}"
            )

        # Parse dependencies
        depends_on = None
        if 'depends_on' in data:
            depends_on = self._parse_depends_on(data['depends_on'], data['name'], version)

        # Parse wait_for
        wait_for = None
        if 'wait_for' in data:
            wait_for = self._parse_wait_for(data['wait_for'], data['name'])

        # Parse for_each
        for_each = None
        if 'for_each' in data:
            for_each = self._parse_for_each(data['for_each'], data['name'], version)

        # Parse condition
        when = None
        if 'when' in data:
            when = self._parse_condition(data['when'], data['name'])

        # Parse on handlers
        on = None
        if 'on' in data:
            on = self._parse_on_handlers(data['on'], data['name'])

        # Parse retries
        retries = None
        if 'retries' in data:
            retries_data = data['retries']
            if isinstance(retries_data, dict) and 'max' in retries_data:
                retries = RetryConfig(
                    max=retries_data['max'],
                    delay_ms=retries_data.get('delay_ms', 1000)
                )

        # Parse output capture
        output_capture = OutputCapture.TEXT
        if 'output_capture' in data:
            try:
                output_capture = OutputCapture(data['output_capture'])
            except ValueError:
                raise ValidationError(
                    f"Step '{data['name']}' has invalid output_capture: {data['output_capture']}"
                )

        # Parse JSON validation (v1.3 only)
        output_require = None
        if 'output_require' in data:
            if not version.supports_json_validation():
                raise ValidationError(
                    f"Step '{data['name']}' uses 'output_require' which requires version 1.3 or higher"
                )
            output_require = self._parse_output_requirements(data['output_require'], data['name'])

        step = Step(
            name=data['name'],
            agent=data.get('agent'),
            provider=data.get('provider'),
            provider_params=data.get('provider_params'),
            command=data.get('command'),
            wait_for=wait_for,
            for_each=for_each,
            input_file=data.get('input_file'),
            output_file=data.get('output_file'),
            output_capture=output_capture,
            allow_parse_error=data.get('allow_parse_error', False),
            output_schema=data.get('output_schema'),
            output_require=output_require,
            env=data.get('env', {}),
            secrets=data.get('secrets', []),
            depends_on=depends_on,
            timeout_sec=data.get('timeout_sec'),
            retries=retries,
            when=when,
            on=on
        )

        # Validate step constraints
        self._validate_step(step, version)

        return step

    def _parse_depends_on(self, data: Any, step_name: str, version: DSLVersion) -> DependsOnConfig:
        """Parse dependencies configuration"""
        if not isinstance(data, dict):
            raise ValidationError(f"Step '{step_name}' depends_on must be an object")

        # Validate allowed fields
        unknown_fields = set(data.keys()) - self.V1_1_1_DEPENDS_ON_FIELDS
        if unknown_fields:
            raise ValidationError(
                f"Unknown fields in depends_on for step '{step_name}': {unknown_fields}"
            )

        config = DependsOnConfig(
            required=data.get('required', []),
            optional=data.get('optional', [])
        )

        # Parse injection if present
        if 'inject' in data:
            if not version.supports_injection():
                raise ValidationError(
                    f"Step '{step_name}' uses 'inject' which requires version 1.1.1 or higher"
                )

            inject_data = data['inject']
            if isinstance(inject_data, bool):
                if inject_data:
                    config.inject = DependsOnInjection()  # Use defaults
            elif isinstance(inject_data, dict):
                # Validate injection fields
                unknown_inject_fields = set(inject_data.keys()) - self.V1_1_INJECTION_FIELDS
                if unknown_inject_fields:
                    raise ValidationError(
                        f"Unknown fields in inject for step '{step_name}': {unknown_inject_fields}"
                    )

                config.inject = DependsOnInjection(
                    mode=inject_data.get('mode', 'list'),
                    instruction=inject_data.get('instruction'),
                    position=inject_data.get('position', 'prepend')
                )

                # Validate mode value
                if config.inject.mode not in ('list', 'content', 'none'):
                    raise ValidationError(
                        f"Step '{step_name}' has invalid inject.mode: {config.inject.mode}"
                    )

                # Validate position value
                if config.inject.position not in ('prepend', 'append'):
                    raise ValidationError(
                        f"Step '{step_name}' has invalid inject.position: {config.inject.position}"
                    )
            else:
                raise ValidationError(
                    f"Step '{step_name}' inject must be boolean or object"
                )

        return config

    def _parse_wait_for(self, data: Dict[str, Any], step_name: str) -> WaitForConfig:
        """Parse wait_for configuration"""
        if 'glob' not in data:
            raise ValidationError(f"Step '{step_name}' wait_for must specify 'glob'")

        return WaitForConfig(
            glob=data['glob'],
            timeout_sec=data.get('timeout_sec', 300),
            poll_ms=data.get('poll_ms', 500),
            min_count=data.get('min_count', 1)
        )

    def _parse_for_each(self, data: Dict[str, Any], step_name: str, version: DSLVersion) -> ForEachBlock:
        """Parse for_each block"""
        if 'steps' not in data:
            raise ValidationError(f"Step '{step_name}' for_each must have 'steps'")

        # Parse nested steps
        nested_steps = []
        for nested_data in data['steps']:
            nested_step = self._parse_step(nested_data, version)
            nested_steps.append(nested_step)

        return ForEachBlock(
            items_from=data.get('items_from'),
            items=data.get('items'),
            as_var=data.get('as', 'item'),
            steps=nested_steps
        )

    def _parse_condition(self, data: Dict[str, Any], step_name: str) -> Condition:
        """Parse when condition"""
        condition = Condition()

        if 'equals' in data:
            equals_data = data['equals']
            if not isinstance(equals_data, dict) or 'left' not in equals_data or 'right' not in equals_data:
                raise ValidationError(
                    f"Step '{step_name}' when.equals must have 'left' and 'right'"
                )
            condition.equals = ConditionEquals(
                left=str(equals_data['left']),
                right=str(equals_data['right'])
            )

        if 'exists' in data:
            condition.exists = data['exists']

        if 'not_exists' in data:
            condition.not_exists = data['not_exists']

        # Ensure at least one condition is specified
        if not (condition.equals or condition.exists or condition.not_exists):
            raise ValidationError(f"Step '{step_name}' when must specify a condition")

        return condition

    def _parse_on_handlers(self, data: Dict[str, Any], step_name: str) -> OnHandlers:
        """Parse on branching handlers"""
        handlers = OnHandlers()

        if 'success' in data:
            success_data = data['success']
            if isinstance(success_data, dict) and 'goto' in success_data:
                handlers.success = GotoTarget(goto=success_data['goto'])

        if 'failure' in data:
            failure_data = data['failure']
            if isinstance(failure_data, dict) and 'goto' in failure_data:
                handlers.failure = GotoTarget(goto=failure_data['goto'])

        if 'always' in data:
            always_data = data['always']
            if isinstance(always_data, dict) and 'goto' in always_data:
                handlers.always = GotoTarget(goto=always_data['goto'])

        return handlers

    def _parse_output_requirements(self, data: List[Dict[str, Any]], step_name: str) -> List[JsonOutputRequirement]:
        """Parse JSON output requirements (v1.3)"""
        requirements = []
        for req_data in data:
            if 'pointer' not in req_data:
                raise ValidationError(
                    f"Step '{step_name}' output_require entry must have 'pointer'"
                )

            req = JsonOutputRequirement(
                pointer=req_data['pointer'],
                exists=req_data.get('exists', True),
                equals=req_data.get('equals'),
                type=req_data.get('type')
            )

            # Validate type value if present
            if req.type and req.type not in ('string', 'number', 'boolean', 'array', 'object', 'null'):
                raise ValidationError(
                    f"Step '{step_name}' output_require has invalid type: {req.type}"
                )

            requirements.append(req)

        return requirements

    def _validate_step(self, step: Step, version: DSLVersion):
        """Validate step constraints"""
        # Count execution types
        exec_types = []
        if step.provider:
            exec_types.append('provider')
        if step.command:
            exec_types.append('command')
        if step.wait_for:
            exec_types.append('wait_for')
        if step.for_each:
            exec_types.append('for_each')

        # Check mutual exclusivity
        if len(exec_types) > 1:
            raise ValidationError(
                f"Step '{step.name}' specifies multiple execution types: {exec_types}. "
                "Only one of provider, command, wait_for, or for_each is allowed."
            )

        # wait_for cannot be combined with for_each
        if step.wait_for and step.for_each:
            raise ValidationError(
                f"Step '{step.name}' cannot combine wait_for with for_each"
            )

        # Validate JSON output requirements
        if step.output_schema or step.output_require:
            if not version.supports_json_validation():
                raise ValidationError(
                    f"Step '{step.name}' uses JSON validation which requires version 1.3"
                )
            if step.output_capture != OutputCapture.JSON:
                raise ValidationError(
                    f"Step '{step.name}' JSON validation requires output_capture: json"
                )
            if step.allow_parse_error:
                raise ValidationError(
                    f"Step '{step.name}' JSON validation incompatible with allow_parse_error: true"
                )

        # Validate env namespace prohibition
        if step.env:
            for key in step.env.keys():
                if key.startswith('env.'):
                    raise ValidationError(
                        f"Step '{step.name}' env cannot use 'env.' namespace"
                    )

    def _validate_workflow(self, workflow: WorkflowSpec):
        """Validate the complete workflow"""
        # Collect all step names
        step_names = set()
        for step in workflow.steps:
            if step.name in step_names:
                raise ValidationError(f"Duplicate step name: {step.name}")
            step_names.add(step.name)

            # Add nested for_each step names
            if step.for_each:
                for nested_step in step.for_each.steps:
                    # Nested steps can have duplicate names (they're scoped)
                    pass

        # Validate goto targets
        for step in workflow.steps:
            if step.on:
                self._validate_goto_targets(step.on, step_names, step.name)

            # Check nested for_each steps
            if step.for_each:
                for nested_step in step.for_each.steps:
                    if nested_step.on:
                        # For nested steps, they can only goto within the loop or _end
                        self._validate_goto_targets(
                            nested_step.on,
                            {s.name for s in step.for_each.steps} | {'_end'},
                            nested_step.name
                        )

        # Validate provider references
        for step in workflow.steps:
            if step.provider and step.provider not in workflow.providers:
                raise ValidationError(
                    f"Step '{step.name}' references unknown provider: {step.provider}"
                )

        # Validate paths (basic check for absolute paths and ..)
        self._validate_paths(workflow)

    def _validate_goto_targets(self, handlers: OnHandlers, valid_targets: Set[str], step_name: str):
        """Validate goto targets exist"""
        valid_targets.add('_end')  # Always allow _end

        if handlers.success and handlers.success.goto not in valid_targets:
            raise ValidationError(
                f"Step '{step_name}' on.success.goto references unknown target: {handlers.success.goto}"
            )

        if handlers.failure and handlers.failure.goto not in valid_targets:
            raise ValidationError(
                f"Step '{step_name}' on.failure.goto references unknown target: {handlers.failure.goto}"
            )

        if handlers.always and handlers.always.goto not in valid_targets:
            raise ValidationError(
                f"Step '{step_name}' on.always.goto references unknown target: {handlers.always.goto}"
            )

    def _validate_paths(self, workflow: WorkflowSpec):
        """Validate path safety constraints"""
        # Check queue directories
        for path_attr in ['processed_dir', 'failed_dir', 'inbox_dir']:
            path_value = getattr(workflow, path_attr)
            self._validate_single_path(path_value, f"workflow.{path_attr}")

        # Check step paths
        for step in workflow.steps:
            if step.input_file:
                self._validate_single_path(step.input_file, f"step '{step.name}' input_file")
            if step.output_file:
                self._validate_single_path(step.output_file, f"step '{step.name}' output_file")
            if step.output_schema:
                self._validate_single_path(step.output_schema, f"step '{step.name}' output_schema")

            # Check dependency paths
            if step.depends_on:
                for req in step.depends_on.required:
                    # Globs are allowed, but still check for absolute/parent
                    if os.path.isabs(req):
                        raise ValidationError(
                            f"Step '{step.name}' depends_on.required has absolute path: {req}"
                        )
                    if '..' in req:
                        raise ValidationError(
                            f"Step '{step.name}' depends_on.required contains '..': {req}"
                        )

                for opt in step.depends_on.optional:
                    if os.path.isabs(opt):
                        raise ValidationError(
                            f"Step '{step.name}' depends_on.optional has absolute path: {opt}"
                        )
                    if '..' in opt:
                        raise ValidationError(
                            f"Step '{step.name}' depends_on.optional contains '..': {opt}"
                        )

    def _validate_single_path(self, path: str, context: str):
        """Validate a single path for safety"""
        # Skip validation if path contains variables (will be validated at runtime)
        if '${' in path:
            return

        # Check for absolute paths
        if os.path.isabs(path):
            raise ValidationError(f"{context} contains absolute path: {path}")

        # Check for parent directory escape
        if '..' in path:
            raise ValidationError(f"{context} contains '..': {path}")

    def compute_checksum(self, workflow_path: Path) -> str:
        """Compute SHA256 checksum of workflow file"""
        with open(workflow_path, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()