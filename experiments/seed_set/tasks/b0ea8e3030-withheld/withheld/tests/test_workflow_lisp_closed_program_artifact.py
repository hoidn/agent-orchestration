from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json

import pytest

from orchestrator.workflow_lisp.closed.program import (
    ClosedProgram,
    ClosedProgramInvalid,
    canonical_configuration,
    canonical_digest,
    logical_asset_base_for_module,
    program_digest,
    strip_provenance,
)
from orchestrator.workflow_lisp.closed.check import validate
from tests.test_workflow_lisp_closed_program_check import (
    BOOL,
    INT,
    _command_result_tree,
    _effectful_call_tree,
    _halt,
    _lit,
    _name,
    _tree,
)
from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding
from orchestrator.workflow_lisp.workflows import PromptExtern, ProviderExtern


VALUE = {"kind": "primitive", "name": "Value"}
STRING = {"kind": "primitive", "name": "String"}


def _closed(tree: dict) -> ClosedProgram:
    return ClosedProgram(
        tree=tree,
        sites=tuple(tuple(row) for row in tree["sites"]),
        digest=program_digest(tree),
    )




















