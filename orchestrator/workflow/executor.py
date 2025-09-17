"""
Workflow executor with for-each loop support.
Implements AT-3, AT-13: Dynamic for-each execution with pointer resolution.
"""

import copy
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..state import StateManager
from ..exec.step_executor import StepExecutor, ExecutionResult
from ..exec.retry import RetryPolicy
from ..providers.executor import ProviderExecutor
from ..providers.registry import ProviderRegistry
from ..deps.resolver import DependencyResolver
from ..deps.injector import DependencyInjector
from .pointers import PointerResolver
from .conditions import ConditionEvaluator
from ..security.secrets import SecretsManager
from ..variables.substitution import VariableSubstitutor


class WorkflowExecutor:
    """
    Main workflow execution engine.
    Handles sequential execution, for-each loops, and control flow.
    """

    def __init__(
        self,
        workflow: Dict[str, Any],
        workspace: Path,
        state_manager: StateManager,
        logs_dir: Optional[Path] = None,
        debug: bool = False,
        max_retries: int = 0,
        retry_delay_ms: int = 1000
    ):
        """
        Initialize workflow executor.

        Args:
            workflow: Validated workflow dictionary
            workspace: Base workspace directory
            state_manager: State persistence manager
            logs_dir: Directory for logs
            debug: Enable debug mode
        """
        self.workflow = workflow
        self.workspace = workspace
        self.state_manager = state_manager
        self.debug = debug

        # Initialize secrets manager
        self.secrets_manager = SecretsManager()

        # Initialize provider registry (load from workflow providers if present)
        self.provider_registry = ProviderRegistry()
        if 'providers' in workflow:
            errors = self.provider_registry.register_from_workflow(workflow['providers'])
            if errors:
                raise ValueError(f"Provider registration errors: {'; '.join(errors)}")

        # Initialize sub-executors
        self.step_executor = StepExecutor(workspace, logs_dir, self.secrets_manager)
        self.provider_executor = ProviderExecutor(workspace, self.provider_registry, self.secrets_manager)
        self.dependency_resolver = DependencyResolver(str(workspace))
        self.dependency_injector = DependencyInjector(str(workspace))
        self.condition_evaluator = ConditionEvaluator(workspace)
        self.variable_substitutor = VariableSubstitutor()

        # Execution state
        self.current_step = 0
        self.steps = workflow.get('steps', [])
        self.variables = workflow.get('variables', {})
        self.global_secrets = workflow.get('secrets', [])

        # Retry configuration
        self.max_retries = max_retries
        self.retry_delay_ms = retry_delay_ms

    def execute(self, run_id: Optional[str] = None, on_error: str = 'stop',
                max_retries: Optional[int] = None, retry_delay_ms: Optional[int] = None) -> Dict[str, Any]:
        """
        Execute the workflow.

        Args:
            run_id: Run identifier
            on_error: Error handling mode ('stop' or 'continue')
            max_retries: Maximum retry attempts (overrides constructor value)
            retry_delay_ms: Retry delay in milliseconds (overrides constructor value)

        Returns:
            Final execution state
        """
        # Override retry config if provided
        if max_retries is not None:
            self.max_retries = max_retries
        if retry_delay_ms is not None:
            self.retry_delay_ms = retry_delay_ms
        # Load current state
        run_state = self.state_manager.load()

        # Convert to dict format for internal processing
        state = run_state.to_dict()

        # Execute steps sequentially
        for step_index, step in enumerate(self.steps):
            self.current_step = step_index

            # Check if step should be executed
            step_name = step.get('name', f'step_{step_index}')

            # Check conditional execution (AT-37, AT-46, AT-47)
            if 'when' in step:
                # Build variables for condition evaluation
                variables = self.variable_substitutor.build_variables(
                    run_state=state,
                    context=self.workflow.get('context', {})
                )

                # Evaluate condition
                try:
                    should_execute = self.condition_evaluator.evaluate(step['when'], variables)
                except Exception as e:
                    # Condition evaluation error - record and skip
                    result = {
                        'status': 'failed',
                        'exit_code': 2,
                        'error': {
                            'message': f"Condition evaluation failed: {e}",
                            'context': {'condition': step['when']}
                        }
                    }
                    if 'steps' not in state:
                        state['steps'] = {}
                    state['steps'][step_name] = result
                    continue

                if not should_execute:
                    # AT-37: Condition false -> step skipped with exit_code 0
                    result = {
                        'status': 'skipped',
                        'exit_code': 0,
                        'skipped': True
                    }
                    if 'steps' not in state:
                        state['steps'] = {}
                    state['steps'][step_name] = result
                    continue

            # Execute based on step type
            if 'for_each' in step:
                state = self._execute_for_each(step, state)
            elif 'wait_for' in step:
                state = self._execute_wait_for(step, state)
            elif 'provider' in step:
                result = self._execute_provider(step, state)
                # Store result in state
                if 'steps' not in state:
                    state['steps'] = {}
                state['steps'][step_name] = result
            elif 'command' in step:
                result = self._execute_command(step, state)
                # Store result in state
                if 'steps' not in state:
                    state['steps'] = {}
                state['steps'][step_name] = result

        return state

    def _execute_for_each(self, step: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a for_each loop step.
        Implements AT-3: Dynamic for-each with items_from.
        Implements AT-13: Pointer grammar for nested JSON paths.

        Args:
            step: Step definition with for_each
            state: Current execution state

        Returns:
            Updated state after loop execution
        """
        step_name = step.get('name', f'step_{self.current_step}')
        for_each = step['for_each']

        # Resolve items to iterate over
        if 'items_from' in for_each:
            # AT-3: Dynamic items from pointer
            pointer_resolver = PointerResolver(state)
            try:
                items = pointer_resolver.resolve(for_each['items_from'])
            except ValueError as e:
                # Record error and fail
                state = self._record_step_error(
                    state, step_name,
                    exit_code=2,
                    error={
                        'message': f"Failed to resolve items_from pointer: {e}",
                        'context': {
                            'pointer': for_each['items_from'],
                            'error': str(e)
                        }
                    }
                )
                return state

            # Verify resolved value is an array
            if not isinstance(items, list):
                state = self._record_step_error(
                    state, step_name,
                    exit_code=2,
                    error={
                        'message': f"items_from must resolve to an array, got {type(items).__name__}",
                        'context': {
                            'pointer': for_each['items_from'],
                            'resolved_type': type(items).__name__
                        }
                    }
                )
                return state
        else:
            # Static items list
            items = for_each.get('items', [])

        # Get loop configuration
        item_var = for_each.get('as', 'item')
        loop_steps = for_each.get('steps', [])

        # Initialize loop state
        if 'steps' not in state:
            state['steps'] = {}

        # Prepare loop state storage (indexed by iteration)
        # Format: steps.<LoopName>[i].<StepName>
        loop_results = []

        # Execute loop iterations
        for index, item in enumerate(items):
            # Setup loop scope variables
            loop_context = {
                'item': item,  # Current item
                item_var: item,  # Custom alias if specified
                'loop': {
                    'index': index,
                    'total': len(items)
                }
            }

            # Execute nested steps for this iteration
            iteration_state = {}
            for nested_step in loop_steps:
                nested_name = nested_step.get('name', f'nested_{index}')

                # Check conditional execution within loop (AT-37, AT-46, AT-47)
                if 'when' in nested_step:
                    # Build variables for condition evaluation (including loop scope)
                    variables = self.variable_substitutor.build_variables(
                        run_state=state,
                        context=self.workflow.get('context', {}),
                        loop_vars=loop_context.get('loop', {}),
                        item=item
                    )

                    # Evaluate condition
                    try:
                        should_execute = self.condition_evaluator.evaluate(nested_step['when'], variables)
                    except Exception as e:
                        # Condition evaluation error
                        result = {
                            'status': 'failed',
                            'exit_code': 2,
                            'error': {
                                'message': f"Condition evaluation failed: {e}",
                                'context': {'condition': nested_step['when']}
                            }
                        }
                        iteration_state[nested_name] = result
                        continue

                    if not should_execute:
                        # Condition false -> step skipped
                        result = {
                            'status': 'skipped',
                            'exit_code': 0,
                            'skipped': True
                        }
                        iteration_state[nested_name] = result
                        continue

                # Create a modified context with loop variables
                nested_context = self._create_loop_context(nested_step, loop_context, state)

                # Execute the nested step based on its type
                if 'command' in nested_step:
                    result = self._execute_command_with_context(nested_step, nested_context, state)
                elif 'provider' in nested_step:
                    result = self._execute_provider_with_context(nested_step, nested_context, state)
                else:
                    # Other step types within loops
                    result = {'exit_code': 0, 'skipped': True}

                # Store in iteration state
                iteration_state[nested_name] = result

            # Store iteration results in indexed format
            loop_results.append(iteration_state)

        # Update state with loop results
        # Store as steps.<LoopName> = [{iteration_0}, {iteration_1}, ...]
        state['steps'][step_name] = loop_results

        # Also store flattened format for compatibility
        # steps.<LoopName>[i].<StepName> = result
        for i, iteration in enumerate(loop_results):
            for nested_name, result in iteration.items():
                indexed_key = f"{step_name}[{i}].{nested_name}"
                state['steps'][indexed_key] = result

                # Update state manager with each loop step result (AT-43)
                from ..state import StepResult
                exit_code = result.get('exit_code', 0)
                step_result = StepResult(
                    status='completed' if exit_code == 0 else 'failed',
                    exit_code=exit_code,
                    output=result.get('output'),
                    lines=result.get('lines'),
                    json=result.get('json'),
                    error=result.get('error'),
                    truncated=result.get('truncated', False)
                )
                self.state_manager.update_loop_step(step_name, i, nested_name, step_result)

        return state

    def _execute_command_with_context(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any],
        state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a command step with variable substitution context.
        Implements AT-21: Raw commands only retry when retries field is set.

        Args:
            step: Step definition
            context: Variable context for substitution
            state: Current state

        Returns:
            Execution result as dict
        """
        # Substitute variables in command
        command = step['command']

        # Apply variable substitution based on command type
        if isinstance(command, list):
            # For list commands, substitute each element individually
            command = [self._substitute_variables(elem, context, state) for elem in command]
        else:
            # For string commands, substitute the entire string
            command = self._substitute_variables(command, context, state)

        # Create retry policy for command steps (AT-21)
        retries_config = step.get('retries')
        retry_policy = RetryPolicy.for_command(retries_config)

        # Execute with retries
        attempt = 0
        result = None

        while True:
            # Execute command
            result = self.step_executor.execute_command(
                step_name=step.get('name', 'command'),
                command=command,
                env=step.get('env'),
                timeout_sec=step.get('timeout_sec'),
                output_capture=step.get('output_capture', 'text'),
                output_file=Path(step['output_file']) if 'output_file' in step else None,
                allow_parse_error=step.get('allow_parse_error', False)
            )

            # Check if should retry
            if retry_policy.should_retry(result.exit_code, attempt):
                if self.debug:
                    print(f"Command failed with exit code {result.exit_code}, retrying (attempt {attempt + 1}/{retry_policy.max_retries})")
                retry_policy.wait()
                attempt += 1
                continue

            # No retry needed or max retries reached
            break

        # Ensure result is not None before calling to_state_dict()
        if result is None:
            return {
                'status': 'failed',
                'exit_code': 1,
                'error': {'message': 'Command execution failed with no result'}
            }

        return result.to_state_dict()

    def _execute_provider_with_context(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any],
        state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a provider step with variable substitution context.
        Implements AT-21: Provider steps retry on exit codes 1 and 124 by default.
        Implements AT-28-35,53: Dependency injection with debug record.

        Args:
            step: Step definition
            context: Variable context for substitution
            state: Current state

        Returns:
            Execution result as dict
        """
        # Initialize debug info dict for injection metadata
        debug_info = {}

        # Handle dependencies if specified (AT-22-27)
        if 'depends_on' in step:
            depends_on = step['depends_on']

            # Build variables dict for substitution
            substitution_vars = self._build_substitution_variables(context, state)

            # Resolve dependencies using the correct API
            resolution = self.dependency_resolver.resolve(
                depends_on=depends_on,
                variables=substitution_vars
            )

            # Check for validation errors (missing required dependencies)
            if not resolution.is_valid:
                # Missing required dependencies - exit code 2
                return {
                    'status': 'failed',
                    'exit_code': 2,
                    'error': {
                        'type': 'dependency_validation',
                        'message': 'Missing required dependencies',
                        'context': {
                            'missing_dependencies': resolution.errors
                        }
                    }
                }

            # Get all resolved files in deterministic order
            all_files = resolution.files

            # Apply dependency injection if configured (AT-28-35,53)
            inject_config = depends_on.get('inject', False)
            if inject_config:
                # Get original prompt
                prompt = ""
                if 'input_file' in step:
                    input_path = self.workspace / step['input_file']
                    if input_path.exists():
                        prompt = input_path.read_text()

                # Apply variable substitution to prompt before injection
                prompt = self._substitute_variables(prompt, context, state)

                # Perform injection (use whether we had required deps)
                has_required = 'required' in depends_on and len(depends_on['required']) > 0
                injection_result = self.dependency_injector.inject(
                    prompt=prompt,
                    files=all_files,
                    inject_config=inject_config,
                    is_required=has_required
                )

                # Use the modified prompt
                prompt = injection_result.modified_prompt

                # Record truncation details if present (AT-35)
                if injection_result.was_truncated and injection_result.truncation_details:
                    debug_info['injection'] = injection_result.truncation_details
        else:
            # No dependencies - just get prompt normally
            prompt = ""
            if 'input_file' in step:
                input_path = self.workspace / step['input_file']
                if input_path.exists():
                    prompt = input_path.read_text()

            # Apply variable substitution to prompt
            prompt = self._substitute_variables(prompt, context, state)

        # Create retry policy for provider steps (AT-21)
        # Providers use global max_retries or step-specific retries
        if 'retries' in step:
            retry_policy = RetryPolicy.for_command(step['retries'])
        else:
            retry_policy = RetryPolicy.for_provider(
                max_retries=self.max_retries,
                delay_ms=self.retry_delay_ms
            )

        # Execute with retries
        attempt = 0
        result: Optional[Dict[str, Any]] = None

        # Build context for provider parameter substitution (AT-44)
        # This should include all variable namespaces
        provider_context = self._create_provider_context(context, state)

        # Import types
        from ..providers.types import ProviderParams
        from ..exec.output_capture import OutputCapture, CaptureResult

        while True:
            # Prepare provider invocation
            params = ProviderParams(
                params=step.get('provider_params', {}),
                input_file=step.get('input_file'),
                output_file=step.get('output_file')
            )

            invocation, error = self.provider_executor.prepare_invocation(
                provider_name=step['provider'],
                params=params,
                context=provider_context,
                prompt_content=prompt,
                env=step.get('env'),
                secrets=step.get('secrets'),
                timeout_sec=step.get('timeout_sec')
            )

            if error or invocation is None:
                # Invocation preparation failed
                return {
                    'status': 'failed',
                    'exit_code': 2,
                    'error': error or {'message': 'Failed to create provider invocation'}
                }

            # Execute the prepared invocation
            exec_result = self.provider_executor.execute(invocation)

            # Capture output according to specified mode
            capture_mode = step.get('output_capture', 'text')
            allow_parse_error = step.get('allow_parse_error', False)
            output_file = Path(step['output_file']) if 'output_file' in step else None

            capturer = OutputCapture(
                workspace=self.workspace,
                logs_dir=self.state_manager.logs_dir if hasattr(self.state_manager, 'logs_dir') else None
            )

            # Convert mode string to CaptureMode enum
            from ..exec.output_capture import CaptureMode
            if capture_mode == 'text':
                mode = CaptureMode.TEXT
            elif capture_mode == 'lines':
                mode = CaptureMode.LINES
            else:
                mode = CaptureMode.JSON

            capture_result = capturer.capture(
                stdout=exec_result.stdout,
                stderr=exec_result.stderr,
                step_name=step.get('name', 'provider'),
                mode=mode,
                output_file=output_file,
                allow_parse_error=allow_parse_error,
                exit_code=exec_result.exit_code
            )

            # Build result dict
            result = {
                'status': 'completed' if exec_result.exit_code == 0 else 'failed',
                'exit_code': exec_result.exit_code,
                'duration_ms': exec_result.duration_ms
            }

            # Add captured output
            result.update(capture_result.to_state_dict())

            # Add error info if present
            if exec_result.error:
                result['error'] = exec_result.error
            elif exec_result.missing_placeholders:
                result['error'] = {
                    'message': 'Missing placeholders in provider template',
                    'context': {
                        'missing_placeholders': exec_result.missing_placeholders
                    }
                }
            elif exec_result.invalid_prompt_placeholder:
                result['error'] = {
                    'message': 'Invalid ${PROMPT} placeholder in stdin mode',
                    'context': {
                        'invalid_prompt_placeholder': True
                    }
                }

            # Check if should retry
            if retry_policy.should_retry(exec_result.exit_code, attempt):
                if self.debug:
                    print(f"Provider failed with exit code {exec_result.exit_code}, retrying (attempt {attempt + 1}/{retry_policy.max_retries})")
                retry_policy.wait()
                attempt += 1
                continue

            # No retry needed or max retries reached
            break

        # Ensure result is not None before returning
        if result is None:
            return {
                'status': 'failed',
                'exit_code': 1,
                'error': {'message': 'Provider execution failed with no result'}
            }

        # Add debug info if present (AT-35: injection truncation metadata)
        if debug_info:
            result['debug'] = debug_info

        return result

    def _create_loop_context(
        self,
        step: Dict[str, Any],
        loop_context: Dict[str, Any],
        state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create variable substitution context for a loop iteration.

        Args:
            step: Step being executed
            loop_context: Loop-specific variables
            state: Current state

        Returns:
            Combined context dictionary
        """
        # Combine contexts (loop vars override globals)
        # Get run metadata from current state
        run_state = self.state_manager.load()
        run_metadata = {
            'id': run_state.run_id,
            'timestamp_utc': run_state.started_at
        }

        context = {
            'run': run_metadata,
            'context': self.variables,
            'steps': state.get('steps', {}),
            **loop_context  # Loop vars override
        }
        return context

    def _create_provider_context(
        self,
        context: Dict[str, Any],
        state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create context for provider parameter substitution.

        Ensures all variable namespaces are available for AT-44.

        Args:
            context: Current execution context
            state: Current state

        Returns:
            Combined context for provider params
        """
        # Ensure we have all namespaces available
        run_state = self.state_manager.load()
        provider_context = {
            'run': {
                'id': run_state.run_id,
                'timestamp_utc': run_state.started_at,
                'root': str(self.state_manager.run_root) if hasattr(self.state_manager, 'run_root') else ''
            },
            'context': context.get('context', self.variables),
            'steps': state.get('steps', {})
        }

        # Add loop variables if present
        if 'loop' in context:
            provider_context['loop'] = context['loop']
        if 'item' in context:
            provider_context['item'] = context['item']

        return provider_context

    def _build_substitution_variables(self, context: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, str]:
        """Build variables dict for dependency pattern substitution.

        Args:
            context: Context with run/context/loop namespaces
            state: Current state

        Returns:
            Flattened dict of variable name to value for substitution
        """
        # Flatten the context structure for substitution
        variables = {}

        # Add run namespace
        if 'run' in context:
            for key, value in context['run'].items():
                variables[f'run.{key}'] = str(value)

        # Add context namespace
        if 'context' in context:
            for key, value in context['context'].items():
                variables[f'context.{key}'] = str(value)

        # Add loop namespace if present
        if 'loop' in context:
            for key, value in context['loop'].items():
                variables[f'loop.{key}'] = str(value)

        # Add item if present
        if 'item' in context:
            variables['item'] = str(context['item'])

        return variables

    def _substitute_variables(
        self,
        text: str,
        context: Dict[str, Any],
        state: Dict[str, Any]
    ) -> str:
        """
        Perform variable substitution in text.

        Args:
            text: Text with ${var} placeholders
            context: Variable context
            state: Current state

        Returns:
            Text with variables substituted
        """
        import re

        def replacer(match):
            var_path = match.group(1)
            # Simple dot notation traversal
            parts = var_path.split('.')
            value = context

            for part in parts:
                if isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    # Variable not found, leave as-is
                    return match.group(0)

            return str(value)

        # Replace ${var.path} patterns
        return re.sub(r'\$\{([^}]+)\}', replacer, text)

    def _record_step_error(
        self,
        state: Dict[str, Any],
        step_name: str,
        exit_code: int,
        error: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Record a step execution error in state.

        Args:
            state: Current state
            step_name: Name of failed step
            exit_code: Exit code
            error: Error details

        Returns:
            Updated state
        """
        if 'steps' not in state:
            state['steps'] = {}

        state['steps'][step_name] = {
            'exit_code': exit_code,
            'error': error,
            'failed': True
        }

        return state

    # Stub implementations for other step types
    def _execute_wait_for(self, step: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute wait_for step (already implemented in fsq module)."""
        # This would integrate with fsq.wait.WaitFor
        return state

    def _execute_provider(self, step: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute provider step without loop context."""
        return self._execute_provider_with_context(step, {}, state)

    def _execute_command(self, step: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute command step without loop context."""
        return self._execute_command_with_context(step, {}, state)