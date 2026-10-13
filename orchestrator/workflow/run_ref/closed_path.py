"""Ordinary full compilation and E1 admission for a checked path child."""

from dataclasses import dataclass
import json

from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed import artifact
from orchestrator.workflow_lisp.closed.artifact import ClosedProgramBuildResult
from orchestrator.workflow_lisp.closed.target import entry_target_dsl_version
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError, serialize_diagnostics
from orchestrator.workflow_lisp.reader import SourceReadTrace
from orchestrator.workflow_lisp.syntax import target_dsl_uses_evaluated_execution

from .contracts import canonical_json_bytes
from .path_contracts import (
    _closed_identity,
    _require_closed_signature,
    _refuse,
)
from .path_compile import (
    _compile_refusal, _effect_summary_facts, _path_compile_evidence,
    _require_program_file, _validate_path_compile_authority,
)


@dataclass(frozen=True)
class AdmittedClosedPathProgram:
    build_result: ClosedProgramBuildResult
    workflow_checksum: str
    _facts_json: bytes

    @property
    def path_compile(self):
        return json.loads(self._facts_json)


def _require_closed_effects(built, step_config):
    try:
        summary = _effect_summary_facts(built.entry_effect_summary)
    except (TypeError, ValueError) as exc:
        raise _refuse("trial_candidate_environment_not_admissible", {"entry": built.program.tree["entry"]},
                      secondary_causes=("effect_summary_invalid",)) from exc
    facts = {"direct": summary["direct"], "transitive": summary["transitive"]}
    if facts["direct"] or facts["transitive"] or site_classes(built.program):
        raise _refuse("trial_candidate_environment_not_admissible",
                      {"environment": step_config.run_ref.program.environment, "effect_facts": facts},
                      secondary_causes=("closed_child_effects_not_empty",))
    return facts


def _closed_diagnostics(built):
    from .wire import _validate_compile_diagnostic_row

    if not isinstance(built.compile_diagnostics, tuple):
        raise _refuse("trial_program_compile_rejected", {"entry": built.program.tree["entry"]},
                      secondary_causes=("compile_diagnostics_missing",))
    diagnostics = serialize_diagnostics(built.compile_diagnostics)
    for row in diagnostics:
        _validate_compile_diagnostic_row(row)
    return diagnostics


def compile_closed_path_if_evaluated(*, materialized_source, step_config):
    """Prepare once through the ordinary builder, or retain the legacy branch."""
    program, compiler_identity = _validate_path_compile_authority(materialized_source, step_config)
    source = _require_program_file(materialized_source.workspace_path, program)
    trace = SourceReadTrace()
    try:
        if not target_dsl_uses_evaluated_execution(entry_target_dsl_version(source, source_read_trace=trace)):
            return None
        request = FrontendBuildRequest(source_path=source, source_roots=(materialized_source.workspace_path,),
            entry_workflow=program.entry_name, workspace_root=materialized_source.workspace_path)
        built = artifact.prepare_closed_program_bundle(request, source_read_trace=trace)
    except LispFrontendCompileError as exc:
        raise _compile_refusal(exc, program) from exc
    signature = _require_closed_signature(built.program, step_config)
    effects = _require_closed_effects(built, step_config)
    diagnostics = _closed_diagnostics(built)
    identity = _closed_identity(built.program, compiler_identity)
    evidence = _path_compile_evidence(materialized_source, step_config, compiler_identity,
                                     identity, signature, effects, diagnostics)
    facts = {"diagnostics": diagnostics, "program_identity": identity, "signature": signature,
             "effect_facts": effects, "evidence": evidence}
    from hashlib import sha256

    checksum = "sha256:" + sha256(trace.raw_bytes_by_path[source]).hexdigest()
    return AdmittedClosedPathProgram(built, checksum, canonical_json_bytes(facts))
