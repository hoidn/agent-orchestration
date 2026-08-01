from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import subprocess

import pytest

from orchestrator.workflow.executable_ir import RunRefStepConfig, StepCommonConfig
from orchestrator.workflow_lisp.effects import RunsRefEffect, effect_summary
from orchestrator.workflow_lisp.compiler import (
    Stage3ValidationProfile,
    WorkflowBoundaryAdmissionProfile,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.wcc.route import LoweringRoute
from orchestrator.workflow.run_ref import path_compile as path_compile_module
from orchestrator.workflow.run_ref.config import (
    PathProgram,
    ReferenceBinding,
    RunRefInput,
    build_run_ref_static_config,
)
from orchestrator.workflow.run_ref.contracts import (
    PostSetupBaselineIdentity,
    RepositoryRevisionId,
    SetupPolicy,
    VerifiedGitTreeIdentity,
    canonical_sha256,
    compute_compiler_runtime_identity,
)
from orchestrator.workflow.run_ref.path_compile import (
    RunRefPathCompileRefusal,
    compile_and_admit_path_program,
)
from orchestrator.workflow.run_ref.result_contract import (
    RUN_REF_RESULT_CONTRACT_SCHEMA,
    _accounting_descriptor,
    _workspace_delta_descriptor,
)
from orchestrator.workflow.run_ref.source import MaterializedSource, SourceRequest
from orchestrator.workflow.run_ref.workspace import manifest_from_entries


_COMMIT = "0123456789abcdef0123456789abcdef01234567"
_SITE = "6c347f1d65bf55f7" + "0" * 48
_VALUE = {"kind": "primitive", "name": "Value"}


def _result_descriptor(value_descriptor: dict[str, object]) -> dict[str, object]:
    return {
        "schema": RUN_REF_RESULT_CONTRACT_SCHEMA,
        "envelope": {
            "kind": "record",
            "name": f"RunRefResult${_SITE[:16]}",
            "fields": [
                {"name": "value", "type": value_descriptor},
                {"name": "workspace_delta", "type": _workspace_delta_descriptor()},
                {"name": "accounting", "type": _accounting_descriptor()},
            ],
        },
    }


def _materialized(workspace: Path) -> MaterializedSource:
    repository_revision = RepositoryRevisionId.build(
        normalized_locator="file:///repo",
        resolved_commit_sha=_COMMIT,
        materializer_version="git-detached-clone-v1",
        submodule_policy="reject-v1",
        lfs_policy="reject-v1",
        authored_setup_identity=canonical_sha256({"commands": []}),
    )
    empty_manifest = manifest_from_entries(())
    return MaterializedSource(
        repository_revision_id=repository_revision,
        normalized_locator=repository_revision.normalized_locator,
        resolved_commit_sha=_COMMIT,
        verified_git_tree=VerifiedGitTreeIdentity("git-tree:" + "a" * 40),
        mirror_path=workspace.parent / "mirror",
        mirror_seal_path=workspace.parent / "mirror" / "seal.json",
        workspace_path=workspace,
        source_tree_manifest=empty_manifest,
        setup_evidence_path=workspace.parent / "setup.json",
        setup_evidence_digest=canonical_sha256({"setup": "complete"}),
        post_setup_tree_manifest=empty_manifest,
        post_setup_baseline_identity=PostSetupBaselineIdentity(
            canonical_sha256({"tree": empty_manifest.digest})
        ),
    )


def _config(
    *,
    inputs: tuple[RunRefInput, ...] = (),
    return_refinement: dict[str, object] | None = _VALUE,
    compiler_identity: str | None = None,
):
    result_descriptor = _result_descriptor(
        _VALUE if return_refinement is None else return_refinement
    )
    static_config = build_run_ref_static_config(
        compiler_runtime_identity_digest=(
            compiler_identity or compute_compiler_runtime_identity().digest
        ),
        site_digest=_SITE,
        source=SourceRequest(locator="file:///repo", commit=_COMMIT, setup=SetupPolicy()),
        program=PathProgram(
            path="candidate.orc",
            entry_name="run",
            return_refinement=return_refinement,
        ),
        inputs=inputs,
        result_descriptor=result_descriptor,
        result_digest=canonical_sha256(result_descriptor),
    )
    return RunRefStepConfig(common=StepCommonConfig(), run_ref=static_config)


def _write_candidate(workspace: Path, *, body: str, params: str = "") -> Path:
    workspace.mkdir(parents=True)
    path = workspace / "candidate.orc"
    path.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.24")',
                "  (defmodule candidate)",
                "  (export run)",
                f"  (defworkflow run ({params}) -> Value",
                f"    {body}))",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def _write_typed_passthrough(
    workspace: Path,
    *,
    type_name: str,
    definitions: tuple[str, ...] = (),
) -> None:
    workspace.mkdir(parents=True)
    (workspace / "candidate.orc").write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.24")',
                "  (defmodule candidate)",
                "  (export run)",
                *(f"  {definition}" for definition in definitions),
                f"  (defworkflow run ((payload {type_name})) -> {type_name}",
                "    payload))",
            )
        )
        + "\n",
        encoding="utf-8",
    )


