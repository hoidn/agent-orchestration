import importlib
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import (
    _definition_only_syntax_module,
    compile_stage1_module,
    compile_stage3_module,
)
from orchestrator.workflow_lisp.definitions import elaborate_definition_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.diagnostics import serialize_diagnostic
from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.syntax import build_syntax_module
from orchestrator.workflow_lisp.workflows import ExternalToolBinding, elaborate_workflow_definitions


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp"
MODULE_FIXTURES = FIXTURES / "modules"
VALID_ALIAS_FIXTURE = FIXTURES / "valid" / "macro_workflow_alias.orc"
HYGIENE_FIXTURE = FIXTURES / "valid" / "macro_hygiene_local_binding.orc"


def _macros_module():
    return importlib.import_module("orchestrator.workflow_lisp.macros")


def _compiler_module():
    return importlib.import_module("orchestrator.workflow_lisp.compiler")


def _expanded_module(path: Path):
    syntax_module = build_syntax_module(read_sexpr_file(path))
    macros = _macros_module()
    catalog = macros.collect_macro_catalog(syntax_module)
    return catalog, macros.expand_module_forms(syntax_module, catalog=catalog)


def _walk_syntax(node: object):
    if hasattr(node, "forms"):
        for form in getattr(node, "forms"):
            yield from _walk_syntax(form)
        return
    yield node
    if hasattr(node, "items"):
        for item in getattr(node, "items"):
            yield from _walk_syntax(item)


def test_collect_macro_catalog_supports_same_file_forward_references() -> None:
    catalog, expanded = _expanded_module(VALID_ALIAS_FIXTURE)

    assert tuple(catalog.definitions_by_name) == ("defworkflow-alias",)
    assert [workflow.name for workflow in elaborate_workflow_definitions(expanded)] == [
        "command_checks",
        "provider_attempt",
    ]
    assert [definition.name for definition in elaborate_definition_module(_definition_only_syntax_module(expanded)).definitions] == [
        "WorkReport",
        "ChecksResult",
        "ImplementationSummary",
        "ImplementationState",
    ]


def test_macro_expansion_assigns_deterministic_ids_and_hygienic_resolved_names() -> None:
    _, expanded = _expanded_module(HYGIENE_FIXTURE)

    identifiers = [node for node in _walk_syntax(expanded) if hasattr(node, "display_name")]
    introduced_tmps = [
        identifier
        for identifier in identifiers
        if identifier.display_name == "tmp" and identifier.introduced_by_expansion_id is not None
    ]
    caller_tmps = [
        identifier
        for identifier in identifiers
        if identifier.display_name == "tmp" and identifier.introduced_by_expansion_id is None
    ]

    assert {identifier.introduced_by_expansion_id for identifier in introduced_tmps} == {"m0001"}
    assert {identifier.resolved_name for identifier in introduced_tmps} == {
        "%macro__preserve-caller-tmp__m0001__tmp"
    }
    assert any(identifier.resolved_name == "tmp" for identifier in caller_tmps)


def test_compile_stage1_rejects_reserved_macro_names() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage1_module(FIXTURES / "invalid" / "macro_reserved_name.orc")

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "macro_reserved_name"
    assert "defworkflow" in diagnostic.message


def test_form_registry_reserved_macro_names_match_current_policy_exactly() -> None:
    registry = importlib.import_module("orchestrator.workflow_lisp.form_registry")

    assert registry.reserved_macro_names() == _macros_module()._RESERVED_MACRO_NAMES


def test_form_registry_admitted_top_level_heads_match_current_policy_exactly() -> None:
    registry = importlib.import_module("orchestrator.workflow_lisp.form_registry")

    assert registry.admitted_top_level_heads() == _macros_module()._ALLOWED_TOP_LEVEL_HEADS


def test_form_registry_keeps_current_bindable_compiler_forms_bindable() -> None:
    registry = importlib.import_module("orchestrator.workflow_lisp.form_registry")

    reserved = registry.reserved_macro_names()

    assert {
        "review-revise-loop",
        "variant",
        "if",
        "loop/recur",
        "fn",
        "continue",
        "done",
        "workflow-ref",
        "proc-ref",
        "bind-proc",
        "let-proc",
    }.isdisjoint(reserved)


