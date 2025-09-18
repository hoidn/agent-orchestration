#!/usr/bin/env python3
"""Trace the exact location of encode error"""

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

# Override the provider executor to add detailed logging
import orchestrator.providers.executor as prov_exec

original_execute = prov_exec.ProviderExecutor.execute

def traced_execute(self, invocation):
    print(f"\n=== TRACED EXECUTE START ===")
    print(f"invocation.prompt type: {type(invocation.prompt)}")
    print(f"invocation.prompt: {repr(invocation.prompt)}")
    print(f"invocation.input_mode: {invocation.input_mode}")

    # Manually replicate what should happen
    print("\n--- Manual stdin preparation ---")
    stdin_input = None
    if invocation.input_mode.value == 'stdin' and invocation.prompt:  # Use .value to get string
        print(f"About to encode prompt of type: {type(invocation.prompt)}")
        try:
            stdin_input = invocation.prompt.encode('utf-8')
            print(f"Successfully encoded to: {type(stdin_input)}")
        except Exception as e:
            print(f"Encoding failed: {e}")
            print(f"Exception type: {type(e)}")
            import traceback
            traceback.print_exc()
            return {
                'exit_code': 1,
                'stdout': b'',
                'stderr': str(e).encode('utf-8'),
                'duration_ms': 0
            }

    print(f"stdin_input: {repr(stdin_input)}")

    # Call original and see what happens
    print("\n--- Calling original execute ---")
    try:
        return original_execute(self, invocation)
    except Exception as e:
        print(f"Original execute failed: {e}")
        import traceback
        traceback.print_exc()
        raise

prov_exec.ProviderExecutor.execute = traced_execute

# Simple mock that won't interfere
def simple_mock_run(cmd, **kwargs):
    return MagicMock(returncode=0, stdout=b'output', stderr=b'')

with patch('subprocess.run', side_effect=simple_mock_run):
    result = executor.execute()

print(f"\nFinal result status: {result.get('status')}")