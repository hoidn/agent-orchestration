"""Compatibility shim for split phase/resource lowering owners."""

from .phase_flow import _lower_produce_one_of, _lower_resume_or_start, _lower_run_provider_phase
from .phase_resource import _lower_finalize_selected_item, _lower_resource_transition
from .phase_scope import _lower_with_phase
