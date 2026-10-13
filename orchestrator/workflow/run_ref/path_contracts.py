"""Source-free path-child signatures, refusals and recorded compilation facts."""

from __future__ import annotations

import json
from typing import Mapping

from orchestrator.contracts.closed_program.program import ClosedProgram
from orchestrator.contracts.closed_program.targets import (
    target_dsl_supports_nested_structural_transport,
    target_dsl_uses_evaluated_execution,
)
from orchestrator.workflow.evaluated.machine import site_classes

from .config import PathProgram, RunRefInput
from .contracts import canonical_json_bytes, canonical_sha256
from .result_contract import is_transportable_type_descriptor


PATH_COMPILE_EVIDENCE_SCHEMA = "run_ref_path_compile_evidence.v1"
_VALUE_DESCRIPTOR = {"kind": "primitive", "name": "Value"}


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


def _signature_mismatch_causes(
    signature: Mapping[str, object],
    configured_inputs: tuple[RunRefInput, ...],
    program: PathProgram,
    *,
    target_dsl_version: str = "2.24",
) -> tuple[str, ...]:
    allow_nested_structures = target_dsl_supports_nested_structural_transport(
        target_dsl_version
    )
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


def _recorded_path_compile_evidence(step_config, local_compiler_identity,
                                  program_identity, signature, effect_facts, diagnostics,
                                  *, repository_revision_digest, verified_git_tree):
    program = step_config.run_ref.program
    input_facts = signature["inputs"]
    return_fact = signature["return"]
    evidence_components = {
        "schema_version": PATH_COMPILE_EVIDENCE_SCHEMA,
        "repository_revision_digest": repository_revision_digest,
        "verified_git_tree": verified_git_tree,
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
    return evidence


def closed_program_signature(program):
    defaults = program.tree.get("defaults", {})
    return {"inputs": [{"name": name, "required": name not in defaults, "type": descriptor}
                       for name, descriptor in program.tree["params"]],
            "return": program.tree["result"]}


def _require_closed_signature(program, step_config):
    signature = closed_program_signature(program)
    causes = _signature_mismatch_causes(signature, step_config.run_ref.inputs,
                                       step_config.run_ref.program,
                                       target_dsl_version=program.tree["target"])
    if causes:
        raise _refuse("trial_program_signature_mismatch",
                      {"program": step_config.run_ref.program.record, "signature": signature,
                       "provided_inputs": [{"name": row.name, "type": row.type_descriptor}
                                           for row in step_config.run_ref.inputs]},
                      secondary_causes=causes)
    return signature


def _closed_identity(program, compiler_identity):
    components = {"schema_version": "run_ref_closed_program_identity.v1",
                  "compiler_runtime_identity": compiler_identity, "program_digest": program.digest}
    return {**components, "digest": canonical_sha256(components)}


def validate_closed_path_facts(facts, *, program, materialized_source, step_config):
    """Project live preparation authority to the same recorded facts validator."""
    return validate_recorded_closed_path_facts(facts, program=program, step_config=step_config,
        repository_revision_digest=materialized_source.repository_revision_id.digest,
        verified_git_tree=materialized_source.verified_git_tree.value)


def validate_recorded_closed_path_facts(facts, *, program, step_config,
                                        repository_revision_digest, verified_git_tree):
    """Validate exact v2 facts against checked artifact and recorded static authority."""
    from .wire import _validate_compile_diagnostic_row

    try:
        if type(program) is not ClosedProgram or not target_dsl_uses_evaluated_execution(program.tree["target"]):
            raise ValueError("closed artifact required")
        if not isinstance(facts, dict) or set(facts) != {"diagnostics", "program_identity", "signature", "effect_facts", "evidence"}:
            raise ValueError("closed path facts shape is invalid")
        diagnostics = facts["diagnostics"]
        if not isinstance(diagnostics, list):
            raise ValueError("closed diagnostics must be rows")
        for row in diagnostics:
            _validate_compile_diagnostic_row(row)
        signature = _require_closed_signature(program, step_config)
        effects = {"direct": [], "transitive": []}
        if site_classes(program):
            raise ValueError("closed child effects are not empty")
        compiler = step_config.run_ref.compiler_runtime_identity_digest
        identity = _closed_identity(program, compiler)
        evidence = _recorded_path_compile_evidence(step_config, compiler, identity, signature, effects, diagnostics,
            repository_revision_digest=repository_revision_digest, verified_git_tree=verified_git_tree)
        expected = {"diagnostics": diagnostics, "program_identity": identity, "signature": signature,
                    "effect_facts": effects, "evidence": evidence}
        if canonical_json_bytes(facts) != canonical_json_bytes(expected):
            raise ValueError("closed path facts disagree with checked authority")
    except (KeyError, TypeError, ValueError) as exc:
        raise _refuse("trial_program_compile_rejected", {"path_compile": facts},
                      secondary_causes=("closed_path_facts_invalid",)) from exc