def test_review_revise_loop_not_reserved_core_macro_name() -> None:
    registry = importlib.import_module("orchestrator.workflow_lisp.form_registry")

    reserved = registry.reserved_macro_names()
    review_loop = registry.get_form_spec("review-revise-loop")
    bridge = registry.get_form_spec("__stdlib-specialization__")

    assert "review-revise-loop" not in reserved
    assert "__stdlib-specialization__" not in reserved
    assert review_loop is not None and review_loop.macro_bindable is True
    assert bridge is None


def test_bridge_intrinsic_heads_become_macro_bindable_for_imported_stdlib_shadowing() -> None:
    registry = importlib.import_module("orchestrator.workflow_lisp.form_registry")

    for head_name in ("with-phase", "finalize-selected-item", "backlog-drain"):
        spec = registry.get_form_spec(head_name)

        assert spec is not None
        assert spec.macro_bindable is True


def test_form_registry_does_not_publish_review_loop_bridge_metadata() -> None:
    registry_path = Path(importlib.import_module("orchestrator.workflow_lisp.form_registry").__file__)
    source = registry_path.read_text(encoding="utf-8")

    assert "__stdlib-specialization__" not in source
    assert "phase-review-loop" not in source


def test_compile_stage1_reports_macro_expansion_cycles() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage1_module(FIXTURES / "invalid" / "macro_expansion_cycle.orc")

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "macro_expansion_cycle"
    assert "cyclic-workflow" in diagnostic.message


def test_compile_stage1_rejects_invalid_splice_and_invalid_emitted_forms() -> None:
    with pytest.raises(LispFrontendCompileError) as bad_splice:
        compile_stage1_module(FIXTURES / "invalid" / "macro_bad_splice.orc")
    assert bad_splice.value.diagnostics[0].code == "macro_emits_invalid_ast"

    with pytest.raises(LispFrontendCompileError) as invalid_form:
        compile_stage1_module(FIXTURES / "invalid" / "macro_emits_invalid_form.orc")
    assert invalid_form.value.diagnostics[0].code == "macro_emits_invalid_ast"


def test_compile_stage1_rejects_macro_expansions_that_emit_top_level_defmacro(tmp_path: Path) -> None:
    invalid_macro_output = tmp_path / "macro_emits_defmacro.orc"
    invalid_macro_output.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (emit-generated-macro generated)",
                "  (defmacro emit-generated-macro (name)",
                "    (defmacro name ()",
                "      42)))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage1_module(invalid_macro_output)

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "macro_emits_invalid_ast"
    assert "top-level `defmacro`" in diagnostic.message


def test_compile_stage1_allows_macro_emitted_defschema_forms(tmp_path: Path) -> None:
    fixture = tmp_path / "macro_emits_defschema.orc"
    fixture.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (emit-schema ReportTargets)",
                "  (defrecord ImplementationSummary",
                "    (:include ReportTargets))",
                "  (defmacro emit-schema (name)",
                "    (defschema name",
                "      (report WorkReport))))",
            ]
        ),
        encoding="utf-8",
    )

    module = compile_stage1_module(fixture)

    implementation_summary = module.definitions[1]
    assert implementation_summary.name == "ImplementationSummary"
    assert [field.name for field in implementation_summary.fields] == ["report"]


def test_compile_stage3_module_accepts_macro_emitted_provider_and_command_results(tmp_path: Path) -> None:
    result = compile_stage3_module(
        VALID_ALIAS_FIXTURE,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=False,
        workspace_root=tmp_path,
    )

    assert [workflow.definition.name for workflow in result.typed_workflows] == [
        "command_checks",
        "provider_attempt",
    ]
    assert [workflow.name for workflow in elaborate_workflow_definitions(_expanded_module(VALID_ALIAS_FIXTURE)[1])] == [
        "command_checks",
        "provider_attempt",
    ]


