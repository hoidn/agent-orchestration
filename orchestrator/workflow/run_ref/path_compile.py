"""Full-compiler admission for one pinned mode-2 ``run-ref`` program."""

from __future__ import annotations

from dataclasses import dataclass, fields
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping

from orchestrator.workflow.executable_ir import RunRefStepConfig
from orchestrator.workflow_lisp.build import (
    FrontendBuildRequest,
    FrontendBuildResult,
    build_frontend_bundle,
)
from orchestrator.workflow_lisp.compile_diagnostics import (
    build_accepted_compile_diagnostics_document,
    build_rejected_compile_diagnostics_document,
)
from orchestrator.workflow_lisp.compiler import (
    WorkflowBoundaryAdmissionProfile,
    linked_module_type_environment,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.effects import EffectAtom, EffectSummary, ProcedureCallEdge
from orchestrator.workflow_lisp.normalized_type_descriptor import (
    compiler_normalized_type_descriptor,
)
from orchestrator.workflow_lisp.workflows import TypedWorkflowDef
from orchestrator.workflow_lisp.wcc.route import LoweringRoute

from .config import (
    PathProgram,
    RunRefInput,
    validate_run_ref_static_config_authority,
)
from .contracts import canonical_json_bytes, canonical_sha256, compute_compiler_runtime_identity
from .result_contract import is_transportable_type_descriptor
from .source import MaterializedSource, canonical_source_request


PATH_COMPILE_EVIDENCE_SCHEMA = "run_ref_path_compile_evidence.v1"
_EFFECT_DIAGNOSTIC_CODES = frozenset(
    {"provider_result_provider_invalid", "command_adapter_missing_contract"}
)
_VALUE_DESCRIPTOR = {"kind": "primitive", "name": "Value"}
_CAMEL_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")


class RunRefPathCompileRefusal(ValueError):
    """One closed structural refusal from full compile or admission."""

    def __init__(
        self,
        code: str,
        rejected_value: object,
        *,
        secondary_causes: tuple[str, ...] = (),
        compile_diagnostics_document: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self._rejected_value_json = canonical_json_bytes(rejected_value)
        self.secondary_causes = tuple(secondary_causes)
        self._compile_diagnostics_json = (
            None
            if compile_diagnostics_document is None
            else canonical_json_bytes(compile_diagnostics_document)
        )

    @property
    def rejected_value(self) -> object:
        return json.loads(self._rejected_value_json)

    @property
    def compile_diagnostics_document(self) -> dict[str, object] | None:
        if self._compile_diagnostics_json is None:
            return None
        return json.loads(self._compile_diagnostics_json)

    @property
    def record(self) -> dict[str, object]:
        return {
            "code": self.code,
            "rejected_value": self.rejected_value,
            "secondary_causes": list(self.secondary_causes),
        }


@dataclass(frozen=True, slots=True)
class AdmittedPathProgram:
    """Immutable accepted full-compiler result and its path-free evidence."""

    build_result: FrontendBuildResult
    _diagnostics_json: bytes
    _program_identity_json: bytes
    _signature_json: bytes
    _effect_facts_json: bytes
    _evidence_json: bytes

    @property
    def diagnostics_document(self) -> dict[str, object]:
        return json.loads(self._diagnostics_json)

    @property
    def program_identity(self) -> dict[str, object]:
        return json.loads(self._program_identity_json)

    @property
    def signature(self) -> dict[str, object]:
        return json.loads(self._signature_json)

    @property
    def effect_facts(self) -> dict[str, object]:
        return json.loads(self._effect_facts_json)

    @property
    def evidence(self) -> dict[str, object]:
        return json.loads(self._evidence_json)


def _refuse(
    code: str,
    rejected_value: object,
    *,
    secondary_causes: tuple[str, ...] = (),
    diagnostics: Mapping[str, object] | None = None,
) -> RunRefPathCompileRefusal:
    return RunRefPathCompileRefusal(
        code,
        rejected_value,
        secondary_causes=secondary_causes,
        compile_diagnostics_document=diagnostics,
    )


def _require_program_file(workspace: Path, program: PathProgram) -> Path:
    program_path = workspace.joinpath(*program.path.split("/"))
    try:
        identity = os.lstat(program_path)
    except OSError as exc:
        raise _refuse(
            "trial_program_missing",
            program.record,
            secondary_causes=("program_missing",),
        ) from exc
    if stat.S_ISLNK(identity.st_mode):
        raise _refuse(
            "trial_program_missing",
            program.record,
            secondary_causes=("program_symlink",),
        )
    if not stat.S_ISREG(identity.st_mode):
        raise _refuse(
            "trial_program_missing",
            program.record,
            secondary_causes=("program_not_regular",),
        )
    return program_path


def _compile(
    materialized_source: MaterializedSource,
    program: PathProgram,
) -> tuple[FrontendBuildResult, dict[str, object]]:
    source_path = _require_program_file(materialized_source.workspace_path, program)
    request = FrontendBuildRequest(
        source_path=source_path,
        source_roots=(materialized_source.workspace_path,),
        entry_workflow=program.entry_name,
        boundary_admission_profile=(
            WorkflowBoundaryAdmissionProfile.TRANSPORTABLE_CHILD
        ),
        provider_externs_path=None,
        prompt_externs_path=None,
        imported_workflow_bundles_path=None,
        command_boundaries_path=None,
        workspace_root=materialized_source.workspace_path,
        lowering_route=LoweringRoute.WCC_M4,
    )
    try:
        result = build_frontend_bundle(request)
    except LispFrontendCompileError as exc:
        document = build_rejected_compile_diagnostics_document(exc.diagnostics)
        diagnostic_codes = tuple(
            str(row["code"]) for row in document["diagnostics"]
        )
        code = (
            "trial_candidate_environment_not_admissible"
            if _EFFECT_DIAGNOSTIC_CODES.intersection(diagnostic_codes)
            else "trial_program_compile_rejected"
        )
        raise _refuse(
            code,
            {"program": program.record, "compile_diagnostics": document},
            secondary_causes=diagnostic_codes,
            diagnostics=document,
        ) from exc
    return result, build_accepted_compile_diagnostics_document(result)


def _selected_typed_workflow(result: FrontendBuildResult) -> TypedWorkflowDef:
    canonical_name = result.entry_selection.canonical_name
    selected_name = result.entry_selection.selected_name
    signature = result.compile_result.entry_result.workflow_catalog.signatures_by_name.get(
        canonical_name
    )
    if signature is None:
        signature = result.compile_result.entry_result.workflow_catalog.signatures_by_name.get(
            selected_name
        )
    compiled_results = (
        result.compile_result.entry_result,
        *result.compile_result.compiled_results_by_name.values(),
    )
    candidates_by_identity = {
        id(workflow): workflow
        for compiled in compiled_results
        for workflow in compiled.typed_workflows
        if workflow.signature is signature or workflow.signature == signature
    }
    candidates = tuple(
        workflow
        for workflow in candidates_by_identity.values()
    )
    if len(candidates) != 1 or type(candidates[0]) is not TypedWorkflowDef:
        raise _refuse(
            "trial_candidate_environment_not_admissible",
            {"entry": canonical_name},
            secondary_causes=("typed_workflow_summary_missing_or_ambiguous",),
        )
    return candidates[0]


def _signature(
    result: FrontendBuildResult,
    workflow: TypedWorkflowDef,
) -> dict[str, object]:
    module_name = result.compile_result.graph.entry_module_name
    type_env = linked_module_type_environment(result.compile_result, module_name)
    inputs = [
        {
            "name": name,
            "required": name not in workflow.signature.param_defaults,
            "type": compiler_normalized_type_descriptor(type_ref, type_env=type_env),
        }
        for name, type_ref in workflow.signature.params
    ]
    return_descriptor = compiler_normalized_type_descriptor(
        workflow.signature.return_type_ref,
        type_env=type_env,
    )
    return {"inputs": inputs, "return": return_descriptor}


def _signature_mismatch_causes(
    signature: Mapping[str, object],
    configured_inputs: tuple[RunRefInput, ...],
    program: PathProgram,
    *,
    target_dsl_version: str = "2.24",
) -> tuple[str, ...]:
    allow_nested_structures = target_dsl_version == "2.25"
    expected_rows = signature["inputs"]
    if not isinstance(expected_rows, list):
        return ("signature_inputs_malformed",)
    expected_by_name = {
        str(row["name"]): row for row in expected_rows if isinstance(row, Mapping)
    }
    configured_by_name = {row.name: row for row in configured_inputs}
    causes: list[str] = []
    for name, row in expected_by_name.items():
        descriptor = row.get("type")
        if not isinstance(descriptor, Mapping) or not is_transportable_type_descriptor(
            descriptor,
            allow_nested_structures=allow_nested_structures,
        ):
            causes.append(f"input_nontransportable:{name}")
        configured = configured_by_name.get(name)
        if configured is None:
            if row.get("required") is True:
                causes.append(f"missing_input:{name}")
        elif configured.type_descriptor != descriptor:
            causes.append(f"input_type_mismatch:{name}")
    for name in sorted(
        set(configured_by_name).difference(expected_by_name),
        key=lambda value: value.encode("utf-8"),
    ):
        causes.append(f"extra_input:{name}")
    return_descriptor = signature.get("return")
    if not isinstance(return_descriptor, Mapping) or not is_transportable_type_descriptor(
        return_descriptor,
        allow_nested_structures=allow_nested_structures,
    ):
        causes.append("return_nontransportable")
    return_claim = program.return_refinement or _VALUE_DESCRIPTOR
    if return_descriptor != return_claim:
        causes.append("return_type_mismatch")
    return tuple(causes)


def _canonical_field_value(value: object) -> object:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, tuple):
        return [_canonical_field_value(item) for item in value]
    raise TypeError("effect atom contains a non-structural field")


def _effect_atom_fact(atom: object) -> dict[str, object]:
    if not isinstance(atom, EffectAtom):
        raise TypeError("effect summary contains an unknown atom")
    return {
        "kind": _CAMEL_BOUNDARY.sub("_", type(atom).__name__).lower(),
        "fields": {
            field.name: _canonical_field_value(getattr(atom, field.name))
            for field in fields(atom)
        },
    }


def _effect_facts(workflow: TypedWorkflowDef) -> dict[str, object]:
    summary = workflow.effect_summary
    if type(summary) is not EffectSummary:
        raise TypeError("typed workflow effect summary is malformed")
    if not isinstance(summary.direct_effects, frozenset) or not isinstance(
        summary.transitive_effects, frozenset
    ) or not isinstance(summary.procedure_edges, frozenset):
        raise TypeError("typed workflow effect sets are malformed")

    def atoms(values: frozenset[EffectAtom]) -> list[dict[str, object]]:
        return sorted(
            (_effect_atom_fact(value) for value in values),
            key=canonical_json_bytes,
        )

    edges: list[dict[str, object]] = []
    for edge in summary.procedure_edges:
        if type(edge) is not ProcedureCallEdge:
            raise TypeError("effect summary contains an unknown procedure edge")
        edges.append(
            {"callee_name": edge.callee_name, "form_path": list(edge.form_path)}
        )
    edges.sort(key=canonical_json_bytes)
    return {
        "direct": atoms(summary.direct_effects),
        "transitive": atoms(summary.transitive_effects),
        "procedure_edges": edges,
    }


def compile_and_admit_path_program(
    *,
    materialized_source: MaterializedSource,
    step_config: RunRefStepConfig,
) -> AdmittedPathProgram:
    """Compile and admit one exact path-mode program without launching it."""

    if type(materialized_source) is not MaterializedSource:
        raise TypeError("path compile requires exact MaterializedSource authority")
    if type(step_config) is not RunRefStepConfig:
        raise TypeError("path compile requires exact RunRefStepConfig authority")
    if type(step_config.run_ref.program) is not PathProgram:
        raise TypeError("path compile requires an exact PathProgram")
    validate_run_ref_static_config_authority(step_config.run_ref)
    if step_config.capsule_binding is not None:
        raise ValueError("path compile forbids a compiled-bundle capsule binding")

    program = step_config.run_ref.program
    source_record = canonical_source_request(step_config.run_ref.source)
    revision = materialized_source.repository_revision_id
    source_identity_matches = (
        revision.normalized_locator == source_record["normalized_locator"]
        and revision.resolved_commit_sha == source_record["resolved_commit_sha"]
        and revision.materializer_version == source_record["materializer_version"]
        and revision.submodule_policy == source_record["submodule_policy"]
        and revision.lfs_policy == source_record["lfs_policy"]
        and revision.authored_setup_identity
        == source_record["authored_setup_identity"]
        and materialized_source.normalized_locator == revision.normalized_locator
        and materialized_source.resolved_commit_sha == revision.resolved_commit_sha
    )
    if not source_identity_matches:
        raise _refuse(
            "trial_program_compile_rejected",
            {
                "expected_source_identity": {
                    key: source_record[key]
                    for key in (
                        "normalized_locator",
                        "resolved_commit_sha",
                        "materializer_version",
                        "submodule_policy",
                        "lfs_policy",
                        "authored_setup_identity",
                    )
                },
                "materialized_source_identity": revision.components,
            },
            secondary_causes=("source_identity_mismatch",),
        )
    local_compiler_identity = compute_compiler_runtime_identity().digest
    if local_compiler_identity != step_config.run_ref.compiler_runtime_identity_digest:
        raise _refuse(
            "trial_program_compile_rejected",
            {
                "expected_compiler_runtime_identity_digest": (
                    step_config.run_ref.compiler_runtime_identity_digest
                ),
                "actual_compiler_runtime_identity_digest": local_compiler_identity,
            },
            secondary_causes=("compiler_runtime_identity_mismatch",),
        )

    build_result, diagnostics = _compile(materialized_source, program)
    workflow = _selected_typed_workflow(build_result)
    signature = _signature(build_result, workflow)
    mismatch_causes = _signature_mismatch_causes(
        signature,
        step_config.run_ref.inputs,
        program,
        target_dsl_version=step_config.run_ref.target_dsl_version,
    )
    if mismatch_causes:
        raise _refuse(
            "trial_program_signature_mismatch",
            {
                "program": program.record,
                "signature": signature,
                "provided_inputs": [
                    {"name": row.name, "type": row.type_descriptor}
                    for row in step_config.run_ref.inputs
                ],
            },
            secondary_causes=mismatch_causes,
            diagnostics=diagnostics,
        )

    try:
        effect_facts = _effect_facts(workflow)
    except (TypeError, ValueError) as exc:
        raise _refuse(
            "trial_candidate_environment_not_admissible",
            {"entry": build_result.entry_selection.canonical_name},
            secondary_causes=("effect_summary_invalid",),
            diagnostics=diagnostics,
        ) from exc
    if effect_facts["direct"] or effect_facts["transitive"]:
        effect_kinds = sorted(
            {
                str(row["kind"])
                for collection in (effect_facts["direct"], effect_facts["transitive"])
                for row in collection
            }
        )
        raise _refuse(
            "trial_candidate_environment_not_admissible",
            {
                "environment": program.environment,
                "effect_facts": effect_facts,
            },
            secondary_causes=tuple(f"effect:{kind}" for kind in effect_kinds),
            diagnostics=diagnostics,
        )

    program_identity = diagnostics["normalized_program_identity"]
    if not isinstance(program_identity, Mapping):
        raise _refuse(
            "trial_program_compile_rejected",
            diagnostics,
            secondary_causes=("program_identity_missing",),
            diagnostics=diagnostics,
        )
    if (
        program_identity.get("schema_version")
        != "workflow_lisp_program_identity.v2"
        or program_identity.get("boundary_admission_profile")
        != WorkflowBoundaryAdmissionProfile.TRANSPORTABLE_CHILD.value
    ):
        raise _refuse(
            "trial_program_compile_rejected",
            diagnostics,
            secondary_causes=(
                "program_identity_boundary_admission_profile_mismatch",
            ),
            diagnostics=diagnostics,
        )
    if program_identity.get("compiler_runtime_identity") != local_compiler_identity:
        raise _refuse(
            "trial_program_compile_rejected",
            diagnostics,
            secondary_causes=("program_identity_compiler_mismatch",),
            diagnostics=diagnostics,
        )
    input_facts = signature["inputs"]
    return_fact = signature["return"]
    evidence_components = {
        "schema_version": PATH_COMPILE_EVIDENCE_SCHEMA,
        "repository_revision_digest": materialized_source.repository_revision_id.digest,
        "verified_git_tree": materialized_source.verified_git_tree.value,
        "step_config_digest": step_config.step_config_digest,
        "compiler_runtime_identity_digest": local_compiler_identity,
        "program_identity_digest": program_identity["digest"],
        "signature_digest": canonical_sha256(signature),
        "input_digest": canonical_sha256(input_facts),
        "return_digest": canonical_sha256(return_fact),
        "effect_digest": canonical_sha256(effect_facts),
        "diagnostics_digest": canonical_sha256(diagnostics),
        "environment": program.environment,
    }
    evidence = {
        **evidence_components,
        "digest": canonical_sha256(evidence_components),
    }
    return AdmittedPathProgram(
        build_result=build_result,
        _diagnostics_json=canonical_json_bytes(diagnostics),
        _program_identity_json=canonical_json_bytes(program_identity),
        _signature_json=canonical_json_bytes(signature),
        _effect_facts_json=canonical_json_bytes(effect_facts),
        _evidence_json=canonical_json_bytes(evidence),
    )


__all__ = [
    "AdmittedPathProgram",
    "PATH_COMPILE_EVIDENCE_SCHEMA",
    "RunRefPathCompileRefusal",
    "compile_and_admit_path_program",
]
