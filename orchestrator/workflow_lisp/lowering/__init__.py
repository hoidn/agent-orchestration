"""Compatibility facade for Workflow Lisp lowering."""

from . import core as _core
from ..procedure_specialization import specialize_typed_procedure as _specialize_typed_procedure
from .procedures import (
    _lower_procedure_call_expr,
    _private_workflow_from_procedure,
    _procedure_provenance_notes,
    _resolve_procedure_lowering,
)
from .origins import (
    _missing_validation_subject_message,
    _origin_for_validation_subject_refs,
    _remap_validation_message,
    _shared_validation_diagnostic_code,
)


for _name in dir(_core):
    if _name.startswith("__"):
        continue
    globals()[_name] = getattr(_core, _name)
