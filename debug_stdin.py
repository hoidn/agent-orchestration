#!/usr/bin/env python3
"""Debug stdin mode issue"""

import tempfile
import yaml
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.state import StateManager

# Create test setup
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

# Mock subprocess to see what's happening
captured_calls = []

def mock_run(cmd, **kwargs):
    call_info = {
        'cmd': cmd,
        'kwargs': kwargs
    }
    captured_calls.append(call_info)
    print(f"Command: {cmd}")
    print(f"Input: {kwargs.get('input', 'NO INPUT')}")
    print(f"Text mode: {kwargs.get('text', False)}")

    result = MagicMock()
    result.returncode = 0
    result.stdout = kwargs.get('input', '').encode() if 'input' in kwargs else b''
    result.stderr = b""
    return result

with patch('subprocess.run', side_effect=mock_run):
    executor = WorkflowExecutor(
        workflow=workflow,
        workspace=workspace,
        state_manager=state_manager,
        debug=False
    )

    result = executor.execute()

    print(f"\nFinal result: {result}")

    state = state_manager.load()
    print(f"State status: {state.status}")

    if state.steps and 'StdinStep' in state.steps:
        step_result = state.steps['StdinStep']
        print(f"Step result: {step_result}")

    print(f"\nAll captured calls: {len(captured_calls)}")
    for i, call in enumerate(captured_calls):
        print(f"Call {i}: {call}")