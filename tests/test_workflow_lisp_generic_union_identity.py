"""CF-1b Task 2: applied generic unions keep their arguments in type identity.

Specialization names (`parametric_specialization_name`) and checkpoint schema
digests are built from `repr(type_ref)`. An applied union's arguments must
therefore appear in its `repr` (phantom arguments included), while
non-generic types keep the repr the dataclass generates, so existing
identities do not move. Contract: `docs/design/workflow_lisp_parametric_type_system.md`,
"Proposed CF-1 First-Order Generic Unions".
"""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path

from orchestrator.workflow_lisp.compiler import compile_stage1_module, compile_stage3_entrypoint
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment

MODULE_ROOT = (Path(__file__).parent / "fixtures" / "workflow_lisp" / "generic_unions" / "modules").resolve()
SPAN = SourceSpan(
    start=SourcePosition(path="identity.orc", line=1, column=1, offset=0),
    end=SourcePosition(path="identity.orc", line=1, column=1, offset=0),
)
FORM_PATH = ("workflow-lisp", "identity")
APPLIED_ONLY_FIELDS = frozenset({"type_args", "union_type_args"})


def _type_env(tmp_path: Path) -> FrontendTypeEnvironment:
    path = tmp_path / "identity.orc"
    path.write_text(
        """(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defunion Plain
    (ONLY (value Int)))
  (defunion Outcome :forall (T E)
    (OK (value T))
    (ERROR (error E))))
""",
        encoding="utf-8",
    )
    return FrontendTypeEnvironment.from_module(compile_stage1_module(path))


def _generated_repr(value: object) -> str:
    """The repr the dataclass generates for the fields that predate generic unions."""

    shown = ", ".join(
        f"{field.name}={getattr(value, field.name)!r}"
        for field in fields(value)
        if field.name not in APPLIED_ONLY_FIELDS
    )
    return f"{type(value).__qualname__}({shown})"


def test_phantom_arguments_from_different_modules_get_distinct_specializations(tmp_path: Path) -> None:
    # `cx/a` and `cx/b` each return `Tagged[Item]` for their own `Item`; the
    # phantom argument is the only difference between the two applied types.
    result = compile_stage3_entrypoint(
        MODULE_ROOT / "cx" / "entry.orc",
        source_roots=(MODULE_ROOT,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route="legacy",
    )
    specializations = {
        name
        for name in result.entry_result.procedure_catalog.signatures_by_name
        if name.startswith("%parametric-call.cx.lib.keep.")
    }

    assert len(specializations) == 2


def test_non_generic_union_types_keep_the_generated_repr(tmp_path: Path) -> None:
    type_env = _type_env(tmp_path)
    plain = type_env.resolve_type("Plain", span=SPAN, form_path=FORM_PATH)
    variant = type_env.union_variant(plain, "ONLY", span=SPAN, form_path=FORM_PATH)

    assert (repr(plain), repr(variant)) == (_generated_repr(plain), _generated_repr(variant))


def test_different_arguments_give_different_reprs(tmp_path: Path) -> None:
    type_env = _type_env(tmp_path)

    assert repr(type_env.resolve_type("Outcome[Int String]", span=SPAN, form_path=FORM_PATH)) != repr(
        type_env.resolve_type("Outcome[String Int]", span=SPAN, form_path=FORM_PATH)
    )
