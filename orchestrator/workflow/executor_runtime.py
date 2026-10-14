"""Shared provider-prompt step input type."""

from typing import Any, Dict
from .runtime_step import RuntimeStep

RuntimeStepInput = Dict[str, Any] | RuntimeStep
