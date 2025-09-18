"""
Workflow executor with for-each loop support.
Implements AT-3, AT-13: Dynamic for-each execution with pointer resolution.
"""

import copy
import logging
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

logger = logging.getLogger(__name__)


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
                max_retries: Optional[int] = None, retry_delay_ms: Optional[int] = None,
                resume: bool = False) -> Dict[str, Any]:
        """
        Execute the workflow.

        Args:
            run_id: Run identifier
            on_error: Error handling mode ('stop' or 'continue')
            max_retries: Maximum retry attempts (overrides constructor value)
            retry_delay_ms: Retry delay in milliseconds (overrides constructor value)
            resume: If True, skip already completed steps

        Returns:
            Final execution state
        """
        # Override retry config if provided
        if max_retries is not None:
            self.max_retries = max_retries
        if retry_delay_ms is not None:
            self.retry_delay_ms = retry_delay_ms

        # Store resume flag for nested methods
        self.resume_mode = resume
        # Load current state
        run_state = self.state_manager.load()

        # Convert to dict format for internal processing
        state = run_state.to_dict()

        # Execute steps with control flow support
        step_index = 0
        while step_index < len(self.steps):
            step = self.steps[step_index]
            self.current_step = step_index

            # Check if step should be executed
            step_name = step.get('name', f'step_{step_index}')

            # Check if step is already completed (for resume)
            if resume and 'steps' in state and step_name in state['steps']:
                step_result = state['steps'][step_name]
                # For for-each loops, check if it's an array of results
                if isinstance(step_result, list):
                    # Check if all iterations are complete
                    all_complete = all(
                        isinstance(iteration, dict) and
                        iteration.get('status') in ['completed', 'skipped']
                        for iteration in step_result
                        if isinstance(iteration, dict)
                    )
                    if all_complete:
                        logger.info(f"Skipping already completed for-each step: {step_name}")
                        step_index += 1
                        continue
                    # Partially complete for-each will be handled by _execute_for_each
                elif isinstance(step_result, dict):
                    status = step_result.get('status')
                    if status in ['completed', 'skipped']:
                        logger.info(f"Skipping already {status} step: {step_name}")
                        step_index += 1
                        continue
                    elif status == 'failed' and on_error == 'stop':
                        logger.info(f"Step {step_name} previously failed, retrying")
                        # Continue to retry the failed step

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
                    error_info = {
                        'message': f"Condition evaluation failed: {e}",
                        'context': {'condition': step['when']}
                    }
                    result = {
                        'status': 'failed',
                        'exit_code': 2,
                        'error': error_info
                    }
                    if 'steps' not in state:
                        state['steps'] = {}
                    state['steps'][step_name] = result

                    # Persist to state manager
                    from ..state import StepResult
                    step_result = StepResult(
                        status='failed',
                        exit_code=2,
                        error=error_info
                    )
                    self.state_manager.update_step(step_name, step_result)

                    step_index += 1
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

                    # Persist to state manager
                    from ..state import StepResult
                    step_result = StepResult(
                        status='skipped',
                        exit_code=0,
                        skipped=True
                    )
                    self.state_manager.update_step(step_name, step_result)

                    step_index += 1
                    continue

            # AT-69: Create backup before step execution if debug enabled
            if self.debug:
                self.state_manager.backup_state(step_name)

            # Execute based on step type
            if 'for_each' in step:
                state = self._execute_for_each(step, state, resume=resume)
                # Persist the for_each summary array to state manager
                # The for_each method already updates individual iteration results,
                # but we also need to persist the summary array result
                if step_name in state['steps']:
                    loop_results = state['steps'][step_name]
                    # Update state manager with the loop results array
                    # This ensures the array is persisted to disk and tests can access
                    # state['steps']['ProcessFiles'] as expected
                    if isinstance(loop_results, list):
                        self.state_manager.update_loop_results(step_name, loop_results)
            elif 'wait_for' in step:
                state = self._execute_wait_for(step, state)
            elif 'provider' in step:
                result = self._execute_provider(step, state)
                # Store result in state
                if 'steps' not in state:
                    state['steps'] = {}
                state['steps'][step_name] = result

                # Update state manager (persist to disk) - AT-72
                from ..state import StepResult
                step_result = StepResult(
                    status='completed' if result.get('exit_code') == 0 else 'failed',
                    exit_code=result.get('exit_code', 0),
                    duration_ms=result.get('duration_ms', 0),
                    output=result.get('output'),
                    lines=result.get('lines'),
                    json=result.get('json'),
                    error=result.get('error'),
                    truncated=result.get('truncated', False),
                    debug=result.get('debug')  # Include debug fields for injection metadata
                )
                self.state_manager.update_step(step_name, step_result)
            elif 'command' in step:
                result = self._execute_command(step, state)
                # Store result in state
                if 'steps' not in state:
                    state['steps'] = {}
                state['steps'][step_name] = result

                # Update state manager (persist to disk)
                from ..state import StepResult
                step_result = StepResult(
                    status='completed' if result.get('exit_code') == 0 else 'failed',
                    exit_code=result.get('exit_code', 0),
                    duration_ms=result.get('duration_ms', 0),
                    output=result.get('output'),
                    lines=result.get('lines'),
                    json=result.get('json'),
                    error=result.get('error'),
                    truncated=result.get('truncated', False)
                )
                self.state_manager.update_step(step_name, step_result)

            # Handle control flow after step execution (AT-56, AT-57, AT-58)
            next_step = self._handle_control_flow(step, state, step_name, step_index, on_error)

            if next_step == '_end':
                # Special target to end workflow successfully
                break
            elif next_step == '_stop':
                # Stop execution due to error with strict_flow
                return state
            elif isinstance(next_step, int):
                # Jump to specific step index
                step_index = next_step
            else:
                # Continue to next step
                step_index += 1

        # Update run status to completed when workflow finishes successfully
        self.state_manager.update_status('completed')
        # Return the updated state
        return self.state_manager.load().to_dict()

    def _write_prompt_audit(self, step_name: str, prompt_text: str, secrets: Optional[List[str]] = None, env: Optional[Dict[str, str]] = None) -> None:
        """
        Write prompt to audit log with secrets masking.

        AT-70: With --debug, composed prompt text is written to logs/<Step>.prompt.txt
        with known secret values masked.

        Args:
            step_name: Name of the step
            prompt_text: The composed prompt text to audit
            secrets: List of secret names to resolve and mask
            env: Environment variables that may override secrets
        """
        if not self.state_manager.logs_dir:
            return

        # Get the secrets manager to mask known secrets
        secrets_manager = self.step_executor.secrets_manager

        # Resolve secrets to get their values tracked for masking
        if secrets or env:
            secrets_context = secrets_manager.resolve_secrets(
                declared_secrets=secrets,
                step_env=env
            )
            # Note: The resolve call adds the secret values to the manager's masked_values set

        # Mask known secrets in the prompt
        masked_prompt = secrets_manager.mask_text(prompt_text)

        # Write to logs/<Step>.prompt.txt
        prompt_file = self.state_manager.logs_dir / f"{step_name}.prompt.txt"
        prompt_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            prompt_file.write_text(masked_prompt)
        except Exception as e:
            # Log but don't fail if we can't write the audit file
            if self.debug:
                print(f"Warning: Could not write prompt audit for {step_name}: {e}")

    def _handle_control_flow(self, step: Dict[str, Any], state: Dict[str, Any],
                            step_name: str, current_index: int, on_error: str) -> Any:
        """
        Handle control flow after step execution.

        Implements:
        - AT-56: Strict flow stop - non-zero exit halts run when no goto and on_error=stop
        - AT-57: on_error continue - with --on-error continue, run proceeds after non-zero
        - AT-58: Goto precedence - on.success/failure execute before strict_flow applies
        - AT-59: Goto always ordering - on.always evaluated after success/failure handlers

        Returns:
            - '_end': terminate workflow successfully
            - '_stop': stop workflow due to error
            - int: jump to specific step index
            - None: continue to next step
        """
        # Get step result
        step_result = state.get('steps', {}).get(step_name, {})

        # Handle for-each loops (which return a list of results)
        if isinstance(step_result, list):
            # For for-each loops, control flow doesn't apply to individual iterations
            # The loop as a whole is considered successful if it completes
            return None  # Continue to next step

        # Handle regular steps (which return a dict)
        if not isinstance(step_result, dict):
            return None  # No result yet, continue

        exit_code = step_result.get('exit_code', 0)

        # Check if step was skipped (conditional execution)
        if step_result.get('skipped'):
            return None  # Continue to next step

        # AT-58, AT-59: Check on.success/on.failure handlers first, then on.always (with precedence)
        if 'on' in step:
            handlers = step['on']
            goto_target = None

            # Determine which handler applies based on exit code
            if exit_code == 0 and 'success' in handlers:
                if 'goto' in handlers['success']:
                    goto_target = handlers['success']['goto']
            elif exit_code != 0 and 'failure' in handlers:
                if 'goto' in handlers['failure']:
                    goto_target = handlers['failure']['goto']

            # AT-59: on.always evaluated after success/failure and overrides them
            if 'always' in handlers:
                if 'goto' in handlers['always']:
                    goto_target = handlers['always']['goto']

            # If we found a goto target, use it
            if goto_target:
                return self._resolve_goto_target(goto_target)

        # AT-56, AT-57: Apply strict_flow and on_error behavior
        # Only if no goto handler was found
        if exit_code != 0:
            strict_flow = self.workflow.get('strict_flow', True)

            if strict_flow and on_error == 'stop':
                # AT-56: Strict flow stop - halt on non-zero exit
                logger.error(f"Step '{step_name}' failed with exit code {exit_code}. "
                           f"Stopping execution (strict_flow=true, on_error=stop)")
                return '_stop'
            elif on_error == 'continue':
                # AT-57: Continue despite error
                logger.warning(f"Step '{step_name}' failed with exit code {exit_code}. "
                             f"Continuing execution (on_error=continue)")
                return None

        # Default: continue to next step
        return None

    def _resolve_goto_target(self, target: str) -> Any:
        """
        Resolve a goto target to a step index or special value.

        Args:
            target: Target step name or '_end'

        Returns:
            - '_end' for workflow termination
            - int for step index
            - None if target not found (should not happen if validation passed)
        """
        if target == '_end':
            return '_end'

        # Find step index by name
        for i, step in enumerate(self.steps):
            if step.get('name') == target:
                return i

        # This should not happen if validation passed
        logger.error(f"Goto target '{target}' not found")
        return None

    def _execute_for_each(self, step: Dict[str, Any], state: Dict[str, Any], resume: bool = False) -> Dict[str, Any]:
        """
        Execute a for_each loop step.
        Implements AT-3: Dynamic for-each with items_from.
        Implements AT-13: Pointer grammar for nested JSON paths.

        Args:
            step: Step definition with for_each
            state: Current execution state
            resume: If True, skip already completed iterations

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

        # Check for existing partial results (for resume)
        start_index = 0
        if resume and step_name in state['steps']:
            existing_results = state['steps'][step_name]
            if isinstance(existing_results, list):
                # Count completed iterations
                for i, iteration_result in enumerate(existing_results):
                    if isinstance(iteration_result, dict):
                        # Check if this iteration has all steps complete
                        all_steps_complete = True
                        for nested_step in loop_steps:
                            nested_name = nested_step.get('name', f'step_{i}')
                            iteration_key = f"{step_name}[{i}].{nested_name}"
                            if iteration_key in state['steps']:
                                nested_status = state['steps'][iteration_key].get('status')
                                if nested_status not in ['completed', 'skipped']:
                                    all_steps_complete = False
                                    break
                            else:
                                all_steps_complete = False
                                break

                        if all_steps_complete:
                            loop_results.append(iteration_result)
                            start_index = i + 1
                            logger.info(f"Skipping completed iteration {i} of {step_name}")
                        else:
                            # Start from this incomplete iteration
                            start_index = i
                            break

        # Execute loop iterations (starting from start_index for resume)
        for index in range(start_index, len(items)):
            item = items[index]
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
                # AT-65: Pass iteration_state to ensure loop scoping of steps.* variables
                nested_context = self._create_loop_context(nested_step, loop_context, iteration_state)

                # AT-69: Create backup for loop steps if debug enabled
                if self.debug:
                    backup_name = f"{step_name}[{index}].{nested_name}"
                    self.state_manager.backup_state(backup_name)

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
        Implements AT-63: Undefined variable detection with error context.

        Args:
            step: Step definition
            context: Variable context for substitution
            state: Current state

        Returns:
            Execution result as dict
        """
        # Substitute variables in command
        command = step['command']

        # Build variables from all sources
        # AT-65: Use context's steps for loop scoping (contains only current iteration)
        scoped_state = state.copy()
        if 'steps' in context:
            # Inside loop: use scoped steps from context (current iteration only)
            scoped_state['steps'] = context['steps']

        variables = self.variable_substitutor.build_variables(
            run_state=scoped_state,
            context=context.get('context', {}),
            loop_vars=context.get('loop'),
            item=context.get('item')
        )

        # Add any custom loop variables (e.g., from for_each with "as: filename")
        # These come directly in the context, not under any namespace
        for key, value in context.items():
            if key not in ['run', 'context', 'steps', 'loop', 'item']:
                # This is likely a custom loop variable
                variables[key] = value

        # Apply variable substitution with error tracking (AT-63)
        try:
            if isinstance(command, list):
                # For list commands, substitute each element individually
                substituted_command = []
                for elem in command:
                    substituted_elem = self.variable_substitutor.substitute(elem, variables)
                    substituted_command.append(substituted_elem)
                command = substituted_command
            else:
                # For string commands, substitute the entire string
                command = self.variable_substitutor.substitute(command, variables)
        except ValueError as e:
            # AT-63: Undefined variable detected, return error without executing
            undefined_vars = list(self.variable_substitutor.undefined_vars)

            # Build substituted command for error context (best effort with undefined vars)
            try:
                # Try substituting without tracking undefined to show what we could substitute
                if isinstance(step['command'], list):
                    substituted_cmd = []
                    for elem in step['command']:
                        # Substitute without error tracking
                        subst = self.variable_substitutor.substitute(elem, variables, track_undefined=False)
                        substituted_cmd.append(subst)
                else:
                    substituted_cmd = self.variable_substitutor.substitute(
                        step['command'], variables, track_undefined=False
                    )
            except:
                substituted_cmd = step['command']

            return {
                'exit_code': 2,
                'error': {
                    'type': 'undefined_variables',
                    'message': f'Undefined variables in command: {", ".join(undefined_vars)}',
                    'context': {
                        'undefined_vars': undefined_vars,
                        'substituted_command': substituted_cmd if isinstance(substituted_cmd, list) else [substituted_cmd]
                    }
                },
                'output': '',
                'duration_ms': 0
            }

        # Create retry policy for command steps (AT-21)
        retries_config = step.get('retries')
        retry_policy = RetryPolicy.for_command(retries_config)

        # Execute with retries
        attempt = 0
        result = None

        while True:
            # Apply variable substitution to output_file if present
            output_file = None
            if 'output_file' in step:
                output_file_str = self.variable_substitutor.substitute(step['output_file'], variables)
                output_file = Path(output_file_str)

            # Convert output_capture string to CaptureMode enum
            from ..exec.output_capture import CaptureMode
            capture_mode_str = step.get('output_capture', 'text')
            if capture_mode_str == 'text':
                capture_mode = CaptureMode.TEXT
            elif capture_mode_str == 'lines':
                capture_mode = CaptureMode.LINES
            else:
                capture_mode = CaptureMode.JSON

            # Execute command
            result = self.step_executor.execute_command(
                step_name=step.get('name', 'command'),
                command=command,
                env=step.get('env'),
                timeout_sec=step.get('timeout_sec'),
                output_capture=capture_mode,
                output_file=output_file,
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

        # Initialize prompt variable (will be set based on dependencies or input_file)
        prompt = ""

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

            # Get original prompt (needed whether or not we inject)
            if 'input_file' in step:
                input_path = self.workspace / step['input_file']
                if input_path.exists():
                    prompt = input_path.read_text()

            # Apply variable substitution to prompt
            # Build variables for substitution
            # AT-65: Use context's steps for loop scoping (contains only current iteration)
            scoped_state = state.copy()
            if 'steps' in context:
                # Inside loop: use scoped steps from context (current iteration only)
                scoped_state['steps'] = context['steps']

            variables = self.variable_substitutor.build_variables(
                run_state=scoped_state,
                context=context.get('context', {}),
                loop_vars=context.get('loop'),
                item=context.get('item')
            )

            # Add any custom loop variables
            for key, value in context.items():
                if key not in ['run', 'context', 'steps', 'loop', 'item']:
                    variables[key] = value

            # AT-73: Do NOT substitute variables in prompt text (input_file contents are literal)
            # The spec states: "input_file: read literal contents; no substitution inside file contents"
            # prompt = self.variable_substitutor.substitute(prompt, variables, track_undefined=False)

            # Apply dependency injection if configured (AT-28-35,53)
            inject_config = depends_on.get('inject', False)
            if inject_config:
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

            # AT-70: Prompt audit with debug mode (after injection if applicable)
            if self.debug and prompt:
                self._write_prompt_audit(step.get('name', 'provider'), prompt, step.get('secrets'), step.get('env'))
        else:
            # No dependencies - just get prompt normally
            prompt = ""
            if 'input_file' in step:
                input_path = self.workspace / step['input_file']
                if input_path.exists():
                    prompt = input_path.read_text()

            # Apply variable substitution to prompt
            # Build variables for substitution
            # AT-65: Use context's steps for loop scoping (contains only current iteration)
            scoped_state = state.copy()
            if 'steps' in context:
                # Inside loop: use scoped steps from context (current iteration only)
                scoped_state['steps'] = context['steps']

            variables = self.variable_substitutor.build_variables(
                run_state=scoped_state,
                context=context.get('context', {}),
                loop_vars=context.get('loop'),
                item=context.get('item')
            )

            # Add any custom loop variables
            for key, value in context.items():
                if key not in ['run', 'context', 'steps', 'loop', 'item']:
                    variables[key] = value

            # AT-73: Do NOT substitute variables in prompt text (input_file contents are literal)
            # The spec states: "input_file: read literal contents; no substitution inside file contents"
            # prompt = self.variable_substitutor.substitute(prompt, variables, track_undefined=False)

        # AT-70: Prompt audit with debug mode (when no dependencies)
        if self.debug and prompt:
            self._write_prompt_audit(step.get('name', 'provider'), prompt, step.get('secrets'), step.get('env'))

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

            # Apply variable substitution to output_file if present
            output_file = None
            if 'output_file' in step:
                output_file_str = self.variable_substitutor.substitute(step['output_file'], variables)
                output_file = Path(output_file_str)

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
        iteration_state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create variable substitution context for a loop iteration.
        Implements AT-65: Inside for_each, ${steps.<Name>.*} refers only to current iteration.

        Args:
            step: Step being executed
            loop_context: Loop-specific variables (item, loop.index, loop.total)
            iteration_state: Current iteration's step results only

        Returns:
            Combined context dictionary
        """
        # Combine contexts (loop vars override globals)
        # Get run metadata from current state
        run_state = self.state_manager.load()
        run_metadata = {
            'id': run_state.run_id,
            'root': run_state.run_root,  # Include run.root for AT-64
            'timestamp_utc': run_state.started_at
        }

        # AT-65: Use iteration_state for steps.* variables to ensure loop scoping
        context = {
            'run': run_metadata,
            'context': self.variables,
            'steps': iteration_state,  # Only current iteration's results
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
                'root': run_state.run_root or ''  # Use run_root from state
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
        """Execute wait_for step and record results in state (AT-60)."""
        step_name = step['name']
        wait_config = step.get('wait_for', {})

        # Call the StepExecutor to execute the wait_for
        result = self.step_executor.execute_wait_for(step_name, wait_config)

        # Get the wait-specific state dict (has custom to_state_dict method)
        step_result = result.to_state_dict()

        # Add status field based on exit code
        step_result['status'] = 'completed' if result.exit_code == 0 else 'failed'

        # Update state with the result
        state['steps'][step_name] = step_result

        # Persist to state manager
        from ..state import StepResult
        if result.exit_code == 0:
            status = 'completed'
        else:
            status = 'failed'

        state_result = StepResult(
            status=status,
            exit_code=step_result.get('exit_code', 0),
            duration_ms=step_result.get('wait_duration_ms', 0),
            # Add the wait_for specific fields to the state
            files=step_result.get('files', []),
            wait_duration_ms=step_result.get('wait_duration_ms', 0),
            poll_count=step_result.get('poll_count', 0),
            timed_out=step_result.get('timed_out', False)
        )

        if step_result.get('error'):
            state_result.error = step_result['error']

        self.state_manager.update_step(step_name, state_result)

        return state

    def _execute_provider(self, step: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute provider step without loop context."""
        context = {'context': state.get('context', {})}
        return self._execute_provider_with_context(step, context, state)

    def _execute_command(self, step: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute command step without loop context."""
        context = {'context': state.get('context', {})}
        return self._execute_command_with_context(step, context, state)