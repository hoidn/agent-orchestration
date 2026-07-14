"""Tests for loader DSL validation per specs/dsl.md and acceptance tests."""

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import re

import pytest
import tempfile
import yaml

from orchestrator.loader import WorkflowBoundaryValidationPolicy, WorkflowLoader
from orchestrator.exceptions import WorkflowValidationError
from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle, workflow_provenance
from tests.workflow_lisp_command_boundaries import validate_review_findings_v1_binding
from tests.workflow_bundle_helpers import materialize_projection_body_steps, thaw_surface_workflow


def _enable_v214_loader(monkeypatch: pytest.MonkeyPatch) -> None:
    version_order = list(WorkflowLoader.VERSION_ORDER)
    if "2.14" not in version_order:
        version_order.append("2.14")
    monkeypatch.setattr(
        WorkflowLoader,
        "SUPPORTED_VERSIONS",
        WorkflowLoader.SUPPORTED_VERSIONS | {"2.14"},
    )
    monkeypatch.setattr(
        WorkflowLoader,
        "VERSION_ORDER",
        version_order,
    )


def _compile_loop_recur_workflow(workspace: Path) -> dict:
    from orchestrator.workflow_lisp.compiler import compile_stage3_module

    fixture = Path(__file__).parent / "fixtures" / "workflow_lisp" / "valid" / "loop_recur_minimal.orc"
    result = compile_stage3_module(
        fixture,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=False,
        workspace_root=workspace,
    )
    lowered = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "loop-recur-minimal"
    )
    return lowered.authored_mapping


def _compile_loop_recur_scalar_frame_carriage_workflow(workspace: Path):
    from orchestrator.workflow_lisp.compiler import compile_stage3_module

    fixture = (
        Path(__file__).parent
        / "fixtures"
        / "workflow_lisp"
        / "valid"
        / "loop_recur_on_exhausted_scalar_frame_carriage.orc"
    )
    result = compile_stage3_module(
        fixture,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=False,
        workspace_root=workspace,
    )
    return next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "loop-recur-on-exhausted-scalar-frame-carriage"
    )


def _compile_collection_structured_result_workflow(workspace: Path) -> dict:
    from orchestrator.workflow_lisp.compiler import compile_stage3_module

    fixture = Path(__file__).parent / "fixtures" / "workflow_lisp" / "valid" / "collection_structured_result.orc"
    result = compile_stage3_module(
        fixture,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=False,
        workspace_root=workspace,
    )
    lowered = next(
        workflow
        for workflow in result.lowered_workflows
        if workflow.typed_workflow.definition.name == "orchestrate"
    )
    return lowered


def _compile_nested_implementation_phase_workflow(workspace: Path) -> dict:
    from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
    from orchestrator.workflow_lisp.workflows import ExternalToolBinding

    fixture = (
        Path(__file__).parent
        / "fixtures"
        / "workflow_lisp"
        / "valid"
        / "design_delta_nested_implementation_phase.orc"
    )
    source = fixture.read_text(encoding="utf-8")
    module_match = re.search(r"\(defmodule\s+([^\s)]+)\)", source)
    assert module_match is not None
    module_path = (workspace / Path(*module_match.group(1).split("/"))).with_suffix(".orc")
    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(source, encoding="utf-8")
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(fixture.parent, workspace),
        provider_externs={
            "providers.execute": "test-provider",
            "providers.review": "test-review",
            "providers.fix": "test-fix",
        },
        prompt_externs={
            "prompts.implementation.execute": "prompts/implementation/execute.md",
            "prompts.implementation.review": "prompts/implementation/review.md",
            "prompts.implementation.fix": "prompts/implementation/fix.md",
        },
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            ),
            "validate_review_findings_v1": validate_review_findings_v1_binding(),
        },
        validate_shared=True,
        workspace_root=workspace,
    )
    lowered = next(
        workflow
        for workflow in result.entry_result.lowered_workflows
        if workflow.typed_workflow.definition.name == "nested/implementation-phase::implementation-phase"
    )
    return lowered.authored_mapping


