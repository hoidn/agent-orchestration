"""CF-1b Task 3: generic `defproc` type parameters bind through applied unions.

Contract: `docs/design/workflow_lisp_parametric_type_system.md`, section
"Proposed CF-1 First-Order Generic Unions" (invariant binding, constructor
identity, phantom parameters). Instantiating specialized bodies, lowering and
transport are Task 4, so every test here stops at the frontend: stage-3
typecheck on the legacy route without shared validation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow_lisp.build_manifest_io import _json_data
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint, compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from orchestrator.workflow_lisp.type_env import DiscriminantTypeRef

MODULE_ROOT = (Path(__file__).parent / "fixtures" / "workflow_lisp" / "generic_unions" / "modules").resolve()
FRONTEND = {
    "provider_externs": {},
    "prompt_externs": {},
    "command_boundaries": {},
    "validate_shared": False,
    "lowering_route": "legacy",
}

DECISION = """  (defunion Decision :forall (F B)
    (APPROVE (evidence F))
    (REVISE (feedback F))
    (BLOCKED (reason B)))
  (defrecord Subject
    (text String))
  (defrecord MyFeedback
    (note String))
  (defrecord MyBlocker
    (why String))
  (defproc review-hook
    ((subject Subject))
    -> Decision[MyFeedback MyBlocker]
    :effects ()
    (variant Decision[MyFeedback MyBlocker] APPROVE :evidence (record MyFeedback :note subject.text)))"""


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "module.orc"
    path.write_text(f'(workflow-lisp\n  (:language "0.1")\n  (:target-dsl "2.33")\n{body})\n', encoding="utf-8")
    return path


def _line_of(path: Path, needle: str) -> int:
    lines = path.read_text(encoding="utf-8").splitlines()
    return next(index for index, line in enumerate(lines, start=1) if needle in line)


def _declared_at(path: Path, needle: str) -> str:
    return f"{path}:{_line_of(path, needle)}:"


def _compile(path: Path, tmp_path: Path):
    return compile_stage3_module(path, workspace_root=tmp_path, **FRONTEND)


def _compile_entrypoint(path: Path, tmp_path: Path, *source_roots: Path):
    return compile_stage3_entrypoint(
        path,
        source_roots=(*source_roots, MODULE_ROOT),
        workspace_root=tmp_path,
        **FRONTEND,
    )


def _error(compile_call) -> LispFrontendDiagnostic:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_call()
    return excinfo.value.diagnostics[0]


# --- binding through ProcRef signatures -------------------------------------------


def _run_review(decide_return: str) -> str:
    return f"""{DECISION}
  (defproc run-review
    :forall (S F B)
    ((subject S)
     (review ProcRef[(S) -> Decision[F B]]))
    -> Decision[F B]
    :effects ()
    (review subject))
  (defproc decide
    ((subject Subject))
    -> {decide_return}
    :effects ()
    (run-review subject (proc-ref review-hook)))"""


def test_procref_result_binds_generic_union_arguments(tmp_path: Path) -> None:
    result = _compile(_write(tmp_path, _run_review("Decision[MyFeedback MyBlocker]")), tmp_path)

    assert "decide" in result.procedure_catalog.signatures_by_name


def test_procref_result_binds_arguments_by_position(tmp_path: Path) -> None:
    # `F` binds to the first argument and `B` to the second, so the swapped
    # instantiation is not the call's result type.
    path = _write(tmp_path, _run_review("Decision[MyBlocker MyFeedback]"))

    assert _error(lambda: _compile(path, tmp_path)).code == "procedure_return_type_invalid"


def _route(summarize_param: str) -> str:
    """`F B` occur in a ProcRef result and again in another ProcRef's parameter."""

    return f"""{DECISION}
  (defproc summarize-hook
    ((decision {summarize_param}))
    -> Subject
    :effects ()
    (record Subject :text "summary"))
  (defproc route
    :forall (S F B)
    ((subject S)
     (review ProcRef[(S) -> Decision[F B]])
     (summarize ProcRef[(Decision[F B]) -> S]))
    -> S
    :effects ()
    (summarize (review subject)))
  (defproc run
    ((subject Subject))
    -> Subject
    :effects ()
    (route subject
           (proc-ref review-hook)
           (proc-ref summarize-hook)))"""


def test_repeat_bindings_in_procref_parameter_positions_unify(tmp_path: Path) -> None:
    result = _compile(_write(tmp_path, _route("Decision[MyFeedback MyBlocker]")), tmp_path)

    assert "run" in result.procedure_catalog.signatures_by_name


def test_conflicting_repeat_bindings_are_rejected_at_the_argument(tmp_path: Path) -> None:
    path = _write(tmp_path, _route("Decision[MyBlocker MyFeedback]"))

    diagnostic = _error(lambda: _compile(path, tmp_path))

    assert (diagnostic.code, diagnostic.span.start.line) == (
        "parametric_type_binding_ambiguous",
        _line_of(path, "(proc-ref summarize-hook)"),
    )


# --- phantom arguments --------------------------------------------------------------


