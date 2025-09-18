#!/usr/bin/env python3
"""Debug the actual test failure"""

import tempfile
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.state import StateManager

# Replicate the exact test setup
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

# Use the EXACT same mock as the test
captured_stdin = []
def mock_run(cmd, **kwargs):
    print(f"mock_run called with cmd: {cmd}")
    print(f"mock_run called with kwargs keys: {list(kwargs.keys())}")
    if 'input' in kwargs:
        print(f"input type: {type(kwargs['input'])}")
        print(f"input value: {repr(kwargs['input'])}")
        captured_stdin.clear()
        captured_stdin.append(kwargs['input'])
    result = MagicMock()
    result.returncode = 0
    result.stdout = kwargs.get('input', '').encode() if 'input' in kwargs else b''
    result.stderr = b""
    return result

# Let me also intercept the provider executor to see what's happening
original_execute = executor.provider_executor.execute

def debug_execute(invocation):
    print(f"\n=== PROVIDER EXECUTE ===")
    print(f"Invocation prompt type: {type(invocation.prompt)}")
    print(f"Invocation prompt: {repr(invocation.prompt)}")
    print(f"Input mode: {invocation.input_mode}")

    try:
        result = original_execute(invocation)
        print(f"Provider execute result: {result}")
        return result
    except Exception as e:
        print(f"Error in provider execute: {e}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        raise

executor.provider_executor.execute = debug_execute

with patch('subprocess.run', side_effect=mock_run):
    result = executor.execute()

print(f"\nFinal result: {result}")
print(f"Captured stdin: {captured_stdin}")