#!/usr/bin/env python3
"""Minimal loop test to understand the issue"""

import tempfile
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.state import StateManager

# Create the simplest possible for_each test
tmp_path = Path(tempfile.mkdtemp())
workspace = tmp_path / 'workspace'
workspace.mkdir()

# Create a very simple workflow exactly like the passing test
workflow = {
    'version': '1.1',
    'steps': [
        {
            'name': 'ProcessItems',
            'for_each': {
                'items': ['alpha', 'beta', 'gamma'],
                'as': 'value'
            },
            'steps': [
                {
                    'name': 'ShowIndex',
                    'command': ['echo', 'Item ${loop.index} of ${loop.total}: ${value}'],
                    'output_capture': 'text'
                }
            ]
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
state_manager.initialize('workflow.yaml', {})

executor = WorkflowExecutor(
    workflow=workflow,
    workspace=workspace,
    state_manager=state_manager,
    debug=False
)

# Simple mock
captured_calls = []
def simple_mock(cmd, **kwargs):
    captured_calls.append(cmd)
    print(f"Command: {cmd}")
    result = MagicMock()
    result.returncode = 0
    result.stdout = b"output"
    result.stderr = b""
    return result

with patch('subprocess.run', side_effect=simple_mock):
    result = executor.execute()

print(f"\nExecution result status: {result.get('status')}")
print(f"Total commands executed: {len(captured_calls)}")

final_state = state_manager.load()
print(f"Steps in final state: {list(final_state.steps.keys())}")

for step_name, step_data in final_state.steps.items():
    print(f"  {step_name}: {step_data.get('status', 'unknown')}")