def test_compile_stage3_allows_caller_authored_effect_spliced_through_macro_alias(tmp_path: Path) -> None:
    fixture = tmp_path / "macro_caller_authored_effect_alias.orc"
    fixture.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord ChecksResult",
                "    (status String)",
                "    (report WorkReport))",
                "  (defrecord ImplementationSummary",
                "    (report WorkReport))",
                "  (defworkflow-alias command_checks",
                "    ((report_path WorkReport))",
                "    ChecksResult",
                "    (command-result run_checks",
                '      :argv ("python" "scripts/run_checks.py" report_path)',
                "      :returns ChecksResult))",
                "  (defworkflow-alias provider_attempt",
                "    ((input ChecksResult)",
                "     (report_path WorkReport))",
                "    ImplementationSummary",
                "    (let* ((attempt",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs (input report_path)",
                "               :returns ImplementationSummary)))",
                "      attempt))",
                "  (defmacro defworkflow-alias (name params return_type &body body)",
                "    (defworkflow name",
                "      params",
                "      -> return_type",
                "      (splice body))))",
            ]
        ),
        encoding="utf-8",
    )

    result = compile_stage3_module(
        fixture,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validate_shared=False,
        workspace_root=tmp_path,
    )

    assert [workflow.definition.name for workflow in result.typed_workflows] == [
        "command_checks",
        "provider_attempt",
    ]


def test_compile_stage3_allows_macro_introduced_letstar_binding_field_access(tmp_path: Path) -> None:
    fixture = tmp_path / "macro_letstar_field_access.orc"
    fixture.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defrecord Payload",
                "    (status String))",
                "  (defrecord Summary",
                "    (status String))",
                "  (defproc load-payload",
                "    ()",
                "    -> Payload",
                "    :effects ()",
                "    :lowering inline",
                "    (record Payload",
                '      :status "ok"))',
                "  (emit-summary summarize)",
                "  (defmacro emit-summary (name)",
                "    (defworkflow name",
                "      ()",
                "      -> Summary",
                "      (let* ((payload",
                "               (load-payload)))",
                "        (record Summary",
                "          :status payload.status)))))",
            ]
        ),
        encoding="utf-8",
    )

    result = compile_stage3_module(
        fixture,
        validate_shared=False,
        workspace_root=tmp_path,
    )

    assert [workflow.definition.name for workflow in result.typed_workflows] == ["summarize"]


def test_compile_stage3_entrypoint_rejects_imported_macros_that_introduce_hidden_effects(
    tmp_path: Path,
) -> None:
    compile_fn = getattr(_compiler_module(), "compile_stage3_entrypoint", None)
    assert callable(compile_fn), "compile_stage3_entrypoint is missing"

    source_root = MODULE_FIXTURES / "valid" / "import_macro"
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_fn(
            source_root / "neurips" / "entry.orc",
            source_roots=(source_root,),
            provider_externs={"providers.execute": "test-provider"},
            prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
            validate_shared=False,
            workspace_root=tmp_path,
        )

    diagnostic = excinfo.value.diagnostics[0]

    assert diagnostic.code == "macro_hidden_effect"
    assert diagnostic.span.start.path.endswith("tests/fixtures/workflow_lisp/modules/valid/import_macro/neurips/macros.orc")


def test_compile_stage3_rejects_macro_introduced_provider_effects_as_macro_hidden_effect(
    tmp_path: Path,
) -> None:
    path = tmp_path / "macro_hidden_effect.orc"
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defrecord ImplementationSummary",
                "    (report String))",
                "  (emit-provider-workflow generated)",
                "  (defmacro emit-provider-workflow (name)",
                "    (defworkflow name",
                "      ((report String))",
                "      -> ImplementationSummary",
                "      (provider-result providers.execute",
                "        :prompt prompts.implementation.execute",
                "        :inputs (report)",
                "        :returns ImplementationSummary))))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            path,
            provider_externs={"providers.execute": "test-provider"},
            prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
            validate_shared=False,
            workspace_root=tmp_path,
        )

    diagnostic = excinfo.value.diagnostics[0]

    assert diagnostic.code == "macro_hidden_effect"
    payload = serialize_diagnostic(diagnostic)
    assert payload["diagnostic_kind"] == "required_lint"
    assert payload["validation_pass"] == "effect"
    assert payload["authority_layer"] == "frontend"


