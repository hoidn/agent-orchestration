"""Target selection and availability checks for evaluated execution."""

from __future__ import annotations

from pathlib import Path

from orchestrator._common.safe_tree import resolve_path_preserving_fd
from orchestrator.workflow_lisp import syntax
from orchestrator.workflow_lisp.diagnostics import (
    LispFrontendCompileError,
    LispFrontendDiagnostic,
)
from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.sexpr import KeywordAtom, ListExpr, StringAtom
from orchestrator.workflow_lisp.spans import SourceSpan


def _entry_target_header(path: Path) -> tuple[str, SourceSpan]:
    path = resolve_path_preserving_fd(path)
    parse_tree = read_sexpr_file(path)
    syntax_module = syntax.build_syntax_module(parse_tree)
    root = parse_tree.items[0]
    assert isinstance(root, ListExpr)
    for form in root.items[1:]:
        if (
            isinstance(form, ListExpr)
            and len(form.items) == 2
            and isinstance(form.items[0], KeywordAtom)
            and form.items[0].value == ":target-dsl"
            and isinstance(form.items[1], StringAtom)
        ):
            return syntax_module.target_dsl_version, form.items[1].span
    raise AssertionError("validated module is missing its :target-dsl header")


def entry_target_dsl_version(path: Path) -> str:
    """Return the target declared by one entry module without resolving imports."""

    target_dsl_version, _span = _entry_target_header(path)
    return target_dsl_version


def refuse_run_at_evaluated_execution_target(path: Path) -> None:
    """Refuse run/resume until evaluated execution can dispatch the closed program."""

    target_dsl_version, target_span = _entry_target_header(path)
    if not syntax.target_dsl_uses_evaluated_execution(target_dsl_version):
        return
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code="evaluated_execution_unavailable",
                message=(
                    f"target DSL {target_dsl_version} requires evaluated execution "
                    f"from DSL {syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION}; "
                    "run and resume are unavailable until Phase 3"
                ),
                span=target_span,
                phase="lowering",
            ),
        )
    )
