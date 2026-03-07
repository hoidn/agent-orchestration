"""Tests for loader DSL validation per specs/dsl.md and acceptance tests."""

import pytest
import tempfile
import yaml
from pathlib import Path

from orchestrator.loader import WorkflowLoader
from orchestrator.exceptions import WorkflowValidationError


class TestLoaderValidation:
    """Test strict DSL validation in the loader."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir)
        self.loader = WorkflowLoader(self.workspace)

    def write_workflow(self, content: dict) -> Path:
        """Helper to write workflow YAML."""
        path = self.workspace / "workflow.yml"
        with open(path, 'w') as f:
            yaml.dump(content, f)
        return path

    def test_at7_env_namespace_rejected(self):
        """AT-7: ${env.*} namespace rejected by schema validator."""
        workflow = {
            "version": "1.1",
            "name": "test",
            "steps": [{
                "name": "step1",
                "command": ["echo", "${env.HOME}"]  # Not allowed
            }]
        }

        path = self.write_workflow(workflow)

        # Should raise WorkflowValidationError
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2

        # Verify error message
        assert any("${env.*} namespace not allowed" in str(err.message)
                  for err in exc_info.value.errors)

    def test_at7_env_in_provider_params_rejected(self):
        """AT-7: ${env.*} rejected in provider_params."""
        workflow = {
            "version": "1.1",
            "name": "test",
            "providers": {
                "claude": {
                    "command": ["claude", "code"]
                }
            },
            "steps": [{
                "name": "step1",
                "provider": "claude",
                "provider_params": {
                    "model": "${env.MODEL}"  # Not allowed
                }
            }]
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("${env.*} namespace not allowed" in str(err.message)
                  for err in exc_info.value.errors)

    def test_at10_provider_command_exclusivity(self):
        """AT-10: Provider/Command exclusivity - validation error when both present."""
        workflow = {
            "version": "1.1",
            "name": "test",
            "providers": {
                "claude": {
                    "command": ["claude"]
                }
            },
            "steps": [{
                "name": "invalid_step",
                "provider": "claude",  # Can't have both
                "command": ["echo", "test"]  # Can't have both
            }]
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("mutually exclusive" in str(err.message)
                  for err in exc_info.value.errors)

    def test_at36_wait_for_exclusivity(self):
        """AT-36: wait_for cannot be combined with command/provider/for_each."""
        workflow = {
            "version": "1.1",
            "name": "test",
            "steps": [{
                "name": "invalid_wait",
                "wait_for": {
                    "patterns": ["*.txt"],
                    "timeout_sec": 10
                },
                "command": ["echo", "test"]  # Can't combine with wait_for
            }]
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("wait_for cannot be combined" in str(err.message)
                  for err in exc_info.value.errors)

    def test_assert_requires_version_1_5(self):
        """Assert steps are gated to v1.5+."""
        workflow = {
            "version": "1.4",
            "name": "assert-gated",
            "steps": [{
                "name": "Gate",
                "assert": {
                    "equals": {
                        "left": "APPROVE",
                        "right": "APPROVE",
                    }
                },
            }],
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("assert requires version '1.5'" in str(err.message)
                  for err in exc_info.value.errors)

    def test_assert_is_exclusive_with_other_step_execution_fields(self):
        """Assert steps cannot also declare command/provider/wait_for/for_each."""
        workflow = {
            "version": "1.5",
            "name": "invalid-assert-step",
            "steps": [{
                "name": "Gate",
                "assert": {
                    "equals": {
                        "left": "APPROVE",
                        "right": "APPROVE",
                    }
                },
                "command": ["echo", "unexpected"],
            }],
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("assert cannot be combined" in str(err.message)
                  for err in exc_info.value.errors)

    def test_scalar_bookkeeping_requires_version_1_7(self):
        """Scalar bookkeeping steps are gated to v1.7+."""
        workflow = {
            "version": "1.6",
            "name": "scalar-bookkeeping-gated",
            "artifacts": {
                "failed_count": {
                    "kind": "scalar",
                    "type": "integer",
                }
            },
            "steps": [{
                "name": "Initialize",
                "set_scalar": {
                    "artifact": "failed_count",
                    "value": 0,
                },
            }],
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("set_scalar requires version '1.7'" in str(err.message)
                  for err in exc_info.value.errors)

    def test_set_scalar_requires_declared_scalar_artifact(self):
        """Scalar bookkeeping must target a declared top-level scalar artifact."""
        workflow = {
            "version": "1.7",
            "name": "missing-scalar-artifact",
            "artifacts": {},
            "steps": [{
                "name": "Initialize",
                "set_scalar": {
                    "artifact": "failed_count",
                    "value": 0,
                },
            }],
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("declared scalar artifact" in str(err.message)
                  for err in exc_info.value.errors)

    def test_max_transitions_requires_version_1_8(self):
        """Cycle guards are gated to v1.8+."""
        workflow = {
            "version": "1.7",
            "name": "cycle-guard-gated",
            "max_transitions": 3,
            "steps": [{
                "name": "RunCheck",
                "command": ["bash", "-lc", "exit 1"],
            }],
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("max_transitions requires version '1.8'" in str(err.message)
                  for err in exc_info.value.errors)

    def test_step_ids_require_version_2_0(self):
        """Authored stable ids are gated to the post-Task-6 DSL boundary."""
        workflow = {
            "version": "1.8",
            "name": "id-gated",
            "steps": [{
                "name": "RunCheck",
                "id": "run_check",
                "command": ["echo", "ok"],
            }],
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("id requires version '2.0'" in str(err.message)
                  for err in exc_info.value.errors)

    def test_v2_scoped_refs_allow_self_and_parent_in_nested_steps(self):
        """v2.0 typed refs can address the current loop scope and its parent."""
        workflow = {
            "version": "2.0",
            "name": "scoped-refs",
            "artifacts": {
                "root_flag": {
                    "kind": "scalar",
                    "type": "bool",
                },
                "iteration_flag": {
                    "kind": "scalar",
                    "type": "bool",
                },
            },
            "steps": [
                {
                    "name": "RootFlag",
                    "id": "root_flag",
                    "set_scalar": {
                        "artifact": "root_flag",
                        "value": True,
                    },
                },
                {
                    "name": "Loop",
                    "id": "loop",
                    "for_each": {
                        "items": ["one"],
                        "steps": [
                            {
                                "name": "SetIterationFlag",
                                "id": "set_iteration_flag",
                                "set_scalar": {
                                    "artifact": "iteration_flag",
                                    "value": True,
                                },
                            },
                            {
                                "name": "AssertScopes",
                                "id": "assert_scopes",
                                "assert": {
                                    "all_of": [
                                        {
                                            "artifact_bool": {
                                                "ref": "self.steps.SetIterationFlag.artifacts.iteration_flag",
                                            }
                                        },
                                        {
                                            "artifact_bool": {
                                                "ref": "parent.steps.RootFlag.artifacts.root_flag",
                                            }
                                        },
                                    ]
                                },
                            },
                        ],
                    },
                },
            ],
        }

        path = self.write_workflow(workflow)
        loaded = self.loader.load(path)

        loop_step = loaded["steps"][1]
        assert loop_step["step_id"] == "root.loop"
        assert loop_step["for_each"]["steps"][0]["step_id"] == "root.loop.set_iteration_flag"
        assert loop_step["for_each"]["steps"][1]["step_id"] == "root.loop.assert_scopes"

    def test_step_id_stability_from_authored_ids_survives_sibling_insertion(self):
        """Authored ids keep internal step ids stable when siblings are inserted."""
        workflow_a = {
            "version": "2.0",
            "name": "stable-ids-a",
            "steps": [
                {
                    "name": "Prepare",
                    "id": "prepare",
                    "command": ["echo", "prepare"],
                },
                {
                    "name": "Loop",
                    "id": "loop",
                    "for_each": {
                        "items": ["one"],
                        "steps": [
                            {
                                "name": "Process",
                                "id": "process",
                                "command": ["echo", "process"],
                            }
                        ],
                    },
                },
            ],
        }
        workflow_b = {
            "version": "2.0",
            "name": "stable-ids-b",
            "steps": [
                {
                    "name": "Inserted",
                    "id": "inserted",
                    "command": ["echo", "inserted"],
                },
                *workflow_a["steps"],
            ],
        }

        path_a = self.write_workflow(workflow_a)
        loaded_a = self.loader.load(path_a)
        path_b = self.write_workflow(workflow_b)
        loaded_b = self.loader.load(path_b)

        assert loaded_a["steps"][1]["step_id"] == "root.loop"
        assert loaded_b["steps"][2]["step_id"] == "root.loop"
        assert loaded_a["steps"][1]["for_each"]["steps"][0]["step_id"] == "root.loop.process"
        assert loaded_b["steps"][2]["for_each"]["steps"][0]["step_id"] == "root.loop.process"

    def test_for_each_steps_reject_max_visits_before_stable_ids_land(self):
        """Cycle guards are limited to top-level steps in the first tranche."""
        workflow = {
            "version": "1.8",
            "name": "nested-cycle-guard",
            "steps": [{
                "name": "Loop",
                "for_each": {
                    "items": ["a"],
                    "steps": [{
                        "name": "NestedCheck",
                        "max_visits": 2,
                        "command": ["bash", "-lc", "printf '%s' '${item}'"],
                    }],
                },
            }],
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("max_visits is only supported on top-level steps" in str(err.message)
                  for err in exc_info.value.errors)

    def test_at38_absolute_path_rejected(self):
        """AT-38: Absolute paths rejected at validation."""
        workflow = {
            "version": "1.1",
            "name": "test",
            "steps": [{
                "name": "step1",
                "command": ["cat"],
                "input_file": "/etc/passwd"  # Absolute path not allowed
            }]
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("absolute paths not allowed" in str(err.message)
                  for err in exc_info.value.errors)

    def test_at39_parent_escape_rejected(self):
        """AT-39: Parent directory traversal rejected."""
        workflow = {
            "version": "1.1",
            "name": "test",
            "steps": [{
                "name": "step1",
                "command": ["cat"],
                "output_file": "../outside.txt"  # Parent escape not allowed
            }]
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("parent directory traversal" in str(err.message)
                  for err in exc_info.value.errors)

    def test_at40_deprecated_override_rejected(self):
        """AT-40: Deprecated command_override usage rejected."""
        workflow = {
            "version": "1.1",
            "name": "test",
            "steps": [{
                "name": "step1",
                "command": ["echo"],
                "command_override": "echo test"  # Deprecated, must reject
            }]
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("deprecated 'command_override' not supported" in str(err.message)
                  for err in exc_info.value.errors)

    def test_strict_unknown_fields_rejected(self):
        """Strict validation: unknown fields rejected."""
        workflow = {
            "version": "1.1",
            "name": "test",
            "unknown_field": "value",  # Not a valid field
            "steps": [{
                "name": "step1",
                "command": ["echo", "test"]
            }]
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("Unknown field 'unknown_field'" in str(err.message)
                  for err in exc_info.value.errors)

    def test_goto_target_validation(self):
        """Goto targets must exist."""
        workflow = {
            "version": "1.1",
            "name": "test",
            "steps": [{
                "name": "step1",
                "command": ["test", "-f", "file.txt"],
                "on": {
                    "failure": {
                        "goto": "nonexistent_step"  # Must exist
                    }
                }
            }]
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("unknown target 'nonexistent_step'" in str(err.message)
                  for err in exc_info.value.errors)

    def test_version_gating_inject_requires_1_1_1(self):
        """depends_on.inject requires version 1.1.1."""
        workflow = {
            "version": "1.1",  # Wrong version
            "name": "test",
            "steps": [{
                "name": "step1",
                "command": ["echo"],
                "depends_on": {
                    "required": ["file.txt"],
                    "inject": True  # Requires 1.1.1
                }
            }]
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("inject requires version '1.1.1'" in str(err.message)
                  for err in exc_info.value.errors)

    # Positive test cases

    def test_valid_minimal_workflow(self):
        """Valid minimal workflow loads successfully."""
        workflow = {
            "version": "1.1",
            "name": "minimal",
            "steps": [{
                "name": "step1",
                "command": ["echo", "hello"]
            }]
        }

        path = self.write_workflow(workflow)
        result = self.loader.load(path)

        assert result["version"] == "1.1"
        assert result["name"] == "minimal"
        assert len(result["steps"]) == 1

    def test_valid_provider_workflow(self):
        """Valid provider-based workflow."""
        workflow = {
            "version": "1.1",
            "name": "provider test",
            "providers": {
                "claude": {
                    "command": ["claude", "code", "${PROMPT}"],
                    "input_mode": "argv"
                }
            },
            "steps": [{
                "name": "ask_claude",
                "provider": "claude",
                "provider_params": {
                    "model": "claude-3"
                }
            }]
        }

        path = self.write_workflow(workflow)
        result = self.loader.load(path)

        assert "providers" in result
        assert "claude" in result["providers"]

    def test_valid_for_each_loop(self):
        """Valid for_each loop configuration."""
        workflow = {
            "version": "1.1",
            "name": "loop test",
            "steps": [
                {
                    "name": "list_files",
                    "command": ["ls", "-1"],
                    "output_capture": "lines"
                },
                {
                    "name": "process_files",
                    "for_each": {
                        "items_from": "steps.list_files.lines",
                        "steps": [{
                            "name": "process",
                            "command": ["echo", "${item}"]
                        }]
                    }
                }
            ]
        }

        path = self.write_workflow(workflow)
        result = self.loader.load(path)

        assert len(result["steps"]) == 2
        assert "for_each" in result["steps"][1]

    def test_valid_variables_usage(self):
        """Valid variable substitution in allowed fields."""
        workflow = {
            "version": "1.1",
            "name": "variables test",
            "context": {
                "project": "test"
            },
            "steps": [{
                "name": "step1",
                "command": ["echo", "${context.project}"],
                "input_file": "${context.project}/input.txt",
                "output_file": "output_${run.id}.txt"
            }]
        }

        path = self.write_workflow(workflow)
        result = self.loader.load(path)

        # Should load without errors
        assert result["context"]["project"] == "test"

    def test_goto_end_target_valid(self):
        """_end is a valid goto target."""
        workflow = {
            "version": "1.1",
            "name": "goto test",
            "steps": [{
                "name": "step1",
                "command": ["test", "-f", "done.txt"],
                "on": {
                    "success": {
                        "goto": "_end"  # Reserved target
                    }
                }
            }, {
                "name": "step2",
                "command": ["echo", "not reached"]
            }]
        }

        path = self.write_workflow(workflow)
        result = self.loader.load(path)

        # Should load without errors
        assert len(result["steps"]) == 2

    def test_expected_outputs_valid_shape(self):
        """expected_outputs with required fields loads successfully."""
        workflow = {
            "version": "1.1.1",
            "name": "expected outputs valid",
            "steps": [{
                "name": "DraftPlan",
                "provider": "codex",
                "expected_outputs": [
                    {
                        "name": "plan_path",
                        "path": "state/plan_path.txt",
                        "type": "relpath",
                        "under": "docs/plans",
                        "must_exist_target": True
                    }
                ]
            }]
        }

        path = self.write_workflow(workflow)
        result = self.loader.load(path)
        assert result["steps"][0]["expected_outputs"][0]["type"] == "relpath"

    def test_expected_outputs_guidance_fields_accept_strings(self):
        """Optional expected_outputs guidance fields accept string values."""
        workflow = {
            "version": "1.1.1",
            "name": "expected outputs guidance valid",
            "steps": [{
                "name": "DraftPlan",
                "provider": "codex",
                "expected_outputs": [
                    {
                        "name": "plan_path",
                        "path": "state/plan_path.txt",
                        "type": "relpath",
                        "description": "Path to generated implementation plan.",
                        "format_hint": "Workspace-relative path",
                        "example": "docs/plans/2026-02-27-feature.md",
                    }
                ]
            }]
        }

        path = self.write_workflow(workflow)
        result = self.loader.load(path)
        output_spec = result["steps"][0]["expected_outputs"][0]
        assert output_spec["description"] == "Path to generated implementation plan."
        assert output_spec["format_hint"] == "Workspace-relative path"
        assert output_spec["example"] == "docs/plans/2026-02-27-feature.md"

    @pytest.mark.parametrize(
        "field,bad_value",
        [
            ("description", {"not": "string"}),
            ("format_hint", ["not", "string"]),
            ("example", 123),
        ],
    )
    def test_expected_outputs_guidance_fields_require_strings(self, field, bad_value):
        """Optional expected_outputs guidance fields must be strings when provided."""
        workflow = {
            "version": "1.1.1",
            "name": "expected outputs guidance invalid",
            "steps": [{
                "name": "DraftPlan",
                "command": ["echo", "ok"],
                "expected_outputs": [{
                    "name": "plan_path",
                    "path": "state/plan_path.txt",
                    "type": "relpath",
                    field: bad_value,
                }]
            }]
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any(f"'{field}' must be a string" in str(err.message)
                  for err in exc_info.value.errors)

    def test_expected_outputs_missing_required_keys(self):
        """expected_outputs entries must include path and type."""
        workflow = {
            "version": "1.1.1",
            "name": "missing keys",
            "steps": [{
                "name": "DraftPlan",
                "command": ["echo", "ok"],
                "expected_outputs": [{"name": "plan_path", "path": "state/plan_path.txt"}]
            }]
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("missing required 'type'" in str(err.message) for err in exc_info.value.errors)

    def test_expected_outputs_invalid_type(self):
        """expected_outputs type must be one of supported values."""
        workflow = {
            "version": "1.1.1",
            "name": "bad type",
            "steps": [{
                "name": "DraftPlan",
                "command": ["echo", "ok"],
                "expected_outputs": [{
                    "name": "plan_path",
                    "path": "state/plan_path.txt",
                    "type": "string"
                }]
            }]
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("invalid expected_outputs type 'string'" in str(err.message)
                  for err in exc_info.value.errors)

    def test_expected_outputs_under_rejects_parent_escape(self):
        """expected_outputs under must satisfy path safety checks."""
        workflow = {
            "version": "1.1.1",
            "name": "bad under",
            "steps": [{
                "name": "DraftPlan",
                "command": ["echo", "ok"],
                "expected_outputs": [{
                    "name": "plan_path",
                    "path": "state/plan_path.txt",
                    "type": "relpath",
                    "under": "../outside"
                }]
            }]
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("parent directory traversal" in str(err.message) for err in exc_info.value.errors)

    def test_expected_outputs_missing_name(self):
        """expected_outputs entries must define explicit artifact names."""
        workflow = {
            "version": "1.1.1",
            "name": "missing name",
            "steps": [{
                "name": "DraftPlan",
                "command": ["echo", "ok"],
                "expected_outputs": [{
                    "path": "state/plan_path.txt",
                    "type": "relpath"
                }]
            }]
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("missing required 'name'" in str(err.message) for err in exc_info.value.errors)

    def test_inject_output_contract_requires_boolean(self):
        """inject_output_contract must be a boolean when present."""
        workflow = {
            "version": "1.1.1",
            "name": "bad inject flag",
            "steps": [{
                "name": "DraftPlan",
                "provider": "codex",
                "inject_output_contract": "false"
            }]
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("'inject_output_contract' must be a boolean" in str(err.message)
                  for err in exc_info.value.errors)

    def test_persist_artifacts_in_state_requires_boolean(self):
        """persist_artifacts_in_state must be a boolean when present."""
        workflow = {
            "version": "1.1.1",
            "name": "bad persist flag",
            "steps": [{
                "name": "SelectBacklogItem",
                "command": ["echo", "ok"],
                "persist_artifacts_in_state": "false",
                "expected_outputs": [{
                    "name": "backlog_item_path",
                    "path": "state/backlog_item_path.txt",
                    "type": "relpath",
                    "under": "docs/backlog",
                }],
            }]
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("'persist_artifacts_in_state' must be a boolean" in str(err.message)
                  for err in exc_info.value.errors)

    def test_expected_outputs_name_must_be_unique(self):
        """Duplicate expected_outputs names are rejected."""
        workflow = {
            "version": "1.1.1",
            "name": "dup names",
            "steps": [{
                "name": "DraftPlan",
                "command": ["echo", "ok"],
                "expected_outputs": [
                    {"name": "plan_path", "path": "state/a.txt", "type": "relpath"},
                    {"name": "plan_path", "path": "state/b.txt", "type": "relpath"},
                ],
            }]
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("duplicate artifact name 'plan_path'" in str(err.message)
                  for err in exc_info.value.errors)

    def test_v12_artifacts_rejected_in_v1_1_1(self):
        """Top-level artifacts are version-gated to v1.2+."""
        workflow = {
            "version": "1.1.1",
            "name": "artifacts-gated",
            "artifacts": {
                "execution_log": {
                    "pointer": "state/execution_log_path.txt",
                    "type": "relpath",
                    "under": "artifacts/work",
                    "must_exist_target": True,
                }
            },
            "steps": [{
                "name": "step1",
                "command": ["echo", "ok"],
            }],
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("artifacts requires version '1.2'" in str(err.message)
                   for err in exc_info.value.errors)

    def test_v12_artifacts_schema_accepts_in_v1_2(self):
        """Top-level artifacts schema is accepted in v1.2."""
        workflow = {
            "version": "1.2",
            "name": "artifacts-ok",
            "artifacts": {
                "execution_log": {
                    "pointer": "state/execution_log_path.txt",
                    "type": "relpath",
                    "under": "artifacts/work",
                    "must_exist_target": True,
                }
            },
            "steps": [{
                "name": "step1",
                "command": ["echo", "ok"],
            }],
        }

        path = self.write_workflow(workflow)
        result = self.loader.load(path)
        assert result["version"] == "1.2"
        assert "artifacts" in result
        assert "execution_log" in result["artifacts"]

    def test_v14_artifacts_schema_accepts_in_v1_4(self):
        """Top-level artifacts schema is accepted in v1.4."""
        workflow = {
            "version": "1.4",
            "name": "artifacts-ok-v14",
            "artifacts": {
                "execution_log": {
                    "pointer": "state/execution_log_path.txt",
                    "type": "relpath",
                    "under": "artifacts/work",
                    "must_exist_target": True,
                }
            },
            "steps": [{
                "name": "step1",
                "command": ["echo", "ok"],
            }],
        }

        path = self.write_workflow(workflow)
        result = self.loader.load(path)
        assert result["version"] == "1.4"
        assert "artifacts" in result
        assert "execution_log" in result["artifacts"]

    def test_v14_consumes_controls_accept_in_v1_4(self):
        """v1.4 accepts consumes and consume prompt controls."""
        workflow = {
            "version": "1.4",
            "name": "v14-consumes-controls",
            "artifacts": {
                "execution_log": {
                    "pointer": "state/execution_log_path.txt",
                    "type": "relpath",
                    "under": "artifacts/work",
                }
            },
            "steps": [{
                "name": "Review",
                "command": ["echo", "ok"],
                "consumes": [{
                    "artifact": "execution_log",
                    "policy": "latest_successful",
                    "freshness": "any",
                }],
                "inject_consumes": True,
                "consumes_injection_position": "append",
                "prompt_consumes": ["execution_log"],
            }],
        }

        path = self.write_workflow(workflow)
        result = self.loader.load(path)
        assert result["version"] == "1.4"
        assert result["steps"][0]["consumes"][0]["artifact"] == "execution_log"

    def test_v12_publishes_rejected_in_v1_1_1(self):
        """Step publishes are version-gated to v1.2+."""
        workflow = {
            "version": "1.1.1",
            "name": "publishes-gated",
            "steps": [{
                "name": "ExecutePlan",
                "command": ["echo", "ok"],
                "expected_outputs": [{
                    "name": "execution_log_path",
                    "path": "state/execution_log_path.txt",
                    "type": "relpath",
                    "under": "artifacts/work",
                }],
                "publishes": [{
                    "artifact": "execution_log",
                    "from": "execution_log_path",
                }],
            }],
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("publishes requires version '1.2'" in str(err.message)
                   for err in exc_info.value.errors)

    def test_v12_consumes_rejected_in_v1_1_1(self):
        """Step consumes are version-gated to v1.2+."""
        workflow = {
            "version": "1.1.1",
            "name": "consumes-gated",
            "steps": [{
                "name": "Review",
                "command": ["echo", "ok"],
                "consumes": [{
                    "artifact": "execution_log",
                    "producers": ["ExecutePlan", "FixIssues"],
                    "policy": "latest_successful",
                    "freshness": "since_last_consume",
                }],
            }],
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("consumes requires version '1.2'" in str(err.message)
                   for err in exc_info.value.errors)

    def test_v12_publishes_from_must_reference_expected_output_name(self):
        """publishes.from must reference a local expected_outputs artifact key."""
        workflow = {
            "version": "1.2",
            "name": "bad-from",
            "artifacts": {
                "execution_log": {
                    "pointer": "state/execution_log_path.txt",
                    "type": "relpath",
                    "under": "artifacts/work",
                }
            },
            "steps": [{
                "name": "ExecutePlan",
                "command": ["echo", "ok"],
                "expected_outputs": [{
                    "name": "execution_log_path",
                    "path": "state/execution_log_path.txt",
                    "type": "relpath",
                    "under": "artifacts/work",
                }],
                "publishes": [{
                    "artifact": "execution_log",
                    "from": "missing_output_name",
                }],
            }],
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("publishes.from 'missing_output_name' not found in expected_outputs" in str(err.message)
                   for err in exc_info.value.errors)

    def test_v12_publishes_pointer_must_match_registry_pointer(self):
        """publishes target expected_outputs path must match registry pointer path."""
        workflow = {
            "version": "1.2",
            "name": "bad-pointer",
            "artifacts": {
                "execution_log": {
                    "pointer": "state/execution_log_path.txt",
                    "type": "relpath",
                    "under": "artifacts/work",
                }
            },
            "steps": [{
                "name": "ExecutePlan",
                "command": ["echo", "ok"],
                "expected_outputs": [{
                    "name": "execution_log_path",
                    "path": "state/some_other_pointer.txt",
                    "type": "relpath",
                    "under": "artifacts/work",
                }],
                "publishes": [{
                    "artifact": "execution_log",
                    "from": "execution_log_path",
                }],
            }],
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("publishes pointer mismatch for artifact 'execution_log'" in str(err.message)
                   for err in exc_info.value.errors)

    def test_v12_publishes_incompatible_with_persist_artifacts_disabled(self):
        """publishes requires artifacts to be persisted in step result state."""
        workflow = {
            "version": "1.2",
            "name": "bad-publish-persist-combo",
            "artifacts": {
                "execution_log": {
                    "pointer": "state/execution_log_path.txt",
                    "type": "relpath",
                    "under": "artifacts/work",
                }
            },
            "steps": [{
                "name": "ExecutePlan",
                "command": ["echo", "ok"],
                "persist_artifacts_in_state": False,
                "expected_outputs": [{
                    "name": "execution_log_path",
                    "path": "state/execution_log_path.txt",
                    "type": "relpath",
                    "under": "artifacts/work",
                }],
                "publishes": [{
                    "artifact": "execution_log",
                    "from": "execution_log_path",
                }],
            }],
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("publishes requires persist_artifacts_in_state to be true" in str(err.message)
                   for err in exc_info.value.errors)

    def test_v12_consumes_producers_must_publish_artifact(self):
        """consumes.producers entries must reference steps that publish that artifact."""
        workflow = {
            "version": "1.2",
            "name": "bad-producers",
            "artifacts": {
                "execution_log": {
                    "pointer": "state/execution_log_path.txt",
                    "type": "relpath",
                    "under": "artifacts/work",
                }
            },
            "steps": [{
                "name": "ExecutePlan",
                "command": ["echo", "ok"],
                "expected_outputs": [{
                    "name": "execution_log_path",
                    "path": "state/execution_log_path.txt",
                    "type": "relpath",
                    "under": "artifacts/work",
                }],
                "publishes": [{
                    "artifact": "execution_log",
                    "from": "execution_log_path",
                }],
            }, {
                "name": "Review",
                "command": ["echo", "ok"],
                "consumes": [{
                    "artifact": "execution_log",
                    "producers": ["FixIssues"],
                    "policy": "latest_successful",
                    "freshness": "any",
                }],
            }],
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("consumes producer 'FixIssues' does not publish artifact 'execution_log'" in str(err.message)
                   for err in exc_info.value.errors)

    def test_v12_inject_consumes_requires_boolean(self):
        """inject_consumes must be a boolean when present."""
        workflow = {
            "version": "1.2",
            "name": "bad-inject-consumes",
            "artifacts": {
                "execution_log": {
                    "pointer": "state/execution_log_path.txt",
                    "type": "relpath",
                    "under": "artifacts/work",
                }
            },
            "steps": [{
                "name": "Review",
                "provider": "codex",
                "consumes": [{
                    "artifact": "execution_log",
                    "policy": "latest_successful",
                }],
                "inject_consumes": "true",
            }],
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("'inject_consumes' must be a boolean" in str(err.message)
                   for err in exc_info.value.errors)

    def test_v12_consumes_injection_position_must_be_prepend_or_append(self):
        """consumes_injection_position only supports prepend|append."""
        workflow = {
            "version": "1.2",
            "name": "bad-consumes-position",
            "artifacts": {
                "execution_log": {
                    "pointer": "state/execution_log_path.txt",
                    "type": "relpath",
                    "under": "artifacts/work",
                }
            },
            "steps": [{
                "name": "Review",
                "provider": "codex",
                "consumes": [{
                    "artifact": "execution_log",
                    "policy": "latest_successful",
                }],
                "consumes_injection_position": "middle",
            }],
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("consumes_injection_position must be 'prepend' or 'append'" in str(err.message)
                   for err in exc_info.value.errors)

    def test_v12_consumes_injection_position_requires_v1_2(self):
        """consumes injection controls are version-gated to v1.2+."""
        workflow = {
            "version": "1.1.1",
            "name": "position-gated",
            "steps": [{
                "name": "Review",
                "provider": "codex",
                "consumes_injection_position": "prepend",
            }],
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("consumes_injection_position requires version '1.2'" in str(err.message)
                   for err in exc_info.value.errors)

    def test_v12_prompt_consumes_requires_list_of_strings(self):
        """prompt_consumes must be a list of non-empty artifact names."""
        workflow = {
            "version": "1.2",
            "name": "bad-prompt-consumes-type",
            "artifacts": {
                "execution_log": {
                    "pointer": "state/execution_log_path.txt",
                    "type": "relpath",
                    "under": "artifacts/work",
                }
            },
            "steps": [{
                "name": "Review",
                "provider": "codex",
                "consumes": [{
                    "artifact": "execution_log",
                    "policy": "latest_successful",
                }],
                "prompt_consumes": ["execution_log", 7],
            }],
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("prompt_consumes must be a list of artifact names" in str(err.message)
                   for err in exc_info.value.errors)

    def test_v12_prompt_consumes_requires_consumes(self):
        """prompt_consumes cannot be declared without consumes."""
        workflow = {
            "version": "1.2",
            "name": "prompt-consumes-without-consumes",
            "steps": [{
                "name": "Review",
                "provider": "codex",
                "prompt_consumes": ["execution_log"],
            }],
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("prompt_consumes requires consumes" in str(err.message)
                   for err in exc_info.value.errors)

    def test_v12_prompt_consumes_must_be_subset_of_consumes(self):
        """prompt_consumes entries must be declared in consumes[*].artifact."""
        workflow = {
            "version": "1.2",
            "name": "prompt-consumes-subset",
            "artifacts": {
                "execution_log": {
                    "pointer": "state/execution_log_path.txt",
                    "type": "relpath",
                    "under": "artifacts/work",
                },
                "plan": {
                    "pointer": "state/plan_path.txt",
                    "type": "relpath",
                    "under": "docs/plans",
                },
            },
            "steps": [{
                "name": "Review",
                "provider": "codex",
                "consumes": [{
                    "artifact": "execution_log",
                    "policy": "latest_successful",
                }],
                "prompt_consumes": ["plan"],
            }],
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("prompt_consumes artifact 'plan' must appear in consumes" in str(err.message)
                   for err in exc_info.value.errors)

    def test_v12_consumes_guidance_fields_accept_strings(self):
        """Optional consumes guidance fields accept string values."""
        workflow = {
            "version": "1.2",
            "name": "consumes-guidance-valid",
            "artifacts": {
                "execution_log": {
                    "pointer": "state/execution_log_path.txt",
                    "type": "relpath",
                    "under": "artifacts/work",
                }
            },
            "steps": [{
                "name": "Review",
                "provider": "codex",
                "consumes": [{
                    "artifact": "execution_log",
                    "policy": "latest_successful",
                    "description": "Primary execution log generated by ExecutePlan.",
                    "format_hint": "Workspace-relative .log path",
                    "example": "artifacts/work/latest-execution.log",
                }],
            }],
        }

        path = self.write_workflow(workflow)
        loaded = self.loader.load(path)
        consume_spec = loaded["steps"][0]["consumes"][0]
        assert consume_spec["description"] == "Primary execution log generated by ExecutePlan."
        assert consume_spec["format_hint"] == "Workspace-relative .log path"
        assert consume_spec["example"] == "artifacts/work/latest-execution.log"

    @pytest.mark.parametrize(
        "field,bad_value",
        [
            ("description", {"not": "string"}),
            ("format_hint", ["not", "string"]),
            ("example", 1),
        ],
    )
    def test_v12_consumes_guidance_fields_require_strings(self, field, bad_value):
        """Optional consumes guidance fields must be strings when provided."""
        workflow = {
            "version": "1.2",
            "name": "consumes-guidance-invalid",
            "artifacts": {
                "execution_log": {
                    "pointer": "state/execution_log_path.txt",
                    "type": "relpath",
                    "under": "artifacts/work",
                }
            },
            "steps": [{
                "name": "Review",
                "provider": "codex",
                "consumes": [{
                    "artifact": "execution_log",
                    "policy": "latest_successful",
                    field: bad_value,
                }],
            }],
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any(f"'{field}' must be a string" in str(err.message)
                   for err in exc_info.value.errors)

    def test_v12_consumes_producer_can_reference_top_level_from_for_each_nested_step(self):
        """Nested for_each consumes may reference producers declared at top-level."""
        workflow = {
            "version": "1.2",
            "name": "for-each-cross-scope-producer",
            "artifacts": {
                "execution_log": {
                    "pointer": "state/execution_log_path.txt",
                    "type": "relpath",
                    "under": "artifacts/work",
                }
            },
            "steps": [
                {
                    "name": "Produce",
                    "command": ["bash", "-lc", "echo produce"],
                    "expected_outputs": [
                        {
                            "name": "execution_log_path",
                            "path": "state/execution_log_path.txt",
                            "type": "relpath",
                            "under": "artifacts/work",
                        }
                    ],
                    "publishes": [{"artifact": "execution_log", "from": "execution_log_path"}],
                },
                {
                    "name": "Loop",
                    "for_each": {
                        "items": ["one"],
                        "steps": [
                            {
                                "name": "ConsumeInLoop",
                                "command": ["bash", "-lc", "echo consume"],
                                "consumes": [
                                    {
                                        "artifact": "execution_log",
                                        "producers": ["Produce"],
                                        "policy": "latest_successful",
                                        "freshness": "any",
                                    }
                                ],
                            }
                        ],
                    },
                },
            ],
        }

        path = self.write_workflow(workflow)
        loaded = self.loader.load(path)

        assert loaded["name"] == "for-each-cross-scope-producer"

    def test_v12_artifact_kind_scalar_accepts_non_relpath_types(self):
        """kind:scalar supports scalar output types without pointer-file requirements."""
        workflow = {
            "version": "1.2",
            "name": "scalar-artifact",
            "artifacts": {
                "failed_count": {
                    "kind": "scalar",
                    "type": "integer",
                }
            },
            "steps": [{
                "name": "CountFailures",
                "command": ["bash", "-lc", "echo 0"],
            }],
        }

        path = self.write_workflow(workflow)
        loaded = self.loader.load(path)
        assert loaded["artifacts"]["failed_count"]["kind"] == "scalar"

    def test_v12_artifact_kind_scalar_rejects_relpath_pointer_fields(self):
        """kind:scalar cannot use pointer/under/must_exist_target relpath constraints."""
        workflow = {
            "version": "1.2",
            "name": "bad-scalar-fields",
            "artifacts": {
                "failed_count": {
                    "kind": "scalar",
                    "type": "integer",
                    "pointer": "state/failed_count.txt",
                    "under": "state",
                    "must_exist_target": True,
                }
            },
            "steps": [{
                "name": "CountFailures",
                "command": ["bash", "-lc", "echo 0"],
            }],
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("kind 'scalar' forbids 'pointer'" in str(err.message)
                   for err in exc_info.value.errors)
        assert any("kind 'scalar' forbids 'under'" in str(err.message)
                   for err in exc_info.value.errors)
        assert any("kind 'scalar' forbids 'must_exist_target'" in str(err.message)
                   for err in exc_info.value.errors)

    def test_v12_artifact_kind_relpath_requires_pointer(self):
        """kind:relpath requires explicit pointer path."""
        workflow = {
            "version": "1.2",
            "name": "missing-relpath-pointer",
            "artifacts": {
                "execution_log": {
                    "kind": "relpath",
                    "type": "relpath",
                    "under": "artifacts/work",
                }
            },
            "steps": [{
                "name": "ExecutePlan",
                "command": ["bash", "-lc", "echo ok"],
            }],
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("kind 'relpath' requires 'pointer'" in str(err.message)
                   for err in exc_info.value.errors)

    def test_v12_artifact_kind_defaults_to_relpath_for_back_compat(self):
        """Omitting kind preserves relpath semantics for existing v1.2 workflows."""
        workflow = {
            "version": "1.2",
            "name": "artifact-kind-default",
            "artifacts": {
                "execution_log": {
                    "pointer": "state/execution_log_path.txt",
                    "type": "relpath",
                    "under": "artifacts/work",
                    "must_exist_target": True,
                }
            },
            "steps": [{
                "name": "ExecutePlan",
                "command": ["bash", "-lc", "echo ok"],
            }],
        }

        path = self.write_workflow(workflow)
        loaded = self.loader.load(path)
        assert loaded["artifacts"]["execution_log"]["type"] == "relpath"

    def test_v13_output_bundle_requires_version_1_3(self):
        """output_bundle is gated to version 1.3+."""
        workflow = {
            "version": "1.2",
            "name": "v13-gated-output-bundle",
            "steps": [{
                "name": "Assess",
                "command": ["echo", "ok"],
                "output_bundle": {
                    "path": "artifacts/work/summary.json",
                    "fields": [{
                        "name": "status",
                        "json_pointer": "/status",
                        "type": "enum",
                        "allowed": ["COMPLETE", "INCOMPLETE", "BLOCKED"],
                    }],
                },
            }],
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("output_bundle requires version '1.3'" in str(err.message)
                   for err in exc_info.value.errors)

    def test_v13_output_bundle_rejects_expected_outputs_on_same_step(self):
        """output_bundle and expected_outputs cannot be combined on one step."""
        workflow = {
            "version": "1.3",
            "name": "v13-output-bundle-mutual-exclusion",
            "steps": [{
                "name": "Assess",
                "command": ["echo", "ok"],
                "expected_outputs": [{
                    "name": "status_path",
                    "path": "state/status.txt",
                    "type": "enum",
                    "allowed": ["COMPLETE", "INCOMPLETE", "BLOCKED"],
                }],
                "output_bundle": {
                    "path": "artifacts/work/summary.json",
                    "fields": [{
                        "name": "status",
                        "json_pointer": "/status",
                        "type": "enum",
                        "allowed": ["COMPLETE", "INCOMPLETE", "BLOCKED"],
                    }],
                },
            }],
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("output_bundle is mutually exclusive with expected_outputs" in str(err.message)
                   for err in exc_info.value.errors)

    def test_v14_output_bundle_accepts_in_v1_4(self):
        """output_bundle remains valid in v1.4."""
        workflow = {
            "version": "1.4",
            "name": "v14-output-bundle",
            "steps": [{
                "name": "Assess",
                "command": ["echo", "ok"],
                "output_bundle": {
                    "path": "artifacts/work/summary.json",
                    "fields": [{
                        "name": "status",
                        "json_pointer": "/status",
                        "type": "enum",
                        "allowed": ["COMPLETE", "INCOMPLETE", "BLOCKED"],
                    }],
                },
            }],
        }

        path = self.write_workflow(workflow)
        result = self.loader.load(path)
        assert result["version"] == "1.4"
        assert result["steps"][0]["output_bundle"]["path"] == "artifacts/work/summary.json"

    def test_v13_output_bundle_requires_non_empty_fields(self):
        """output_bundle.fields must be a non-empty list."""
        workflow = {
            "version": "1.3",
            "name": "v13-output-bundle-empty-fields",
            "steps": [{
                "name": "Assess",
                "command": ["echo", "ok"],
                "output_bundle": {
                    "path": "artifacts/work/summary.json",
                    "fields": [],
                },
            }],
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("output_bundle.fields must be a non-empty list" in str(err.message)
                   for err in exc_info.value.errors)

    def test_v13_output_bundle_field_requires_json_pointer_and_type(self):
        """Each output_bundle field requires name, json_pointer, and type."""
        workflow = {
            "version": "1.3",
            "name": "v13-output-bundle-field-shape",
            "steps": [{
                "name": "Assess",
                "command": ["echo", "ok"],
                "output_bundle": {
                    "path": "artifacts/work/summary.json",
                    "fields": [{
                        "name": "status",
                    }],
                },
            }],
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("output_bundle.fields[0] missing required 'json_pointer'" in str(err.message)
                   for err in exc_info.value.errors)
        assert any("output_bundle.fields[0] missing required 'type'" in str(err.message)
                   for err in exc_info.value.errors)

    def test_v13_consume_bundle_requires_version_1_3(self):
        """consume_bundle is gated to version 1.3+."""
        workflow = {
            "version": "1.2",
            "name": "v13-gated-consume-bundle",
            "artifacts": {
                "plan": {
                    "pointer": "state/plan_path.txt",
                    "type": "relpath",
                    "under": "docs/plans",
                },
            },
            "steps": [{
                "name": "Review",
                "provider": "codex",
                "consumes": [{
                    "artifact": "plan",
                    "policy": "latest_successful",
                }],
                "consume_bundle": {
                    "path": "state/consumes/review.json",
                },
            }],
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("consume_bundle requires version '1.3'" in str(err.message)
                   for err in exc_info.value.errors)

    def test_v13_consume_bundle_requires_consumes(self):
        """consume_bundle cannot be used on a step with no consumes contract."""
        workflow = {
            "version": "1.3",
            "name": "v13-consume-bundle-requires-consumes",
            "steps": [{
                "name": "Review",
                "provider": "codex",
                "consume_bundle": {
                    "path": "state/consumes/review.json",
                },
            }],
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("consume_bundle requires consumes" in str(err.message)
                   for err in exc_info.value.errors)

    def test_v14_consume_bundle_accepts_in_v1_4(self):
        """consume_bundle remains valid in v1.4."""
        workflow = {
            "version": "1.4",
            "name": "v14-consume-bundle",
            "artifacts": {
                "plan": {
                    "pointer": "state/plan_path.txt",
                    "type": "relpath",
                    "under": "docs/plans",
                },
            },
            "steps": [{
                "name": "Review",
                "command": ["echo", "ok"],
                "consumes": [{
                    "artifact": "plan",
                    "policy": "latest_successful",
                }],
                "consume_bundle": {
                    "path": "state/consumes/review.json",
                },
            }],
        }

        path = self.write_workflow(workflow)
        result = self.loader.load(path)
        assert result["version"] == "1.4"
        assert result["steps"][0]["consume_bundle"]["path"] == "state/consumes/review.json"

    def test_v13_consume_bundle_include_must_be_subset_of_consumes(self):
        """consume_bundle.include must only contain artifacts declared in consumes."""
        workflow = {
            "version": "1.3",
            "name": "v13-consume-bundle-include-subset",
            "artifacts": {
                "execution_log": {
                    "pointer": "state/execution_log_path.txt",
                    "type": "relpath",
                    "under": "artifacts/work",
                },
                "plan": {
                    "pointer": "state/plan_path.txt",
                    "type": "relpath",
                    "under": "docs/plans",
                },
            },
            "steps": [{
                "name": "Review",
                "provider": "codex",
                "consumes": [{
                    "artifact": "execution_log",
                    "policy": "latest_successful",
                }],
                "consume_bundle": {
                    "path": "state/consumes/review.json",
                    "include": ["execution_log", "plan"],
                },
            }],
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("consume_bundle.include artifact 'plan' must appear in consumes" in str(err.message)
                   for err in exc_info.value.errors)