def test_compile_stage3_rejects_macro_introduced_hidden_command_effects_as_macro_hidden_effect(
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            FIXTURES / "invalid" / "macro_hidden_command_effect.orc",
            command_boundaries={
                "run_checks": ExternalToolBinding(
                    name="run_checks",
                    stable_command=("python", "scripts/run_checks.py"),
                )
            },
            validate_shared=False,
            workspace_root=tmp_path,
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "macro_hidden_effect"
    assert "hidden command effect" in diagnostic.message
    assert diagnostic.expansion_stack
    assert diagnostic.expansion_stack[0].macro_name == "emit-command-workflow"
    payload = serialize_diagnostic(diagnostic)
    assert payload["diagnostic_kind"] == "required_lint"
    assert payload["validation_pass"] == "effect"
    assert payload["authority_layer"] == "frontend"


def test_compile_stage3_rejects_macro_emitted_malformed_match_with_owned_diagnostic(
    tmp_path: Path,
) -> None:
    fixture = tmp_path / "macro_malformed_match.orc"
    fixture.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord ImplementationSummary",
                "    (report WorkReport))",
                "  (emit-bad-match broken)",
                "  (defmacro emit-bad-match (name)",
                "    (defworkflow name",
                "      ((report_path WorkReport))",
                "      -> ImplementationSummary",
                "      (match))))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            fixture,
            validate_shared=False,
            workspace_root=tmp_path,
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.expansion_stack
    assert diagnostic.expansion_stack[0].macro_name == "emit-bad-match"
    assert "match" in diagnostic.message


def test_compile_stage3_rejects_macro_emitted_malformed_defworkflow_with_owned_diagnostic(
    tmp_path: Path,
) -> None:
    fixture = tmp_path / "macro_malformed_defworkflow.orc"
    fixture.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (emit-bad-workflow broken)",
                "  (defmacro emit-bad-workflow (name)",
                "    (defworkflow name)))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            fixture,
            validate_shared=False,
            workspace_root=tmp_path,
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.expansion_stack
    assert diagnostic.expansion_stack[0].macro_name == "emit-bad-workflow"
    assert "defworkflow" in diagnostic.message


def test_compile_stage3_entrypoint_rejects_imported_macros_that_introduce_hidden_command_effects(
    tmp_path: Path,
) -> None:
    compile_fn = getattr(_compiler_module(), "compile_stage3_entrypoint", None)
    assert callable(compile_fn), "compile_stage3_entrypoint is missing"

    source_root = MODULE_FIXTURES / "invalid" / "import_macro_hidden_command"

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_fn(
            source_root / "neurips" / "entry.orc",
            source_roots=(source_root,),
            command_boundaries={
                "run_checks": ExternalToolBinding(
                    name="run_checks",
                    stable_command=("python", "scripts/run_checks.py"),
                )
            },
            validate_shared=False,
            workspace_root=tmp_path,
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "macro_hidden_effect"
    assert diagnostic.span.start.path.endswith(
        "modules/invalid/import_macro_hidden_command/neurips/macros.orc"
    )
    payload = serialize_diagnostic(diagnostic)
    assert payload["diagnostic_kind"] == "required_lint"
    assert payload["validation_pass"] == "effect"
    assert payload["authority_layer"] == "frontend"


def test_compile_stage1_rejects_defun_as_a_reserved_macro_name(tmp_path: Path) -> None:
    fixture = tmp_path / "macro_reserved_defun.orc"
    fixture.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmacro defun ()",
                "    42))",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage1_module(fixture)

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "macro_reserved_name"
    assert "defun" in diagnostic.message


def test_compile_stage3_module_accepts_macro_emitted_top_level_defun(tmp_path: Path) -> None:
    fixture = tmp_path / "macro_emits_defun.orc"
    fixture.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord ChecksResult",
                "    (report WorkReport))",
                "  (defrecord ImplementationSummary",
                "    (report WorkReport))",
                "  (emit-helper summarize)",
                "  (defmacro emit-helper (name)",
                "    (defun name",
                "      ((input ChecksResult))",
                "      -> ImplementationSummary",
                "      (record ImplementationSummary",
                "        :report input.report)))",
                "  (defworkflow orchestrate",
                "    ((input ChecksResult))",
                "    -> ImplementationSummary",
                "    (summarize input)))",
            ]
        ),
        encoding="utf-8",
    )

    result = compile_stage3_module(
        fixture,
        validate_shared=False,
        workspace_root=tmp_path,
    )

    assert result.typed_workflows[0].definition.name == "orchestrate"
