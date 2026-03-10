"""
Test AT-72: Provider state persistence.

After executing a provider step, `steps.<Name>` is persisted to `state.json`
with `exit_code`, captured output per mode, and any `error`/`debug` fields.
After reload (`state_manager.load()`), the provider result is present and unchanged.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from orchestrator.state import StateManager, StepResult
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.loader import WorkflowLoader


class TestProviderStatePersistence:
    """Test provider state persistence (AT-72)."""

    def setup_method(self):
        """Set up test workspace."""
        self.test_workspace = Path("/tmp/test_provider_persistence")
        self.test_workspace.mkdir(parents=True, exist_ok=True)

        # Create state directory
        self.state_dir = self.test_workspace / ".orchestrate" / "runs" / "test-run"
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def teardown_method(self):
        """Clean up test workspace."""
        import shutil
        if self.test_workspace.exists():
            shutil.rmtree(self.test_workspace)

    def test_at72_provider_result_persisted(self):
        """AT-72: Provider step results are persisted to state.json."""
        # Create workflow with provider step
        workflow_data = {
            "version": "1.1",
            "steps": [
                {
                    "name": "TestProvider",
                    "provider": "test-provider",
                    "provider_params": {
                        "model": "test-model"
                    },
                    "output_capture": "json"
                }
            ]
        }

        # Write workflow file
        workflow_file = self.test_workspace / "test_workflow.yaml"
        with open(workflow_file, 'w') as f:
            import yaml
            yaml.dump(workflow_data, f)

        # Load workflow
        loader = WorkflowLoader(self.test_workspace)
        workflow = loader.load(workflow_file)

        # Create state manager
        state_manager = StateManager(
            workspace=self.test_workspace,
            run_id="test-run"
        )
        state_manager.initialize(str(workflow_file))

        # Mock provider registry and executor
        with patch('orchestrator.workflow.executor.ProviderRegistry') as MockRegistry:
            with patch('orchestrator.workflow.executor.ProviderExecutor') as MockExecutor:
                # Set up mock provider
                mock_registry = MockRegistry.return_value
                mock_registry.get_provider.return_value = {
                    "template": "echo test",
                    "input_mode": "argv"
                }

                # Set up mock executor with successful result
                mock_executor = MockExecutor.return_value
                mock_invocation = MagicMock()
                mock_executor.prepare_invocation.return_value = (mock_invocation, None)

                # Mock execution result with JSON output
                mock_exec_result = MagicMock()
                mock_exec_result.exit_code = 0
                mock_exec_result.stdout = b'{"result": "test data", "status": "ok"}'
                mock_exec_result.stderr = b""
                mock_exec_result.duration_ms = 100
                mock_exec_result.error = None
                mock_exec_result.missing_placeholders = None
                mock_exec_result.invalid_prompt_placeholder = False
                mock_executor.execute.return_value = mock_exec_result

                # Execute workflow
                executor = WorkflowExecutor(
                    workflow=workflow,
                    workspace=self.test_workspace,
                    state_manager=state_manager
                )

                result_state = executor.execute()

                # Verify result is in memory state
                assert 'steps' in result_state
                assert 'TestProvider' in result_state['steps']
                provider_result = result_state['steps']['TestProvider']

                # Verify the result structure
                assert provider_result['exit_code'] == 0
                assert provider_result['status'] == 'completed'
                assert provider_result['duration_ms'] == 100
                assert provider_result['json'] == {"result": "test data", "status": "ok"}

                # CRITICAL: Load state from disk to verify persistence
                state_manager2 = StateManager(
                    workspace=self.test_workspace,
                    run_id="test-run"
                )
                state_manager2.load()

                # Check that provider result was persisted
                persisted_state = state_manager2.state.to_dict()
                assert 'steps' in persisted_state
                assert 'TestProvider' in persisted_state['steps']

                # Verify persisted result matches original
                persisted_result = persisted_state['steps']['TestProvider']
                assert persisted_result['exit_code'] == 0
                assert persisted_result['status'] == 'completed'
                assert persisted_result['duration_ms'] == 100
                assert persisted_result['json'] == {"result": "test data", "status": "ok"}

    def test_at72_provider_error_persisted(self):
        """AT-72: Provider step error results are persisted with error context."""
        # Create workflow with provider step
        workflow_data = {
            "version": "1.1",
            "steps": [
                {
                    "name": "FailingProvider",
                    "provider": "test-provider",
                    "provider_params": {
                        "model": "test-model"
                    },
                    "output_capture": "text"
                }
            ]
        }

        # Write workflow file
        workflow_file = self.test_workspace / "test_workflow.yaml"
        with open(workflow_file, 'w') as f:
            import yaml
            yaml.dump(workflow_data, f)

        # Load workflow
        loader = WorkflowLoader(self.test_workspace)
        workflow = loader.load(workflow_file)

        # Create state manager
        state_manager = StateManager(
            workspace=self.test_workspace,
            run_id="test-run"
        )
        state_manager.initialize(str(workflow_file))

        # Mock provider registry and executor
        with patch('orchestrator.workflow.executor.ProviderRegistry') as MockRegistry:
            with patch('orchestrator.workflow.executor.ProviderExecutor') as MockExecutor:
                # Set up mock provider
                mock_registry = MockRegistry.return_value
                mock_registry.get_provider.return_value = {
                    "template": "failing command",
                    "input_mode": "argv"
                }

                # Set up mock executor with error result
                mock_executor = MockExecutor.return_value
                mock_invocation = MagicMock()
                mock_executor.prepare_invocation.return_value = (mock_invocation, None)

                # Mock execution result with error
                mock_exec_result = MagicMock()
                mock_exec_result.exit_code = 1
                mock_exec_result.stdout = b"Error message"
                mock_exec_result.stderr = b"Fatal error"
                mock_exec_result.duration_ms = 50
                mock_exec_result.error = {
                    "type": "execution_failed",
                    "message": "Provider execution failed"
                }
                mock_exec_result.missing_placeholders = None
                mock_exec_result.invalid_prompt_placeholder = False
                mock_executor.execute.return_value = mock_exec_result

                # Execute workflow
                executor = WorkflowExecutor(
                    workflow=workflow,
                    workspace=self.test_workspace,
                    state_manager=state_manager
                )

                result_state = executor.execute(on_error='continue')  # Continue on error to complete execution

                # Verify error result is in memory state
                assert 'steps' in result_state
                assert 'FailingProvider' in result_state['steps']
                provider_result = result_state['steps']['FailingProvider']

                # Verify the error result structure
                assert provider_result['exit_code'] == 1
                assert provider_result['status'] == 'failed'
                assert provider_result['duration_ms'] == 50
                assert provider_result['output'] == "Error message"
                assert 'error' in provider_result

                # CRITICAL: Load state from disk to verify persistence
                state_manager2 = StateManager(
                    workspace=self.test_workspace,
                    run_id="test-run"
                )
                state_manager2.load()

                # Check that error result was persisted
                persisted_state = state_manager2.state.to_dict()
                assert 'steps' in persisted_state
                assert 'FailingProvider' in persisted_state['steps']

                # Verify persisted error result matches original
                persisted_result = persisted_state['steps']['FailingProvider']
                assert persisted_result['exit_code'] == 1
                assert persisted_result['status'] == 'failed'
                assert persisted_result['duration_ms'] == 50
                assert persisted_result['output'] == "Error message"
                assert 'error' in persisted_result
                assert persisted_result['error']['type'] == "execution_failed"

    def test_at72_provider_with_debug_fields_persisted(self):
        """AT-72: Provider step with debug fields (e.g., injection) are persisted."""
        # Create workflow with provider step and dependency injection
        workflow_data = {
            "version": "1.1.1",  # Required for injection feature
            "steps": [
                {
                    "name": "ProviderWithInjection",
                    "provider": "test-provider",
                    "provider_params": {
                        "model": "test-model"
                    },
                    "depends_on": {
                        "required": ["test.txt"],
                        "inject": True  # This will add debug.injection metadata
                    },
                    "input_file": "prompt.txt",
                    "output_capture": "lines"
                }
            ]
        }

        # Write workflow file and dependencies
        workflow_file = self.test_workspace / "test_workflow.yaml"
        with open(workflow_file, 'w') as f:
            import yaml
            yaml.dump(workflow_data, f)

        # Create required dependency and prompt files
        (self.test_workspace / "test.txt").write_text("Test content")
        (self.test_workspace / "prompt.txt").write_text("Test prompt")

        # Load workflow
        loader = WorkflowLoader(self.test_workspace)
        workflow = loader.load(workflow_file)

        # Create state manager
        state_manager = StateManager(
            workspace=self.test_workspace,
            run_id="test-run"
        )
        state_manager.initialize(str(workflow_file))

        # Mock provider registry and executor
        with patch('orchestrator.workflow.executor.ProviderRegistry') as MockRegistry:
            with patch('orchestrator.workflow.executor.ProviderExecutor') as MockExecutor:
                # Set up mock provider
                mock_registry = MockRegistry.return_value
                mock_registry.get_provider.return_value = {
                    "template": "echo test",
                    "input_mode": "argv"
                }

                # Set up mock executor
                mock_executor = MockExecutor.return_value
                mock_invocation = MagicMock()
                mock_executor.prepare_invocation.return_value = (mock_invocation, None)

                # Mock execution result
                mock_exec_result = MagicMock()
                mock_exec_result.exit_code = 0
                mock_exec_result.stdout = b"Line 1\nLine 2\nLine 3"
                mock_exec_result.stderr = b""
                mock_exec_result.duration_ms = 75
                mock_exec_result.error = None
                mock_exec_result.missing_placeholders = None
                mock_exec_result.invalid_prompt_placeholder = False
                mock_executor.execute.return_value = mock_exec_result

                # Execute workflow
                executor = WorkflowExecutor(
                    workflow=workflow,
                    workspace=self.test_workspace,
                    state_manager=state_manager
                )

                result_state = executor.execute()

                # Verify result with debug info is in memory state
                assert 'steps' in result_state
                assert 'ProviderWithInjection' in result_state['steps']
                provider_result = result_state['steps']['ProviderWithInjection']

                # Verify the result structure
                assert provider_result['exit_code'] == 0
                assert provider_result['status'] == 'completed'
                assert provider_result['lines'] == ["Line 1", "Line 2", "Line 3"]
                # Debug info may or may not be present depending on injection size

                # CRITICAL: Load state from disk to verify persistence
                state_manager2 = StateManager(
                    workspace=self.test_workspace,
                    run_id="test-run"
                )
                state_manager2.load()

                # Check that result with debug was persisted
                persisted_state = state_manager2.state.to_dict()
                assert 'steps' in persisted_state
                assert 'ProviderWithInjection' in persisted_state['steps']

                # Verify persisted result matches original
                persisted_result = persisted_state['steps']['ProviderWithInjection']
                assert persisted_result['exit_code'] == 0
                assert persisted_result['status'] == 'completed'
                assert persisted_result['lines'] == ["Line 1", "Line 2", "Line 3"]
                # If debug was in original, it should be persisted too
                if 'debug' in provider_result:
                    assert 'debug' in persisted_result
                    assert persisted_result['debug'] == provider_result['debug']

    def test_provider_session_success_persists_metadata_and_published_handle(self):
        """Fresh provider-session visits finalize metadata after state publication."""
        session_script = "\n".join(
            [
                "python - <<'PY'",
                "print('{\"type\":\"session.started\",\"session_id\":\"sess-123\"}')",
                "print('{\"type\":\"assistant.message\",\"role\":\"assistant\",\"text\":\"hello\"}')",
                "print('{\"type\":\"response.completed\",\"session_id\":\"sess-123\"}')",
                "PY",
            ]
        )
        workflow_data = {
            "version": "2.10",
            "providers": {
                "codex_session": {
                    "command": ["bash", "-lc", session_script],
                    "input_mode": "stdin",
                    "session_support": {
                        "metadata_mode": "codex_exec_jsonl_stdout",
                        "fresh_command": ["bash", "-lc", session_script],
                        "resume_command": ["bash", "-lc", session_script + " # ${SESSION_ID}"],
                    },
                }
            },
            "artifacts": {
                "implementation_session_id": {
                    "kind": "scalar",
                    "type": "string",
                }
            },
            "steps": [
                {
                    "name": "AskProvider",
                    "provider": "codex_session",
                    "provider_session": {
                        "mode": "fresh",
                        "publish_artifact": "implementation_session_id",
                    },
                }
            ],
        }

        workflow_file = self.test_workspace / "provider_session_workflow.yaml"
        with open(workflow_file, 'w') as f:
            import yaml
            yaml.dump(workflow_data, f)

        workflow = WorkflowLoader(self.test_workspace).load(workflow_file)
        state_manager = StateManager(workspace=self.test_workspace, run_id="test-run")
        state_manager.initialize(str(workflow_file))

        result_state = WorkflowExecutor(
            workflow=workflow,
            workspace=self.test_workspace,
            state_manager=state_manager,
        ).execute()

        persisted_state = StateManager(
            workspace=self.test_workspace,
            run_id="test-run",
        ).load().to_dict()
        provider_debug = persisted_state["steps"]["AskProvider"]["debug"]["provider_session"]
        metadata_path = Path(provider_debug["metadata_path"])
        transport_spool_path = metadata_path.with_suffix(".transport.log")
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

        assert result_state["steps"]["AskProvider"]["artifacts"] == {
            "implementation_session_id": "sess-123"
        }
        assert provider_debug["publication_state"] == "published"
        assert provider_debug["transport_spool_path"] is None
        assert metadata["step_status"] == "completed"
        assert metadata["publication_state"] == "published"
        assert metadata["session_id"] == "sess-123"
        assert metadata["command_variant"] == "fresh_command"
        assert metadata["metadata_mode"] == "codex_exec_jsonl_stdout"
        assert metadata["transport_spool_path"] is None
        assert metadata["captured_transport_bytes"] > 0
        assert not transport_spool_path.exists()

    def test_provider_session_debug_mode_retains_transport_spool(self):
        """Debug mode keeps the masked per-visit transport spool on successful completion."""
        session_script = "\n".join(
            [
                "python - <<'PY'",
                "print('{\"type\":\"session.started\",\"session_id\":\"sess-123\"}')",
                "print('{\"type\":\"assistant.message\",\"role\":\"assistant\",\"text\":\"hello\"}')",
                "print('{\"type\":\"response.completed\",\"session_id\":\"sess-123\"}')",
                "PY",
            ]
        )
        workflow_data = {
            "version": "2.10",
            "providers": {
                "codex_session": {
                    "command": ["bash", "-lc", session_script],
                    "input_mode": "stdin",
                    "session_support": {
                        "metadata_mode": "codex_exec_jsonl_stdout",
                        "fresh_command": ["bash", "-lc", session_script],
                        "resume_command": ["bash", "-lc", session_script + " # ${SESSION_ID}"],
                    },
                }
            },
            "artifacts": {
                "implementation_session_id": {
                    "kind": "scalar",
                    "type": "string",
                }
            },
            "steps": [
                {
                    "name": "AskProvider",
                    "provider": "codex_session",
                    "provider_session": {
                        "mode": "fresh",
                        "publish_artifact": "implementation_session_id",
                    },
                }
            ],
        }

        workflow_file = self.test_workspace / "provider_session_debug_workflow.yaml"
        with open(workflow_file, 'w') as f:
            import yaml
            yaml.dump(workflow_data, f)

        workflow = WorkflowLoader(self.test_workspace).load(workflow_file)
        state_manager = StateManager(workspace=self.test_workspace, run_id="test-run", debug=True)
        state_manager.initialize(str(workflow_file))

        WorkflowExecutor(
            workflow=workflow,
            workspace=self.test_workspace,
            state_manager=state_manager,
            debug=True,
        ).execute()

        persisted_state = StateManager(
            workspace=self.test_workspace,
            run_id="test-run",
        ).load().to_dict()
        provider_debug = persisted_state["steps"]["AskProvider"]["debug"]["provider_session"]
        metadata_path = Path(provider_debug["metadata_path"])
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        transport_spool_path = Path(metadata["transport_spool_path"])

        assert metadata["publication_state"] == "published"
        assert transport_spool_path.exists()
        assert transport_spool_path.read_text(encoding="utf-8")

    def test_provider_session_updates_metadata_before_deleting_success_spool(self):
        """Successful non-debug finalization updates metadata before deleting the spool."""
        session_script = "\n".join(
            [
                "python - <<'PY'",
                "print('{\"type\":\"session.started\",\"session_id\":\"sess-123\"}')",
                "print('{\"type\":\"assistant.message\",\"role\":\"assistant\",\"text\":\"hello\"}')",
                "print('{\"type\":\"response.completed\",\"session_id\":\"sess-123\"}')",
                "PY",
            ]
        )
        workflow_data = {
            "version": "2.10",
            "providers": {
                "codex_session": {
                    "command": ["bash", "-lc", session_script],
                    "input_mode": "stdin",
                    "session_support": {
                        "metadata_mode": "codex_exec_jsonl_stdout",
                        "fresh_command": ["bash", "-lc", session_script],
                        "resume_command": ["bash", "-lc", session_script + " # ${SESSION_ID}"],
                    },
                }
            },
            "artifacts": {
                "implementation_session_id": {
                    "kind": "scalar",
                    "type": "string",
                }
            },
            "steps": [
                {
                    "name": "AskProvider",
                    "provider": "codex_session",
                    "provider_session": {
                        "mode": "fresh",
                        "publish_artifact": "implementation_session_id",
                    },
                }
            ],
        }

        workflow_file = self.test_workspace / "provider_session_ordering_workflow.yaml"
        with open(workflow_file, 'w') as f:
            import yaml
            yaml.dump(workflow_data, f)

        workflow = WorkflowLoader(self.test_workspace).load(workflow_file)
        state_manager = StateManager(workspace=self.test_workspace, run_id="test-run")
        state_manager.initialize(str(workflow_file))

        observed = {"spool_exists_during_finalize_update": None}
        original_update = state_manager.update_provider_session_metadata

        def recording_update(metadata_path, updates):
            if updates.get("step_status") == "completed" and updates.get("transport_spool_path") is None:
                observed["spool_exists_during_finalize_update"] = Path(metadata_path).with_suffix(
                    ".transport.log"
                ).exists()
            return original_update(metadata_path, updates)

        with patch.object(state_manager, "update_provider_session_metadata", side_effect=recording_update):
            WorkflowExecutor(
                workflow=workflow,
                workspace=self.test_workspace,
                state_manager=state_manager,
            ).execute()

        assert observed["spool_exists_during_finalize_update"] is True