def test_analyze_reusable_write_roots_accepts_hyphenated_relpath_input_refs(tmp_path: Path) -> None:
    loader = WorkflowLoader(tmp_path)
    workflow = {
        "name": "hyphenated-hidden-input",
        "version": "2.14",
        "inputs": {
            "phase-ctx__state-root": {
                "kind": "relpath",
                "type": "relpath",
                "under": "state",
                "must_exist_target": False,
            }
        },
        "steps": [
            {
                "name": "WriteBundle",
                "command": ["python", "-c", "print('ok')"],
                "output_bundle": {
                    "path": "${inputs.phase-ctx__state-root}/phases/plan/state.json",
                    "fields": [
                        {
                            "name": "plan_path",
                            "json_pointer": "/plan_path",
                            "type": "relpath",
                            "under": "docs/plans",
                            "must_exist_target": True,
                        }
                    ],
                },
            }
        ],
    }

    managed_inputs, errors = loader._analyze_reusable_write_roots(workflow)

    assert managed_inputs == {"phase-ctx__state-root"}
    assert errors == []


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

    def test_provider_field_allows_context_variable(self):
        """Provider aliases may be resolved dynamically from workflow data."""
        workflow = {
            "version": "2.7",
            "name": "dynamic-provider",
            "context": {"provider_alias": "claude"},
            "providers": {
                "claude": {
                    "command": ["claude", "-p", "${PROMPT}"],
                }
            },
            "steps": [{
                "name": "step1",
                "provider": "${context.provider_alias}",
                "input_file": "prompt.md",
            }],
        }

        path = self.write_workflow(workflow)
        loaded = self.loader.load(path)
        surface = thaw_surface_workflow(loaded)

        assert surface["steps"][0]["provider"] == "${context.provider_alias}"

    def test_at7_env_in_provider_field_rejected(self):
        """AT-7: ${env.*} rejected in provider field."""
        workflow = {
            "version": "2.7",
            "name": "test",
            "providers": {
                "claude": {
                    "command": ["claude", "-p", "${PROMPT}"],
                }
            },
            "steps": [{
                "name": "step1",
                "provider": "${env.PROVIDER}",
                "input_file": "prompt.md",
            }],
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

    def test_version_2_9_is_supported(self):
        """Advisory linting release version should load successfully."""
        workflow = {
            "version": "2.9",
            "name": "lint-release-version",
            "steps": [{
                "name": "Echo",
                "command": ["echo", "ok"],
            }],
        }

        path = self.write_workflow(workflow)

        loaded = self.loader.load(path)
        surface = thaw_surface_workflow(loaded)

        assert surface["version"] == "2.9"
        assert surface["steps"][0]["name"] == "Echo"

    def test_version_2_10_is_supported(self):
        """Provider-session release version should load successfully."""
        workflow = {
            "version": "2.10",
            "name": "provider-session-release-version",
            "steps": [{
                "name": "Echo",
                "command": ["echo", "ok"],
            }],
        }

        path = self.write_workflow(workflow)

        loaded = self.loader.load(path)
        surface = thaw_surface_workflow(loaded)

        assert surface["version"] == "2.10"
        assert surface["steps"][0]["name"] == "Echo"
        assert loaded.core_workflow_ast.workflow_name == "provider-session-release-version"

    def test_version_2_12_is_supported(self):
        """repeat_until.on_exhausted release version should load successfully."""
        workflow = {
            "version": "2.12",
            "name": "repeat-until-on-exhausted-release-version",
            "steps": [{
                "name": "Echo",
                "command": ["echo", "ok"],
            }],
        }

        path = self.write_workflow(workflow)

        loaded = self.loader.load(path)
        surface = thaw_surface_workflow(loaded)

        assert surface["version"] == "2.12"
        assert surface["steps"][0]["name"] == "Echo"

    def test_version_2_14_is_supported(self):
        """Public v2.14 workflows load on normal loader paths after release."""
        workflow = {
            "version": "2.14",
            "name": "v214-release-gate",
            "steps": [{
                "name": "Echo",
                "command": ["echo", "ok"],
            }],
        }

        path = self.write_workflow(workflow)

        loaded = self.loader.load(path)
        surface = thaw_surface_workflow(loaded)

        assert surface["version"] == "2.14"
        assert surface["steps"][0]["name"] == "Echo"

    def test_materialize_artifacts_requires_version_2_14(self):
        """Phase 1 internals must not expose materialize_artifacts on public pre-2.14 workflows."""
        workflow = {
            "version": "2.13",
            "name": "materialize-gated",
            "inputs": {
                "design_path": {
                    "type": "relpath",
                    "under": "docs",
                }
            },
            "steps": [{
                "name": "MaterializeInputs",
                "id": "materialize_inputs",
                "materialize_artifacts": {
                    "values": [
                        {
                            "name": "design_path",
                            "source": {"input": "design_path"},
                            "contract": {"inherit": "source"},
                        }
                    ]
                },
            }],
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("materialize_artifacts requires version '2.14'" in str(err.message) for err in exc_info.value.errors)

    def test_variant_output_requires_version_2_14(self):
        """Phase 1 internals must not expose variant_output on public pre-2.14 workflows."""
        workflow = {
            "version": "2.13",
            "name": "variant-output-gated",
            "providers": {
                "mock_provider": {
                    "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                    "input_mode": "stdin",
                }
            },
            "steps": [{
                "name": "EmitVariantBundle",
                "id": "emit_variant_bundle",
                "provider": "mock_provider",
                "input_file": "prompt.md",
                "variant_output": {
                    "path": "state/variant_bundle.json",
                    "discriminant": {
                        "name": "implementation_state",
                        "json_pointer": "/implementation_state",
                        "allowed": ["COMPLETED", "BLOCKED"],
                    },
                    "variants": {
                        "COMPLETED": {
                            "fields": [
                                {
                                    "name": "execution_report_path",
                                    "json_pointer": "/execution_report_path",
                                    "type": "relpath",
                                    "under": "artifacts/work",
                                    "must_exist_target": True,
                                }
                            ]
                        },
                        "BLOCKED": {
                            "fields": [
                                {
                                    "name": "progress_report_path",
                                    "json_pointer": "/progress_report_path",
                                    "type": "relpath",
                                    "under": "artifacts/work",
                                    "must_exist_target": True,
                                }
                            ]
                        },
                    },
                },
            }],
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("variant_output requires version '2.14'" in str(err.message) for err in exc_info.value.errors)

    def test_variant_specific_materialize_ref_requires_author_time_proof(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Variant-only artifacts must not be consumable without match/requires_variant proof."""
        _enable_v214_loader(monkeypatch)
        workflow = {
            "version": "2.14",
            "name": "variant-proof-required",
            "steps": [
                {
                    "name": "EmitVariantBundle",
                    "id": "emit_variant_bundle",
                    "command": ["echo", "ok"],
                    "variant_output": {
                        "path": "state/implementation_state.json",
                        "discriminant": {
                            "name": "implementation_state",
                            "json_pointer": "/implementation_state",
                            "type": "enum",
                            "allowed": ["COMPLETED", "BLOCKED"],
                        },
                        "variants": {
                            "COMPLETED": {
                                "fields": [
                                    {
                                        "name": "execution_report_path",
                                        "json_pointer": "/execution_report_path",
                                        "type": "relpath",
                                        "under": "artifacts/work",
                                        "must_exist_target": True,
                                    }
                                ]
                            },
                            "BLOCKED": {
                                "fields": [
                                    {
                                        "name": "progress_report_path",
                                        "json_pointer": "/progress_report_path",
                                        "type": "relpath",
                                        "under": "artifacts/work",
                                        "must_exist_target": True,
                                    }
                                ]
                            },
                        },
                    },
                },
                {
                    "name": "UseExecutionReport",
                    "id": "use_execution_report",
                    "materialize_artifacts": {
                        "values": [
                            {
                                "name": "execution_report_copy",
                                "source": {
                                    "ref": "root.steps.EmitVariantBundle.artifacts.execution_report_path",
                                },
                                "contract": {
                                    "type": "relpath",
                                    "under": "artifacts/work",
                                    "must_exist_target": True,
                                },
                            }
                        ]
                    },
                },
            ],
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any(
            "execution_report_path" in str(err.message) and "variant proof" in str(err.message)
            for err in exc_info.value.errors
        )

    def test_match_case_proof_allows_variant_specific_materialize_ref(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """A match over the same discriminant should prove access to that variant's fields."""
        _enable_v214_loader(monkeypatch)
        workflow = {
            "version": "2.14",
            "name": "match-variant-proof",
            "steps": [
                {
                    "name": "EmitVariantBundle",
                    "id": "emit_variant_bundle",
                    "command": ["echo", "ok"],
                    "variant_output": {
                        "path": "state/implementation_state.json",
                        "discriminant": {
                            "name": "implementation_state",
                            "json_pointer": "/implementation_state",
                            "type": "enum",
                            "allowed": ["COMPLETED", "BLOCKED"],
                        },
                        "variants": {
                            "COMPLETED": {
                                "fields": [
                                    {
                                        "name": "execution_report_path",
                                        "json_pointer": "/execution_report_path",
                                        "type": "relpath",
                                        "under": "artifacts/work",
                                        "must_exist_target": True,
                                    }
                                ]
                            },
                            "BLOCKED": {
                                "fields": [
                                    {
                                        "name": "progress_report_path",
                                        "json_pointer": "/progress_report_path",
                                        "type": "relpath",
                                        "under": "artifacts/work",
                                        "must_exist_target": True,
                                    }
                                ]
                            },
                        },
                    },
                },
                {
                    "name": "RouteOutcome",
                    "id": "route_outcome",
                    "match": {
                        "ref": "root.steps.EmitVariantBundle.artifacts.implementation_state",
                        "cases": {
                            "COMPLETED": [
                                {
                                    "name": "UseExecutionReport",
                                    "id": "use_execution_report",
                                    "materialize_artifacts": {
                                        "values": [
                                            {
                                                "name": "execution_report_copy",
                                                "source": {
                                                    "ref": "root.steps.EmitVariantBundle.artifacts.execution_report_path",
                                                },
                                                "contract": {
                                                    "type": "relpath",
                                                    "under": "artifacts/work",
                                                    "must_exist_target": True,
                                                },
                                            }
                                        ]
                                    },
                                }
                            ],
                            "BLOCKED": [
                                {
                                    "name": "UseProgressReport",
                                    "id": "use_progress_report",
                                    "materialize_artifacts": {
                                        "values": [
                                            {
                                                "name": "progress_report_copy",
                                                "source": {
                                                    "ref": "root.steps.EmitVariantBundle.artifacts.progress_report_path",
                                                },
                                                "contract": {
                                                    "type": "relpath",
                                                    "under": "artifacts/work",
                                                    "must_exist_target": True,
                                                },
                                            }
                                        ]
                                    },
                                }
                            ],
                        },
                    },
                },
            ],
        }

        path = self.write_workflow(workflow)
        loaded = self.loader.load(path)
        surface = thaw_surface_workflow(loaded)

        assert surface["version"] == "2.14"
        assert surface["steps"][1]["name"] == "RouteOutcome"

    def test_snapshot_refs_are_restricted_to_selector_evidence(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Snapshot refs must not be usable as general structured refs."""
        _enable_v214_loader(monkeypatch)
        workflow = {
            "version": "2.14",
            "name": "snapshot-refs-restricted",
            "steps": [
                {
                    "name": "MaterializeReportPath",
                    "id": "materialize_report_path",
                    "materialize_artifacts": {
                        "values": [
                            {
                                "name": "report_path",
                                "source": {"literal": "artifacts/work/execution_report.md"},
                                "contract": {
                                    "type": "relpath",
                                    "under": "artifacts/work",
                                    "must_exist_target": False,
                                },
                                "pointer": {"path": "state/report_path.txt"},
                            }
                        ]
                    },
                },
                {
                    "name": "CaptureBefore",
                    "id": "capture_before",
                    "pre_snapshot": {
                        "name": "before",
                        "digest": "sha256",
                        "candidates": {
                            "COMPLETED": {
                                "ref": "root.steps.MaterializeReportPath.artifacts.report_path",
                            }
                        },
                    },
                    "command": ["echo", "ok"],
                },
                {
                    "name": "InvalidSnapshotUse",
                    "id": "invalid_snapshot_use",
                    "materialize_artifacts": {
                        "values": [
                            {
                                "name": "snapshot_copy",
                                "source": {
                                    "ref": "root.steps.CaptureBefore.snapshots.before",
                                },
                                "contract": {
                                    "type": "string",
                                },
                            }
                        ]
                    },
                },
            ],
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any(
            "snapshots.before" in str(err.message)
            and "select_variant_output.evidence.snapshot.ref" in str(err.message)
            for err in exc_info.value.errors
        )

    def test_materialize_published_relpath_pointer_must_match_canonical_artifact_pointer(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Published relpath materializations must not declare a noncanonical local pointer."""
        _enable_v214_loader(monkeypatch)
        workflow = {
            "version": "2.14",
            "name": "materialize-pointer-conflict",
            "inputs": {
                "design_path": {
                    "type": "relpath",
                    "under": "docs/plans",
                    "must_exist_target": True,
                }
            },
            "artifacts": {
                "design": {
                    "kind": "relpath",
                    "type": "relpath",
                    "pointer": "state/canonical_design.txt",
                    "under": "docs/plans",
                    "must_exist_target": True,
                }
            },
            "steps": [
                {
                    "name": "MaterializeDesign",
                    "id": "materialize_design",
                    "materialize_artifacts": {
                        "values": [
                            {
                                "name": "design_path",
                                "source": {"input": "design_path"},
                                "contract": {"inherit": "source"},
                                "pointer": {"path": "state/noncanonical_design.txt"},
                            }
                        ]
                    },
                    "publishes": [{"artifact": "design", "from": "design_path"}],
                }
            ],
        }

        temp_dir = Path(self.temp_dir)
        (temp_dir / "docs" / "plans").mkdir(parents=True, exist_ok=True)
        (temp_dir / "docs" / "plans" / "approved-plan.md").write_text(
            "# approved\n",
            encoding="utf-8",
        )

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any(
            "pointer_authority_conflict" in str(err.message)
            and "MaterializeDesign" in str(err.message)
            and "design" in str(err.message)
            for err in exc_info.value.errors
        )

    def test_pointer_authority_conflict_for_materialized_published_relpath_pointer(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Alias coverage for the stable shared pointer-authority error code."""
        _enable_v214_loader(monkeypatch)
        workflow = {
            "version": "2.14",
            "name": "materialize-pointer-conflict",
            "inputs": {
                "design_path": {
                    "type": "relpath",
                    "under": "docs/plans",
                    "must_exist_target": True,
                }
            },
            "artifacts": {
                "design": {
                    "kind": "relpath",
                    "type": "relpath",
                    "pointer": "state/canonical_design.txt",
                    "under": "docs/plans",
                    "must_exist_target": True,
                }
            },
            "steps": [
                {
                    "name": "MaterializeDesign",
                    "id": "materialize_design",
                    "materialize_artifacts": {
                        "values": [
                            {
                                "name": "design_path",
                                "source": {"input": "design_path"},
                                "contract": {"inherit": "source"},
                                "pointer": {"path": "state/noncanonical_design.txt"},
                            }
                        ]
                    },
                    "publishes": [{"artifact": "design", "from": "design_path"}],
                }
            ],
        }

        temp_dir = Path(self.temp_dir)
        (temp_dir / "docs" / "plans").mkdir(parents=True, exist_ok=True)
        (temp_dir / "docs" / "plans" / "approved-plan.md").write_text(
            "# approved\n",
            encoding="utf-8",
        )

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert any(
            "pointer_authority_conflict" in str(err.message)
            for err in exc_info.value.errors
        )

    def test_pre_snapshot_digest_must_be_sha256(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """pre_snapshot currently supports only sha256 digests."""
        _enable_v214_loader(monkeypatch)
        workflow = {
            "version": "2.14",
            "name": "snapshot-digest-invalid",
            "steps": [
                {
                    "name": "MaterializeReportPath",
                    "id": "materialize_report_path",
                    "materialize_artifacts": {
                        "values": [
                            {
                                "name": "report_path",
                                "source": {"literal": "artifacts/work/execution_report.md"},
                                "contract": {
                                    "type": "relpath",
                                    "under": "artifacts/work",
                                    "must_exist_target": False,
                                },
                            }
                        ]
                    },
                },
                {
                    "name": "CaptureBefore",
                    "id": "capture_before",
                    "pre_snapshot": {
                        "name": "before",
                        "digest": "md5",
                        "candidates": {
                            "COMPLETED": {
                                "ref": "root.steps.MaterializeReportPath.artifacts.report_path",
                            }
                        },
                    },
                    "command": ["echo", "ok"],
                },
            ],
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any(
            "pre_snapshot.digest" in str(err.message)
            and "sha256" in str(err.message)
            for err in exc_info.value.errors
        )

    def test_select_variant_output_evidence_mode_must_be_snapshot_diff(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """select_variant_output currently supports only snapshot_diff evidence."""
        _enable_v214_loader(monkeypatch)
        workflow = {
            "version": "2.14",
            "name": "selector-mode-invalid",
            "steps": [
                {
                    "name": "MaterializeTargets",
                    "id": "materialize_targets",
                    "materialize_artifacts": {
                        "values": [
                            {
                                "name": "execution_report_target_path",
                                "source": {"literal": "artifacts/work/execution_report.md"},
                                "contract": {
                                    "type": "relpath",
                                    "under": "artifacts/work",
                                    "must_exist_target": False,
                                },
                            }
                        ]
                    },
                },
                {
                    "name": "CaptureBefore",
                    "id": "capture_before",
                    "pre_snapshot": {
                        "name": "before",
                        "digest": "sha256",
                        "candidates": {
                            "COMPLETED": {
                                "ref": "root.steps.MaterializeTargets.artifacts.execution_report_target_path",
                            }
                        },
                    },
                    "command": ["echo", "ok"],
                },
                {
                    "name": "SelectImplementationOutcome",
                    "id": "select_implementation_outcome",
                    "select_variant_output": {
                        "path": "state/implementation_state.json",
                        "discriminant": {
                            "name": "implementation_state",
                            "json_pointer": "/implementation_state",
                            "type": "enum",
                            "allowed": ["COMPLETED"],
                        },
                        "variants": {
                            "COMPLETED": {
                                "fields": [
                                    {
                                        "name": "execution_report_path",
                                        "json_pointer": "/execution_report_path",
                                        "type": "relpath",
                                        "under": "artifacts/work",
                                        "must_exist_target": True,
                                    }
                                ]
                            }
                        },
                        "evidence": {
                            "mode": "not_snapshot_diff",
                            "snapshot": {
                                "ref": "root.steps.CaptureBefore.snapshots.before",
                            },
                        },
                    },
                },
            ],
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any(
            "select_variant_output.evidence.mode" in str(err.message)
            and "snapshot_diff" in str(err.message)
            for err in exc_info.value.errors
        )

    def test_variant_selection_facets_load_through_shared_validation(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Attached facet surfaces should survive shared loader validation together."""
        _enable_v214_loader(monkeypatch)
        workflow = {
            "version": "2.14",
            "name": "facet-combo-valid",
            "artifacts": {
                "selected_report_target": {
                    "kind": "relpath",
                    "type": "relpath",
                    "pointer": "state/selected_report_target.txt",
                    "under": "artifacts/work",
                    "must_exist_target": False,
                }
            },
            "steps": [
                {
                    "name": "MaterializeTargets",
                    "id": "materialize_targets",
                    "materialize_artifacts": {
                        "values": [
                            {
                                "name": "execution_report_target_path",
                                "source": {
                                    "literal": "artifacts/work/execution_report.md",
                                },
                                "contract": {
                                    "type": "relpath",
                                    "under": "artifacts/work",
                                    "must_exist_target": False,
                                },
                                "pointer": {
                                    "path": "state/selected_report_target.txt",
                                },
                            }
                        ]
                    },
                    "publishes": [
                        {
                            "artifact": "selected_report_target",
                            "from": "execution_report_target_path",
                        }
                    ],
                },
                {
                    "name": "CaptureBefore",
                    "id": "capture_before",
                    "pre_snapshot": {
                        "name": "before",
                        "digest": "sha256",
                        "candidates": {
                            "COMPLETED": {
                                "ref": "root.steps.MaterializeTargets.artifacts.execution_report_target_path",
                            }
                        },
                    },
                    "command": ["echo", "ok"],
                },
                {
                    "name": "EmitOutcome",
                    "id": "emit_outcome",
                    "command": ["echo", "ok"],
                    "variant_output": {
                        "path": "state/implementation_state.json",
                        "discriminant": {
                            "name": "implementation_state",
                            "json_pointer": "/implementation_state",
                            "type": "enum",
                            "allowed": ["COMPLETED", "BLOCKED"],
                        },
                        "variants": {
                            "COMPLETED": {
                                "fields": [
                                    {
                                        "name": "execution_report_path",
                                        "json_pointer": "/execution_report_path",
                                        "type": "relpath",
                                        "under": "artifacts/work",
                                        "must_exist_target": True,
                                    }
                                ]
                            },
                            "BLOCKED": {
                                "fields": [
                                    {
                                        "name": "progress_report_path",
                                        "json_pointer": "/progress_report_path",
                                        "type": "relpath",
                                        "under": "artifacts/work",
                                        "must_exist_target": True,
                                    },
                                    {
                                        "name": "blocker_class",
                                        "json_pointer": "/blocker_class",
                                        "type": "enum",
                                        "allowed": [
                                            "missing_resource",
                                            "unavailable_hardware",
                                        ],
                                    },
                                ]
                            },
                        },
                    },
                },
                {
                    "name": "SelectOutcome",
                    "id": "select_outcome",
                    "select_variant_output": {
                        "path": "state/implementation_state.json",
                        "discriminant": {
                            "name": "implementation_state",
                            "json_pointer": "/implementation_state",
                            "type": "enum",
                            "allowed": ["COMPLETED", "BLOCKED"],
                        },
                        "variants": {
                            "COMPLETED": {
                                "fields": [
                                    {
                                        "name": "execution_report_path",
                                        "json_pointer": "/execution_report_path",
                                        "type": "relpath",
                                        "under": "artifacts/work",
                                        "must_exist_target": True,
                                    }
                                ]
                            },
                            "BLOCKED": {
                                "fields": [
                                    {
                                        "name": "progress_report_path",
                                        "json_pointer": "/progress_report_path",
                                        "type": "relpath",
                                        "under": "artifacts/work",
                                        "must_exist_target": True,
                                    },
                                    {
                                        "name": "blocker_class",
                                        "json_pointer": "/blocker_class",
                                        "type": "enum",
                                        "allowed": [
                                            "missing_resource",
                                            "unavailable_hardware",
                                        ],
                                    },
                                ]
                            },
                        },
                        "evidence": {
                            "mode": "snapshot_diff",
                            "snapshot": {
                                "ref": "root.steps.CaptureBefore.snapshots.before",
                            },
                        },
                    },
                },
            ],
        }

        path = self.write_workflow(workflow)
        loaded = self.loader.load(path)
        surface = thaw_surface_workflow(loaded)

        assert surface["steps"][0]["publishes"][0]["artifact"] == "selected_report_target"
        assert surface["steps"][1]["pre_snapshot"]["name"] == "before"
        assert surface["steps"][2]["variant_output"]["discriminant"]["name"] == "implementation_state"
        assert surface["steps"][3]["select_variant_output"]["evidence"]["mode"] == "snapshot_diff"

    def test_materialize_artifacts_input_values_expand_to_values(
        self,
    ):
        """input_values should expand into the same internal values representation."""
        workflow = {
            "version": "2.14",
            "name": "materialize-input-values",
            "inputs": {
                "state_root": {
                    "type": "relpath",
                    "under": "state",
                },
                "steering_path": {
                    "type": "relpath",
                    "under": "docs",
                    "must_exist_target": True,
                },
                "design_path": {
                    "type": "relpath",
                    "under": "docs/plans",
                    "must_exist_target": True,
                },
            },
            "steps": [
                {
                    "name": "MaterializeInputs",
                    "id": "materialize_inputs",
                    "materialize_artifacts": {
                        "input_values": [
                            {
                                "names": ["steering_path", "design_path"],
                                "contract": "inherit",
                                "pointer_template": "${inputs.state_root}/{name}.txt",
                            }
                        ]
                    },
                }
            ],
        }

        path = self.write_workflow(workflow)
        loaded = self.loader.load(path)
        surface = thaw_surface_workflow(loaded)

        values = surface["steps"][0]["materialize_artifacts"]["values"]
        assert values == [
            {
                "name": "steering_path",
                "source": {"input": "steering_path"},
                "contract": {"inherit": "source"},
                "pointer": {"path": "${inputs.state_root}/steering_path.txt"},
            },
            {
                "name": "design_path",
                "source": {"input": "design_path"},
                "contract": {"inherit": "source"},
                "pointer": {"path": "${inputs.state_root}/design_path.txt"},
            },
        ]

    def test_materialize_artifacts_input_values_requires_pointer_name_placeholder(
        self,
    ):
        """input_values pointer templates must include the {name} placeholder."""
        workflow = {
            "version": "2.14",
            "name": "materialize-input-values-invalid-template",
            "inputs": {
                "state_root": {
                    "type": "relpath",
                    "under": "state",
                },
                "steering_path": {
                    "type": "relpath",
                    "under": "docs",
                    "must_exist_target": True,
                },
            },
            "steps": [
                {
                    "name": "MaterializeInputs",
                    "id": "materialize_inputs",
                    "materialize_artifacts": {
                        "input_values": [
                            {
                                "names": ["steering_path"],
                                "contract": "inherit",
                                "pointer_template": "${inputs.state_root}/pointer.txt",
                            }
                        ]
                    },
                }
            ],
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any(
            "pointer_template" in str(err.message) and "{name}" in str(err.message)
            for err in exc_info.value.errors
        )

    def test_variant_output_shared_fields_reject_duplicate_field_name(
        self,
    ):
        """shared_fields must not duplicate variant-only field names."""
        workflow = {
            "version": "2.14",
            "name": "variant-shared-fields-duplicate",
            "steps": [
                {
                    "name": "EmitBundle",
                    "id": "emit_bundle",
                    "command": ["echo", "ok"],
                    "variant_output": {
                        "path": "state/variant_bundle.json",
                        "discriminant": {
                            "name": "implementation_state",
                            "json_pointer": "/implementation_state",
                            "type": "enum",
                            "allowed": ["COMPLETED"],
                        },
                        "shared_fields": [
                            {
                                "name": "report_path",
                                "json_pointer": "/report_path",
                                "type": "relpath",
                                "under": "artifacts/work",
                                "must_exist_target": True,
                            }
                        ],
                        "variants": {
                            "COMPLETED": {
                                "fields": [
                                    {
                                        "name": "report_path",
                                        "json_pointer": "/other_report_path",
                                        "type": "relpath",
                                        "under": "artifacts/work",
                                        "must_exist_target": True,
                                    }
                                ]
                            }
                        },
                    },
                }
            ],
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any(
            "shared_fields" in str(err.message) and "report_path" in str(err.message)
            for err in exc_info.value.errors
        )

    def test_variant_output_allows_duplicate_field_name_across_distinct_variants(
        self,
    ):
        """Variant-only fields may reuse one name and json_pointer on different variants."""
        workflow = {
            "version": "2.14",
            "name": "variant-duplicate-field-across-variants",
            "steps": [
                {
                    "name": "EmitBundle",
                    "id": "emit_bundle",
                    "command": ["echo", "ok"],
                    "variant_output": {
                        "path": "state/variant_bundle.json",
                        "discriminant": {
                            "name": "status",
                            "json_pointer": "/status",
                            "type": "enum",
                            "allowed": ["EMPTY", "BLOCKED"],
                        },
                        "variants": {
                            "EMPTY": {
                                "fields": [
                                    {
                                        "name": "run_state",
                                        "json_pointer": "/run_state",
                                        "type": "relpath",
                                        "under": "state",
                                        "must_exist_target": False,
                                    }
                                ]
                            },
                            "BLOCKED": {
                                "fields": [
                                    {
                                        "name": "run_state",
                                        "json_pointer": "/run_state",
                                        "type": "relpath",
                                        "under": "state",
                                        "must_exist_target": False,
                                    }
                                ]
                            },
                        },
                    },
                }
            ],
        }

        path = self.write_workflow(workflow)

        loaded = self.loader.load(path)

        assert loaded is not None

    def test_match_requires_version_2_6(self):
        """Structured match statements are gated to v2.6+."""
        workflow = {
            "version": "2.5",
            "name": "match-gated",
            "artifacts": {
                "review_decision": {
                    "kind": "scalar",
                    "type": "enum",
                    "allowed": ["APPROVE", "REVISE"],
                }
            },
            "steps": [
                {
                    "name": "WriteDecision",
                    "id": "write_decision",
                    "set_scalar": {
                        "artifact": "review_decision",
                        "value": "APPROVE",
                    },
                },
                {
                    "name": "RouteDecision",
                    "id": "route_decision",
                    "match": {
                        "ref": "root.steps.WriteDecision.artifacts.review_decision",
                        "cases": {
                            "APPROVE": [{"name": "Approve", "command": ["echo", "approve"]}],
                            "REVISE": [{"name": "Revise", "command": ["echo", "revise"]}],
                        },
                    },
                },
            ],
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("match requires version '2.6'" in str(err.message)
                  for err in exc_info.value.errors)

    def test_repeat_until_requires_version_2_7(self):
        """Structured repeat_until statements are gated to v2.7+."""
        workflow = {
            "version": "2.6",
            "name": "repeat-until-gated",
            "steps": [
                {
                    "name": "ReviewLoop",
                    "id": "review_loop",
                    "repeat_until": {
                        "id": "iteration_body",
                        "outputs": {
                            "review_decision": {
                                "kind": "scalar",
                                "type": "enum",
                                "allowed": ["APPROVE", "REVISE"],
                                "from": {
                                    "ref": "self.steps.WriteDecision.artifacts.review_decision",
                                },
                            }
                        },
                        "condition": {
                            "compare": {
                                "left": {
                                    "ref": "self.outputs.review_decision",
                                },
                                "op": "eq",
                                "right": "APPROVE",
                            }
                        },
                        "max_iterations": 3,
                        "steps": [
                            {
                                "name": "WriteDecision",
                                "id": "write_decision",
                                "command": [
                                    "bash",
                                    "-lc",
                                    "mkdir -p state && printf 'APPROVE\\n' > state/review_decision.txt",
                                ],
                                "expected_outputs": [
                                    {
                                        "name": "review_decision",
                                        "path": "state/review_decision.txt",
                                        "type": "enum",
                                        "allowed": ["APPROVE", "REVISE"],
                                    }
                                ],
                            }
                        ],
                    },
                }
            ],
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("repeat_until requires version '2.7'" in str(err.message)
                  for err in exc_info.value.errors)

    def test_repeat_until_condition_rejects_direct_inner_step_refs(self):
        """repeat_until conditions must read declared loop-frame outputs, not inner multi-visit steps."""
        workflow = {
            "version": "2.7",
            "name": "repeat-until-direct-inner-ref",
            "steps": [
                {
                    "name": "ReviewLoop",
                    "id": "review_loop",
                    "repeat_until": {
                        "id": "iteration_body",
                        "outputs": {
                            "review_decision": {
                                "kind": "scalar",
                                "type": "enum",
                                "allowed": ["APPROVE", "REVISE"],
                                "from": {
                                    "ref": "self.steps.WriteDecision.artifacts.review_decision",
                                },
                            }
                        },
                        "condition": {
                            "compare": {
                                "left": {
                                    "ref": "self.steps.WriteDecision.artifacts.review_decision",
                                },
                                "op": "eq",
                                "right": "APPROVE",
                            }
                        },
                        "max_iterations": 3,
                        "steps": [
                            {
                                "name": "WriteDecision",
                                "id": "write_decision",
                                "command": [
                                    "bash",
                                    "-lc",
                                    "mkdir -p state && printf 'APPROVE\\n' > state/review_decision.txt",
                                ],
                                "expected_outputs": [
                                    {
                                        "name": "review_decision",
                                        "path": "state/review_decision.txt",
                                        "type": "enum",
                                        "allowed": ["APPROVE", "REVISE"],
                                    }
                                ],
                            }
                        ],
                    },
                }
            ],
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any(
            "repeat_until.condition" in str(err.message) and "self.outputs" in str(err.message)
            for err in exc_info.value.errors
        )

    def _repeat_until_on_exhausted_workflow(self, **overrides):
        repeat_until = {
            "id": "iteration_body",
            "outputs": {
                "decision": {
                    "kind": "scalar",
                    "type": "enum",
                    "allowed": ["APPROVE", "REVISE", "ESCALATE"],
                    "from": {
                        "ref": "self.steps.Route.artifacts.decision",
                    },
                },
                "loop_exhausted": {
                    "kind": "scalar",
                    "type": "bool",
                    "from": {
                        "ref": "self.steps.MarkNotExhausted.artifacts.loop_exhausted",
                    },
                },
            },
            "condition": {
                "compare": {
                    "left": {
                        "ref": "self.outputs.decision",
                    },
                    "op": "eq",
                    "right": "APPROVE",
                }
            },
            "max_iterations": 2,
            "on_exhausted": {
                "outputs": {
                    "decision": "ESCALATE",
                    "loop_exhausted": True,
                }
            },
            "steps": [
                {
                    "name": "Route",
                    "id": "route",
                    "set_scalar": {
                        "artifact": "decision",
                        "value": "REVISE",
                    },
                },
                {
                    "name": "MarkNotExhausted",
                    "id": "mark_not_exhausted",
                    "set_scalar": {
                        "artifact": "loop_exhausted",
                        "value": False,
                    },
                },
            ],
        }
        repeat_until.update(overrides)
        return {
            "version": "2.12",
            "name": "repeat-until-on-exhausted",
            "artifacts": {
                "decision": {
                    "kind": "scalar",
                    "type": "enum",
                    "allowed": ["APPROVE", "REVISE", "ESCALATE"],
                },
                "loop_exhausted": {
                    "kind": "scalar",
                    "type": "bool",
                },
            },
            "steps": [
                {
                    "name": "ReviewLoop",
                    "id": "review_loop",
                    "repeat_until": repeat_until,
                }
            ],
        }

    def test_repeat_until_accepts_on_exhausted_scalar_output_overrides(self):
        """repeat_until.on_exhausted may override declared scalar loop outputs."""
        path = self.write_workflow(self._repeat_until_on_exhausted_workflow())

        loaded = self.loader.load(path)
        surface = thaw_surface_workflow(loaded)

        repeat_until = surface["steps"][0]["repeat_until"]
        assert repeat_until["on_exhausted"]["outputs"] == {
            "decision": "ESCALATE",
            "loop_exhausted": True,
        }

    def test_repeat_until_on_exhausted_requires_version_2_12(self):
        """repeat_until.on_exhausted is gated to v2.12+."""
        workflow = self._repeat_until_on_exhausted_workflow()
        workflow["version"] = "2.7"
        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any(
            "repeat_until.on_exhausted requires version '2.12'" in str(err.message)
            for err in exc_info.value.errors
        )

    def test_repeat_until_on_exhausted_rejects_unknown_output(self):
        """on_exhausted overrides must target declared repeat_until outputs."""
        workflow = self._repeat_until_on_exhausted_workflow(
            on_exhausted={"outputs": {"unknown": "ESCALATE"}},
        )
        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert any(
            "repeat_until.on_exhausted.outputs.unknown targets unknown repeat_until output"
            in str(err.message)
            for err in exc_info.value.errors
        )

    def test_repeat_until_on_exhausted_validates_enum_and_bool_values(self):
        """on_exhausted override values must satisfy the declared output contracts."""
        workflow = self._repeat_until_on_exhausted_workflow(
            on_exhausted={
                "outputs": {
                    "decision": "NOPE",
                    "loop_exhausted": "maybe",
                }
            },
        )
        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        messages = [str(err.message) for err in exc_info.value.errors]
        assert any("repeat_until.on_exhausted.outputs.decision is invalid" in msg for msg in messages)
        assert any("repeat_until.on_exhausted.outputs.loop_exhausted is invalid" in msg for msg in messages)

    def test_repeat_until_on_exhausted_rejects_ref_override_in_authored_yaml(self):
        """Authored YAML may not use ref-backed on_exhausted scalar overrides."""
        workflow = self._repeat_until_on_exhausted_workflow(
            on_exhausted={
                "outputs": {
                    "decision": {"ref": "self.steps.Route.artifacts.decision"},
                    "loop_exhausted": True,
                }
            },
        )
        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert any(
            "repeat_until.on_exhausted.outputs.decision must be a scalar literal"
            in str(err.message)
            for err in exc_info.value.errors
        )

    def test_repeat_until_on_exhausted_rejects_relpath_output_override(self):
        """on_exhausted currently supports scalar loop outputs only."""
        workflow = self._repeat_until_on_exhausted_workflow()
        workflow["steps"][0]["repeat_until"]["outputs"]["report_path"] = {
            "kind": "relpath",
            "type": "relpath",
            "from": {
                "ref": "self.steps.WriteReport.artifacts.report_path",
            },
        }
        workflow["steps"][0]["repeat_until"]["on_exhausted"]["outputs"]["report_path"] = "state/report.txt"
        workflow["steps"][0]["repeat_until"]["steps"].append(
            {
                "name": "WriteReport",
                "id": "write_report",
                "command": [
                    "bash",
                    "-lc",
                    "mkdir -p state && printf 'state/report.md\\n' > state/report_path.txt && printf report > state/report.md",
                ],
                "expected_outputs": [
                    {
                        "name": "report_path",
                        "path": "state/report_path.txt",
                        "type": "relpath",
                        "must_exist_target": True,
                    }
                ],
            }
        )
        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert any(
            "repeat_until.on_exhausted.outputs.report_path may only override scalar repeat_until outputs"
            in str(err.message)
            for err in exc_info.value.errors
        )

    def test_repeat_until_on_exhausted_must_be_mapping(self):
        """repeat_until.on_exhausted must be an object when present."""
        workflow = self._repeat_until_on_exhausted_workflow(on_exhausted="ESCALATE")
        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert any(
            "repeat_until.on_exhausted must be a dictionary" in str(err.message)
            for err in exc_info.value.errors
        )

    def test_repeat_until_body_accepts_nested_call_and_match(self):
        """repeat_until bodies may compose statement-layer call and match forms."""
        library_path = self.workspace / "workflows" / "library" / "repeat_until_review_loop.yaml"
        library_path.parent.mkdir(parents=True, exist_ok=True)
        library_path.write_text(
            yaml.safe_dump(
                {
                    "version": "2.7",
                    "name": "repeat-until-review-loop",
                    "inputs": {
                        "write_root": {
                            "kind": "relpath",
                            "type": "relpath",
                        }
                    },
                    "artifacts": {
                        "review_decision": {
                            "kind": "scalar",
                            "type": "enum",
                            "allowed": ["APPROVE", "REVISE"],
                        }
                    },
                    "outputs": {
                        "review_decision": {
                            "kind": "scalar",
                            "type": "enum",
                            "allowed": ["APPROVE", "REVISE"],
                            "from": {
                                "ref": "root.steps.WriteReviewDecision.artifacts.review_decision",
                            },
                        }
                    },
                    "steps": [
                        {
                            "name": "WriteReviewDecision",
                            "id": "write_review_decision",
                            "command": [
                                "bash",
                                "-lc",
                                "mkdir -p \"${inputs.write_root}\" && printf 'APPROVE\\n' > \"${inputs.write_root}/review_decision.txt\"",
                            ],
                            "expected_outputs": [
                                {
                                    "name": "review_decision",
                                    "path": "${inputs.write_root}/review_decision.txt",
                                    "type": "enum",
                                    "allowed": ["APPROVE", "REVISE"],
                                }
                            ],
                        }
                    ],
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        workflow = {
            "version": "2.7",
            "name": "repeat-until-call-match",
            "imports": {
                "review_loop": "workflows/library/repeat_until_review_loop.yaml",
            },
            "artifacts": {
                "review_decision": {
                    "kind": "scalar",
                    "type": "enum",
                    "allowed": ["APPROVE", "REVISE"],
                }
            },
            "steps": [
                {
                    "name": "ReviewLoop",
                    "id": "review_loop",
                    "repeat_until": {
                        "id": "iteration_body",
                        "outputs": {
                            "review_decision": {
                                "kind": "scalar",
                                "type": "enum",
                                "allowed": ["APPROVE", "REVISE"],
                                "from": {
                                    "ref": "self.steps.RouteDecision.artifacts.review_decision",
                                },
                            }
                        },
                        "condition": {
                            "compare": {
                                "left": {
                                    "ref": "self.outputs.review_decision",
                                },
                                "op": "eq",
                                "right": "APPROVE",
                            }
                        },
                        "max_iterations": 2,
                        "steps": [
                            {
                                "name": "PrepareCallInputs",
                                "id": "prepare_call_inputs",
                                "command": [
                                    "bash",
                                    "-lc",
                                    "\n".join(
                                        [
                                            "mkdir -p state/review-loop-inputs",
                                            "iteration=$(( ${loop.index} + 1 ))",
                                            "printf '{\"write_root\":\"state/review-loop/iterations/%s\"}\\n' \"$iteration\" > state/review-loop-inputs/current.json",
                                        ]
                                    ),
                                ],
                                "output_bundle": {
                                    "path": "state/review-loop-inputs/current.json",
                                    "fields": [
                                        {
                                            "name": "write_root",
                                            "json_pointer": "/write_root",
                                            "type": "relpath",
                                        }
                                    ],
                                },
                            },
                            {
                                "name": "RunReviewLoop",
                                "id": "run_review_loop",
                                "call": "review_loop",
                                "with": {
                                    "write_root": {
                                        "ref": "self.steps.PrepareCallInputs.artifacts.write_root",
                                    },
                                },
                            },
                            {
                                "name": "RouteDecision",
                                "id": "route_decision",
                                "match": {
                                    "ref": "self.steps.RunReviewLoop.artifacts.review_decision",
                                    "cases": {
                                        "APPROVE": {
                                            "id": "approve_path",
                                            "outputs": {
                                                "review_decision": {
                                                    "kind": "scalar",
                                                    "type": "enum",
                                                    "allowed": ["APPROVE", "REVISE"],
                                                    "from": {
                                                        "ref": "self.steps.WriteApproved.artifacts.review_decision",
                                                    },
                                                }
                                            },
                                            "steps": [
                                                {
                                                    "name": "WriteApproved",
                                                    "id": "write_approved",
                                                    "set_scalar": {
                                                        "artifact": "review_decision",
                                                        "value": "APPROVE",
                                                    },
                                                }
                                            ],
                                        },
                                        "REVISE": {
                                            "id": "revise_path",
                                            "outputs": {
                                                "review_decision": {
                                                    "kind": "scalar",
                                                    "type": "enum",
                                                    "allowed": ["APPROVE", "REVISE"],
                                                    "from": {
                                                        "ref": "self.steps.WriteRevision.artifacts.review_decision",
                                                    },
                                                }
                                            },
                                            "steps": [
                                                {
                                                    "name": "WriteRevision",
                                                    "id": "write_revision",
                                                    "set_scalar": {
                                                        "artifact": "review_decision",
                                                        "value": "REVISE",
                                                    },
                                                }
                                            ],
                                        },
                                    },
                                },
                            },
                        ],
                    },
                }
            ],
        }

        path = self.write_workflow(workflow)
        loaded = self.loader.load_bundle(path)

        body_steps = {
            step["name"]: step["step_id"]
            for step in materialize_projection_body_steps(loaded)[0]["repeat_until"]["steps"]
        }
        assert (
            body_steps["PrepareCallInputs"]
            == "root.review_loop.iteration_body.prepare_call_inputs"
        )
        assert body_steps["RunReviewLoop"] == "root.review_loop.iteration_body.run_review_loop"
        assert body_steps["RouteDecision.APPROVE"] == "root.review_loop.iteration_body.route_decision.approve_path"
        assert (
            body_steps["RouteDecision.APPROVE.WriteApproved"]
            == "root.review_loop.iteration_body.route_decision.approve_path.write_approved"
        )
        assert body_steps["RouteDecision"] == "root.review_loop.iteration_body.route_decision"

    def test_frontend_generated_loop_recur_repeat_until_shape_loads(self, monkeypatch: pytest.MonkeyPatch):
        """Frontend-generated loop/recur workflows should load through the shared repeat_until surface."""
        _enable_v214_loader(monkeypatch)

        workflow_path = self.workspace / "loop_recur_minimal.yaml"
        workflow_path.write_text(
            yaml.safe_dump(_compile_loop_recur_workflow(self.workspace), sort_keys=False),
            encoding="utf-8",
        )

        generated_loader = WorkflowLoader(
            self.workspace,
            boundary_validation_policy=WorkflowBoundaryValidationPolicy.DEDICATED_RUNTIME_PROOF,
        )
        loaded = generated_loader.load_bundle(workflow_path)
        body_steps = {
            step["name"]: step["step_id"] for step in materialize_projection_body_steps(loaded)
        }

        assert body_steps["loop-recur-minimal__loop"] == "root.loop_recur_minimal__loop"
        assert any(
            checkpoint.node_id == "root.loop_recur_minimal__loop"
            and checkpoint.checkpoint_kind == "repeat_until_frame"
            for checkpoint in loaded.runtime_plan.resume_checkpoints
        )

    def test_frontend_generated_loop_recur_on_exhausted_refs_only_accept_loop_frame_state_outputs(self):
        """Compiler validation accepts only the exact generated loop-frame state refs."""
        from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
        from orchestrator.workflow_lisp.lowering import validate_lowered_workflows

        lowered = _compile_loop_recur_scalar_frame_carriage_workflow(self.workspace)
        validated = validate_lowered_workflows((lowered,), workspace_root=self.workspace)
        surface = thaw_surface_workflow(
            validated["loop-recur-on-exhausted-scalar-frame-carriage"]
        )
        loop_step = next(step for step in surface["steps"] if step["name"].endswith("__loop"))
        outputs = loop_step["repeat_until"]["on_exhausted"]["outputs"]

        assert outputs["result__attempt_count"] == {
            "ref": (
                "root.steps.loop-recur-on-exhausted-scalar-frame-carriage__loop."
                "artifacts.state__attempt_count"
            )
        }
        assert outputs["result__reason"] == {
            "ref": (
                "root.steps.loop-recur-on-exhausted-scalar-frame-carriage__loop."
                "artifacts.state__exhaustion_reason"
            )
        }

        cases = (
            {
                "attempt_count": (
                    "root.steps.loop-recur-on-exhausted-scalar-frame-carriage__loop."
                    "artifacts.result__attempt_count"
                ),
                "reason": (
                    "root.steps.loop-recur-on-exhausted-scalar-frame-carriage__loop."
                    "artifacts.result__reason"
                ),
            },
            {
                "attempt_count": (
                    "root.steps.loop-recur-on-exhausted-scalar-frame-carriage__loop."
                    "artifacts.state__bogus"
                ),
                "reason": (
                    "root.steps.loop-recur-on-exhausted-scalar-frame-carriage__loop."
                    "artifacts.state__attempt_count"
                ),
            },
        )
        for refs in cases:
            mutated_mapping = deepcopy(lowered.authored_mapping)
            mutated_step = next(
                step for step in mutated_mapping["steps"] if step["name"].endswith("__loop")
            )
            mutated_outputs = mutated_step["repeat_until"]["on_exhausted"]["outputs"]
            mutated_outputs["result__attempt_count"] = {"ref": refs["attempt_count"]}
            mutated_outputs["result__reason"] = {"ref": refs["reason"]}
            mutated = replace(lowered, authored_mapping=mutated_mapping)

            with pytest.raises(LispFrontendCompileError) as exc_info:
                validate_lowered_workflows((mutated,), workspace_root=self.workspace)

            messages = [diagnostic.message for diagnostic in exc_info.value.diagnostics]
            assert any(
                "repeat_until.on_exhausted.outputs.result__attempt_count must be a scalar literal"
                in message
                for message in messages
            )
            assert any(
                "repeat_until.on_exhausted.outputs.result__reason must be a scalar literal"
                in message
                for message in messages
            )

    def test_match_requires_enum_ref(self):
        """Structured match only accepts enum refs."""
        workflow = {
            "version": "2.6",
            "name": "invalid-match",
            "artifacts": {
                "attempt_count": {
                    "kind": "scalar",
                    "type": "integer",
                }
            },
            "steps": [
                {
                    "name": "WriteAttempts",
                    "id": "write_attempts",
                    "set_scalar": {
                        "artifact": "attempt_count",
                        "value": 1,
                    },
                },
                {
                    "name": "RouteDecision",
                    "id": "route_decision",
                    "match": {
                        "ref": "root.steps.WriteAttempts.artifacts.attempt_count",
                        "cases": {
                            "1": [{"name": "HandleOne", "command": ["echo", "one"]}],
                        },
                    },
                },
            ],
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("match.ref must resolve to an enum artifact or input" in str(err.message)
                  for err in exc_info.value.errors)

    def test_match_rejects_duplicate_case_ids(self):
        """Structured match case ids must stay unique within one statement."""
        workflow = {
            "version": "2.6",
            "name": "duplicate-match-case-ids",
            "artifacts": {
                "review_decision": {
                    "kind": "scalar",
                    "type": "enum",
                    "allowed": ["APPROVE", "REVISE"],
                },
                "route_action": {
                    "kind": "scalar",
                    "type": "enum",
                    "allowed": ["SHIP", "FIX"],
                },
            },
            "steps": [
                {
                    "name": "WriteDecision",
                    "id": "write_decision",
                    "set_scalar": {
                        "artifact": "review_decision",
                        "value": "APPROVE",
                    },
                },
                {
                    "name": "RouteDecision",
                    "id": "route_decision",
                    "match": {
                        "ref": "root.steps.WriteDecision.artifacts.review_decision",
                        "cases": {
                            "APPROVE": {
                                "id": "decision_path",
                                "outputs": {
                                    "route_action": {
                                        "kind": "scalar",
                                        "type": "enum",
                                        "allowed": ["SHIP", "FIX"],
                                        "from": {
                                            "ref": "self.steps.WriteApproved.artifacts.route_action",
                                        },
                                    }
                                },
                                "steps": [
                                    {
                                        "name": "WriteApproved",
                                        "id": "write_approved",
                                        "set_scalar": {
                                            "artifact": "route_action",
                                            "value": "SHIP",
                                        },
                                    }
                                ],
                            },
                            "REVISE": {
                                "id": "decision_path",
                                "outputs": {
                                    "route_action": {
                                        "kind": "scalar",
                                        "type": "enum",
                                        "allowed": ["SHIP", "FIX"],
                                        "from": {
                                            "ref": "self.steps.WriteRevision.artifacts.route_action",
                                        },
                                    }
                                },
                                "steps": [
                                    {
                                        "name": "WriteRevision",
                                        "id": "write_revision",
                                        "set_scalar": {
                                            "artifact": "route_action",
                                            "value": "FIX",
                                        },
                                    }
                                ],
                            },
                        },
                    },
                },
            ],
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("duplicate case id 'decision_path'" in str(err.message)
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

    def test_assert_equals_rejects_env_namespace(self):
        """AT-7 applies to legacy assert variable substitution surfaces."""
        workflow = {
            "version": "1.5",
            "name": "assert-env-invalid",
            "steps": [{
                "name": "Gate",
                "assert": {
                    "equals": {
                        "left": "${env.SECRET}",
                        "right": "APPROVE",
                    }
                },
            }],
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("${env.*} namespace not allowed" in str(err.message)
                  for err in exc_info.value.errors)

    def test_typed_assert_rejects_multiple_operator_keys(self):
        """Typed predicate nodes must declare exactly one operator."""
        workflow = {
            "version": "1.6",
            "name": "typed-predicate-multi-key",
            "steps": [
                {
                    "name": "WriteReady",
                    "command": ["echo", "ok"],
                    "expected_outputs": [{
                        "name": "ready",
                        "path": "state/ready.txt",
                        "type": "bool",
                    }],
                },
                {
                    "name": "GateReady",
                    "assert": {
                        "artifact_bool": {"ref": "root.steps.WriteReady.artifacts.ready"},
                        "compare": {"left": 1, "op": "eq", "right": 1},
                    },
                },
            ],
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert any("exactly one typed predicate operator" in str(err.message)
                  for err in exc_info.value.errors)

    def test_nested_typed_predicates_reject_multiple_operator_keys(self):
        """Nested typed predicates under all_of/any_of/not keep the same exclusivity rule."""
        workflow = {
            "version": "1.6",
            "name": "typed-predicate-nested-multi-key",
            "steps": [
                {
                    "name": "WriteReady",
                    "command": ["echo", "ok"],
                    "expected_outputs": [{
                        "name": "ready",
                        "path": "state/ready.txt",
                        "type": "bool",
                    }],
                },
                {
                    "name": "GateReady",
                    "assert": {
                        "all_of": [
                            {
                                "artifact_bool": {"ref": "root.steps.WriteReady.artifacts.ready"},
                                "compare": {"left": 1, "op": "eq", "right": 2},
                            }
                        ]
                    },
                },
            ],
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert any("exactly one typed predicate operator" in str(err.message)
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

    def test_workflow_inputs_require_version_2_1(self):
        """Workflow signatures are gated after the v2.0 stable-id tranche."""
        workflow = {
            "version": "2.0",
            "name": "signature-gated",
            "inputs": {
                "max_cycles": {
                    "kind": "scalar",
                    "type": "integer",
                }
            },
            "steps": [{
                "name": "RunCheck",
                "id": "run_check",
                "command": ["echo", "ok"],
            }],
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert any("inputs requires version '2.1'" in str(err.message)
                  for err in exc_info.value.errors)

    def test_if_else_requires_version_2_2(self):
        """Structured if/else is gated after workflow signatures land."""
        workflow = {
            "version": "2.1",
            "name": "if-else-gated",
            "artifacts": {
                "ready": {
                    "kind": "scalar",
                    "type": "bool",
                }
            },
            "steps": [
                {
                    "name": "SetReady",
                    "set_scalar": {
                        "artifact": "ready",
                        "value": True,
                    },
                },
                {
                    "name": "RouteReview",
                    "if": {
                        "artifact_bool": {
                            "ref": "root.steps.SetReady.artifacts.ready",
                        }
                    },
                    "then": {
                        "steps": [
                            {
                                "name": "WriteApproved",
                                "set_scalar": {
                                    "artifact": "ready",
                                    "value": True,
                                },
                            }
                        ],
                    },
                },
            ],
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert any("if/else requires version '2.2'" in str(err.message)
                  for err in exc_info.value.errors)

    def test_workflow_outputs_require_from_binding(self):
        """Workflow outputs must declare an explicit export source."""
        workflow = {
            "version": "2.1",
            "name": "missing-output-source",
            "outputs": {
                "review_decision": {
                    "kind": "scalar",
                    "type": "bool",
                }
            },
            "steps": [{
                "name": "RunCheck",
                "command": ["echo", "ok"],
            }],
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert any("outputs.review_decision missing required 'from'" in str(err.message)
                  for err in exc_info.value.errors)

    def test_workflow_relpath_boundaries_accept_type_without_kind(self):
        """Workflow-boundary relpath contracts may omit redundant kind: relpath."""
        workflow = {
            "version": "2.1",
            "name": "relpath-boundary-style",
            "inputs": {
                "task_path": {
                    "type": "relpath",
                    "under": "docs/tasks",
                    "must_exist_target": True,
                }
            },
            "outputs": {
                "report_path": {
                    "type": "relpath",
                    "under": "artifacts/reports",
                    "must_exist_target": True,
                    "from": {"ref": "root.steps.GenerateReport.artifacts.report_path"},
                }
            },
            "steps": [{
                "name": "GenerateReport",
                "command": ["echo", "ok"],
                "expected_outputs": [{
                    "name": "report_path",
                    "path": "state/report_path.txt",
                    "type": "relpath",
                    "under": "artifacts/reports",
                }],
            }],
        }

        path = self.write_workflow(workflow)

        loaded = self.loader.load(path)
        surface = thaw_surface_workflow(loaded)

        assert surface["inputs"]["task_path"]["type"] == "relpath"
        assert "kind" not in surface["inputs"]["task_path"]
        assert surface["outputs"]["report_path"]["type"] == "relpath"
        assert "kind" not in surface["outputs"]["report_path"]

    def test_v210_workflow_boundary_and_scalar_artifacts_accept_string(self):
        """Workflow signatures and scalar artifacts accept string contracts in v2.10."""
        workflow = {
            "version": "2.10",
            "name": "string-signatures",
            "inputs": {
                "resume_note": {
                    "kind": "scalar",
                    "type": "string",
                    "default": "  keep exact whitespace  ",
                }
            },
            "outputs": {
                "session_id": {
                    "kind": "scalar",
                    "type": "string",
                    "from": {"ref": "root.steps.RecordSession.artifacts.session_id"},
                }
            },
            "artifacts": {
                "session_id": {
                    "kind": "scalar",
                    "type": "string",
                }
            },
            "steps": [{
                "name": "RecordSession",
                "set_scalar": {
                    "artifact": "session_id",
                    "value": "session-abc-123",
                },
                "publishes": [{"artifact": "session_id", "from": "session_id"}],
            }],
        }

        path = self.write_workflow(workflow)
        loaded = self.loader.load(path)
        surface = thaw_surface_workflow(loaded)

        assert surface["inputs"]["resume_note"]["type"] == "string"
        assert surface["outputs"]["session_id"]["type"] == "string"
        assert surface["artifacts"]["session_id"]["type"] == "string"

    def test_v210_provider_session_fresh_accepts_top_level_provider_step(self):
        """provider_session fresh mode is valid on root-level provider steps in v2.10."""
        workflow = {
            "version": "2.10",
            "name": "provider-session-fresh",
            "providers": {
                "session_provider": {
                    "command": ["tool", "--model", "${model}"],
                    "input_mode": "stdin",
                    "session_support": {
                        "metadata_mode": "codex_exec_jsonl_stdout",
                        "fresh_command": ["tool", "--json", "--model", "${model}"],
                        "resume_command": ["tool", "resume", "${SESSION_ID}", "--json", "--model", "${model}"],
                    },
                }
            },
            "artifacts": {
                "implementation_session_id": {
                    "kind": "scalar",
                    "type": "string",
                }
            },
            "steps": [{
                "name": "StartImplementation",
                "provider": "session_provider",
                "provider_session": {
                    "mode": "fresh",
                    "publish_artifact": "implementation_session_id",
                },
            }],
        }

        path = self.write_workflow(workflow)
        loaded = self.loader.load(path)
        surface = thaw_surface_workflow(loaded)

        assert surface["steps"][0]["provider_session"]["mode"] == "fresh"

    def test_v210_provider_session_rejects_dynamic_provider_name(self):
        """provider_session support is loader-validated and requires a static provider alias."""
        workflow = {
            "version": "2.10",
            "name": "provider-session-dynamic-provider",
            "context": {"provider_alias": "session_provider"},
            "providers": {
                "session_provider": {
                    "command": ["tool", "--model", "${model}"],
                    "input_mode": "stdin",
                    "session_support": {
                        "metadata_mode": "codex_exec_jsonl_stdout",
                        "fresh_command": ["tool", "--json", "--model", "${model}"],
                    },
                }
            },
            "artifacts": {
                "implementation_session_id": {
                    "kind": "scalar",
                    "type": "string",
                }
            },
            "steps": [{
                "name": "StartImplementation",
                "provider": "${context.provider_alias}",
                "provider_session": {
                    "mode": "fresh",
                    "publish_artifact": "implementation_session_id",
                },
            }],
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert any("requires a static provider template" in str(err.message)
                  for err in exc_info.value.errors)

    def test_v210_provider_session_rejects_nested_usage(self):
        """provider_session is rejected in nested loop/branch scopes in v1."""
        workflow = {
            "version": "2.10",
            "name": "provider-session-nested",
            "providers": {
                "session_provider": {
                    "command": ["tool", "--model", "${model}"],
                    "input_mode": "stdin",
                    "session_support": {
                        "metadata_mode": "codex_exec_jsonl_stdout",
                        "fresh_command": ["tool", "--json", "--model", "${model}"],
                    },
                }
            },
            "artifacts": {
                "implementation_session_id": {
                    "kind": "scalar",
                    "type": "string",
                }
            },
            "steps": [{
                "name": "Loop",
                "for_each": {
                    "items": ["one"],
                    "steps": [{
                        "name": "StartImplementation",
                        "provider": "session_provider",
                        "provider_session": {
                            "mode": "fresh",
                            "publish_artifact": "implementation_session_id",
                        },
                    }],
                },
            }],
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert any("authored directly under the root workflow steps list" in str(err.message)
                  for err in exc_info.value.errors)

    def test_v210_provider_session_rejects_retries_and_persist_false(self):
        """Session-enabled steps reject authored retries and fresh-step artifact suppression."""
        workflow = {
            "version": "2.10",
            "name": "provider-session-fresh-invalid-step-settings",
            "providers": {
                "session_provider": {
                    "command": ["tool", "--model", "${model}"],
                    "input_mode": "stdin",
                    "session_support": {
                        "metadata_mode": "codex_exec_jsonl_stdout",
                        "fresh_command": ["tool", "--json", "--model", "${model}"],
                    },
                }
            },
            "artifacts": {
                "implementation_session_id": {
                    "kind": "scalar",
                    "type": "string",
                }
            },
            "steps": [{
                "name": "StartImplementation",
                "provider": "session_provider",
                "retries": 2,
                "persist_artifacts_in_state": False,
                "provider_session": {
                    "mode": "fresh",
                    "publish_artifact": "implementation_session_id",
                },
            }],
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert any("forbids retries" in str(err.message) for err in exc_info.value.errors)
        assert any("requires persist_artifacts_in_state to be true" in str(err.message)
                  for err in exc_info.value.errors)

    def test_v210_provider_session_resume_requires_unique_any_freshness_consume(self):
        """Resume steps require exactly one matching consume and forbid since_last_consume freshness."""
        workflow = {
            "version": "2.10",
            "name": "provider-session-resume-invalid-consume",
            "providers": {
                "session_provider": {
                    "command": ["tool", "--model", "${model}"],
                    "input_mode": "stdin",
                    "session_support": {
                        "metadata_mode": "codex_exec_jsonl_stdout",
                        "fresh_command": ["tool", "--json", "--model", "${model}"],
                        "resume_command": ["tool", "resume", "${SESSION_ID}", "--json", "--model", "${model}"],
                    },
                }
            },
            "artifacts": {
                "implementation_session_id": {
                    "kind": "scalar",
                    "type": "string",
                },
                "review_feedback": {
                    "kind": "scalar",
                    "type": "string",
                },
            },
            "steps": [{
                "name": "ResumeImplementation",
                "provider": "session_provider",
                "consumes": [
                    {
                        "artifact": "implementation_session_id",
                        "policy": "latest_successful",
                        "freshness": "since_last_consume",
                    },
                    {
                        "artifact": "review_feedback",
                        "policy": "latest_successful",
                    },
                ],
                "prompt_consumes": ["implementation_session_id"],
                "consume_bundle": {
                    "path": "state/resume_bundle.json",
                    "include": ["implementation_session_id", "review_feedback"],
                },
                "provider_session": {
                    "mode": "resume",
                    "session_id_from": "implementation_session_id",
                },
            }],
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert any("must omit freshness or set freshness to 'any'" in str(err.message)
                  for err in exc_info.value.errors)
        assert any("cannot be re-included through prompt_consumes" in str(err.message)
                  for err in exc_info.value.errors)
        assert any("cannot be re-included through consume_bundle.include" in str(err.message)
                  for err in exc_info.value.errors)

    def test_if_else_rejects_goto_inside_branch_steps(self):
        """The first structured-control tranche rejects branch-local goto escapes."""
        workflow = {
            "version": "2.2",
            "name": "if-else-no-goto",
            "artifacts": {
                "ready": {
                    "kind": "scalar",
                    "type": "bool",
                }
            },
            "steps": [
                {
                    "name": "SetReady",
                    "id": "set_ready",
                    "set_scalar": {
                        "artifact": "ready",
                        "value": True,
                    },
                },
                {
                    "name": "RouteReview",
                    "id": "route_review",
                    "if": {
                        "artifact_bool": {
                            "ref": "root.steps.SetReady.artifacts.ready",
                        }
                    },
                    "then": {
                        "steps": [
                            {
                                "name": "WriteApproved",
                                "id": "write_approved",
                                "set_scalar": {
                                    "artifact": "ready",
                                    "value": True,
                                },
                                "on": {
                                    "success": {
                                        "goto": "_end",
                                    }
                                },
                            }
                        ],
                    },
                    "else": {
                        "steps": [
                            {
                                "name": "WriteRevision",
                                "id": "write_revision",
                                "set_scalar": {
                                    "artifact": "ready",
                                    "value": False,
                                },
                            }
                        ],
                    },
                },
            ],
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert any("goto" in str(err.message) and "structured if/else" in str(err.message)
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

        loop_step = materialize_projection_body_steps(loaded)[1]
        assert loop_step["step_id"] == "root.loop"
        assert loop_step["for_each"]["steps"][0]["step_id"] == "root.loop.set_iteration_flag"
        assert loop_step["for_each"]["steps"][1]["step_id"] == "root.loop.assert_scopes"

    def test_shared_validation_accepts_nested_implementation_phase_without_split_leaves(self):
        authored = _compile_nested_implementation_phase_workflow(self.workspace)

        assert authored["version"] == "2.14"
        assert any("match" in step for step in authored["steps"])
        assert "return__execution_report" in authored["outputs"]

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
        steps_a = materialize_projection_body_steps(loaded_a)
        steps_b = materialize_projection_body_steps(loaded_b)

        assert steps_a[1]["step_id"] == "root.loop"
        assert steps_b[2]["step_id"] == "root.loop"
        assert steps_a[1]["for_each"]["steps"][0]["step_id"] == "root.loop.process"
        assert steps_b[2]["for_each"]["steps"][0]["step_id"] == "root.loop.process"

    def test_compiler_generated_step_ids_disambiguate_colliding_names(self):
        """Compiler-generated step ids must remain unique when names normalize alike."""
        workflow = {
            "version": "2.0",
            "name": "compiler-id-collisions",
            "steps": [
                {
                    "name": "Build A",
                    "command": ["echo", "first"],
                },
                {
                    "name": "Build-A",
                    "command": ["echo", "second"],
                },
            ],
        }

        path = self.write_workflow(workflow)
        loaded = self.loader.load(path)
        steps = materialize_projection_body_steps(loaded)

        assert steps[0]["step_id"] == "root.build_a"
        assert steps[1]["step_id"] == "root.build_a_2"
        assert steps[0]["step_id"] != steps[1]["step_id"]

    def test_v2_parent_refs_reject_multi_visit_targets(self):
        """Scoped parent refs cannot target provably multi-visit parent steps."""
        workflow = {
            "version": "2.0",
            "name": "parent-ref-cycle",
            "artifacts": {
                "flag": {
                    "kind": "scalar",
                    "type": "bool",
                },
            },
            "steps": [
                {
                    "name": "Start",
                    "id": "start",
                    "set_scalar": {
                        "artifact": "flag",
                        "value": True,
                    },
                    "on": {
                        "success": {
                            "goto": "Loop",
                        }
                    },
                },
                {
                    "name": "Loop",
                    "id": "loop",
                    "for_each": {
                        "items": ["one"],
                        "steps": [
                            {
                                "name": "CheckParent",
                                "id": "check_parent",
                                "assert": {
                                    "artifact_bool": {
                                        "ref": "parent.steps.Start.artifacts.flag",
                                    }
                                },
                            }
                        ],
                    },
                    "on": {
                        "success": {
                            "goto": "Start",
                        }
                    },
                },
            ],
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any(
            "targets multi-visit step 'Start'" in str(err.message)
            for err in exc_info.value.errors
        )

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

    def test_max_visits_does_not_bypass_execution_field_exclusivity(self):
        """max_visits must not suppress command/provider exclusivity validation."""
        workflow = {
            "version": "1.8",
            "name": "invalid-max-visits-step",
            "providers": {
                "mock_provider": {
                    "command": ["bash", "-lc", "cat >/dev/null; echo ok"],
                    "input_mode": "stdin",
                }
            },
            "steps": [{
                "name": "BadStep",
                "max_visits": 1,
                "provider": "mock_provider",
                "command": ["bash", "-lc", "echo invalid"],
            }],
        }

        path = self.write_workflow(workflow)

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("mutually exclusive" in str(err.message) for err in exc_info.value.errors)

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
        surface = thaw_surface_workflow(result)

        assert surface["version"] == "1.1"
        assert surface["name"] == "minimal"
        assert len(surface["steps"]) == 1

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
        surface = thaw_surface_workflow(result)

        assert "providers" in surface
        assert "claude" in surface["providers"]

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
        surface = thaw_surface_workflow(result)

        assert len(surface["steps"]) == 2
        assert "for_each" in surface["steps"][1]

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
        surface = thaw_surface_workflow(result)

        # Should load without errors
        assert surface["context"]["project"] == "test"

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
        surface = thaw_surface_workflow(result)

        # Should load without errors
        assert len(surface["steps"]) == 2

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
        surface = thaw_surface_workflow(result)
        assert surface["steps"][0]["expected_outputs"][0]["type"] == "relpath"

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
        surface = thaw_surface_workflow(result)
        output_spec = surface["steps"][0]["expected_outputs"][0]
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

    def test_expected_outputs_string_type_accepts_in_v2_10(self):
        """expected_outputs type string is allowed once the 2.10 scalar contract lands."""
        workflow = {
            "version": "2.10",
            "name": "string output",
            "steps": [{
                "name": "DraftPlan",
                "command": ["echo", "ok"],
                "expected_outputs": [{
                    "name": "execution_summary",
                    "path": "state/execution_summary.txt",
                    "type": "string"
                }]
            }]
        }

        path = self.write_workflow(workflow)
        loaded = self.loader.load(path)
        surface = thaw_surface_workflow(loaded)

        assert surface["steps"][0]["expected_outputs"][0]["type"] == "string"

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
        surface = thaw_surface_workflow(result)
        assert surface["version"] == "1.2"
        assert "artifacts" in surface
        assert "execution_log" in surface["artifacts"]

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
        surface = thaw_surface_workflow(result)
        assert surface["version"] == "1.4"
        assert "artifacts" in surface
        assert "execution_log" in surface["artifacts"]

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
        surface = thaw_surface_workflow(result)
        assert surface["version"] == "1.4"
        assert surface["steps"][0]["consumes"][0]["artifact"] == "execution_log"

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
        surface = thaw_surface_workflow(loaded)
        consume_spec = surface["steps"][0]["consumes"][0]
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

    def test_v12_consume_prompt_requires_mapping(self):
        """consumes[*].prompt must be a mapping when provided."""
        workflow = {
            "version": "1.2",
            "name": "consume-prompt-mapping-required",
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
                    "prompt": "reference",
                }],
            }],
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("consume prompt metadata must be a mapping" in str(err.message)
                   for err in exc_info.value.errors)

    def test_v12_consume_prompt_mode_rejects_unknown_value(self):
        """consumes[*].prompt.mode must be one of the supported rendering modes."""
        workflow = {
            "version": "1.2",
            "name": "consume-prompt-mode-invalid",
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
                    "prompt": {
                        "mode": "summary",
                    },
                }],
            }],
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("consume prompt mode must be one of: content, reference, none" in str(err.message)
                   for err in exc_info.value.errors)

    @pytest.mark.parametrize(
        "field,bad_value",
        [
            ("label", 7),
            ("description", {"not": "string"}),
            ("format_hint", ["not", "string"]),
            ("example", 1),
            ("role", False),
        ],
    )
    def test_v12_consume_prompt_fields_require_strings(self, field, bad_value):
        """Nested consumes[*].prompt guidance fields must be strings when present."""
        workflow = {
            "version": "1.2",
            "name": "consume-prompt-field-invalid",
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
                    "prompt": {
                        field: bad_value,
                    },
                }],
            }],
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any(f"consume prompt '{field}' must be a string" in str(err.message)
                   for err in exc_info.value.errors)

    def test_v12_legacy_consume_guidance_without_prompt_remains_valid(self):
        """Legacy row-level consume guidance remains valid when nested prompt metadata is absent."""
        workflow = {
            "version": "1.2",
            "name": "consume-legacy-guidance-valid",
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
        surface = thaw_surface_workflow(loaded)
        consume_spec = surface["steps"][0]["consumes"][0]

        assert consume_spec["description"] == "Primary execution log generated by ExecutePlan."
        assert consume_spec["format_hint"] == "Workspace-relative .log path"
        assert consume_spec["example"] == "artifacts/work/latest-execution.log"
        assert "prompt" not in consume_spec

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

        assert loaded.surface.name == "for-each-cross-scope-producer"

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
        surface = thaw_surface_workflow(loaded)
        assert surface["artifacts"]["failed_count"]["kind"] == "scalar"

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
        surface = thaw_surface_workflow(loaded)
        assert surface["artifacts"]["execution_log"]["type"] == "relpath"

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
        surface = thaw_surface_workflow(result)
        assert surface["version"] == "1.4"
        assert surface["steps"][0]["output_bundle"]["path"] == "artifacts/work/summary.json"

    def test_v210_output_bundle_accepts_string_field(self):
        """output_bundle field type string is allowed in v2.10."""
        workflow = {
            "version": "2.10",
            "name": "v210-output-bundle-string",
            "steps": [{
                "name": "Assess",
                "command": ["echo", "ok"],
                "output_bundle": {
                    "path": "artifacts/work/summary.json",
                    "fields": [{
                        "name": "assistant_text",
                        "json_pointer": "/assistant_text",
                        "type": "string",
                    }],
                },
            }],
        }

        path = self.write_workflow(workflow)
        result = self.loader.load(path)
        surface = thaw_surface_workflow(result)
        assert surface["version"] == "2.10"
        assert surface["steps"][0]["output_bundle"]["fields"][0]["type"] == "string"

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

    def test_variant_output_field_requires_type(self):
        """Each variant_output field requires an explicit type, even with recursive schemas supported."""
        workflow = {
            "version": "2.14",
            "name": "variant-output-field-shape",
            "steps": [{
                "name": "Assess",
                "command": ["echo", "ok"],
                "variant_output": {
                    "path": "state/variant_bundle.json",
                    "discriminant": {
                        "name": "implementation_state",
                        "json_pointer": "/implementation_state",
                        "type": "enum",
                        "allowed": ["COMPLETED"],
                    },
                    "shared_fields": [{
                        "name": "status",
                        "json_pointer": "/status",
                    }],
                    "variants": {
                        "COMPLETED": {"fields": []},
                    },
                },
            }],
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("variant_output.shared_fields[0] missing required 'type'" in str(err.message)
                   for err in exc_info.value.errors)

    def test_output_bundle_rejects_collection_field_types_in_authored_yaml(self):
        """Authored YAML DSL must not accept lowered-only collection schema types."""
        workflow = {
            "version": "1.3",
            "name": "authored-output-bundle-collections",
            "steps": [{
                "name": "Collect",
                "command": ["echo", "ok"],
                "output_bundle": {
                    "path": "state/bundle.json",
                    "fields": [{
                        "name": "attempt_ids",
                        "json_pointer": "/attempt_ids",
                        "type": "list",
                        "items": {"type": "integer"},
                    }],
                },
            }],
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("output_bundle.fields[0] invalid output_bundle field type 'list'" in str(err.message)
                   for err in exc_info.value.errors)

    def test_variant_output_rejects_collection_field_types_in_authored_yaml(self):
        """Authored YAML variant_output must also reject lowered-only collection schema types."""
        workflow = {
            "version": "2.14",
            "name": "authored-variant-output-collections",
            "steps": [{
                "name": "Assess",
                "command": ["echo", "ok"],
                "variant_output": {
                    "path": "state/variant_bundle.json",
                    "discriminant": {
                        "name": "implementation_state",
                        "json_pointer": "/implementation_state",
                        "type": "enum",
                        "allowed": ["COMPLETED"],
                    },
                    "shared_fields": [{
                        "name": "attempt_ids",
                        "json_pointer": "/attempt_ids",
                        "type": "list",
                        "items": {"type": "integer"},
                    }],
                    "variants": {
                        "COMPLETED": {"fields": []},
                    },
                },
            }],
        }

        path = self.write_workflow(workflow)
        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        assert exc_info.value.exit_code == 2
        assert any("variant_output.shared_fields[0] invalid variant_output field type 'list'" in str(err.message)
                   for err in exc_info.value.errors)

    def test_loader_accepts_collection_field_types_for_lowered_structured_result_workflows(self):
        """Frontend-lowered validation still accepts recursive collection schemas."""
        from orchestrator.workflow_lisp.lowering import validate_lowered_workflows

        lowered = _compile_collection_structured_result_workflow(self.workspace)
        validated = validate_lowered_workflows((lowered,), workspace_root=self.workspace)
        surface = thaw_surface_workflow(validated["orchestrate"])
        fields = surface["steps"][0]["output_bundle"]["fields"]

        assert [field["type"] for field in fields] == [
            "string",
            "optional",
            "list",
            "map",
            "list",
        ]

    def _v215_workflow(self) -> dict:
        return {
            "version": "2.15",
            "name": "v215-root-result",
            "steps": [{"name": "emit", "command": ["python", "-c", "print('true')"]}],
        }

    def _guidance_output_bundle_workflow(self, version: str = "2.15") -> dict:
        return {
            "version": version,
            "name": "guided-output-bundle",
            "steps": [{
                "name": "Review",
                "command": ["echo", "ok"],
                "output_bundle": {
                    "path": "state/review.json",
                    "guidance": {
                        "description": "Complete review result.",
                        "format_hint": "Return one JSON object.",
                        "example": {"approved": True},
                    },
                    "fields": [{
                        "name": "approved",
                        "json_pointer": "/review/approved",
                        "type": "bool",
                        "guidance_context": [{
                            "json_pointer": "/review",
                            "description": "The complete review.",
                            "example": {"approved": True},
                        }],
                        "description": "True only when no blockers remain.",
                        "format_hint": "JSON boolean.",
                        "example": True,
                    }],
                },
            }],
            "outputs": {
                "approved": {
                    "kind": "scalar",
                    "type": "bool",
                    "from": {"ref": "root.steps.Review.artifacts.approved"},
                },
            },
            "result_guidance": {
                "description": "The public review result.",
                "format_hint": "Use the declared output shape.",
                "example": None,
            },
        }

    def _guidance_variant_output_workflow(self, version: str = "2.15") -> dict:
        return {
            "version": version,
            "name": "guided-variant-output",
            "steps": [{
                "name": "Decide",
                "command": ["echo", "ok"],
                "variant_output": {
                    "path": "state/decision.json",
                    "guidance": {"description": "Complete decision result."},
                    "discriminant": {
                        "name": "decision",
                        "json_pointer": "/decision",
                        "type": "enum",
                        "allowed": ["APPROVE", "REVISE"],
                    },
                    "shared_fields": [{
                        "name": "score",
                        "json_pointer": "/metrics/score",
                        "type": "float",
                        "guidance_by_variant": {
                            "APPROVE": {
                                "description": "Approval confidence.",
                                "format_hint": "A number from zero to one.",
                                "example": 0.95,
                                "guidance_context": [{
                                    "json_pointer": "/metrics",
                                    "description": "Decision metrics.",
                                    "example": {"score": 0.95},
                                }],
                            },
                            "REVISE": {
                                "description": "Revision confidence.",
                                "example": 0.8,
                            },
                        },
                    }],
                    "variants": {
                        "APPROVE": {"fields": [{
                            "name": "approved",
                            "json_pointer": "/approved",
                            "type": "bool",
                            "description": "The approval flag.",
                            "example": True,
                        }]},
                        "REVISE": {"fields": []},
                    },
                },
            }],
        }

    def _v215_loader(self) -> WorkflowLoader:
        return WorkflowLoader(self.workspace)

    def test_v215_guidance_contracts_accept_every_public_container(self):
        loaded = self._v215_loader().load(
            self.write_workflow(self._guidance_output_bundle_workflow())
        )
        surface = thaw_surface_workflow(loaded)

        assert surface["steps"][0]["output_bundle"]["guidance"]["example"] == {
            "approved": True,
        }
        assert surface["steps"][0]["output_bundle"]["fields"][0]["guidance_context"] == [{
            "json_pointer": "/review",
            "description": "The complete review.",
            "example": {"approved": True},
        }]

        variant_loaded = self._v215_loader().load(
            self.write_workflow(self._guidance_variant_output_workflow())
        )
        variant = thaw_surface_workflow(variant_loaded)["steps"][0]["variant_output"]
        assert list(variant["shared_fields"][0]["guidance_by_variant"]) == ["APPROVE", "REVISE"]

    @pytest.mark.parametrize(
        ("mutate", "expected"),
        [
            (lambda workflow: workflow["steps"][0]["output_bundle"].update(
                guidance={"description": "bundle"}
            ), "output_bundle.guidance requires version '2.15'"),
            (lambda workflow: workflow["steps"][0]["output_bundle"]["fields"][0].update(
                description="field"
            ), "field guidance requires version '2.15'"),
            (lambda workflow: workflow["steps"][0]["output_bundle"]["fields"][0].update(
                guidance_context=[{"json_pointer": "/review", "description": "parent"}]
            ), "field guidance requires version '2.15'"),
            (lambda workflow: workflow.update(result_guidance={"description": "result"}),
             "result_guidance requires version '2.15'"),
        ],
    )
    def test_v214_rejects_every_new_guidance_container(self, mutate, expected):
        workflow = self._guidance_output_bundle_workflow("2.14")
        workflow["steps"][0]["output_bundle"].pop("guidance")
        field = workflow["steps"][0]["output_bundle"]["fields"][0]
        for key in ("description", "format_hint", "example", "guidance_context"):
            field.pop(key, None)
        workflow.pop("result_guidance")
        mutate(workflow)

        with pytest.raises(WorkflowValidationError, match=expected):
            self.loader.load(self.write_workflow(workflow))

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda output: output.update(guidance={"description": "bundle"}),
            lambda output: output["shared_fields"][0].update(description="shared"),
            lambda output: output["shared_fields"][0].update(
                guidance_by_variant={"APPROVE": {"description": "shared variant"}}
            ),
            lambda output: output["variants"]["APPROVE"]["fields"][0].update(
                example=True
            ),
        ],
    )
    def test_v214_rejects_every_variant_guidance_container(self, mutate):
        workflow = self._guidance_variant_output_workflow("2.14")
        output = workflow["steps"][0]["variant_output"]
        output.pop("guidance")
        output["shared_fields"][0].pop("guidance_by_variant")
        field = output["variants"]["APPROVE"]["fields"][0]
        for key in ("description", "example"):
            field.pop(key)
        mutate(output)

        with pytest.raises(WorkflowValidationError, match="requires version '2.15'"):
            self.loader.load(self.write_workflow(workflow))

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"description": ""},
            {"description": "   "},
            {"format_hint": 7},
            {"unknown": "value"},
            {"guidance_context": [{"json_pointer": "/review", "description": "nested"}]},
        ],
    )
    def test_v215_bundle_guidance_rejects_invalid_closed_payloads(self, payload):
        workflow = self._guidance_output_bundle_workflow()
        workflow["steps"][0]["output_bundle"]["guidance"] = payload

        with pytest.raises(WorkflowValidationError):
            self._v215_loader().load(self.write_workflow(workflow))

    @pytest.mark.parametrize("bundle_kind", ["output_bundle", "variant_output"])
    @pytest.mark.parametrize("misplaced_key", ["description", "format_hint", "example", "guidance_context"])
    def test_v215_bundle_guidance_rejects_guidance_keys_outside_container(
        self, bundle_kind, misplaced_key
    ):
        workflow = (
            self._guidance_output_bundle_workflow()
            if bundle_kind == "output_bundle"
            else self._guidance_variant_output_workflow()
        )
        bundle = workflow["steps"][0][bundle_kind]
        bundle[misplaced_key] = (
            [{"json_pointer": "/parent", "description": "misplaced"}]
            if misplaced_key == "guidance_context"
            else "misplaced"
        )

        with pytest.raises(WorkflowValidationError, match="not allowed at bundle level"):
            self._v215_loader().load(self.write_workflow(workflow))

    @pytest.mark.parametrize(
        ("key", "value"),
        [
            ("description", ""),
            ("description", "  "),
            ("format_hint", 4),
        ],
    )
    def test_v215_direct_field_guidance_rejects_empty_or_invalid_strings(self, key, value):
        workflow = self._guidance_output_bundle_workflow()
        workflow["steps"][0]["output_bundle"]["fields"][0][key] = value

        with pytest.raises(WorkflowValidationError):
            self._v215_loader().load(self.write_workflow(workflow))

    def test_v215_field_guidance_rejects_guidance_nested_in_value_schema(self):
        workflow = self._guidance_output_bundle_workflow()
        field = workflow["steps"][0]["output_bundle"]["fields"][0]
        field.update({"type": "list", "items": {"type": "bool", "description": "nested"}})
        field["example"] = [True]

        with pytest.raises(WorkflowValidationError, match="not allowed in a nested schema"):
            self._v215_loader().load(self.write_workflow(workflow))

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"description": ""},
            {"format_hint": "\t"},
            {"unknown": True},
            {"guidance_context": []},
            {"guidance_by_variant": {"APPROVE": {"description": "no context here"}}},
        ],
    )
    def test_v215_result_guidance_rejects_invalid_closed_payloads(self, payload):
        workflow = self._guidance_output_bundle_workflow()
        workflow["result_guidance"] = payload

        with pytest.raises(WorkflowValidationError):
            self._v215_loader().load(self.write_workflow(workflow))

    def test_v215_result_guidance_requires_at_least_one_output(self):
        workflow = self._guidance_output_bundle_workflow()
        workflow["outputs"] = {}

        with pytest.raises(WorkflowValidationError, match="result_guidance requires at least one declared output"):
            self._v215_loader().load(self.write_workflow(workflow))

    @pytest.mark.parametrize(
        "context_rows",
        [
            [],
            [{"json_pointer": "/review"}],
            [{"json_pointer": "review", "description": "bad syntax"}],
            [{"json_pointer": "/other", "description": "not a prefix"}],
            [{"json_pointer": "/review/approved", "description": "equal leaf"}],
            [
                {"json_pointer": "/review", "description": "first"},
                {"json_pointer": "/review", "description": "duplicate"},
            ],
            [
                {"json_pointer": "/review/details", "description": "deep"},
                {"json_pointer": "/review", "description": "shallow"},
            ],
            [{"json_pointer": "/review/~2bad", "description": "bad escape"}],
        ],
    )
    def test_v215_field_guidance_context_rejects_invalid_pointer_contracts(self, context_rows):
        workflow = self._guidance_output_bundle_workflow()
        field = workflow["steps"][0]["output_bundle"]["fields"][0]
        field["json_pointer"] = "/review/details/approved"
        field["guidance_context"] = context_rows

        with pytest.raises(WorkflowValidationError):
            self._v215_loader().load(self.write_workflow(workflow))

    @pytest.mark.parametrize(
        "row",
        [
            {"json_pointer": "/review", "unknown": "closed"},
            {"json_pointer": "/review", "description": ""},
            {"json_pointer": "/review", "format_hint": []},
        ],
    )
    def test_v215_field_guidance_context_rejects_closed_or_empty_row_payload(self, row):
        workflow = self._guidance_output_bundle_workflow()
        workflow["steps"][0]["output_bundle"]["fields"][0]["guidance_context"] = [row]

        with pytest.raises(WorkflowValidationError):
            self._v215_loader().load(self.write_workflow(workflow))

    def test_v215_field_guidance_context_accepts_rfc6901_escaped_prefixes(self):
        workflow = self._guidance_output_bundle_workflow()
        field = workflow["steps"][0]["output_bundle"]["fields"][0]
        field["json_pointer"] = "/review~1items/detail~0key/approved"
        field["guidance_context"] = [
            {"json_pointer": "/review~1items", "description": "Escaped slash."},
            {"json_pointer": "/review~1items/detail~0key", "description": "Escaped tilde."},
        ]

        self._v215_loader().load(self.write_workflow(workflow))

    def test_v215_root_field_rejects_guidance_context_and_root_with_sibling(self):
        workflow = self._guidance_output_bundle_workflow()
        root_field = workflow["steps"][0]["output_bundle"]["fields"][0]
        root_field["json_pointer"] = ""
        root_field["guidance_context"] = [{"json_pointer": "/review", "description": "bad"}]

        with pytest.raises(WorkflowValidationError, match="root field cannot declare guidance_context"):
            self._v215_loader().load(self.write_workflow(workflow))

        root_field.pop("guidance_context")
        workflow["steps"][0]["output_bundle"]["fields"].append({
            "name": "other", "json_pointer": "/other", "type": "bool"
        })
        with pytest.raises(WorkflowValidationError, match="root json_pointer cannot have sibling fields"):
            self._v215_loader().load(self.write_workflow(workflow))

    @pytest.mark.parametrize(
        "guidance_by_variant",
        [
            {},
            {"UNKNOWN": {"description": "unknown"}},
            {"APPROVE": {}},
        ],
    )
    def test_v215_guidance_by_variant_rejects_unknown_ordered_or_empty_payloads(
        self, guidance_by_variant
    ):
        workflow = self._guidance_variant_output_workflow()
        shared = workflow["steps"][0]["variant_output"]["shared_fields"][0]
        shared["guidance_by_variant"] = guidance_by_variant

        with pytest.raises(WorkflowValidationError):
            self._v215_loader().load(self.write_workflow(workflow))

    def test_v215_guidance_by_variant_rejects_keys_out_of_discriminant_order(self):
        workflow = self._guidance_variant_output_workflow()
        variant_output = workflow["steps"][0]["variant_output"]
        variant_output["discriminant"]["allowed"] = ["REVISE", "APPROVE"]

        with pytest.raises(WorkflowValidationError, match="discriminant allowed order"):
            self._v215_loader().load(self.write_workflow(workflow))

    def test_v215_guidance_by_variant_rejects_direct_guidance_coexistence(self):
        workflow = self._guidance_variant_output_workflow()
        shared = workflow["steps"][0]["variant_output"]["shared_fields"][0]
        shared["description"] = "Direct guidance conflicts."

        with pytest.raises(WorkflowValidationError, match="mutually exclusive"):
            self._v215_loader().load(self.write_workflow(workflow))

    @pytest.mark.parametrize(
        "payload",
        [
            {"description": ""},
            {"unknown": "closed"},
            "not-a-mapping",
        ],
    )
    def test_v215_guidance_by_variant_rejects_invalid_nested_payloads(self, payload):
        workflow = self._guidance_variant_output_workflow()
        shared = workflow["steps"][0]["variant_output"]["shared_fields"][0]
        shared["guidance_by_variant"] = {"APPROVE": payload}

        with pytest.raises(WorkflowValidationError):
            self._v215_loader().load(self.write_workflow(workflow))

    @pytest.mark.parametrize(
        ("example", "expected"),
        [("true", "invalid"), (1, "invalid")],
    )
    def test_v215_field_guidance_examples_obey_field_schema(self, example, expected):
        workflow = self._guidance_output_bundle_workflow()
        workflow["steps"][0]["output_bundle"]["fields"][0]["example"] = example

        with pytest.raises(WorkflowValidationError, match=expected):
            self._v215_loader().load(self.write_workflow(workflow))

    def test_v215_path_guidance_example_checks_safety_without_existence(self):
        workflow = self._guidance_output_bundle_workflow()
        field = workflow["steps"][0]["output_bundle"]["fields"][0]
        field.update({
            "type": "relpath",
            "under": "docs/reviews",
            "must_exist_target": True,
            "example": "docs/reviews/not-created.md",
        })
        workflow.pop("outputs")
        workflow.pop("result_guidance")

        self._v215_loader().load(self.write_workflow(workflow))

        field["example"] = "../outside.md"
        with pytest.raises(WorkflowValidationError, match="invalid"):
            self._v215_loader().load(self.write_workflow(workflow))

    @pytest.mark.parametrize(
        "value",
        [
            {"not-json"},
            ("tuple",),
            {1: "integer key"},
            float("nan"),
        ],
    )
    def test_v215_guidance_json_compatibility_validator_rejects_non_json_values(self, value):
        loader = self._v215_loader()
        loader._validate_guidance_payload(
            {"example": value},
            context="test.guidance",
            version="2.15",
            allow_context=False,
        )

        assert any("JSON-compatible" in error.message for error in loader.errors)

    @pytest.mark.parametrize("container", ["context", "variant"])
    def test_v215_nested_guidance_examples_reject_non_json_values_directly(self, container):
        loader = self._v215_loader()
        field = {
            "name": "approved",
            "json_pointer": "/review/approved",
            "type": "bool",
        }
        if container == "context":
            loader._validate_guidance_payload(
                {
                    "guidance_context": [{
                        "json_pointer": "/review",
                        "example": {"not-json"},
                    }],
                },
                context="field",
                version="2.15",
                allow_context=True,
                leaf_pointer=field["json_pointer"],
                field_spec=field,
            )
        else:
            field["guidance_by_variant"] = {"APPROVE": {"example": {"not-json"}}}
            loader._validate_field_guidance(
                field,
                context="shared",
                version="2.15",
                allowed_variants=["APPROVE"],
                allow_guidance_by_variant=True,
            )

        assert any("JSON-compatible" in error.message for error in loader.errors)

    def _collection_outputs_workflow(self, version: str) -> dict:
        return {
            "version": version,
            "name": "public-collection-outputs",
            "steps": [{
                "name": "Collect",
                "command": ["echo", "ok"],
                "output_bundle": {
                    "path": "state/bundle.json",
                    "fields": [
                        {
                            "name": "attempt_ids",
                            "json_pointer": "/attempt_ids",
                            "type": "list",
                            "items": {"type": "integer"},
                        },
                        {
                            "name": "maybe_ready",
                            "json_pointer": "/maybe_ready",
                            "type": "optional",
                            "item": {"type": "bool"},
                        },
                        {
                            "name": "scores",
                            "json_pointer": "/scores",
                            "type": "map",
                            "keys": {"type": "string"},
                            "values": {"type": "float"},
                        },
                    ],
                },
            }],
            "outputs": {
                "attempt_ids": {
                    "kind": "collection",
                    "type": "list",
                    "items": {"type": "integer"},
                    "from": {"ref": "root.steps.Collect.artifacts.attempt_ids"},
                },
                "maybe_ready": {
                    "kind": "collection",
                    "type": "optional",
                    "item": {"type": "bool"},
                    "from": {"ref": "root.steps.Collect.artifacts.maybe_ready"},
                },
                "scores": {
                    "kind": "collection",
                    "type": "map",
                    "keys": {"type": "string"},
                    "values": {"type": "float"},
                    "from": {"ref": "root.steps.Collect.artifacts.scores"},
                },
            },
        }

    def test_v215_version_accepted_by_default_loader_after_combined_promotion(self):
        """The ordinary loader accepts the complete public v2.15 contract."""
        loaded = self.loader.load(self.write_workflow(self._v215_workflow()))

        assert loaded.surface.version == "2.15"

    def test_v215_version_accepted_by_fresh_ordinary_loader(self):
        """A fresh ordinary loader accepts v2.15 workflows."""
        loaded = WorkflowLoader(self.workspace).load(self.write_workflow(self._v215_workflow()))

        assert loaded.surface.version == "2.15"

    def test_v215_public_collection_outputs_accepted_by_ordinary_loader(self):
        """Public v2.15 optional/list/map outputs are not compiler-private."""
        loaded = self.loader.load(self.write_workflow(self._collection_outputs_workflow("2.15")))
        surface = thaw_surface_workflow(loaded)

        assert {name: spec["type"] for name, spec in surface["outputs"].items()} == {
            "attempt_ids": "list",
            "maybe_ready": "optional",
            "scores": "map",
        }

    def test_v215_guidance_contract_accepted_by_ordinary_loader(self):
        loaded = self.loader.load(self.write_workflow(self._guidance_output_bundle_workflow()))
        surface = thaw_surface_workflow(loaded)

        assert surface["result_guidance"] == {
            "description": "The public review result.",
            "format_hint": "Use the declared output shape.",
            "example": None,
        }
        assert surface["steps"][0]["output_bundle"]["guidance"]["description"] == (
            "Complete review result."
        )

    def test_v214_public_collection_outputs_rejected(self):
        """v2.14 authored YAML still rejects public collection output schemas."""
        path = self.write_workflow(self._collection_outputs_workflow("2.14"))

        with pytest.raises(WorkflowValidationError) as exc_info:
            self.loader.load(path)

        messages = [str(err.message) for err in exc_info.value.errors]
        assert any("outputs.attempt_ids.type invalid type 'list'" in message for message in messages)
        assert any(
            "outputs.attempt_ids: kind 'collection' is only available for frontend-lowered workflows" in message
            for message in messages
        )

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
        surface = thaw_surface_workflow(result)
        assert surface["version"] == "1.4"
        assert surface["steps"][0]["consume_bundle"]["path"] == "state/consumes/review.json"

    def test_load_returns_typed_bundle_without_legacy_adapter(self):
        """load() now returns the typed bundle and no longer exposes a legacy adapter."""
        workflow = {
            "version": "2.5",
            "name": "typed-provenance-adapter",
            "steps": [{
                "name": "Echo",
                "command": ["echo", "ok"],
            }],
        }

        path = self.write_workflow(workflow)
        loaded = self.loader.load(path)

        provenance = workflow_provenance(loaded)

        assert isinstance(loaded, LoadedWorkflowBundle)
        assert not hasattr(loaded, "legacy_workflow")
        assert not isinstance(loaded, Mapping)
        assert loaded.surface.name == "typed-provenance-adapter"
        assert provenance.workflow_path == path.resolve()
        assert provenance.source_root == path.parent.resolve()

    def test_load_returns_typed_bundle_with_semantic_ir(self):
        loaded_bundle_module = __import__(
            "orchestrator.workflow.loaded_bundle",
            fromlist=["workflow_semantic_ir"],
        )
        workflow = {
            "version": "2.7",
            "name": "typed-semantic-ir",
            "steps": [{
                "name": "Echo",
                "id": "echo",
                "command": ["echo", "ok"],
            }],
        }

        path = self.write_workflow(workflow)
        loaded = self.loader.load(path)
        semantic_ir = loaded_bundle_module.workflow_semantic_ir(loaded)

        assert semantic_ir is not None
        assert semantic_ir.schema_version == "workflow_semantic_ir.v1"
        assert semantic_ir.workflows["typed-semantic-ir"].workflow_name == "typed-semantic-ir"

    def test_load_bundle_surface_ast_exposes_no_raw_payloads(self):
        """Typed surface AST records should not retain authored raw payload copies."""
        workflow = {
            "version": "2.7",
            "name": "surface-without-raw",
            "artifacts": {
                "ready": {
                    "kind": "scalar",
                    "type": "bool",
                },
                "decision": {
                    "kind": "scalar",
                    "type": "enum",
                    "allowed": ["APPROVE", "REVISE"],
                },
            },
            "steps": [
                {
                    "name": "SetReady",
                    "id": "set_ready",
                    "set_scalar": {
                        "artifact": "ready",
                        "value": True,
                    },
                },
                {
                    "name": "Route",
                    "id": "route",
                    "if": {
                        "artifact_bool": {
                            "ref": "root.steps.SetReady.artifacts.ready",
                        },
                    },
                    "then": {
                        "id": "approve",
                        "steps": [
                            {
                                "name": "WriteApproved",
                                "id": "write_approved",
                                "set_scalar": {
                                    "artifact": "decision",
                                    "value": "APPROVE",
                                },
                            }
                        ],
                    },
                    "else": {
                        "id": "revise",
                        "steps": [
                            {
                                "name": "WriteRevision",
                                "id": "write_revision",
                                "set_scalar": {
                                    "artifact": "decision",
                                    "value": "REVISE",
                                },
                            }
                        ],
                    },
                }
            ],
            "finally": {
                "id": "cleanup",
                "steps": [
                    {
                        "name": "Cleanup",
                        "id": "cleanup_step",
                        "command": ["bash", "-lc", "true"],
                    }
                ],
            },
        }

        path = self.write_workflow(workflow)
        loaded = self.loader.load(path)
        surface_step = loaded.surface.steps[1]

        assert not hasattr(loaded.surface, "raw")
        assert not hasattr(surface_step, "raw")
        assert surface_step.then_branch is not None
        assert not hasattr(surface_step.then_branch, "raw")
        assert loaded.surface.finalization is not None
        assert not hasattr(loaded.surface.finalization, "raw")

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