def _phantom(second_tag: str) -> str:
    """`Tag` occurs in no payload; the two hooks' results differ only in it."""

    return f"""  (defunion Tagged :forall (Tag)
    (VAL (value Int)))
  (defrecord Subject
    (text String))
  (defproc tag-first
    ((subject Subject))
    -> Tagged[Int]
    :effects ()
    (variant Tagged[Int] VAL :value 1))
  (defproc tag-second
    ((subject Subject))
    -> Tagged[{second_tag}]
    :effects ()
    (variant Tagged[{second_tag}] VAL :value 2))
  (defproc both
    :forall (S T)
    ((subject S)
     (first ProcRef[(S) -> Tagged[T]])
     (second ProcRef[(S) -> Tagged[T]]))
    -> Tagged[T]
    :effects ()
    (first subject))
  (defproc run
    ((subject Subject))
    -> Tagged[Int]
    :effects ()
    (both subject
          (proc-ref tag-first)
          (proc-ref tag-second)))"""


def test_phantom_argument_binds_its_parameter(tmp_path: Path) -> None:
    result = _compile(_write(tmp_path, _phantom("Int")), tmp_path)

    assert "run" in result.procedure_catalog.signatures_by_name


def test_phantom_argument_is_part_of_binding_identity(tmp_path: Path) -> None:
    path = _write(tmp_path, _phantom("String"))

    diagnostic = _error(lambda: _compile(path, tmp_path))

    assert (diagnostic.code, diagnostic.span.start.line) == (
        "parametric_type_binding_ambiguous",
        _line_of(path, "(proc-ref tag-second)"),
    )


# --- constructor identity across modules ---------------------------------------------
#
# The `gb` hooks pass their argument through. A specialized helper typechecks a
# pure hook's body in the generic's module, where caller-local type names such
# as `MyFeedback` do not resolve; that is specialization (Task 4), for
# non-generic unions too.


def test_imported_alias_of_the_defining_module_matches(tmp_path: Path) -> None:
    result = _compile_entrypoint(MODULE_ROOT / "gb" / "entry_alias.orc", tmp_path)

    assert "decide" in result.entry_result.procedure_catalog.signatures_by_name


def test_same_short_name_union_from_another_module_is_a_constructor_mismatch(tmp_path: Path) -> None:
    path = MODULE_ROOT / "gb" / "entry_shadow.orc"

    diagnostic = _error(lambda: _compile_entrypoint(path, tmp_path))

    assert (diagnostic.code, diagnostic.span.start.line) == ("type_mismatch", _line_of(path, "(proc-ref review-hook)"))


def test_constructor_mismatch_notes_both_declarations(tmp_path: Path) -> None:
    path = MODULE_ROOT / "gb" / "entry_shadow.orc"
    declarations = (
        _declared_at(MODULE_ROOT / "gb" / "lib.orc", "(defunion Decision"),
        _declared_at(path, "(defunion Decision"),
    )

    diagnostic = _error(lambda: _compile_entrypoint(path, tmp_path))

    assert [any(location in note for note in diagnostic.notes) for location in declarations] == [True, True]


# --- discriminants of applied unions -------------------------------------------------


def _tags_module(tmp_path: Path, left: str, right: str) -> Path:
    """`gu/lib::Outcome`, a local same-short-name `Outcome`, and two `Item`s."""

    path = tmp_path / "t3" / "tags.orc"
    path.parent.mkdir()
    path.write_text(
        f"""(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule t3/tags)
  (import gu/lib :as lib)
  (import cx/a :only (Item))
  (import cx/b :as b)
  (export same-tag)
  (defunion Outcome :forall (T E)
    (OK (value T))
    (ERROR (error E)))
  (defrecord Flag
    (same Bool))
  (defproc same-tag
    ((left {left})
     (right {right}))
    -> Flag
    :effects ()
    (record Flag :same (= left.variant right.variant))))
""",
        encoding="utf-8",
    )
    return path


def test_discriminants_of_one_imported_applied_union_are_comparable(tmp_path: Path) -> None:
    path = _tags_module(tmp_path, "lib.Outcome[Item Int]", "lib.Outcome[Item Int]")

    result = _compile_entrypoint(path, tmp_path, tmp_path)

    assert "t3/tags::same-tag" in result.entry_result.procedure_catalog.signatures_by_name


@pytest.mark.parametrize(
    ("left", "right"),
    [
        pytest.param("lib.Outcome[Item Int]", "lib.Outcome[b.Item Int]", id="same-short-name-arguments"),
        pytest.param("Outcome[Int Int]", "lib.Outcome[Int Int]", id="same-short-name-declarations"),
    ],
)
def test_discriminants_from_different_modules_are_not_comparable(tmp_path: Path, left: str, right: str) -> None:
    path = _tags_module(tmp_path, left, right)

    diagnostic = _error(lambda: _compile_entrypoint(path, tmp_path, tmp_path))

    assert (diagnostic.code, diagnostic.span.start.line) == (
        "variant_tag_union_mismatch",
        _line_of(path, "(= left.variant right.variant)"),
    )


def test_non_applied_discriminant_keeps_its_identity_encoding() -> None:
    """`repr` feeds specialization and checkpoint digests; build JSON serializes fields."""

    discriminant = DiscriminantTypeRef(union_name="Plain", variant_names=("ONLY",))

    assert (repr(discriminant), _json_data(discriminant)) == (
        "DiscriminantTypeRef(union_name='Plain', variant_names=('ONLY',))",
        {"union_name": "Plain", "variant_names": ["ONLY"]},
    )
