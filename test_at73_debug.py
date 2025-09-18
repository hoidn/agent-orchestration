#!/usr/bin/env python3
"""Debug AT-73 issue"""

import tempfile
import yaml
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.state import StateManager
from orchestrator.providers.executor import ProviderExecutor

tmp_path = Path(tempfile.mkdtemp())
workspace = tmp_path / 'workspace'
workspace.mkdir()

prompt_dir = workspace / 'prompts'
prompt_dir.mkdir()

prompt_file = prompt_dir / 'test.md'
prompt_content = 'Process this ${context.project}'
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
            'name': 'TestStep',
            'provider': 'test-provider',
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
state_manager.initialize('workflow.yaml', {})

# Mock subprocess to see what command is built
original_run = __import__('subprocess').run
commands_executed = []

def mock_run(cmd, **kwargs):
    commands_executed.append(cmd)
    print(f"Command executed: {cmd}")
    result = MagicMock()
    result.returncode = 0
    result.stdout = b"mocked output"
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

    # Get the actual run state
    state = state_manager.load()

    print(f"Run status from state: {state.status}")
    print(f"Result variable type: {type(result)}")
    print(f"Result variable: {result}")

    if state.steps and 'TestStep' in state.steps:
        step_result = state.steps['TestStep']
        print(f"Step result: {step_result}")

    if commands_executed:
        print(f"Commands: {commands_executed}")
    else:
        print("No commands were executed!")