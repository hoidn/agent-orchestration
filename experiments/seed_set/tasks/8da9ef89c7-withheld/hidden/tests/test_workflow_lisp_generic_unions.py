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


def test_generic_union_declaration_keeps_its_type_parameters(tmp_path: Path) -> None:
    module = compile_stage1_module(_write(tmp_path, OUTCOME))

    outcome = next(
        definition
        for definition in module.definitions
        if isinstance(definition, UnionDef) and definition.name == "Outcome"
    )

    assert outcome.type_params == ("T", "E")


def test_concrete_applications_compile_through_shared_validation(tmp_path: Path) -> None:
    result = _compile(FIXTURES / "concrete_outcome.orc", tmp_path)

    assert result.validated_bundles["entry"].surface.version == "2.33"


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


def test_procref_parameter_position_accepts_matching_instantiation(tmp_path: Path) -> None:
    path = _write(tmp_path, _describe_through_procref("Outcome[Int String]"))

    result = _compile(path, tmp_path, frontend=True)

    assert "describe-ok" in result.procedure_catalog.signatures_by_name


def test_union_type_parameters_are_scoped_to_their_declaration(tmp_path: Path) -> None:
    diagnostic = _frontend_error(tmp_path, f"{OUTCOME}\n{_identity_proc('T')}")

    assert diagnostic.code == "type_unknown"


# --- instantiated field types and applied identity ---------------------------


def test_constructor_checks_fields_against_the_instantiation(tmp_path: Path) -> None:
    diagnostic = _frontend_error(
        tmp_path,
        f"""{OUTCOME}
  (defproc make-bad
    ()
    -> Outcome[Int String]
    :effects ()
    (variant Outcome[Int String] OK :value "not-an-int"))""",
    )

    assert diagnostic.code == "type_mismatch"


def test_match_projects_instantiated_field_types(tmp_path: Path) -> None:
    diagnostic = _frontend_error(
        tmp_path,
        f"""{OUTCOME}
  (defproc error-text
    ((outcome Outcome[String Int]))
    -> String
    :effects ()
    (match outcome
      ((OK ok) ok.value)
      ((ERROR err) err.error)))""",
    )

    assert diagnostic.code == "type_mismatch"


def test_different_arguments_are_different_applied_types(tmp_path: Path) -> None:
    diagnostic = _frontend_error(
        tmp_path,
        f"""{OUTCOME}
{_identity_proc('Outcome[Int String]')}
  (defproc relay
    ((value Outcome[String String]))
    -> Outcome[Int String]
    :effects ()
    (keep value))""",
    )

    assert diagnostic.code == "type_mismatch"


def test_phantom_arguments_keep_applied_identities_distinct(tmp_path: Path) -> None:
    diagnostic = _frontend_error(
        tmp_path,
        f"""  (defunion Tagged :forall (Tag)
    (MARK (label String)))
{_identity_proc('Tagged[Int]')}
  (defproc relay
    ((value Tagged[String]))
    -> Tagged[Int]
    :effects ()
    (keep value))""",
    )

    assert diagnostic.code == "type_mismatch"


def test_procref_result_position_rejects_other_instantiation(tmp_path: Path) -> None:
    diagnostic = _frontend_error(
        tmp_path,
        f"""{OUTCOME}
  (defproc make-text
    ((n Int))
    -> Outcome[String String]
    :effects ()
    (variant Outcome[String String] ERROR :error "no"))
  (defproc run-check
    ((check ProcRef[(Int) -> Outcome[Int String]])
     (n Int))
    -> Outcome[Int String]
    :effects ()
    (check n))
  (defproc run-text
    ((n Int))
    -> Outcome[Int String]
    :effects ()
    (run-check (proc-ref make-text) n))""",
    )

    assert diagnostic.code == "proc_ref_signature_invalid"


def test_procref_parameter_position_rejects_other_instantiation(tmp_path: Path) -> None:
    diagnostic = _frontend_error(tmp_path, _describe_through_procref("Outcome[String String]"))

    assert diagnostic.code == "proc_ref_signature_invalid"


NESTED = f"""{OUTCOME}
  (defunion Wrapped :forall (V)
    (WRAP (inner Outcome[V String])))"""


def test_nested_application_substitutes_outer_arguments(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        f"""{NESTED}
  (defproc wrap-ok
    ((n Int))
    -> Wrapped[Int]
    :effects ()
    (variant Wrapped[Int] WRAP :inner (variant Outcome[Int String] OK :value n)))""",
    )

    result = _compile(path, tmp_path, frontend=True)

    assert "wrap-ok" in result.procedure_catalog.signatures_by_name