def _assert_refusal(exc: RunRefPathCompileRefusal, code: str) -> None:
    assert exc.code == code
    assert exc.record == {
        "code": code,
        "rejected_value": exc.rejected_value,
        "secondary_causes": list(exc.secondary_causes),
    }


def test_full_compile_admits_exact_effect_free_signature_and_binds_evidence(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "first" / "workspace"
    _write_candidate(workspace, body="payload", params="(payload Value)")
    config = _config(
        inputs=(
            RunRefInput(
                name="payload",
                type_descriptor=_VALUE,
                binding=ReferenceBinding("inputs.payload"),
            ),
        )
    )

    admitted = compile_and_admit_path_program(
        materialized_source=_materialized(workspace),
        step_config=config,
    )

    assert admitted.build_result.selected_workflow_name == "candidate::run"
    assert admitted.diagnostics_document["status"] == "accepted"
    assert admitted.program_identity["schema_version"] == (
        "workflow_lisp_program_identity.v2"
    )
    assert admitted.program_identity["boundary_admission_profile"] == (
        "transportable_child"
    )
    assert admitted.signature == {
        "inputs": [{"name": "payload", "required": True, "type": _VALUE}],
        "return": _VALUE,
    }
    assert admitted.effect_facts == {
        "direct": [],
        "transitive": [],
        "procedure_edges": [],
    }
    evidence = admitted.evidence
    assert evidence["schema_version"] == "run_ref_path_compile_evidence.v1"
    assert evidence["repository_revision_digest"] == _materialized(
        workspace
    ).repository_revision_id.digest
    assert evidence["verified_git_tree"] == "git-tree:" + "a" * 40
    assert evidence["step_config_digest"] == config.step_config_digest
    assert evidence["compiler_runtime_identity_digest"] == (
        config.run_ref.compiler_runtime_identity_digest
    )
    assert evidence["program_identity_digest"] == admitted.program_identity["digest"]
    assert "path" not in evidence
    assert "fingerprint" not in evidence
    assert "timestamp" not in evidence


def test_full_compile_rejection_preserves_machine_document_and_codes(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    _write_candidate(workspace, body="missing")

    with pytest.raises(RunRefPathCompileRefusal) as excinfo:
        compile_and_admit_path_program(
            materialized_source=_materialized(workspace),
            step_config=_config(),
        )

    _assert_refusal(excinfo.value, "trial_program_compile_rejected")
    document = excinfo.value.compile_diagnostics_document
    assert document["status"] == "rejected"
    assert [row["code"] for row in document["diagnostics"]] == ["name_unknown"]
    assert excinfo.value.secondary_causes == ("name_unknown",)


def test_malformed_program_is_a_structured_compile_rejection(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "candidate.orc").write_text(
        "(workflow-lisp (:language \"0.1\")",
        encoding="utf-8",
    )

    with pytest.raises(RunRefPathCompileRefusal) as excinfo:
        compile_and_admit_path_program(
            materialized_source=_materialized(workspace),
            step_config=_config(),
        )

    assert excinfo.value.code == "trial_program_compile_rejected"
    assert excinfo.value.compile_diagnostics_document["status"] == "rejected"
    assert excinfo.value.secondary_causes


def test_signature_mismatch_rejects_before_any_launch(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _write_candidate(workspace, body="payload", params="(payload Value)")

    with pytest.raises(RunRefPathCompileRefusal) as excinfo:
        compile_and_admit_path_program(
            materialized_source=_materialized(workspace),
            step_config=_config(),
        )

    _assert_refusal(excinfo.value, "trial_program_signature_mismatch")
    assert excinfo.value.secondary_causes == ("missing_input:payload",)


def test_provider_diagnostic_routes_to_environment_refusal(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "candidate.orc").write_text(
        """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.24")
  (defmodule candidate)
  (export run)
  (defworkflow run () -> Value
    (provider-result providers.worker
      :prompt prompts.worker :inputs () :returns Value)))
""",
        encoding="utf-8",
    )

    with pytest.raises(RunRefPathCompileRefusal) as excinfo:
        compile_and_admit_path_program(
            materialized_source=_materialized(workspace),
            step_config=_config(),
        )

    _assert_refusal(
        excinfo.value,
        "trial_candidate_environment_not_admissible",
    )
    assert "provider_result_provider_invalid" in excinfo.value.secondary_causes


def test_command_diagnostic_routes_to_environment_refusal(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "candidate.orc").write_text(
        """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.24")
  (defmodule candidate)
  (export run)
  (defworkflow run () -> Value
    (command-result missing_adapter
      :adapter missing_adapter :inputs () :returns Value)))
""",
        encoding="utf-8",
    )

    with pytest.raises(RunRefPathCompileRefusal) as excinfo:
        compile_and_admit_path_program(
            materialized_source=_materialized(workspace),
            step_config=_config(),
        )

    assert excinfo.value.code == "trial_candidate_environment_not_admissible"
    assert "command_adapter_missing_contract" in excinfo.value.secondary_causes


def test_materialized_source_identity_must_match_step_config(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _write_candidate(workspace, body="payload", params="(payload Value)")
    materialized = _materialized(workspace)
    mismatched_revision = RepositoryRevisionId.build(
        normalized_locator="file:///different",
        resolved_commit_sha=_COMMIT,
        materializer_version="git-detached-clone-v1",
        submodule_policy="reject-v1",
        lfs_policy="reject-v1",
        authored_setup_identity=canonical_sha256({"commands": []}),
    )

    with pytest.raises(RunRefPathCompileRefusal) as excinfo:
        compile_and_admit_path_program(
            materialized_source=replace(
                materialized,
                repository_revision_id=mismatched_revision,
                normalized_locator=mismatched_revision.normalized_locator,
            ),
            step_config=_config(
                inputs=(
                    RunRefInput(
                        name="payload",
                        type_descriptor=_VALUE,
                        binding=ReferenceBinding("inputs.payload"),
                    ),
                )
            ),
        )

    assert excinfo.value.code == "trial_program_compile_rejected"
    assert excinfo.value.secondary_causes == ("source_identity_mismatch",)


def test_equal_pinned_inputs_at_distinct_roots_have_equal_evidence_identity(
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "first" / "workspace"
    second_root = tmp_path / "second" / "workspace"
    _write_candidate(first_root, body="payload", params="(payload Value)")
    _write_candidate(second_root, body="payload", params="(payload Value)")
    step_config = _config(
        inputs=(
            RunRefInput(
                name="payload",
                type_descriptor=_VALUE,
                binding=ReferenceBinding("inputs.payload"),
            ),
        )
    )

    first = compile_and_admit_path_program(
        materialized_source=_materialized(first_root),
        step_config=step_config,
    )
    second = compile_and_admit_path_program(
        materialized_source=_materialized(second_root),
        step_config=step_config,
    )

    assert first.program_identity == second.program_identity
    assert first.evidence == second.evidence
    assert first.evidence["digest"] == canonical_sha256(
        {key: value for key, value in first.evidence.items() if key != "digest"}
    )


@pytest.mark.parametrize(
    ("type_name", "definitions", "descriptor"),
    (
        ("String", (), {"kind": "primitive", "name": "String"}),
        ("Bool", (), {"kind": "primitive", "name": "Bool"}),
        ("Int", (), {"kind": "primitive", "name": "Int"}),
        ("Float", (), {"kind": "primitive", "name": "Float"}),
        (
            "Decision",
            ("(defenum Decision APPROVE REVISE)",),
            {
                "kind": "enum",
                "name": "Decision",
                "allowed": ["APPROVE", "REVISE"],
            },
        ),
        (
            "Box",
            ("(defrecord Box (value String))",),
            {
                "kind": "record",
                "name": "Box",
                "fields": [
                    {
                        "name": "value",
                        "type": {"kind": "primitive", "name": "String"},
                    }
                ],
            },
        ),
        (
            "List[String]",
            (),
            {
                "kind": "list",
                "item": {"kind": "primitive", "name": "String"},
            },
        ),
        (
            "Optional[String]",
            (),
            {
                "kind": "optional",
                "item": {"kind": "primitive", "name": "String"},
            },
        ),
        (
            "Map[String, Int]",
            (),
            {
                "kind": "map",
                "key": {"kind": "primitive", "name": "String"},
                "value": {"kind": "primitive", "name": "Int"},
            },
        ),
        (
            "Choice",
            (
                "(defunion Choice (KEEP (value String)) (DROP))",
            ),
            {
                "kind": "union",
                "name": "Choice",
                "variants": [
                    {
                        "name": "KEEP",
                        "fields": [
                            {
                                "name": "value",
                                "type": {"kind": "primitive", "name": "String"},
                            }
                        ],
                    },
                    {"name": "DROP", "fields": []},
                ],
            },
        ),
        (
            "WorkPath",
            ('(defpath WorkPath :kind relpath :under "artifacts" :must-exist false)',),
            {
                "kind": "path",
                "name": "WorkPath",
                "under": "artifacts",
                "must_exist_target": False,
            },
        ),
        ("Value", (), _VALUE),
    ),
)
def test_all_transportable_signature_shapes_use_compiler_normalized_descriptors(
    tmp_path: Path,
    type_name: str,
    definitions: tuple[str, ...],
    descriptor: dict[str, object],
) -> None:
    workspace = tmp_path / "workspace"
    _write_typed_passthrough(
        workspace,
        type_name=type_name,
        definitions=definitions,
    )
    admitted = compile_and_admit_path_program(
        materialized_source=_materialized(workspace),
        step_config=_config(
            inputs=(
                RunRefInput(
                    name="payload",
                    type_descriptor=descriptor,
                    binding=ReferenceBinding("inputs.payload"),
                ),
            ),
            return_refinement=descriptor,
        ),
    )

    assert admitted.signature["inputs"][0]["type"] == descriptor
    assert admitted.signature["return"] == descriptor


def test_ordinary_shared_callable_profile_still_rejects_union_inputs(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    _write_typed_passthrough(
        workspace,
        type_name="Choice",
        definitions=("(defunion Choice (KEEP (value String)) (DROP))",),
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        path_compile_module.build_frontend_bundle(
            path_compile_module.FrontendBuildRequest(
                source_path=workspace / "candidate.orc",
                source_roots=(workspace,),
                entry_workflow="run",
                workspace_root=workspace,
                lowering_route=LoweringRoute.WCC_M4,
                boundary_admission_profile=(
                    WorkflowBoundaryAdmissionProfile.SHARED_CALLABLE
                ),
            )
        )

    assert [diagnostic.code for diagnostic in excinfo.value.diagnostics] == [
        "workflow_boundary_type_invalid"
    ]


@pytest.mark.parametrize(
    "descriptor",
    (
        {
            "kind": "union",
            "name": "Choice",
            "variants": [
                {
                    "name": "KEEP",
                    "fields": [
                        {
                            "name": "value",
                            "type": {"kind": "primitive", "name": "String"},
                        }
                    ],
                },
                {"name": "DROP", "fields": []},
            ],
        },
        {
            "kind": "optional",
            "item": {"kind": "primitive", "name": "String"},
        },
        {
            "kind": "map",
            "key": {"kind": "primitive", "name": "String"},
            "value": {"kind": "primitive", "name": "Int"},
        },
    ),
)
def test_exact_union_optional_and_map_signature_descriptors_are_admissible(
    descriptor: dict[str, object],
) -> None:
    configured_input = RunRefInput(
        name="payload",
        type_descriptor=descriptor,
        binding=ReferenceBinding("inputs.payload"),
    )
    signature = {
        "inputs": [{"name": "payload", "required": True, "type": descriptor}],
        "return": descriptor,
    }

    assert path_compile_module._signature_mismatch_causes(
        signature,
        (configured_input,),
        PathProgram(
            path="candidate.orc",
            entry_name="run",
            return_refinement=descriptor,
        ),
    ) == ()


def test_omitted_default_input_is_admitted(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "candidate.orc").write_text(
        """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.24")
  (defmodule candidate)
  (export run)
  (defworkflow run ((payload String :default "fallback")) -> String payload))
""",
        encoding="utf-8",
    )
    descriptor = {"kind": "primitive", "name": "String"}

    admitted = compile_and_admit_path_program(
        materialized_source=_materialized(workspace),
        step_config=_config(return_refinement=descriptor),
    )

    assert admitted.signature["inputs"] == [
        {"name": "payload", "required": False, "type": descriptor}
    ]


@pytest.mark.parametrize(("kind", "secondary"), (("missing", "program_missing"), ("directory", "program_not_regular"), ("symlink", "program_symlink")))
def test_missing_nonregular_and_symlink_programs_fail_closed(
    tmp_path: Path,
    kind: str,
    secondary: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    program = workspace / "candidate.orc"
    if kind == "directory":
        program.mkdir()
    elif kind == "symlink":
        target = workspace / "target.orc"
        target.write_text("not read", encoding="utf-8")
        program.symlink_to(target)

    with pytest.raises(RunRefPathCompileRefusal) as excinfo:
        compile_and_admit_path_program(
            materialized_source=_materialized(workspace),
            step_config=_config(),
        )

    assert excinfo.value.code == "trial_program_missing"
    assert excinfo.value.secondary_causes == (secondary,)


def test_compile_request_is_full_wcc_m4_with_explicit_empty_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    _write_candidate(workspace, body="payload", params="(payload Value)")
    observed = []
    original = path_compile_module.build_frontend_bundle

    def record_request(request):
        observed.append(request)
        return original(request)

    monkeypatch.setattr(path_compile_module, "build_frontend_bundle", record_request)
    monkeypatch.setattr(
        "orchestrator.workflow_lisp.compiler.compile_stage1_entrypoint",
        lambda *args, **kwargs: pytest.fail("reduced stage-1 path used"),
    )
    monkeypatch.setattr(
        "orchestrator.workflow_lisp.compiler.compile_stage3_module",
        lambda *args, **kwargs: pytest.fail("reduced single-module path used"),
    )
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda *args, **kwargs: pytest.fail("runtime child launch attempted"),
    )

    admitted = compile_and_admit_path_program(
        materialized_source=_materialized(workspace),
        step_config=_config(
            inputs=(
                RunRefInput(
                    name="payload",
                    type_descriptor=_VALUE,
                    binding=ReferenceBinding("inputs.payload"),
                ),
            )
        ),
    )

    [request] = observed
    assert request.lowering_route is LoweringRoute.WCC_M4
    assert request.provider_externs_path is None
    assert request.prompt_externs_path is None
    assert request.imported_workflow_bundles_path is None
    assert request.command_boundaries_path is None
    assert request.boundary_admission_profile is (
        WorkflowBoundaryAdmissionProfile.TRANSPORTABLE_CHILD
    )
    assert admitted.build_result.compile_request_capture.validation_profile is (
        Stage3ValidationProfile.SHARED_CALLABLE
    )
    assert (
        admitted.build_result.compile_result.entry_result.workflow_catalog.allow_transportable_input_boundaries
        is True
    )


def test_unknown_effect_summary_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = tmp_path / "workspace"
    _write_candidate(workspace, body="payload", params="(payload Value)")
    original = path_compile_module._selected_typed_workflow

    def malformed(result):
        return replace(original(result), effect_summary=object())

    monkeypatch.setattr(path_compile_module, "_selected_typed_workflow", malformed)
    with pytest.raises(RunRefPathCompileRefusal) as excinfo:
        compile_and_admit_path_program(
            materialized_source=_materialized(workspace),
            step_config=_config(
                inputs=(RunRefInput(name="payload", type_descriptor=_VALUE, binding=ReferenceBinding("inputs.payload")),)
            ),
        )

    assert excinfo.value.code == "trial_candidate_environment_not_admissible"
    assert excinfo.value.secondary_causes == ("effect_summary_invalid",)


def test_known_effect_facts_are_structural_sorted_and_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    _write_candidate(workspace, body="payload", params="(payload Value)")
    original = path_compile_module._selected_typed_workflow

    def effectful(result):
        return replace(
            original(result),
            effect_summary=effect_summary(
                direct_effects=(RunsRefEffect(subject=("z",)), RunsRefEffect(subject=("a",)))
            ),
        )

    monkeypatch.setattr(path_compile_module, "_selected_typed_workflow", effectful)
    with pytest.raises(RunRefPathCompileRefusal) as excinfo:
        compile_and_admit_path_program(
            materialized_source=_materialized(workspace),
            step_config=_config(
                inputs=(RunRefInput(name="payload", type_descriptor=_VALUE, binding=ReferenceBinding("inputs.payload")),)
            ),
        )

    assert excinfo.value.code == "trial_candidate_environment_not_admissible"
    facts = excinfo.value.rejected_value["effect_facts"]
    assert [row["fields"]["subject"] for row in facts["direct"]] == [["a"], ["z"]]


@pytest.mark.parametrize(
    ("configured_inputs", "expected_cause"),
    (
        (
            (
                RunRefInput(
                    name="payload",
                    type_descriptor=_VALUE,
                    binding=ReferenceBinding("inputs.payload"),
                ),
                RunRefInput(
                    name="extra",
                    type_descriptor=_VALUE,
                    binding=ReferenceBinding("inputs.extra"),
                ),
            ),
            "extra_input:extra",
        ),
        (
            (
                RunRefInput(
                    name="payload",
                    type_descriptor={"kind": "primitive", "name": "String"},
                    binding=ReferenceBinding("inputs.payload"),
                ),
            ),
            "input_type_mismatch:payload",
        ),
    ),
)
def test_extra_and_mistyped_inputs_reject_exactly(
    tmp_path: Path,
    configured_inputs: tuple[RunRefInput, ...],
    expected_cause: str,
) -> None:
    workspace = tmp_path / "workspace"
    _write_candidate(workspace, body="payload", params="(payload Value)")

    with pytest.raises(RunRefPathCompileRefusal) as excinfo:
        compile_and_admit_path_program(
            materialized_source=_materialized(workspace),
            step_config=_config(inputs=configured_inputs),
        )

    assert excinfo.value.code == "trial_program_signature_mismatch"
    assert excinfo.value.secondary_causes == (expected_cause,)


def test_explicit_return_refinement_must_match_exactly(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    _write_candidate(workspace, body="payload", params="(payload Value)")
    string_descriptor = {"kind": "primitive", "name": "String"}

    with pytest.raises(RunRefPathCompileRefusal) as excinfo:
        compile_and_admit_path_program(
            materialized_source=_materialized(workspace),
            step_config=_config(
                inputs=(RunRefInput(name="payload", type_descriptor=_VALUE, binding=ReferenceBinding("inputs.payload")),),
                return_refinement=string_descriptor,
            ),
        )

    assert excinfo.value.secondary_causes == ("return_type_mismatch",)


def test_omitted_return_refinement_claims_exact_value(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "candidate.orc").write_text(
        """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.24")
  (defmodule candidate)
  (export run)
  (defworkflow run () -> String "ok"))
""",
        encoding="utf-8",
    )

    with pytest.raises(RunRefPathCompileRefusal) as excinfo:
        compile_and_admit_path_program(
            materialized_source=_materialized(workspace),
            step_config=_config(return_refinement=None),
        )

    assert excinfo.value.secondary_causes == ("return_type_mismatch",)


def test_compiler_runtime_identity_mismatch_rejects_before_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    _write_candidate(workspace, body="payload", params="(payload Value)")
    monkeypatch.setattr(
        path_compile_module,
        "build_frontend_bundle",
        lambda request: pytest.fail("build ran before compiler identity refusal"),
    )

    with pytest.raises(RunRefPathCompileRefusal) as excinfo:
        compile_and_admit_path_program(
            materialized_source=_materialized(workspace),
            step_config=_config(
                inputs=(RunRefInput(name="payload", type_descriptor=_VALUE, binding=ReferenceBinding("inputs.payload")),),
                compiler_identity="sha256:" + "f" * 64,
            ),
        )

    assert excinfo.value.secondary_causes == ("compiler_runtime_identity_mismatch",)


def test_forged_static_config_authority_rejects_before_compile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    _write_candidate(workspace, body="payload", params="(payload Value)")
    step_config = _config(
        inputs=(RunRefInput(name="payload", type_descriptor=_VALUE, binding=ReferenceBinding("inputs.payload")),)
    )
    object.__setattr__(step_config.run_ref, "digest", "sha256:" + "f" * 64)
    monkeypatch.setattr(
        path_compile_module,
        "build_frontend_bundle",
        lambda request: pytest.fail("forged static authority reached build"),
    )

    with pytest.raises(ValueError, match="authority"):
        compile_and_admit_path_program(
            materialized_source=_materialized(workspace),
            step_config=step_config,
        )


def test_accepted_program_identity_must_bind_local_compiler(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    _write_candidate(workspace, body="payload", params="(payload Value)")
    original = path_compile_module.build_accepted_compile_diagnostics_document

    def mismatched(result):
        document = original(result)
        document["normalized_program_identity"]["compiler_runtime_identity"] = (
            "sha256:" + "f" * 64
        )
        return document

    monkeypatch.setattr(
        path_compile_module,
        "build_accepted_compile_diagnostics_document",
        mismatched,
    )
    with pytest.raises(RunRefPathCompileRefusal) as excinfo:
        compile_and_admit_path_program(
            materialized_source=_materialized(workspace),
            step_config=_config(
                inputs=(RunRefInput(name="payload", type_descriptor=_VALUE, binding=ReferenceBinding("inputs.payload")),)
            ),
        )

    assert excinfo.value.secondary_causes == ("program_identity_compiler_mismatch",)


def test_accepted_program_identity_must_bind_candidate_boundary_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    _write_candidate(workspace, body="payload", params="(payload Value)")
    original = path_compile_module.build_accepted_compile_diagnostics_document

    def downgraded(result):
        document = original(result)
        identity = dict(document["normalized_program_identity"])
        identity.pop("boundary_admission_profile")
        identity["schema_version"] = "workflow_lisp_program_identity.v1"
        identity["digest"] = canonical_sha256(
            {key: value for key, value in identity.items() if key != "digest"}
        )
        document["normalized_program_identity"] = identity
        return document

    monkeypatch.setattr(
        path_compile_module,
        "build_accepted_compile_diagnostics_document",
        downgraded,
    )
    with pytest.raises(RunRefPathCompileRefusal) as excinfo:
        compile_and_admit_path_program(
            materialized_source=_materialized(workspace),
            step_config=_config(
                inputs=(
                    RunRefInput(
                        name="payload",
                        type_descriptor=_VALUE,
                        binding=ReferenceBinding("inputs.payload"),
                    ),
                )
            ),
        )

    assert excinfo.value.secondary_causes == (
        "program_identity_boundary_admission_profile_mismatch",
    )


def test_pure_procedure_edges_do_not_count_as_effect_atoms(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "candidate.orc").write_text(
        """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.24")
  (defmodule candidate)
  (export run)
  (defproc pass ((payload Value)) -> Value
    :effects () :lowering inline payload)
  (defworkflow run ((payload Value)) -> Value (pass payload)))
""",
        encoding="utf-8",
    )

    admitted = compile_and_admit_path_program(
        materialized_source=_materialized(workspace),
        step_config=_config(
            inputs=(RunRefInput(name="payload", type_descriptor=_VALUE, binding=ReferenceBinding("inputs.payload")),)
        ),
    )

    assert admitted.effect_facts["direct"] == []
    assert admitted.effect_facts["transitive"] == []
    assert admitted.effect_facts["procedure_edges"] == [
        {
            "callee_name": "candidate::pass",
            "form_path": ["workflow-lisp", "defworkflow", "run"],
        }
    ]
