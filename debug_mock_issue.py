#!/usr/bin/env python3
"""Test the mock issue hypothesis"""

import tempfile
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.state import StateManager

# Create test data
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

# THIS IS THE PROBLEMATIC MOCK FROM THE TEST
captured_stdin = []
def problematic_mock_run(cmd, **kwargs):
    print(f"Mock received input type: {type(kwargs.get('input'))}")
    print(f"Mock received input: {repr(kwargs.get('input'))}")

    if 'input' in kwargs:
        captured_stdin.clear()
        captured_stdin.append(kwargs['input'])

    result = MagicMock()
    result.returncode = 0

    # THIS LINE IS THE PROBLEM!
    # If kwargs['input'] is already bytes, calling .encode() will fail
    try:
        if 'input' in kwargs:
            print(f"About to call .encode() on: {type(kwargs['input'])}")
            stdout_value = kwargs['input'].encode()  # This will fail if input is already bytes!
            print(f"Encode succeeded, result type: {type(stdout_value)}")
        else:
            stdout_value = b''
        result.stdout = stdout_value
    except Exception as e:
        print(f"MOCK ENCODE ERROR: {e}")
        # The mock is failing, but this shouldn't cause the provider to fail
        # The issue is that the exception in the mock is being propagated
        result.stdout = b'mock failed'

    result.stderr = b""
    return result

with patch('subprocess.run', side_effect=problematic_mock_run):
    result = executor.execute()

print(f"\nFinal result: {result}")
print(f"Captured stdin: {captured_stdin}")