def test_nested_application_rejects_inner_instantiation_mismatch(tmp_path: Path) -> None:
    diagnostic = _frontend_error(
        tmp_path,
        f"""{NESTED}
  (defproc wrap-text
    ()
    -> Wrapped[Int]
    :effects ()
    (variant Wrapped[Int] WRAP :inner (variant Outcome[String String] OK :value "x")))""",
    )

    assert diagnostic.code == "type_mismatch"


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


@pytest.mark.parametrize(("body", "code", "use_needle", "declaration_needle"), REJECTIONS)
def test_invalid_generic_union_uses_are_rejected(
    tmp_path: Path, body: str, code: str, use_needle: str, declaration_needle: str
) -> None:
    assert _frontend_error(tmp_path, body).code == code


@pytest.mark.parametrize(("body", "code", "use_needle", "declaration_needle"), REJECTIONS)
def test_rejections_locate_the_use_site_and_the_declaration(
    tmp_path: Path, body: str, code: str, use_needle: str, declaration_needle: str
) -> None:
    diagnostic = _frontend_error(tmp_path, body)
    path = tmp_path / "module.orc"
    declaration_location = f"{path}:{_line_of(path, declaration_needle)}:"

    assert (diagnostic.span.start.line, any(declaration_location in note for note in diagnostic.notes)) == (
        _line_of(path, use_needle),
        True,
    )


# --- target gate ----------------------------------------------------------------


PLAIN = """  (defunion Plain
    (ONLY (value Int)))"""


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(f"{OUTCOME}\n{_identity_proc('Outcome[Int String]')}", id="generic-declaration"),
        pytest.param(f"{PLAIN}\n{_identity_proc('Plain[Int]')}", id="application-in-signature"),
        pytest.param(
            f"""{PLAIN}
  (defproc make
    ()
    -> Plain
    :effects ()
    (variant Plain[Int] ONLY :value 1))""",
            id="application-in-constructor",
        ),
        pytest.param(
            f"""{PLAIN}
  (defrecord Holder
    (plain Plain[Int]))""",
            id="application-in-record-field",
        ),
    ],
)
def test_generic_union_syntax_requires_target_233(tmp_path: Path, body: str) -> None:
    assert _frontend_error(tmp_path, body, target="2.32").code == "generic_union_requires_dsl_2_33"


def test_application_in_record_field_is_rejected_by_definition_only_compile_at_232(tmp_path: Path) -> None:
    path = _write(tmp_path, f"{PLAIN}\n  (defrecord Holder\n    (plain Plain[Int]))", target="2.32")

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage1_module(path)

    assert _first_diagnostic(excinfo).code == "generic_union_requires_dsl_2_33"


# --- module identity --------------------------------------------------------------


@pytest.mark.parametrize("entry", ["entry_only.orc", "entry_alias.orc"], ids=["only-import", "alias-import"])
def test_imported_generic_union_resolves_to_its_defining_declaration(tmp_path: Path, entry: str) -> None:
    result = _compile_entrypoint(MODULE_ROOT / "gu" / entry, tmp_path)

    assert result.entry_result.validated_bundles


def test_same_short_name_declaration_from_another_module_is_distinct(tmp_path: Path) -> None:
    path = MODULE_ROOT / "gu" / "entry_shadow.orc"

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_entrypoint(path, tmp_path)
    diagnostic = _first_diagnostic(excinfo)

    assert (diagnostic.code, diagnostic.span.start.line) == (
        "type_mismatch",
        _line_of(path, "(relay (lib-ok n))"),
    )


# `gu/narrow` applies local generic unions to an imported record, so the applied
# names render module-qualified arguments (`Alpha[gu/lib::Item]`).


def test_narrowed_variant_is_compatible_with_its_applied_union(tmp_path: Path) -> None:
    result = _compile_entrypoint(MODULE_ROOT / "gu" / "narrow.orc", tmp_path, frontend=True)

    assert "gu/narrow::narrow" in result.entry_result.procedure_catalog.signatures_by_name


def test_narrowed_variant_is_not_compatible_with_another_generic_union(tmp_path: Path) -> None:
    (tmp_path / "gu").mkdir()
    (tmp_path / "gu" / "lib.orc").write_text((MODULE_ROOT / "gu" / "lib.orc").read_text(encoding="utf-8"))
    path = tmp_path / "gu" / "narrow.orc"
    narrow = (MODULE_ROOT / "gu" / "narrow.orc").read_text(encoding="utf-8")
    path.write_text(narrow.replace("-> Alpha[Item]", "-> Beta[Item]"), encoding="utf-8")

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_entrypoint(path, tmp_path, source_root=tmp_path, frontend=True)

    assert _first_diagnostic(excinfo).code == "procedure_return_type_invalid"
