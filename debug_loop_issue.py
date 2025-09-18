#!/usr/bin/env python3
"""Debug the loop execution issue"""

import tempfile
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.state import StateManager

# Create test setup identical to failing test
tmp_path = Path(tempfile.mkdtemp())
workspace = tmp_path / 'workspace'
workspace.mkdir()

prompt_dir = workspace / 'prompts'
prompt_dir.mkdir()

prompt_file = prompt_dir / 'loop.md'
prompt_content = 'Process item ${item} at index ${loop.index} of ${loop.total}'
prompt_file.write_text(prompt_content)

workflow = {
    'version': '1.1',
    'providers': {
        'test-provider': {
            'command': ['echo', '${PROMPT}'],
            'input_mode': 'argv',
            'defaults': {}
        }
    },
    'steps': [
        {
            'name': 'ProcessItems',
            'for_each': {
                'items': ['apple', 'banana', 'cherry']
            },
            'steps': [
                {
                    'name': 'ProcessOne',
                    'provider': 'test-provider',
                    'input_file': 'prompts/loop.md',
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

# Debug mock to see what's happening
captured_calls = []
def debug_mock_run(cmd, **kwargs):
    call_info = {
        'cmd': cmd,
        'cwd': kwargs.get('cwd', 'none'),
        'type': 'subprocess_call'
    }
    captured_calls.append(call_info)
    print(f"subprocess.run called: {cmd}")

    result = MagicMock()
    result.returncode = 0
    result.stdout = b"output"
    result.stderr = b""
    return result

with patch('subprocess.run', side_effect=debug_mock_run):
    result = executor.execute()

print(f"\nExecution result: {result}")
print(f"Total subprocess calls: {len(captured_calls)}")

for i, call in enumerate(captured_calls):
    print(f"Call {i}: {call}")

# Check the state to see what steps were processed
final_state = state_manager.load()
print(f"\nFinal state steps: {list(final_state.steps.keys())}")

for step_name, step_result in final_state.steps.items():
    print(f"  {step_name}: {step_result.get('status', 'unknown')}")