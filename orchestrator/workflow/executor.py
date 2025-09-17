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
from ..security.secrets import SecretsManager


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
        self.dependency_resolver = DependencyResolver(workspace)
        self.dependency_injector = DependencyInjector(workspace)

        # Execution state
        self.current_step = 0
        self.steps = workflow.get('steps', [])
        self.variables = workflow.get('variables', {})
        self.global_secrets = workflow.get('secrets', [])

        # Retry configuration
        self.max_retries = max_retries
        self.retry_delay_ms = retry_delay_ms

    def execute(self, run_id: str = None, on_error: str = 'stop',
                max_retries: int = None, retry_delay_ms: int = None) -> Dict[str, Any]:
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
        if isinstance(command, list):
            command = ' '.join(command)

        # Apply variable substitution (simplified for this implementation)
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

        Args:
            step: Step definition
            context: Variable context for substitution
            state: Current state

        Returns:
            Execution result as dict
        """
        # Get prompt if specified
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
        result = None

        while True:
            # Execute provider
            result = self.provider_executor.execute(
                step_name=step.get('name', 'provider'),
                provider_name=step['provider'],
                prompt=prompt,
                provider_params=step.get('provider_params', {}),
                env=step.get('env'),
                timeout_sec=step.get('timeout_sec'),
                output_capture=step.get('output_capture', 'text'),
                output_file=Path(step['output_file']) if 'output_file' in step else None,
                allow_parse_error=step.get('allow_parse_error', False)
            )

            # Check if should retry
            if retry_policy.should_retry(result.exit_code, attempt):
                if self.debug:
                    print(f"Provider failed with exit code {result.exit_code}, retrying (attempt {attempt + 1}/{retry_policy.max_retries})")
                retry_policy.wait()
                attempt += 1
                continue

            # No retry needed or max retries reached
            break

        return result.to_state_dict()

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