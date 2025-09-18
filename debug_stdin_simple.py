#!/usr/bin/env python3
"""Minimal reproduction of stdin encoding issue"""

import tempfile
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.state import StateManager

# Create the exact same setup as the failing test
tmp_path = Path(tempfile.mkdtemp())
workspace = tmp_path / 'workspace'
workspace.mkdir()

prompt_dir = workspace / 'prompts'
prompt_dir.mkdir()

prompt_file = prompt_dir / 'test.md'
prompt_content = 'Analyze ${context.data} using ${loop.index} and ${item}'
prompt_file.write_text(prompt_content)

workflow = {
    'version': '1.1',
    'context': {
        'data': 'important-data'
    },
    'providers': {
        'stdin-provider': {
            'command': ['cat'],
            'input_mode': 'stdin',
            'defaults': {}
        }
    },
    'steps': [
        {
            'name': 'StdinStep',
            'provider': 'stdin-provider',
            'input_file': 'prompts/test.md',
            'output_capture': 'text'
        }
    ]
}

workflow_path = workspace / 'workflow.yaml'
with open(workflow_path, 'w') as f:
    yaml.dump(workflow, f)

state_manager = StateManager(
    workspace=workspace,
    run_id='test-run'
)
state_manager.initialize('workflow.yaml', {'data': 'important-data'})

executor = WorkflowExecutor(
    workflow=workflow,
    workspace=workspace,
    state_manager=state_manager,
    debug=False
)

# Let's intercept the actual execution to see what type the prompt is
original_execute = executor.provider_executor.execute

def debug_execute(invocation):
    print(f"Invocation prompt type: {type(invocation.prompt)}")
    print(f"Invocation prompt: {repr(invocation.prompt)}")
    print(f"Input mode: {invocation.input_mode}")

    # Let the original function handle the rest, but catch the encode error
    try:
        return original_execute(invocation)
    except Exception as e:
        print(f"Error in execute: {e}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        # Return a mock result to continue
        return {'exit_code': 1, 'output': '', 'duration_ms': 0}

executor.provider_executor.execute = debug_execute

result = executor.execute()
print(f"Final result: {result}")