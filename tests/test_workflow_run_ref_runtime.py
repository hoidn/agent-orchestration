from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import stat
from typing import Any

import pytest

import orchestrator.workflow.run_ref.runtime as runtime_module
from orchestrator.workflow.executable_ir import RunRefStepConfig, StepCommonConfig
from orchestrator.workflow.run_ref.config import (
    ArrayBinding,
    BundleProgram,
    LiteralBinding,
    ObjectBinding,
    PathProgram,
    ReferenceBinding,
    RunRefBundleCapsuleBinding,
    RunRefInput,
    build_run_ref_static_config,
)
from orchestrator.workflow.run_ref.contracts import (
    PostSetupBaselineIdentity,
    RepositoryRevisionId,
    RunRefSourceRefusal,
    VerifiedGitTreeIdentity,
    canonical_json_bytes,
    canonical_sha256,
)
from orchestrator.workflow.run_ref.delta import DeclaredArtifact
from orchestrator.workflow.run_ref.ledger import (
    RunRefVisitKey,
    load_attempt_ledger,
)
from orchestrator.workflow.run_ref.result_contract import (
    RUN_REF_RESULT_CONTRACT_SCHEMA,
    _accounting_descriptor,
    _workspace_delta_descriptor,
)
from orchestrator.workflow.run_ref.runtime import (
    ParentBundleOrphanPreimage,
    PreparedRunRefSettlement,
    RunRefChildLaunch,
    RunRefChildProcessResult,
    RunRefRuntimeDependencies,
    RunRefRuntimeError,
    RunRefRuntimeRequest,
    build_run_ref_accounting,
    declared_artifacts_from_value,
    extract_run_ref_value,
    finalize_run_ref_parent_commit,
    flatten_run_ref_result_artifacts,
    prepare_run_ref_settlement,
    resolve_run_ref_inputs,
    validate_completed_run_ref_authority,
    _child_result_document,
    _workspace_for_ordinal,
)
from orchestrator.workflow.run_ref.source import (
    MaterializedSource,
    SourceRequest,
    canonical_source_request,
)
from orchestrator.workflow.run_ref.workspace import freeze_tree


_STRING = {"kind": "primitive", "name": "String"}
_INT = {"kind": "primitive", "name": "Int"}
_COMMIT = "0123456789abcdef0123456789abcdef01234567"


def _digest(marker: str) -> str:
    return "sha256:" + marker * 64


def _result_descriptor(
    value_descriptor: dict[str, Any],
    *,
    site_digest: str,
) -> dict[str, Any]:
    return {
        "schema": RUN_REF_RESULT_CONTRACT_SCHEMA,
        "envelope": {
            "kind": "record",
            "name": f"RunRefResult${site_digest[:16]}",
            "fields": [
                {"name": "value", "type": value_descriptor},
                {"name": "workspace_delta", "type": _workspace_delta_descriptor()},
                {"name": "accounting", "type": _accounting_descriptor()},
            ],
        },
    }


def _runtime_request(
    tmp_path: Path,
    *,
    mode: str = "bundle",
) -> RunRefRuntimeRequest:
    parent_workspace = (tmp_path / "parent-workspace").resolve()
    parent_workspace.mkdir()
    parent_input = parent_workspace / "inputs" / "source.txt"
    parent_input.parent.mkdir()
    parent_input.write_text("parent input\n", encoding="utf-8")
    parent_run_root = parent_workspace / ".orchestrate" / "runs" / "parent-run"
    parent_run_root.mkdir(parents=True)
    run_ref_root = (tmp_path / "external-run-ref-root").resolve()
    site_digest = "1" * 64
    path_descriptor = {
        "kind": "path",
        "name": "ArtifactPath",
        "under": "artifacts/work",
        "must_exist_target": True,
    }
    input_descriptor = {
        "kind": "path",
        "name": "InputPath",
        "under": "inputs",
        "must_exist_target": True,
    }
    if mode == "bundle":
        program = BundleProgram("fixture/child::run")
        capsule_binding = RunRefBundleCapsuleBinding(_digest("c"))
        capsule_dir = (tmp_path / "capsule").resolve()
        capsule_dir.mkdir()
    else:
        program = PathProgram(
            path="candidate.orc",
            entry_name="run",
            return_refinement=path_descriptor,
        )
        capsule_binding = None
        capsule_dir = None
    descriptor = _result_descriptor(path_descriptor, site_digest=site_digest)
    static = build_run_ref_static_config(
        compiler_runtime_identity_digest=_digest("a"),
        site_digest=site_digest,
        source=SourceRequest(locator=parent_workspace.as_uri(), commit=_COMMIT),
        program=program,
        inputs=(
            RunRefInput(
                name="source_path",
                type_descriptor=input_descriptor,
                binding=ReferenceBinding("inputs.source_path"),
            ),
        ),
        result_descriptor=descriptor,
        result_digest=canonical_sha256(descriptor),
    )
    return RunRefRuntimeRequest(
        step_config=RunRefStepConfig(
            common=StepCommonConfig(),
            run_ref=static,
            capsule_binding=capsule_binding,
        ),
        visit=RunRefVisitKey(
            parent_run_id="parent-run",
            execution_frame_id="root",
            call_frame_id=None,
            step_id="root.run-ref",
            visit_count=1,
        ),
        parent_state={
            "bound_inputs": {"source_path": "inputs/source.txt"},
            "steps": {},
        },
        parent_workspace=parent_workspace,
        parent_run_root=parent_run_root,
        run_ref_root=run_ref_root,
        capsule_dir=capsule_dir,
    )


