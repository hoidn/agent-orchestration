"""CF-1b Task 4: generic unions instantiated through specialization, end to end.

Contract: docs/design/workflow_lisp_parametric_type_system.md, "Proposed CF-1
First-Order Generic Unions"; transport obligations in
docs/design/workflow_lisp_composition_first.md sections 4, 9 and 10.

Hooks are command-backed probes (the supported deterministic route); every
probe appends its argv to a call log so tests can assert provider-free replay.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.workflow_evaluated_totality_helpers import _write_sources
from tests.workflow_lisp_generic_union_runtime_sources import MAKE_LIB, PROC_REF_PAYLOAD_ENTRY


from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.workflows import ExternalToolBinding




def _compile(root: Path, *, probes: dict[str, Path] | None = None, validate_shared: bool = True):
    return compile_stage3_entrypoint(
        root / "grt" / "entry.orc",
        source_roots=(root,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={
            name: ExternalToolBinding(name=name, stable_command=("python", path.as_posix()))
            for name, path in (probes or {}).items()
        },
        validate_shared=validate_shared,
        workspace_root=root,
        lowering_route=None,
    )




































APPROVED_OUTPUTS = {
    "return__variant": "APPROVED",
    "return__value__title": "revised-seed",
    "return__value__score": 1,
    "return__evidence__note": "ok-revised-seed",
}










def test_procref_bound_into_an_applied_payload_is_rejected_at_the_call(tmp_path: Path) -> None:
    """Addendum B: the substituted `Outcome[ProcRef[...] String]` is rejected at the caller."""
    _write_sources(tmp_path, {"grt/lib.orc": MAKE_LIB, "grt/entry.orc": PROC_REF_PAYLOAD_ENTRY})


    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(tmp_path)

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "proc_ref_runtime_transport_forbidden"
    assert (Path(diagnostic.span.start.path).name, diagnostic.span.start.line) == ("entry.orc", 13)
    assert any(f"{tmp_path / 'grt' / 'lib.orc'}:6:" in note for note in diagnostic.notes)
