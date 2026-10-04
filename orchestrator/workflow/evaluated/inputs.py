"""In-memory preparation of checked command documents at the reached boundary."""

from __future__ import annotations

import json

from orchestrator.contracts.output_contract import ContractViolation, _validate_direct_transport_value
from orchestrator.workflow.type_descriptor import _escape_pointer_token, transport_schema_for_descriptor

from .commands import command_document_operands
from .values import _thaw


class DocumentInputError(ValueError):
    """A checked field failed its direct-value contract before command start."""

    def __init__(self, field, error):
        self.code = "effect_input_invalid"
        self.field = field
        relative = getattr(error, "value_path", None) or "$"
        self.value_path = "/" + _escape_pointer_token(field) + relative[1:]
        self.violation = getattr(error, "violation", None) or ContractViolation(
            "invalid_transportable_value", str(error), {"value_path": relative, "error": str(error)})
        self.violations = [{**self.violation.to_dict(), "field": field, "value_path": self.value_path}]
        super().__init__(f"{self.value_path}: {self.violation.type}: {error}")


def command_binding_kind(program, owner, boundary):
    configuration = program.tree["configuration"]
    definition = program.tree["definitions"].get(owner, {})
    selected = definition.get("configuration")
    if selected is not None:
        configuration = configuration["imports"][selected]
    return configuration["commands"][boundary]["kind"]


def prepare_command_document(node, operands, *, external, workspace, workspace_files):
    """Validate the checked lanes once; return canonical bytes and ordered types."""
    if "document" not in node:
        return None, []
    payload = {}
    contract = []
    for (field, _expression), value in zip(node["document"], command_document_operands(node, operands), strict=True):
        try:
            schema = transport_schema_for_descriptor(value.descriptor, allow_nested_structures=True)
            payload[field] = _validate_direct_transport_value(value.json_value(), schema, workspace,
                workspace_files=workspace_files)
        except (RecursionError, TypeError, ValueError) as exc:
            raise DocumentInputError(field, exc) from exc
        contract.append([field, _thaw(value.descriptor)])
    return json.dumps(payload, ensure_ascii=False, sort_keys=external,
        separators=(",", ":"), allow_nan=False).encode("utf-8"), contract