class _RuntimeHarness:
    def __init__(self) -> None:
        self.launches: list[RunRefChildLaunch] = []

    def materialize(
        self,
        request: SourceRequest,
        *,
        run_ref_root: Path,
        workspace: Path,
        progress_hook=None,
    ) -> MaterializedSource:
        workspace.mkdir(parents=True)
        (workspace / ".git").mkdir()
        (workspace / "seed.txt").write_text("seed\n", encoding="utf-8")
        source_manifest = freeze_tree(workspace, excluded_roots=(".git",))
        if progress_hook is not None:
            progress_hook("materialized")
        (workspace / "setup.txt").write_text("setup\n", encoding="utf-8")
        source_record = canonical_source_request(request)
        revision = RepositoryRevisionId.build(
            normalized_locator=source_record["normalized_locator"],
            resolved_commit_sha=source_record["resolved_commit_sha"],
            materializer_version=source_record["materializer_version"],
            submodule_policy=source_record["submodule_policy"],
            lfs_policy=source_record["lfs_policy"],
            authored_setup_identity=source_record["authored_setup_identity"],
        )
        setup = {
            "schema_version": "run_ref_setup_evidence.v1",
            "repository_revision_digest": revision.digest,
            "authored_setup_identity": revision.authored_setup_identity,
            "status": "passed",
            "commands": [],
        }
        setup_path = run_ref_root / "setup-evidence" / "fixture.json"
        setup_path.parent.mkdir(parents=True, exist_ok=True)
        setup_path.write_bytes(canonical_json_bytes(setup) + b"\n")
        post_setup = freeze_tree(
            workspace,
            excluded_roots=(".git", ".orchestrate"),
        )
        if progress_hook is not None:
            progress_hook("setup_completed")
        return MaterializedSource(
            repository_revision_id=revision,
            normalized_locator=revision.normalized_locator,
            resolved_commit_sha=revision.resolved_commit_sha,
            verified_git_tree=VerifiedGitTreeIdentity("git-tree:" + "b" * 40),
            mirror_path=run_ref_root / "mirrors" / "fixture",
            mirror_seal_path=run_ref_root / "mirrors" / "fixture" / "seal.json",
            workspace_path=workspace,
            source_tree_manifest=source_manifest,
            setup_evidence_path=setup_path,
            setup_evidence_digest=canonical_sha256(setup),
            post_setup_tree_manifest=post_setup,
            post_setup_baseline_identity=PostSetupBaselineIdentity(post_setup.digest),
        )

    def launch(self, launch: RunRefChildLaunch) -> RunRefChildProcessResult:
        self.launches.append(launch)
        artifact = launch.workspace / "artifacts" / "work" / "result.txt"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("child result\n", encoding="utf-8")
        workflow_outputs = {"__result__": "artifacts/work/result.txt"}
        child_run_root = (
            launch.workspace
            / ".orchestrate"
            / "runs"
            / launch.child_run_id
        )
        child_run_root.mkdir(parents=True)
        state = {
            "run_id": launch.child_run_id,
            "status": "completed",
            "workflow_outputs": workflow_outputs,
        }
        (child_run_root / "state.json").write_bytes(
            canonical_json_bytes(state) + b"\n"
        )
        if launch.mode == "bundle":
            result = {
                "schema_version": "run_ref_child_result.v1",
                "status": "completed",
                "capsule_digest": launch.request_document["expected_capsule_digest"],
                "target_workflow_name": "fixture/child::run",
                "child_run_id": launch.child_run_id,
                "workflow_outputs": workflow_outputs,
            }
        else:
            result = {
                "schema_version": "run_ref_path_child_result.v1",
                "status": "completed",
                "step_config_digest": launch.request_document[
                    "expected_step_config_digest"
                ],
                "target_workflow_name": "run",
                "child_run_id": launch.child_run_id,
                "workflow_outputs": workflow_outputs,
                "path_compile": {
                    "diagnostics": {},
                    "program_identity": {},
                    "signature": {},
                    "effect_facts": {},
                    "evidence": {},
                },
            }
        return RunRefChildProcessResult(
            returncode=0,
            stdout=canonical_json_bytes(result) + b"\n",
            stderr=b"",
            duration_ms=4,
        )

    def dependencies(self) -> RunRefRuntimeDependencies:
        return RunRefRuntimeDependencies(
            materialize_source=self.materialize,
            launch_child=self.launch,
        )


def test_runtime_refusal_freezes_complete_machine_fields() -> None:
    rejected_value = {"command": ["./setup.sh"]}
    machine_fields = {
        "rejected_value": rejected_value,
        "secondary_causes": ["exit_code:2"],
    }

    refusal = RunRefRuntimeError(
        "trial_setup_failed",
        "source_materialization_refused",
        machine_fields=machine_fields,
    )
    rejected_value["command"].append("mutated")
    machine_fields["secondary_causes"].append("mutated")

    assert refusal.machine_fields == {
        "rejected_value": {"command": ["./setup.sh"]},
        "secondary_causes": ["exit_code:2"],
    }
    with pytest.raises(ValueError, match="machine_fields_required"):
        RunRefRuntimeError(
            "trial_setup_failed",
            "source_materialization_refused",
        )


def test_source_refusal_preserves_structured_machine_authority(
    tmp_path: Path,
) -> None:
    request = _runtime_request(tmp_path)

    def refuse(*_args, **_kwargs):
        raise RunRefSourceRefusal(
            "trial_setup_failed",
            {"command_index": 1, "argv": ["./setup.sh"]},
            "setup failed",
            secondary_causes=("exit_code:2",),
        )

    with pytest.raises(RunRefRuntimeError) as excinfo:
        prepare_run_ref_settlement(
            request,
            dependencies=RunRefRuntimeDependencies(materialize_source=refuse),
        )

    assert excinfo.value.code == "trial_setup_failed"
    assert excinfo.value.machine_fields == {
        "rejected_value": {
            "command_index": 1,
            "argv": ["./setup.sh"],
        },
        "secondary_causes": ["exit_code:2"],
    }


