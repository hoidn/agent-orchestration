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
from orchestrator.workflow_lisp.compile_diagnostics import (
    build_rejected_compile_diagnostics_document,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.effects import EffectAtom, EffectSummary, ProcedureCallEdge

from .config import (
    PathProgram,
    validate_run_ref_static_config_authority,
)
from .contracts import canonical_json_bytes, canonical_sha256, compute_compiler_runtime_identity
from .path_contracts import (
    PATH_COMPILE_EVIDENCE_SCHEMA,
    RunRefPathCompileRefusal,
    _recorded_path_compile_evidence,
    _refuse,
    _signature_mismatch_causes,
)
from .source import MaterializedSource, canonical_source_request


_EFFECT_DIAGNOSTIC_CODES = frozenset(
    {"provider_result_provider_invalid", "command_adapter_missing_contract"}
)
_CAMEL_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")




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




def _compile_refusal(exc, program):
    document = build_rejected_compile_diagnostics_document(exc.diagnostics)
    diagnostic_codes = tuple(
        str(row["code"]) for row in document["diagnostics"]
    )
    code = (
        "trial_candidate_environment_not_admissible"
        if _EFFECT_DIAGNOSTIC_CODES.intersection(diagnostic_codes)
        else "trial_program_compile_rejected"
    )
    return _refuse(
        code,
        {"program": program.record, "compile_diagnostics": document},
        secondary_causes=diagnostic_codes,
        diagnostics=document,
    )







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




def _effect_summary_facts(summary: EffectSummary) -> dict[str, object]:
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


def _validate_path_compile_authority(materialized_source, step_config):
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
    _validate_materialized_source_identity(materialized_source, step_config)
    return program, _require_path_compiler_identity(step_config)


def _validate_materialized_source_identity(materialized_source, step_config):
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

def _require_path_compiler_identity(step_config):
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

    return local_compiler_identity


def _path_compile_evidence(materialized_source, step_config, local_compiler_identity,
                           program_identity, signature, effect_facts, diagnostics):
    return _recorded_path_compile_evidence(step_config, local_compiler_identity,
        program_identity, signature, effect_facts, diagnostics,
        repository_revision_digest=materialized_source.repository_revision_id.digest,
        verified_git_tree=materialized_source.verified_git_tree.value)




__all__ = [
    "AdmittedPathProgram",
    "PATH_COMPILE_EVIDENCE_SCHEMA",
    "RunRefPathCompileRefusal",
    "compile_and_admit_path_program",
]
