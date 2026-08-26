"""
Integration tests for provider functionality with loader and executor.

Tests the complete pipeline from workflow definition to provider execution.
"""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from tests.workflow_fixture_loader import WorkflowLoader
from orchestrator.exceptions import WorkflowValidationError
from orchestrator.providers import (
    ProviderRegistry,
    ProviderExecutor,
    ProviderTemplate,
)
from orchestrator.exec.step_executor import StepExecutor
from tests.workflow_bundle_helpers import thaw_surface_workflow


class TestProviderIntegration:
    """Test provider integration with workflow loader and executor."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir)
        self.loader = WorkflowLoader(self.workspace)

    def write_workflow(self, content: dict) -> Path:
        """Helper to write workflow YAML."""
        path = self.workspace / "workflow.yml"
        with open(path, 'w') as f:
            json.dump(content, f)
        return path

    def test_at8_provider_workflow_loading(self):
        """AT-8: Provider templates load and validate correctly."""
        workflow = {
            "version": "1.1",
            "name": "provider_test",
            "providers": {
                "custom": {
                    "command": ["custom-cli", "-p", "${PROMPT}", "--model", "${model}"],
                    "defaults": {
                        "model": "default-model"
                    },
                    "input_mode": "argv"
                }
            },
            "steps": [{
                "name": "UseProvider",
                "provider": "custom",
                "provider_params": {
                    "model": "override-model"
                },
                "input_file": "prompt.txt"
            }]
        }

        # Create prompt file
        (self.workspace / "prompt.txt").write_text("Test prompt")

        path = self.write_workflow(workflow)
        loaded = self.loader.load(path)
        loaded_workflow = thaw_surface_workflow(loaded)

        assert loaded is not None
        assert "custom" in loaded_workflow["providers"]

        # Check provider was parsed correctly
        custom = loaded_workflow["providers"]["custom"]
        assert custom["command"] == ["custom-cli", "-p", "${PROMPT}", "--model", "${model}"]
        assert custom["defaults"]["model"] == "default-model"
        assert custom.get("input_mode", "argv") == "argv"

    def test_at9_stdin_mode_workflow(self):
        """AT-9: stdin mode provider in workflow."""
        workflow = {
            "version": "1.1",
            "name": "stdin_test",
            "providers": {
                "stdin_tool": {
                    "command": ["tool", "--model", "${model}"],
                    "input_mode": "stdin",
                    "defaults": {
                        "model": "test"
                    }
                }
            },
            "steps": [{
                "name": "StdinStep",
                "provider": "stdin_tool",
                "input_file": "input.txt"
            }]
        }

        (self.workspace / "input.txt").write_text("Input for stdin")
        path = self.write_workflow(workflow)
        loaded = self.loader.load(path)
        loaded_workflow = thaw_surface_workflow(loaded)

        assert loaded is not None
        provider = loaded_workflow["providers"]["stdin_tool"]
        assert provider["input_mode"] == "stdin"

    def test_at49_stdin_prompt_validation_in_workflow(self):
        """AT-49: stdin mode with ${PROMPT} fails validation."""
        workflow = {
            "version": "1.1",
            "name": "invalid_stdin",
            "providers": {
                "bad_stdin": {
                    "command": ["tool", "-p", "${PROMPT}"],  # Invalid in stdin
                    "input_mode": "stdin"
                }
            },
            "steps": [{
                "name": "BadStep",
                "provider": "bad_stdin"
            }]
        }

        path = self.write_workflow(workflow)

        # Should fail validation
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        # Check error mentions the issue
        assert any("${PROMPT} not allowed in stdin mode" in str(err.message)
                  for err in exc_info.value.errors)

    def test_at50_provider_without_prompt_placeholder(self):
        """AT-50: Provider without ${PROMPT} works correctly."""
        workflow = {
            "version": "1.1",
            "name": "no_prompt",
            "providers": {
                "simple": {
                    "command": ["simple-tool", "--config", "${config}"],
                    "defaults": {
                        "config": "/etc/config.yml"
                    }
                }
            },
            "steps": [{
                "name": "SimpleStep",
                "provider": "simple",
                "provider_params": {
                    "config": "/custom/config.yml"
                }
            }]
        }

        path = self.write_workflow(workflow)
        loaded = self.loader.load(path)
        loaded_workflow = thaw_surface_workflow(loaded)

        assert loaded is not None
        step = loaded_workflow["steps"][0]
        assert step["provider"] == "simple"
        assert step["provider_params"]["config"] == "/custom/config.yml"

    def test_at51_provider_params_with_variables(self):
        """AT-51: Provider params support variable substitution."""
        workflow = {
            "version": "1.1",
            "name": "param_vars",
            "context": {
                "base_path": "/workspace"
            },
            "providers": {
                "tool": {
                    "command": ["tool", "--input", "${input_path}", "--output", "${output_path}"]
                }
            },
            "steps": [{
                "name": "VarStep",
                "provider": "tool",
                "provider_params": {
                    "input_path": "${context.base_path}/input.txt",
                    "output_path": "${context.base_path}/output.txt"
                }
            }]
        }

        path = self.write_workflow(workflow)
        loaded = self.loader.load(path)
        loaded_workflow = thaw_surface_workflow(loaded)

        assert loaded is not None
        step = loaded_workflow["steps"][0]
        # Variables in provider_params should be preserved for runtime substitution
        assert "${context.base_path}" in step["provider_params"]["input_path"]

    @patch('subprocess.run')
    def test_complete_provider_execution_flow(self, mock_run):
        """Test complete flow from workflow to execution."""
        # Create workflow with provider
        workflow = {
            "version": "1.1",
            "name": "full_test",
            "providers": {
                "test_cli": {
                    "command": ["test-cli", "-p", "${PROMPT}", "--model", "${model}"],
                    "defaults": {
                        "model": "base-model"
                    }
                }
            },
            "steps": [{
                "name": "TestStep",
                "provider": "test_cli",
                "provider_params": {
                    "model": "custom-model"
                },
                "input_file": "prompt.md",
                "output_file": "output.txt"
            }]
        }

        # Create prompt file
        prompt_file = self.workspace / "prompt.md"
        prompt_file.write_text("Execute this task")

        # Load workflow
        path = self.write_workflow(workflow)
        loaded = self.loader.load(path)
        loaded_workflow = thaw_surface_workflow(loaded)

        # Set up provider registry and executor
        registry = ProviderRegistry()
        registry.register_from_workflow(loaded_workflow["providers"])
        executor = ProviderExecutor(self.workspace, registry)

        # Get step and prepare invocation
        step = loaded_workflow["steps"][0]
        params = {
            "params": step.get("provider_params", {}),
            "input_file": step.get("input_file"),
            "output_file": step.get("output_file")
        }

        # Read prompt content
        prompt_content = prompt_file.read_text()

        # Prepare invocation
        from orchestrator.providers import ProviderParams
        provider_params = ProviderParams(**params)
        invocation, error = executor.prepare_invocation(
            step["provider"],
            provider_params,
            {},  # context
            prompt_content
        )

        assert error is None
        assert invocation is not None

        # Verify command was built correctly
        command_str = " ".join(invocation.command)
        assert "Execute this task" in command_str
        assert "custom-model" in command_str  # Step param overrides default

        # Mock successful execution
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=b"Task completed",
            stderr=b""
        )

        # Execute
        result = executor.execute(invocation)

        assert result.exit_code == 0
        assert result.stdout == b"Task completed"

    def test_builtin_providers_available(self):
        """Test that built-in providers work without workflow definition."""
        workflow = {
            "version": "1.1",
            "name": "builtin_test",
            "steps": [
                {
                    "name": "UseClaude",
                    "provider": "claude",  # Built-in provider
                    "input_file": "prompt.txt"
                },
                {
                    "name": "UseCodex",
                    "provider": "codex",  # Built-in stdin provider
                    "input_file": "prompt.txt"
                }
            ]
        }

        (self.workspace / "prompt.txt").write_text("Test")
        path = self.write_workflow(workflow)
        loaded = self.loader.load(path)
        loaded_workflow = thaw_surface_workflow(loaded)

        assert loaded is not None
        # Built-in providers should work without explicit definition
        assert loaded_workflow["steps"][0]["provider"] == "claude"
        assert loaded_workflow["steps"][1]["provider"] == "codex"


def test_omp_json_transport_end_to_end_execution(tmp_path):
    """Complete OMP JSON transport run: template, prepare, execute, parse."""
    import sys

    from orchestrator.providers import (
        InputMode,
        ProviderParams,
        ProviderSessionMetadataMode,
        ProviderSessionRequest,
    )
    from orchestrator.providers.types import (
        OmpTransportExpectation,
        ProviderInvocation,
    )

    fixture_dir = Path(__file__).parent / "fixtures" / "omp" / "protocol"
    fixture = (fixture_dir / "transient.stdout.jsonl").read_bytes()
    header_id = json.loads(fixture.split(b"\n")[0])["id"]
    expected_binary = {
        "platform": "linux",
        "arch": "x86_64",
        "version": "17.3.4",
        "sha256": "f" * 64,
    }
    frame = {
        "type": "orchestrator.omp_launch.v1",
        "lane": "ambient",
        "persistence": "none",
        "binary": expected_binary,
        "child": {"argv": [], "cwd": "/tmp/work", "env_names": [], "exit_code": 0},
        "session": {
            "id": header_id,
            "visit_key": None,
            "primary_relpath": None,
            "primary_sha256": None,
        },
        "conf": {"manifest_sha256": None},
        "confinement": None,
        "observed": {"advisor_relpaths": [], "child_relpaths": []},
    }
    stream = fixture + json.dumps(frame, separators=(",", ":")).encode() + b"\n"

    template = ProviderTemplate(
        name="omp-e2e",
        command=["python", "-c", "import sys;sys.stdout.buffer.write(%r)" % stream],
        input_mode=InputMode.STDIN,
        command_metadata_mode=ProviderSessionMetadataMode.OMP_JSON_STDOUT.value,
    )
    registry = ProviderRegistry()
    registry.register(template)
    executor = ProviderExecutor(tmp_path, registry)

    invocation, error = executor.prepare_invocation(
        "omp-e2e",
        ProviderParams(),
        {},
        prompt_content="run",
    )
    assert error is None
    assert invocation is not None
    assert (
        invocation.metadata_mode
        == ProviderSessionMetadataMode.OMP_JSON_STDOUT.value
    )

    invocation.omp_transport_expectation = OmpTransportExpectation(
        lane="ambient",
        persistence="none",
        binary=expected_binary,
    )
    result = executor.execute(invocation)

    assert result.exit_code == 0
    assert result.error is None
    assert result.raw_stdout == stream
    assert result.stdout == b"OK"
    assert result.provider_session is not None
    assert result.provider_session["session_id"] == header_id
    assert result.provider_session["event_count"] == 11
    assert result.provider_session["final_model"] == "gpt-5.6-sol"
    assert result.is_promotable is True


def test_omp_fresh_transport_rederives_observed_inventory(tmp_path):
    """Fresh OMP frames re-validate against the real visit inventory (Task 5)."""
    import hashlib
    import sys

    from orchestrator.providers import (
        InputMode,
        ProviderParams,
        ProviderSessionMetadataMode,
    )
    from orchestrator.providers.types import OmpTransportExpectation

    fixture_root = Path(__file__).parent / "fixtures" / "omp"
    stream_path = fixture_root / "protocol" / "fresh-session.stdout.jsonl"
    primary_path = fixture_root / "protocol" / "fresh-session.primary.jsonl"
    fixture = stream_path.read_bytes()
    header_id = json.loads(fixture.split(b"\n")[0])["id"]
    expected_binary = {
        "platform": "linux",
        "arch": "x86_64",
        "version": "17.3.4",
        "sha256": "f" * 64,
    }
    visit_dir = tmp_path / "provider_sessions" / "step-1__v1"
    visit_dir.mkdir(parents=True)
    visit_dir.chmod(0o700)
    journal = f"2026-08-23T22-33-31-340Z_{header_id}.jsonl"
    frame = {
        "type": "orchestrator.omp_launch.v1",
        "lane": "ambient",
        "persistence": "fresh",
        "binary": expected_binary,
        "child": {"argv": ["placeholder"], "cwd": str(tmp_path), "env_names": [], "exit_code": 0},
        "session": {
            "id": header_id,
            "visit_key": "step-1__v1",
            "primary_relpath": journal,
            "primary_sha256": hashlib.sha256(primary_path.read_bytes()).hexdigest(),
        },
        "conf": {"manifest_sha256": None},
        "confinement": None,
        "observed": {
            "advisor_relpaths": [],
            "child_relpaths": [f"{journal[:-6]}/alpha.jsonl"],
        },
    }
    frame_path = tmp_path / "frame.json"
    frame_path.write_text(json.dumps(frame), encoding="utf-8")
    isolated_root = tmp_path / "isolated"
    child_path = tmp_path / "alpha.jsonl"
    child_lines = (
        fixture_root / "sessions" / "alpha.jsonl"
    ).read_text(encoding="utf-8").splitlines()
    child_header = json.loads(child_lines[1])
    child_header["cwd"] = str(isolated_root / "wt-1")
    child_lines[1] = json.dumps(child_header, separators=(",", ":"))
    child_path.write_text("\n".join(child_lines) + "\n", encoding="utf-8")
    script = tmp_path / "child.py"
    script.write_text(
        "import os, sys, json\n"
        "d = sys.argv[1]\n"
        "frame = json.loads(open(sys.argv[2]).read())\n"
        "stream = open(sys.argv[3], 'rb').read()\n"
        "sid = json.loads(stream.split(b'\\n')[0])['id']\n"
        "journal = os.path.join(d, '2026-08-23T22-33-31-340Z_' + sid + '.jsonl')\n"
        "with open(journal, 'wb') as h:\n"
        "    h.write(open(sys.argv[4], 'rb').read())\n"
        "artifacts = journal[:-6]\n"
        "os.mkdir(artifacts)\n"
        "with open(os.path.join(artifacts, 'alpha.jsonl'), 'wb') as h:\n"
        "    h.write(open(sys.argv[5], 'rb').read())\n"
        "sys.stdout.buffer.write(stream + json.dumps(frame, separators=(',', ':')).encode() + b'\\n')\n",
        encoding="utf-8",
    )
    command = [
        sys.executable,
        str(script),
        str(visit_dir),
        str(frame_path),
        str(stream_path),
        str(primary_path),
        str(child_path),
    ]
    frame["child"]["argv"] = command
    frame_path.write_text(json.dumps(frame), encoding="utf-8")
    template = ProviderTemplate(
        name="omp-fresh-e2e",
        command=command,
        input_mode=InputMode.STDIN,
        command_metadata_mode=ProviderSessionMetadataMode.OMP_JSON_STDOUT.value,
    )
    registry = ProviderRegistry()
    registry.register(template)
    executor = ProviderExecutor(tmp_path, registry)

    invocation, error = executor.prepare_invocation(
        "omp-fresh-e2e",
        ProviderParams(),
        {},
        prompt_content="run",
    )
    assert error is None
    assert invocation is not None
    # The workflow parent cannot know the child-generated inventory pre-run.
    invocation.omp_transport_expectation = OmpTransportExpectation(
        lane="ambient",
        persistence="fresh",
        binary=expected_binary,
        visit_key="step-1__v1",
        child_argv=tuple(command),
        observed_relpaths=(),
        isolated_worktree_root=str(isolated_root),
    )
    invocation.provider_session_dir = str(visit_dir)
    result = executor.execute(invocation)

    assert result.exit_code == 0, result.error
    assert result.error is None
    assert result.provider_session is not None
    assert result.provider_session["session_id"] == header_id
    assert result.provider_session["launch_frame"]["session"]["primary_relpath"] == journal


def test_omp_fresh_transport_rejects_fabricated_observed_inventory(tmp_path):
    """Fresh frames claiming files the visit directory never held still fail (Task 5)."""
    import sys

    from orchestrator.providers import (
        InputMode,
        ProviderParams,
        ProviderSessionMetadataMode,
    )
    from orchestrator.providers.types import OmpTransportExpectation

    fixture_dir = Path(__file__).parent / "fixtures" / "omp" / "protocol"
    fixture = (fixture_dir / "transient.stdout.jsonl").read_bytes()
    header_id = json.loads(fixture.split(b"\n")[0])["id"]
    expected_binary = {
        "platform": "linux",
        "arch": "x86_64",
        "version": "17.3.4",
        "sha256": "f" * 64,
    }
    visit_dir = tmp_path / "provider_sessions" / "step-1__v1"
    visit_dir.mkdir(parents=True)
    visit_dir.chmod(0o700)
    frame = {
        "type": "orchestrator.omp_launch.v1",
        "lane": "ambient",
        "persistence": "fresh",
        "binary": expected_binary,
        "child": {"argv": ["placeholder"], "cwd": str(tmp_path), "env_names": [], "exit_code": 0},
        "session": {
            "id": header_id,
            "visit_key": "step-1__v1",
            "primary_relpath": "ghost.jsonl",
            "primary_sha256": "a" * 64,
        },
        "conf": {"manifest_sha256": None},
        "confinement": None,
        "observed": {"advisor_relpaths": [], "child_relpaths": ["ghost.jsonl"]},
    }
    frame_path = tmp_path / "frame.json"
    frame_path.write_text(json.dumps(frame), encoding="utf-8")
    script = tmp_path / "child.py"
    script.write_text(
        "import sys, json\n"
        "frame = json.loads(open(sys.argv[2]).read())\n"
        "stream = open(sys.argv[3], 'rb').read()\n"
        "sys.stdout.buffer.write(stream + json.dumps(frame, separators=(',', ':')).encode() + b'\\n')\n",
        encoding="utf-8",
    )
    command = [sys.executable, str(script), str(visit_dir), str(frame_path), str(fixture_dir / "transient.stdout.jsonl")]
    frame["child"]["argv"] = command
    frame_path.write_text(json.dumps(frame), encoding="utf-8")
    template = ProviderTemplate(
        name="omp-fresh-e2e-ghost",
        command=command,
        input_mode=InputMode.STDIN,
        command_metadata_mode=ProviderSessionMetadataMode.OMP_JSON_STDOUT.value,
    )
    registry = ProviderRegistry()
    registry.register(template)
    executor = ProviderExecutor(tmp_path, registry)

    invocation, error = executor.prepare_invocation(
        "omp-fresh-e2e-ghost",
        ProviderParams(),
        {},
        prompt_content="run",
    )
    assert error is None
    assert invocation is not None
    invocation.omp_transport_expectation = OmpTransportExpectation(
        lane="ambient",
        persistence="fresh",
        binary=expected_binary,
        visit_key="step-1__v1",
        child_argv=tuple(command),
        observed_relpaths=(),
    )
    invocation.provider_session_dir = str(visit_dir)
    result = executor.execute(invocation)

    assert result.exit_code != 0
    assert result.error is not None


# ---------------------------------------------------------------------------
# Task 5 review fix round: finding 11 (post-wrapper child argv freeze)
# ---------------------------------------------------------------------------


def test_omp_prepare_derives_post_wrapper_child_argv(tmp_path):
    """The derived expectation freezes post-wrapper argv (finding 11).

    The adapter frame records ``sys.argv[1:]`` after the code-owned wrapper
    prefix; freezing the full wrapper command would mismatch every production
    frame-vs-expectation comparison.
    """
    import sys

    from orchestrator.providers import (
        InputMode,
        ProviderParams,
        ProviderSessionMetadataMode,
    )

    model = "gpt-5.6-sol"
    template = ProviderTemplate(
        name="omp",
        command=[
            sys.executable,
            "-m",
            "orchestrator.providers.omp_launch",
            "run",
            "--lane",
            "omp",
            "--model",
            model,
        ],
        input_mode=InputMode.STDIN,
        command_metadata_mode=ProviderSessionMetadataMode.OMP_JSON_STDOUT.value,
    )
    registry = ProviderRegistry()
    registry.register(template)
    executor = ProviderExecutor(tmp_path, registry)

    invocation, error = executor.prepare_invocation(
        "omp",
        ProviderParams(),
        {},
        prompt_content="run",
    )
    assert error is None, error
    assert invocation is not None
    expectation = invocation.omp_transport_expectation
    assert expectation is not None, "OMP prepare must derive an expectation"
    assert expectation.lane == "ambient"
    assert expectation.persistence == "none"
    assert expectation.child_argv == ("run", "--lane", "omp", "--model", model)
    assert expectation.child_argv[:3] != (
        sys.executable,
        "-m",
        "orchestrator.providers.omp_launch",
    ), "the wrapper prefix must never be part of the frozen child argv"
    assert expectation.child_argv[0] != sys.executable


def test_omp_prepare_rejects_foreign_wrapper_command(tmp_path):
    """A non-code-owned wrapper prefix fails the derivation closed."""
    import sys

    from orchestrator.providers import (
        InputMode,
        ProviderParams,
        ProviderSessionMetadataMode,
    )

    template = ProviderTemplate(
        name="omp",
        command=["/usr/bin/env", "omp", "run"],
        input_mode=InputMode.STDIN,
        command_metadata_mode=ProviderSessionMetadataMode.OMP_JSON_STDOUT.value,
    )
    registry = ProviderRegistry()
    registry.register(template)
    executor = ProviderExecutor(tmp_path, registry)

    invocation, error = executor.prepare_invocation(
        "omp",
        ProviderParams(),
        {},
        prompt_content="run",
    )
    assert invocation is None
    assert error is not None
    assert "code-owned launch wrapper" in error["message"], error


def test_omp_conf_prepare_admits_the_conf_root_via_an_fd(tmp_path):
    """Finding 10: the conf lane admits the tree through an fd, not a path.

    The old derivation passed the conf_root string into the fd-only
    admit_conf_tree, which raised TypeError and failed every production
    conf-lane prepare.
    """
    import sys

    from orchestrator.providers import (
        InputMode,
        ProviderParams,
        ProviderSessionMetadataMode,
    )
    from orchestrator.providers.omp_launch import neutral_conf_root

    env = {
        "HOME": str(tmp_path),
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "XDG_STATE_HOME": str(tmp_path / "state"),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
        "TMPDIR": str(tmp_path / "tmp"),
    }
    for value in env.values():
        Path(value).mkdir(parents=True, exist_ok=True)
    (tmp_path / ".omp").mkdir()

    template = ProviderTemplate(
        name="omp_conf",
        command=[
            sys.executable,
            "-m",
            "orchestrator.providers.omp_launch",
            "run",
            "--lane",
            "omp_conf",
            "--model",
            "gpt-5.6-sol",
            "--conf-root",
            "${omp_conf_root}",
        ],
        input_mode=InputMode.STDIN,
        command_metadata_mode=ProviderSessionMetadataMode.OMP_JSON_STDOUT.value,
    )
    registry = ProviderRegistry()
    registry.register(template)
    executor = ProviderExecutor(tmp_path, registry)

    invocation, error = executor.prepare_invocation(
        "omp_conf",
        ProviderParams(params={"omp_conf_root": neutral_conf_root()}),
        {},
        prompt_content="run",
        env=env,
    )
    assert error is None, error
    assert invocation is not None
    expectation = invocation.omp_transport_expectation
    assert expectation is not None
    assert expectation.lane == "conf"
    assert expectation.conf_manifest_sha256 is not None
    assert expectation.confinement_policy_sha256 is not None