def test_resolve_run_ref_inputs_preserves_nested_typed_values() -> None:
    rows = (
        RunRefInput(
            name="payload",
            type_descriptor={
                "kind": "record",
                "name": "Payload",
                "fields": [
                    {"name": "label", "type": _STRING},
                    {
                        "name": "items",
                        "type": {"kind": "list", "item": _INT},
                    },
                ],
            },
            binding=ObjectBinding(
                (
                    ("label", ReferenceBinding("inputs.label")),
                    (
                        "items",
                        ArrayBinding(
                            (LiteralBinding(1), ReferenceBinding("inputs.count"))
                        ),
                    ),
                )
            ),
        ),
    )

    resolved = resolve_run_ref_inputs(
        rows,
        parent_state={
            "bound_inputs": {"label": "candidate", "count": 2},
            "steps": {},
        },
        parent_workspace=Path("/unused-parent"),
        child_workspace=Path("/unused-child"),
    )

    assert resolved == {"payload": {"label": "candidate", "items": [1, 2]}}


def test_resolve_run_ref_inputs_copies_paths_and_rebinds_to_child(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    child = tmp_path / "child"
    (parent / "artifacts" / "work").mkdir(parents=True)
    child.mkdir()
    source = parent / "artifacts" / "work" / "input.txt"
    source.write_text("input bytes\n", encoding="utf-8")
    descriptor = {
        "kind": "path",
        "name": "InputPath",
        "under": "artifacts/work",
        "must_exist_target": True,
    }
    rows = (
        RunRefInput(
            name="input_path",
            type_descriptor=descriptor,
            binding=ReferenceBinding("inputs.input_path"),
        ),
    )

    resolved = resolve_run_ref_inputs(
        rows,
        parent_state={
            "bound_inputs": {"input_path": "artifacts/work/input.txt"},
            "steps": {},
        },
        parent_workspace=parent,
        child_workspace=child,
    )

    copied = resolved["input_path"]
    assert isinstance(copied, str)
    assert copied != source.as_posix()
    assert copied.startswith("artifacts/work/.run-ref-inputs/input_path/")
    assert (child / copied).read_bytes() == source.read_bytes()


@pytest.mark.parametrize(
    ("descriptor", "value"),
    (
        (_INT, True),
        ({"kind": "list", "item": _INT}, [1, "two"]),
        (
            {
                "kind": "record",
                "name": "Payload",
                "fields": [{"name": "label", "type": _STRING}],
            },
            {"label": "ok", "extra": 1},
        ),
    ),
)
def test_resolve_run_ref_inputs_rejects_type_mismatch(
    descriptor: dict[str, object],
    value: object,
) -> None:
    row = RunRefInput(
        name="value",
        type_descriptor=descriptor,
        binding=ReferenceBinding("inputs.value"),
    )

    with pytest.raises(RunRefRuntimeError, match="run_ref_child_result_invalid"):
        resolve_run_ref_inputs(
            (row,),
            parent_state={"bound_inputs": {"value": value}, "steps": {}},
            parent_workspace=Path("/unused-parent"),
            child_workspace=Path("/unused-child"),
        )


def test_resolve_run_ref_inputs_rejects_missing_reference() -> None:
    row = RunRefInput(
        name="value",
        type_descriptor=_STRING,
        binding=ReferenceBinding("inputs.missing"),
    )

    with pytest.raises(RunRefRuntimeError, match="run_ref_child_launch_failed"):
        resolve_run_ref_inputs(
            (row,),
            parent_state={"bound_inputs": {}, "steps": {}},
            parent_workspace=Path("/unused-parent"),
            child_workspace=Path("/unused-child"),
        )


def test_extract_run_ref_value_validates_direct_root() -> None:
    assert extract_run_ref_value(
        {"__result__": True},
        {"kind": "primitive", "name": "Bool"},
        workspace=Path("/unused-child"),
    ) is True

    with pytest.raises(RunRefRuntimeError, match="run_ref_child_result_invalid"):
        extract_run_ref_value(
            {"__result__": 1},
            {"kind": "primitive", "name": "Bool"},
            workspace=Path("/unused-child"),
        )


def test_extract_run_ref_value_reconstructs_record_and_union() -> None:
    descriptor = {
        "kind": "record",
        "name": "Envelope",
        "fields": [
            {
                "name": "outcome",
                "type": {
                    "kind": "union",
                    "name": "Outcome",
                    "variants": [
                        {
                            "name": "OK",
                            "fields": [{"name": "score", "type": _INT}],
                        },
                        {"name": "STOP", "fields": []},
                    ],
                },
            },
            {"name": "label", "type": _STRING},
        ],
    }

    assert extract_run_ref_value(
        {
            "return__outcome__variant": "OK",
            "return__outcome__score": 7,
            "return__label": "accepted",
        },
        descriptor,
        workspace=Path("/unused-child"),
    ) == {
        "outcome": {"variant": "OK", "score": 7},
        "label": "accepted",
    }


def test_extract_run_ref_value_validates_child_relative_path(tmp_path: Path) -> None:
    workspace = tmp_path / "child"
    target = workspace / "artifacts" / "work" / "result.txt"
    target.parent.mkdir(parents=True)
    target.write_text("result\n", encoding="utf-8")
    descriptor = {
        "kind": "path",
        "name": "ResultPath",
        "under": "artifacts/work",
        "must_exist_target": True,
    }

    assert extract_run_ref_value(
        {"__result__": "artifacts/work/result.txt"},
        descriptor,
        workspace=workspace,
    ) == "artifacts/work/result.txt"

    with pytest.raises(RunRefRuntimeError, match="run_ref_child_result_invalid"):
        extract_run_ref_value(
            {"__result__": "artifacts/work/missing.txt"},
            descriptor,
            workspace=workspace,
        )


def test_extract_run_ref_value_rejects_extra_output_fields() -> None:
    with pytest.raises(RunRefRuntimeError, match="run_ref_child_result_invalid"):
        extract_run_ref_value(
            {"__result__": "ok", "unexpected": True},
            _STRING,
            workspace=Path("/unused-child"),
        )


def test_run_ref_accounting_preserves_unknown_usage_instead_of_zero() -> None:
    assert build_run_ref_accounting(
        child_run_id="child-1",
        attempt_ordinal=2,
        terminal_status="completed",
        elapsed_ms=31,
        setup_ms=7,
        compile_ms=5,
    ) == {
        "child_run_id": "child-1",
        "attempt_ordinal": 2,
        "terminal_status": "completed",
        "elapsed_ms": 31,
        "setup_ms": 7,
        "compile_ms": 5,
        "provider_attempts": "UNKNOWN",
        "token_usage": "UNKNOWN",
        "cost": "UNKNOWN",
    }


def test_declared_artifacts_are_derived_from_every_path_leaf() -> None:
    path = {
        "kind": "path",
        "name": "ArtifactPath",
        "under": "artifacts/work",
        "must_exist_target": True,
    }
    descriptor = {
        "kind": "record",
        "name": "Result",
        "fields": [
            {"name": "primary", "type": path},
            {"name": "others", "type": {"kind": "list", "item": path}},
        ],
    }

    assert declared_artifacts_from_value(
        {
            "primary": "artifacts/work/primary.txt",
            "others": [
                "artifacts/work/other-a.txt",
                "artifacts/work/other-b.txt",
            ],
        },
        descriptor,
    ) == (
        DeclaredArtifact("value.others[0]", "artifacts/work/other-a.txt"),
        DeclaredArtifact("value.others[1]", "artifacts/work/other-b.txt"),
        DeclaredArtifact("value.primary", "artifacts/work/primary.txt"),
    )


def test_flatten_run_ref_result_artifacts_flattens_records_only() -> None:
    union = {
        "kind": "union",
        "name": "Outcome",
        "variants": [{"name": "OK", "fields": []}],
    }
    descriptor = {
        "kind": "record",
        "name": "RunRefResult$fixture",
        "fields": [
            {
                "name": "value",
                "type": {
                    "kind": "record",
                    "name": "ValueRecord",
                    "fields": [
                        {"name": "status", "type": _STRING},
                        {"name": "outcome", "type": union},
                    ],
                },
            },
            {
                "name": "accounting",
                "type": {
                    "kind": "record",
                    "name": "Accounting",
                    "fields": [{"name": "elapsed_ms", "type": _INT}],
                },
            },
        ],
    }
    value = {
        "value": {
            "status": "done",
            "outcome": {"variant": "OK"},
        },
        "accounting": {"elapsed_ms": 9},
    }

    assert flatten_run_ref_result_artifacts(value, descriptor) == {
        "value__status": "done",
        "value__outcome": {"variant": "OK"},
        "accounting__elapsed_ms": 9,
    }


def test_prepare_run_ref_settlement_owns_the_complete_pending_lifecycle(
    tmp_path: Path,
) -> None:
    request = _runtime_request(tmp_path)
    harness = _RuntimeHarness()

    prepared = prepare_run_ref_settlement(
        request,
        dependencies=harness.dependencies(),
    )

    assert type(prepared) is PreparedRunRefSettlement
    assert prepared.envelope["value"] == "artifacts/work/result.txt"
    assert prepared.envelope["accounting"]["provider_attempts"] == "UNKNOWN"
    assert prepared.envelope["accounting"]["token_usage"] == "UNKNOWN"
    assert prepared.envelope["accounting"]["cost"] == "UNKNOWN"
    assert prepared.envelope["workspace_delta"]["declared_artifacts"] == [
        {
            "name": "value",
            "path": "artifacts/work/result.txt",
            "kind": "file",
            "mode": stat.S_IMODE(
                (
                    prepared.settled_result.workspace_path
                    / "artifacts"
                    / "work"
                    / "result.txt"
                ).lstat().st_mode
            ),
            "size": len(b"child result\n"),
            "sha256": "sha256:"
            "60b02de432ace7ebe4110cae5c66d1dfe8a11759cb2b11a4e2fe9c91783941a9",
            "link_target": None,
        }
    ]
    assert prepared.artifacts["value"] == "artifacts/work/result.txt"
    assert prepared.settled_result.attempt_ordinal == 1
    assert (
        prepared.settled_result.step_config_digest
        == request.step_config.step_config_digest
    )
    assert (
        prepared.settled_result.step_config_digest
        != request.step_config.run_ref.digest
    )
    assert prepared.settled_result.run_ref_root == request.run_ref_root
    workspace = prepared.settled_result.workspace_path
    assert workspace.is_relative_to(request.run_ref_root)
    assert not workspace.is_relative_to(request.parent_workspace)
    assert (
        workspace
        / ".orchestrate"
        / "runs"
        / prepared.settled_result.child_run_id
        / "state.json"
    ).is_file()
    copied_input = harness.launches[0].request_document["inputs"]["source_path"]
    assert copied_input.startswith("inputs/.run-ref-inputs/source_path/")
    assert (workspace / copied_input).read_text(encoding="utf-8") == "parent input\n"
    baseline = workspace.parent / "baseline"
    assert (baseline / "setup.txt").read_text(encoding="utf-8") == "setup\n"
    assert (baseline / copied_input).read_text(encoding="utf-8") == "parent input\n"
    assert all(
        ".run-ref-inputs" not in row["path"]
        for field in ("changed_files", "deleted_files", "untracked_files")
        for row in prepared.envelope["workspace_delta"][field]
    )
    ledger = load_attempt_ledger(request.ledger_path)
    assert [row.stage for row in ledger.rows] == [
        "allocated",
        "materialized",
        "setup_completed",
        "program_prepared",
        "launched",
        "child_completed",
        "delta_captured",
        "completed_pending_parent_commit",
    ]
    assert ledger.rows[-1].status == "pending_parent_commit"


def test_finalize_and_validate_completed_authority_reuse_without_child_launch(
    tmp_path: Path,
) -> None:
    request = _runtime_request(tmp_path)
    harness = _RuntimeHarness()
    prepared = prepare_run_ref_settlement(
        request,
        dependencies=harness.dependencies(),
    )

    finalized = finalize_run_ref_parent_commit(
        request,
        prepared,
        persisted_settled_result=prepared.settled_result.record,
    )

    assert finalized.reused is False
    assert load_attempt_ledger(request.ledger_path).rows[-1].stage == "committed"
    assert len(harness.launches) == 1
    reused = validate_completed_run_ref_authority(
        request,
        settled_result=prepared.settled_result.record,
        artifacts=prepared.artifacts,
        reconcile_pending=False,
    )
    assert reused.reused is True
    assert reused.envelope == prepared.envelope
    assert reused.artifacts == prepared.artifacts
    assert len(harness.launches) == 1


@pytest.mark.parametrize("relationship", ["equal", "ancestor", "descendant"])
def test_runtime_request_rejects_every_parent_workspace_root_overlap(
    tmp_path: Path,
    relationship: str,
) -> None:
    valid = _runtime_request(tmp_path)
    if relationship == "equal":
        overlapping = valid.parent_workspace
    elif relationship == "ancestor":
        overlapping = valid.parent_workspace.parent
    else:
        overlapping = valid.parent_workspace / "nested-run-ref-root"

    with pytest.raises(
        RunRefRuntimeError,
        match="run_ref_root_.*parent_workspace",
    ):
        replace(valid, run_ref_root=overlapping)


@pytest.mark.parametrize(
    ("path", "sha256", "byte_size"),
    (
        (Path("relative/output.json"), _digest("e"), 1),
        (Path("/canonical/output.json"), "not-a-digest", 1),
        (Path("/canonical/output.json"), _digest("e"), -1),
        (Path("/canonical/output.json"), _digest("e"), True),
    ),
)
def test_parent_bundle_orphan_preimage_rejects_malformed_records(
    path: Path,
    sha256: str,
    byte_size: int,
) -> None:
    with pytest.raises((RunRefRuntimeError, TypeError, ValueError)):
        ParentBundleOrphanPreimage(
            path=path,
            sha256=sha256,
            byte_size=byte_size,
        )


def test_workspace_path_is_stable_for_the_same_complete_visit_and_ordinal(
    tmp_path: Path,
) -> None:
    request = _runtime_request(tmp_path)
    same_visit = RunRefVisitKey(**request.visit.record)

    workspace = _workspace_for_ordinal(request, 1)

    assert workspace == _workspace_for_ordinal(
        replace(request, visit=same_visit),
        1,
    )
    assert workspace != _workspace_for_ordinal(request, 2)
    assert workspace.is_relative_to(request.run_ref_root)
    assert workspace == workspace.resolve(strict=False)
    assert workspace.name == "workspace"
    assert all(
        len(segment) <= 128
        for segment in workspace.relative_to(request.run_ref_root).parts
    )


@pytest.mark.parametrize(
    "changed_visit",
    (
        RunRefVisitKey("other-parent", "root", None, "root.run-ref", 1),
        RunRefVisitKey("parent-run", "other-frame", None, "root.run-ref", 1),
        RunRefVisitKey("parent-run", "root", "call-frame", "root.run-ref", 1),
        RunRefVisitKey("parent-run", "root", None, "other-step", 1),
        RunRefVisitKey("parent-run", "root", None, "root.run-ref", 2),
    ),
)
def test_workspace_path_does_not_collide_when_any_visit_component_changes(
    tmp_path: Path,
    changed_visit: RunRefVisitKey,
) -> None:
    request = _runtime_request(tmp_path)

    assert _workspace_for_ordinal(request, 1) != _workspace_for_ordinal(
        replace(request, visit=changed_visit),
        1,
    )


def test_default_child_launcher_uses_exact_candidate_workspace_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = (tmp_path / "controller").resolve()
    candidate = (tmp_path / "candidate").resolve()
    controller.mkdir()
    candidate.mkdir()
    request_path = controller / "request.json"
    request_path.write_text("{}", encoding="utf-8")
    observed: dict[str, object] = {}
    monkeypatch.setenv("PYTHONPATH", (tmp_path / "inherited-shadow").as_posix())

    def fake_run(argv, **kwargs):
        observed["argv"] = argv
        observed.update(kwargs)
        return type(
            "Completed",
            (),
            {"returncode": 0, "stdout": b"{}\n", "stderr": b""},
        )()

    monkeypatch.setattr("orchestrator.workflow.run_ref.runtime.subprocess.run", fake_run)
    launch = RunRefChildLaunch(
        mode="bundle",
        request_path=request_path,
        request_document={},
        workspace=candidate,
        child_run_id="child",
    )

    RunRefRuntimeDependencies().launch_child(launch)

    assert observed["cwd"] == candidate
    assert observed["shell"] is False
    assert observed["argv"][1:3] == ("-I", "-c")
    assert Path(observed["argv"][4]) == Path(runtime_module.__file__).resolve().parents[3]
    assert observed["argv"][5:] == ("--request", request_path.as_posix())
    assert "PYTHONPATH" not in observed["env"]
    assert candidate.as_posix() not in observed["argv"]


def test_child_launcher_uses_controller_runtime_over_candidate_shadow(
    tmp_path: Path,
) -> None:
    candidate = (tmp_path / "candidate").resolve()
    shadow_package = candidate / "orchestrator"
    shadow_package.mkdir(parents=True)
    marker = candidate / "candidate-shadow-imported"
    (shadow_package / "__init__.py").write_text(
        (
            "from pathlib import Path\n"
            f"Path({marker.as_posix()!r}).write_text('shadowed')\n"
        ),
        encoding="utf-8",
    )
    request_path = candidate / "invalid-request.json"
    request_path.write_text("{}\n", encoding="utf-8")
    launch = RunRefChildLaunch(
        mode="bundle",
        request_path=request_path,
        request_document={},
        workspace=candidate,
        child_run_id="child",
    )

    result = RunRefRuntimeDependencies().launch_child(launch)

    assert result.returncode == 2
    assert result.stdout == b""
    assert json.loads(result.stderr) == {
        "schema_version": "run_ref_child_diagnostic.v1",
        "status": "rejected",
        "code": "run_ref_child_launch_failed",
        "reason": "request_invalid",
    }
    assert not marker.exists()


def test_parent_preserves_validated_structural_child_failure_authority(
    tmp_path: Path,
) -> None:
    request = _runtime_request(tmp_path, mode="path")
    launch = RunRefChildLaunch(
        mode="path",
        request_path=request.parent_run_root / "request.json",
        request_document={},
        workspace=request.run_ref_root / "workspace",
        child_run_id="child",
    )
    diagnostic = {
        "schema_version": "run_ref_child_diagnostic.v1",
        "status": "rejected",
        "code": "trial_program_missing",
        "reason": "path_compile_rejected",
        "rejected_value": {"path": "candidate.orc"},
        "secondary_causes": ["program_missing"],
    }

    with pytest.raises(RunRefRuntimeError) as excinfo:
        _child_result_document(
            request,
            launch=launch,
            process=RunRefChildProcessResult(
                returncode=2,
                stdout=b"",
                stderr=canonical_json_bytes(diagnostic) + b"\n",
                duration_ms=1,
            ),
        )

    assert excinfo.value.code == "trial_program_missing"
    assert excinfo.value.detail == "path_compile_rejected"
    assert excinfo.value.machine_fields == {
        "rejected_value": {"path": "candidate.orc"},
        "secondary_causes": ["program_missing"],
    }


def test_parent_rejects_open_or_malformed_child_failure_authority(
    tmp_path: Path,
) -> None:
    request = _runtime_request(tmp_path, mode="path")
    launch = RunRefChildLaunch(
        mode="path",
        request_path=request.parent_run_root / "request.json",
        request_document={},
        workspace=request.run_ref_root / "workspace",
        child_run_id="child",
    )
    malformed = {
        "schema_version": "run_ref_child_diagnostic.v1",
        "status": "rejected",
        "code": "trial_program_missing",
        "reason": "path_compile_rejected",
        "rejected_value": {"path": "candidate.orc"},
        "secondary_causes": ["program_missing"],
        "unexpected": "open-authority",
    }

    with pytest.raises(
        RunRefRuntimeError,
        match="child_process_failed_without_diagnostic",
    ) as excinfo:
        _child_result_document(
            request,
            launch=launch,
            process=RunRefChildProcessResult(
                returncode=2,
                stdout=b"",
                stderr=canonical_json_bytes(malformed) + b"\n",
                duration_ms=1,
            ),
        )

    assert excinfo.value.code == "run_ref_child_launch_failed"
    assert excinfo.value.machine_fields == {}


class _InjectedCrash(RuntimeError):
    pass


@pytest.mark.parametrize(
    ("mode", "boundary", "expected_stage"),
    (
        ("bundle", "allocation", "allocated"),
        ("bundle", "materialize", "allocated"),
        ("bundle", "setup", "allocated"),
        ("bundle", "launch", "launched"),
        ("bundle", "child_completion", "child_completed"),
        ("bundle", "delta", "delta_captured"),
    ),
)
def test_every_pre_parent_crash_discards_exact_workspace_and_reruns_fresh(
    tmp_path: Path,
    mode: str,
    boundary: str,
    expected_stage: str,
) -> None:
    request = _runtime_request(tmp_path, mode=mode)
    harness = _RuntimeHarness()

    def crash(observed: str) -> None:
        if observed == boundary:
            raise _InjectedCrash(boundary)

    with pytest.raises(_InjectedCrash, match=boundary):
        prepare_run_ref_settlement(
            request,
            dependencies=replace(harness.dependencies(), crash_hook=crash),
        )

    crashed = load_attempt_ledger(request.ledger_path).rows[-1]
    assert crashed.stage == expected_stage
    assert crashed.status in {"in_progress", "pending_parent_commit"}
    crashed_workspace = crashed.bindings.workspace_path
    recovered = prepare_run_ref_settlement(
        request,
        dependencies=harness.dependencies(),
    )
    ledger = load_attempt_ledger(request.ledger_path)
    discarded = [
        row
        for row in ledger.rows
        if row.attempt_ordinal == 1 and row.status == "discarded"
    ]
    assert len(discarded) == 1
    assert discarded[0].stage == expected_stage
    assert not crashed_workspace.exists()
    disposition_path = crashed_workspace.parent / "disposition.json"
    disposition = json.loads(disposition_path.read_bytes())
    assert disposition_path.read_bytes() == canonical_json_bytes(disposition) + b"\n"
    assert disposition["workspace_deletion"] == {
        "status": "deleted_or_confirmed_absent",
        "workspace_absent": True,
    }
    assert disposition["parent_bundle_orphan_preimage"] is None
    assert canonical_sha256(disposition) == discarded[0].bindings.disposition_digest
    assert recovered.settled_result.attempt_ordinal == 2
    assert recovered.settled_result.workspace_path != crashed_workspace
    assert ledger.rows[-1].stage == "completed_pending_parent_commit"


@pytest.mark.parametrize(
    ("mode", "boundary"),
    (
        ("bundle", "mode_1_decode"),
        ("path", "mode_2_compile"),
    ),
)
def test_actual_child_boundary_crash_is_bound_then_discarded_for_fresh_attempt(
    tmp_path: Path,
    mode: str,
    boundary: str,
) -> None:
    request = _runtime_request(tmp_path, mode=mode)
    harness = _RuntimeHarness()
    observed_progress: list[Path] = []

    def crash_after_actual_boundary(
        launch: RunRefChildLaunch,
    ) -> RunRefChildProcessResult:
        control = launch.request_document["test_control"]
        assert control == {
            "schema_version": "run_ref_child_test_control.v1",
            "boundary": boundary,
            "progress_path": (
                launch.workspace.parent
                / "run-ref-child-boundary-progress.json"
            ).as_posix(),
        }
        progress_path = Path(control["progress_path"])
        progress_path.write_bytes(
            canonical_json_bytes(
                {
                    "schema_version": "run_ref_child_boundary_progress.v1",
                    "boundary": boundary,
                }
            )
            + b"\n"
        )
        observed_progress.append(progress_path)
        return RunRefChildProcessResult(
            returncode=86,
            stdout=b"",
            stderr=b"",
            duration_ms=1,
        )

    with pytest.raises(
        RunRefRuntimeError,
        match="child_process_failed_without_diagnostic",
    ):
        prepare_run_ref_settlement(
            request,
            dependencies=RunRefRuntimeDependencies(
                materialize_source=harness.materialize,
                launch_child=crash_after_actual_boundary,
                child_test_boundary=boundary,
            ),
        )

    incomplete = load_attempt_ledger(request.ledger_path).rows[-1]
    assert incomplete.stage == "launched"
    assert incomplete.status == "in_progress"
    assert len(observed_progress) == 1
    assert observed_progress[0].is_file()

    recovered = prepare_run_ref_settlement(
        request,
        dependencies=harness.dependencies(),
    )

    assert recovered.settled_result.attempt_ordinal == 2
    assert not incomplete.bindings.workspace_path.exists()
    discarded = [
        row
        for row in load_attempt_ledger(request.ledger_path).rows
        if row.attempt_ordinal == 1 and row.status == "discarded"
    ]
    assert len(discarded) == 1


def test_incomplete_attempt_records_exact_parent_bundle_orphan_preimage(
    tmp_path: Path,
) -> None:
    request = _runtime_request(tmp_path)
    harness = _RuntimeHarness()

    with pytest.raises(_InjectedCrash, match="allocation"):
        prepare_run_ref_settlement(
            request,
            dependencies=replace(
                harness.dependencies(),
                crash_hook=lambda boundary: (
                    (_ for _ in ()).throw(_InjectedCrash(boundary))
                    if boundary == "allocation"
                    else None
                ),
            ),
        )

    incomplete = load_attempt_ledger(request.ledger_path).rows[-1]
    orphan_path = (request.parent_run_root / "output-bundle.json").resolve()
    orphan_bytes = b'{"stale":true}\n'
    orphan_path.write_bytes(orphan_bytes)
    preimage = ParentBundleOrphanPreimage(
        path=orphan_path,
        sha256="sha256:" + hashlib.sha256(orphan_bytes).hexdigest(),
        byte_size=len(orphan_bytes),
    )
    recovery_request = replace(
        request,
        parent_bundle_orphan_preimage=preimage,
    )

    prepared = prepare_run_ref_settlement(
        recovery_request,
        dependencies=harness.dependencies(),
    )

    disposition_path = incomplete.bindings.workspace_path.parent / "disposition.json"
    disposition = json.loads(disposition_path.read_bytes())
    assert disposition["parent_bundle_orphan_preimage"] == preimage.record
    discarded = [
        row
        for row in load_attempt_ledger(request.ledger_path).rows
        if row.attempt_ordinal == 1 and row.status == "discarded"
    ]
    assert len(discarded) == 1
    assert discarded[0].bindings.disposition_digest == canonical_sha256(disposition)
    assert prepared.settled_result.attempt_ordinal == 2
    assert recovery_request.step_config.step_config_digest == (
        request.step_config.step_config_digest
    )
    finalized = finalize_run_ref_parent_commit(
        recovery_request,
        prepared,
        persisted_settled_result=prepared.settled_result.record,
    )
    reused = validate_completed_run_ref_authority(
        recovery_request,
        settled_result=prepared.settled_result.record,
        artifacts=prepared.artifacts,
        reconcile_pending=False,
    )
    assert finalized.settled_result == reused.settled_result


def test_parent_bundle_orphan_preimage_without_incomplete_attempt_fails_closed(
    tmp_path: Path,
) -> None:
    request = _runtime_request(tmp_path)
    harness = _RuntimeHarness()
    orphan_path = (request.parent_run_root / "output-bundle.json").resolve()
    orphan_bytes = b'{"stale":true}\n'
    orphan_path.write_bytes(orphan_bytes)
    preimage = ParentBundleOrphanPreimage(
        path=orphan_path,
        sha256="sha256:" + hashlib.sha256(orphan_bytes).hexdigest(),
        byte_size=len(orphan_bytes),
    )

    with pytest.raises(
        RunRefRuntimeError,
        match="parent_bundle_orphan_preimage_without_incomplete_attempt",
    ):
        prepare_run_ref_settlement(
            replace(request, parent_bundle_orphan_preimage=preimage),
            dependencies=harness.dependencies(),
        )

    assert not request.ledger_path.exists()
    assert harness.launches == []


def test_parent_commit_crash_reconciles_from_persisted_parent_without_launch(
    tmp_path: Path,
) -> None:
    request = _runtime_request(tmp_path)
    harness = _RuntimeHarness()
    prepared = prepare_run_ref_settlement(
        request,
        dependencies=harness.dependencies(),
    )

    def crash(boundary: str) -> None:
        if boundary == "parent_commit":
            raise _InjectedCrash(boundary)

    with pytest.raises(_InjectedCrash, match="parent_commit"):
        finalize_run_ref_parent_commit(
            request,
            prepared,
            persisted_settled_result=prepared.settled_result.record,
            dependencies=RunRefRuntimeDependencies(crash_hook=crash),
        )

    assert load_attempt_ledger(request.ledger_path).rows[-1].stage == (
        "completed_pending_parent_commit"
    )
    reconciled = validate_completed_run_ref_authority(
        request,
        settled_result=prepared.settled_result.record,
        artifacts=prepared.artifacts,
        reconcile_pending=True,
    )
    assert reconciled.reused is True
    assert load_attempt_ledger(request.ledger_path).rows[-1].stage == "committed"
    assert len(harness.launches) == 1


def test_completed_authority_tamper_fails_closed(tmp_path: Path) -> None:
    request = _runtime_request(tmp_path)
    harness = _RuntimeHarness()
    prepared = prepare_run_ref_settlement(
        request,
        dependencies=harness.dependencies(),
    )
    finalize_run_ref_parent_commit(
        request,
        prepared,
        persisted_settled_result=prepared.settled_result.record,
    )
    artifact = prepared.settled_result.workspace_path / "artifacts/work/result.txt"
    artifact.write_text("tampered\n", encoding="utf-8")

    with pytest.raises(
        RunRefRuntimeError,
        match="run_ref_delta_capture_failed|run_ref_evidence_invalid",
    ):
        validate_completed_run_ref_authority(
            request,
            settled_result=prepared.settled_result.record,
            artifacts=prepared.artifacts,
            reconcile_pending=False,
        )


def test_incomplete_workspace_discard_failure_never_allocates_fresh_ordinal(
    tmp_path: Path,
) -> None:
    request = _runtime_request(tmp_path)
    harness = _RuntimeHarness()

    with pytest.raises(_InjectedCrash):
        prepare_run_ref_settlement(
            request,
            dependencies=replace(
                harness.dependencies(),
                crash_hook=lambda boundary: (
                    (_ for _ in ()).throw(_InjectedCrash(boundary))
                    if boundary == "allocation"
                    else None
                ),
            ),
        )

    def refuse_discard(_workspace: Path) -> None:
        raise OSError("cannot discard")

    with pytest.raises(
        RunRefRuntimeError,
        match="run_ref_workspace_discard_failed",
    ):
        prepare_run_ref_settlement(
            request,
            dependencies=replace(
                harness.dependencies(),
                discard_workspace=refuse_discard,
            ),
        )
    assert {
        row.attempt_ordinal for row in load_attempt_ledger(request.ledger_path).rows
    } == {1}


def test_finalize_translates_malformed_parent_binding_to_closed_runtime_error(
    tmp_path: Path,
) -> None:
    request = _runtime_request(tmp_path)
    harness = _RuntimeHarness()
    prepared = prepare_run_ref_settlement(
        request,
        dependencies=harness.dependencies(),
    )
    malformed = dict(prepared.settled_result.record)
    malformed.pop("pending_row_digest")

    with pytest.raises(RunRefRuntimeError, match="run_ref_ledger_invalid"):
        finalize_run_ref_parent_commit(
            request,
            prepared,
            persisted_settled_result=malformed,
        )


def test_child_launcher_exception_is_a_closed_launch_failure(tmp_path: Path) -> None:
    request = _runtime_request(tmp_path)
    harness = _RuntimeHarness()

    def fail_launch(_launch: RunRefChildLaunch) -> RunRefChildProcessResult:
        raise OSError("exec failed")

    with pytest.raises(RunRefRuntimeError, match="run_ref_child_launch_failed"):
        prepare_run_ref_settlement(
            request,
            dependencies=replace(
                harness.dependencies(),
                launch_child=fail_launch,
            ),
        )


def test_path_mode_request_and_completed_authority_use_full_child_contract(
    tmp_path: Path,
) -> None:
    request = _runtime_request(tmp_path, mode="path")
    harness = _RuntimeHarness()
    prepared = prepare_run_ref_settlement(
        request,
        dependencies=harness.dependencies(),
    )
    launch = harness.launches[0]

    assert launch.mode == "path"
    assert launch.request_document["schema_version"] == (
        "run_ref_path_child_request.v1"
    )
    assert launch.request_document["expected_step_config_digest"] == (
        request.step_config.step_config_digest
    )
    assert launch.request_document["materialized_source"][
        "post_setup_baseline_identity"
    ] == load_attempt_ledger(request.ledger_path).rows[-1].bindings.post_setup_baseline_digest
    finalized = finalize_run_ref_parent_commit(
        request,
        prepared,
        persisted_settled_result=prepared.settled_result.record,
    )
    assert finalized.reused is False
    reused = validate_completed_run_ref_authority(
        request,
        settled_result=prepared.settled_result.record,
        artifacts=prepared.artifacts,
        reconcile_pending=False,
    )
    assert reused.envelope == prepared.envelope
    assert len(harness.launches) == 1
