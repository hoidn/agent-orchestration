"""CF-1b Task 2: generic union declarations and type applications (target 2.33).

Contract: `docs/design/workflow_lisp_parametric_type_system.md`, section
"Proposed CF-1 First-Order Generic Unions". Binding of generic `defproc` type
parameters through applied unions and specialization are later tasks.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import (
    compile_stage1_module,
    compile_stage3_entrypoint,
    compile_stage3_module,
)
from orchestrator.workflow_lisp.definitions import UnionDef
from orchestrator.workflow_lisp.diagnostics import (
    LispFrontendCompileError,
    LispFrontendDiagnostic,
)

FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp" / "generic_unions"
MODULE_ROOT = FIXTURES / "modules"

OUTCOME = """  (defunion Outcome :forall (T E)
    (OK (value T))
    (ERROR (error E)))"""


def _write(tmp_path: Path, body: str, *, target: str = "2.33") -> Path:
    path = tmp_path / "module.orc"
    path.write_text(
        f'(workflow-lisp\n  (:language "0.1")\n  (:target-dsl "{target}")\n{body})\n',
        encoding="utf-8",
    )
    return path


def _options(tmp_path: Path, *, frontend: bool) -> dict[str, object]:
    """`frontend=True` typechecks on the legacy route without shared validation."""

    return {
        "provider_externs": {},
        "prompt_externs": {},
        "command_boundaries": {},
        "validate_shared": not frontend,
        "workspace_root": tmp_path,
        "lowering_route": "legacy" if frontend else None,
    }


def _compile(path: Path, tmp_path: Path, *, frontend: bool = False):
    return compile_stage3_module(path, **_options(tmp_path, frontend=frontend))


def _compile_entrypoint(path: Path, tmp_path: Path, *, source_root: Path = MODULE_ROOT, frontend: bool = False):
    return compile_stage3_entrypoint(path, source_roots=(source_root,), **_options(tmp_path, frontend=frontend))


def _first_diagnostic(excinfo: pytest.ExceptionInfo[LispFrontendCompileError]) -> LispFrontendDiagnostic:
    return excinfo.value.diagnostics[0]


def _line_of(path: Path, needle: str) -> int:
    lines = path.read_text(encoding="utf-8").splitlines()
    return next(index for index, line in enumerate(lines, start=1) if needle in line)


def _frontend_error(tmp_path: Path, body: str, *, target: str = "2.33") -> LispFrontendDiagnostic:
    path = _write(tmp_path, body, target=target)
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(path, tmp_path, frontend=True)
    return _first_diagnostic(excinfo)


def _param_probe(type_text: str) -> str:
    """A procedure that uses `type_text` only as a parameter type."""

    return f"""  (defproc probe
    ((value {type_text}))
    -> Int
    :effects ()
    1)"""


def _identity_proc(type_text: str) -> str:
    return f"""  (defproc keep
    ((value {type_text}))
    -> {type_text}
    :effects ()
    value)"""


# --- declaration and admitted positions -------------------------------------






def _describe_through_procref(describe_param_type: str) -> str:
    """`describe` is passed where `ProcRef[(Outcome[Int String]) -> Summary]` is expected."""

    return f"""{OUTCOME}
  (defrecord Summary
    (label String))
  (defproc describe
    ((outcome {describe_param_type}))
    -> Summary
    :effects ()
    (record Summary :label "described"))
  (defproc apply-describe
    ((describer ProcRef[(Outcome[Int String]) -> Summary])
     (outcome Outcome[Int String]))
    -> Summary
    :effects ()
    (describer outcome))
  (defproc describe-ok
    ((n Int))
    -> Summary
    :effects ()
    (apply-describe (proc-ref describe) (variant Outcome[Int String] OK :value n)))"""






# --- instantiated field types and applied identity ---------------------------














NESTED = f"""{OUTCOME}
  (defunion Wrapped :forall (V)
    (WRAP (inner Outcome[V String])))"""






# --- rejections ----------------------------------------------------------------


REJECTIONS = [
    pytest.param(
        f"{OUTCOME}\n{_param_probe('Outcome[Int]')}",
        "generic_union_arity_mismatch",
        "((value Outcome[Int]))",
        "(defunion Outcome",
        id="too-few-arguments",
    ),
    pytest.param(
        f"{OUTCOME}\n{_param_probe('Outcome[Int String Bool]')}",
        "generic_union_arity_mismatch",
        "((value Outcome[Int String Bool]))",
        "(defunion Outcome",
        id="too-many-arguments",
    ),
    pytest.param(
        f"{OUTCOME}\n{_param_probe('Outcome')}",
        "generic_union_arity_mismatch",
        "((value Outcome))",
        "(defunion Outcome",
        id="unapplied-generic-union",
    ),
    pytest.param(
        f"{OUTCOME}\n{_param_probe('Outcome[T String]')}",
        "generic_union_unresolved_argument",
        "((value Outcome[T String]))",
        "(defunion Outcome",
        id="unresolved-parameter-in-concrete-position",
    ),
    pytest.param(
        f"{OUTCOME}\n  (defrecord Holder\n    (outcome Outcome[T String]))",
        "generic_union_unresolved_argument",
        "(outcome Outcome[T String])",
        "(defunion Outcome",
        id="unresolved-parameter-in-record-field",
    ),
    pytest.param(
        "  (defunion Plain\n    (ONLY (value Int)))\n" + _param_probe("Plain[Int]"),
        "generic_union_not_generic",
        "((value Plain[Int]))",
        "(defunion Plain",
        id="non-generic-union",
    ),
    pytest.param(
        "  (defrecord Box\n    (value Int))\n" + _param_probe("Box[Int]"),
        "generic_union_not_generic",
        "((value Box[Int]))",
        "(defrecord Box",
        id="record",
    ),
    pytest.param(
        "  (defunion Chain :forall (T)\n    (MORE (next Chain[T]))\n    (DONE (value T)))",
        "generic_union_instantiation_cycle",
        "(MORE (next Chain[T]))",
        "(defunion Chain",
        id="self-application",
    ),
    pytest.param(
        "  (defunion Ping :forall (T)\n    (PING (pong Pong[T])))\n"
        "  (defunion Pong :forall (T)\n    (PONG (ping Ping[T])))",
        "generic_union_instantiation_cycle",
        "(PONG (ping Ping[T]))",
        "(defunion Ping",
        id="mutual-application",
    ),
]






# --- target gate ----------------------------------------------------------------


PLAIN = """  (defunion Plain
    (ONLY (value Int)))"""






# --- module identity --------------------------------------------------------------






# `gu/narrow` applies local generic unions to an imported record, so the applied
# names render module-qualified arguments (`Alpha[gu/lib::Item]`).


def test_narrowed_variant_is_compatible_with_its_applied_union(tmp_path: Path) -> None:
    result = _compile_entrypoint(MODULE_ROOT / "gu" / "narrow.orc", tmp_path, frontend=True)

    assert "gu/narrow::narrow" in result.entry_result.procedure_catalog.signatures_by_name


