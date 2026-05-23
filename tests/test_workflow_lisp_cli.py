from __future__ import annotations

import importlib
import json
from argparse import Namespace
from pathlib import Path

import pytest

from orchestrator.cli.commands.compile import compile_workflow
from orchestrator.cli.commands.explain import explain_workflow
from orchestrator.cli.commands.run import run_workflow
from orchestrator.cli.main import create_parser
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp"
CLI_FIXTURES = FIXTURES / "cli"
ENTRYPOINT = FIXTURES / "modules" / "valid" / "imported_bundle_mix" / "neurips" / "entry.orc"
SOURCE_ROOT = FIXTURES / "modules" / "valid" / "imported_bundle_mix"
CALLABLE_ENTRYPOINT = FIXTURES / "modules" / "valid" / "callables" / "neurips" / "entry.orc"
CALLABLE_SOURCE_ROOT = FIXTURES / "modules" / "valid" / "callables"


def _build_module():
    return importlib.import_module("orchestrator.workflow_lisp.build")


def _orc_run_args(
    *,
    workflow: Path = ENTRYPOINT,
    source_root: Path = SOURCE_ROOT,
    imported_workflow_bundles_file: Path = CLI_FIXTURES / "imported_workflow_bundles.json",
    dry_run: bool = True,
    input_values: list[str] | None = None,
) -> Namespace:
    return Namespace(
        workflow=str(workflow),
        context=None,
        context_file=None,
        input=input_values,
        input_file=None,
        clean_processed=False,
        archive_processed=None,
        debug=False,
        stream_output=False,
        dry_run=dry_run,
        backup_state=False,
        state_dir=None,
        on_error="stop",
        max_retries=0,
        retry_delay=1000,
        quiet=False,
        verbose=False,
        log_level="info",
        step_summaries=False,
        summary_mode=None,
        summary_provider="claude_sonnet_summary",
        summary_timeout_sec=120,
        summary_max_input_chars=12000,
        summary_profile=None,
        live_agent_notes=False,
        live_agent_note_provider=None,
        live_agent_note_interval_sec=15.0,
        live_agent_note_timeout_sec=30,
        live_agent_note_max_tail_chars=6000,
        entry_workflow="orchestrate",
        source_root=[str(source_root)],
        provider_externs_file=str(CLI_FIXTURES / "providers.json"),
        prompt_externs_file=str(CLI_FIXTURES / "prompts.json"),
        imported_workflow_bundles_file=str(imported_workflow_bundles_file),
        command_boundaries_file=str(CLI_FIXTURES / "commands.json"),
        emit_debug_yaml=False,
    )


def _orc_explain_args(
    *,
    workflow: Path = ENTRYPOINT,
    source_root: Path = SOURCE_ROOT,
    form: str | None = None,
    imported_workflow_bundles_file: Path = CLI_FIXTURES / "imported_workflow_bundles.json",
    emit_core_ast: list[str | None] | None = None,
    emit_semantic_ir: list[str | None] | None = None,
    emit_source_map: list[str | None] | None = None,
    emit_debug_yaml: list[str | None] | None = None,
) -> Namespace:
    return Namespace(
        workflow=str(workflow),
        form=form,
        entry_workflow="orchestrate",
        source_root=[str(source_root)],
        provider_externs_file=str(CLI_FIXTURES / "providers.json"),
        prompt_externs_file=str(CLI_FIXTURES / "prompts.json"),
        imported_workflow_bundles_file=str(imported_workflow_bundles_file),
        command_boundaries_file=str(CLI_FIXTURES / "commands.json"),
        emit_core_ast=emit_core_ast or [],
        emit_semantic_ir=emit_semantic_ir or [],
        emit_source_map=emit_source_map or [],
        emit_debug_yaml=emit_debug_yaml or [],
    )


def _orc_compile_args(
    *,
    workflow: Path = ENTRYPOINT,
    source_root: Path = SOURCE_ROOT,
    provider_externs_file: Path = CLI_FIXTURES / "providers.json",
    prompt_externs_file: Path = CLI_FIXTURES / "prompts.json",
    imported_workflow_bundles_file: Path = CLI_FIXTURES / "imported_workflow_bundles.json",
    command_boundaries_file: Path = CLI_FIXTURES / "commands.json",
    emit_core_ast: list[str | None] | None = None,
    emit_semantic_ir: list[str | None] | None = None,
    emit_source_map: list[str | None] | None = None,
    emit_debug_yaml: list[str | None] | None = None,
) -> Namespace:
    return Namespace(
        workflow=str(workflow),
        entry_workflow="orchestrate",
        source_root=[str(source_root)],
        provider_externs_file=str(provider_externs_file),
        prompt_externs_file=str(prompt_externs_file),
        imported_workflow_bundles_file=str(imported_workflow_bundles_file),
        command_boundaries_file=str(command_boundaries_file),
        emit_core_ast=emit_core_ast or [],
        emit_semantic_ir=emit_semantic_ir or [],
        emit_source_map=emit_source_map or [],
        emit_debug_yaml=emit_debug_yaml or [],
    )


def _yaml_run_args(
    *,
    workflow: Path = CLI_FIXTURES / "imported_selector.yaml",
    dry_run: bool = True,
    input_values: list[str] | None = None,
) -> Namespace:
    return Namespace(
        workflow=str(workflow),
        context=None,
        context_file=None,
        input=input_values,
        input_file=None,
        clean_processed=False,
        archive_processed=None,
        debug=False,
        stream_output=False,
        dry_run=dry_run,
        backup_state=False,
        state_dir=None,
        on_error="stop",
        max_retries=0,
        retry_delay=1000,
        quiet=False,
        verbose=False,
        log_level="info",
        step_summaries=False,
        summary_mode=None,
        summary_provider="claude_sonnet_summary",
        summary_timeout_sec=120,
        summary_max_input_chars=12000,
        summary_profile=None,
        live_agent_notes=False,
        live_agent_note_provider=None,
        live_agent_note_interval_sec=15.0,
        live_agent_note_timeout_sec=30,
        live_agent_note_max_tail_chars=6000,
    )


def test_parser_supports_compile_and_explain_subcommands() -> None:
    parser = create_parser()

    compile_args = parser.parse_args(
        [
            "compile",
            str(ENTRYPOINT),
            "--entry-workflow",
            "orchestrate",
            "--source-root",
            str(SOURCE_ROOT),
            "--provider-externs-file",
            str(CLI_FIXTURES / "providers.json"),
            "--prompt-externs-file",
            str(CLI_FIXTURES / "prompts.json"),
            "--imported-workflow-bundles-file",
            str(CLI_FIXTURES / "imported_workflow_bundles.json"),
            "--command-boundaries-file",
            str(CLI_FIXTURES / "commands.json"),
            "--emit-core-ast",
            "--emit-semantic-ir",
            "exports/semantic_ir.json",
            "--emit-source-map",
            "out/maps/source_map.json",
            "--emit-debug-yaml",
        ]
    )
    explain_args = parser.parse_args(
        [
            "explain",
            str(ENTRYPOINT),
            "--form",
            "orchestrate",
            "--entry-workflow",
            "orchestrate",
            "--source-root",
            str(SOURCE_ROOT),
            "--provider-externs-file",
            str(CLI_FIXTURES / "providers.json"),
            "--prompt-externs-file",
            str(CLI_FIXTURES / "prompts.json"),
            "--imported-workflow-bundles-file",
            str(CLI_FIXTURES / "imported_workflow_bundles.json"),
            "--command-boundaries-file",
            str(CLI_FIXTURES / "commands.json"),
            "--emit-debug-yaml",
            "--emit-core-ast",
            "--emit-core-ast",
        ]
    )

    assert compile_args.command == "compile"
    assert compile_args.emit_core_ast == [None]
    assert compile_args.emit_semantic_ir == ["exports/semantic_ir.json"]
    assert compile_args.emit_source_map == ["out/maps/source_map.json"]
    assert compile_args.emit_debug_yaml == [None]
    assert explain_args.command == "explain"
    assert explain_args.form == "orchestrate"
    assert explain_args.emit_debug_yaml == [None]
    assert explain_args.emit_core_ast == [None, None]


def test_parser_accepts_orc_specific_run_flags() -> None:
    parser = create_parser()
    args = parser.parse_args(
        [
            "run",
            str(ENTRYPOINT),
            "--entry-workflow",
            "orchestrate",
            "--source-root",
            str(SOURCE_ROOT),
            "--provider-externs-file",
            str(CLI_FIXTURES / "providers.json"),
            "--prompt-externs-file",
            str(CLI_FIXTURES / "prompts.json"),
            "--imported-workflow-bundles-file",
            str(CLI_FIXTURES / "imported_workflow_bundles.json"),
            "--command-boundaries-file",
            str(CLI_FIXTURES / "commands.json"),
            "--dry-run",
        ]
    )

    assert args.entry_workflow == "orchestrate"
    assert args.source_root == [str(SOURCE_ROOT)]
    assert args.provider_externs_file == str(CLI_FIXTURES / "providers.json")
    assert args.imported_workflow_bundles_file == str(CLI_FIXTURES / "imported_workflow_bundles.json")
    assert args.command_boundaries_file == str(CLI_FIXTURES / "commands.json")
    assert args.dry_run is True


def test_build_service_infers_single_exported_entry_workflow(tmp_path: Path) -> None:
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    source_dir = tmp_path / "single"
    source_dir.mkdir()
    source_path = source_dir / "entry.orc"
    source_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule single/entry)",
                "  (export only)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord Out",
                "    (report WorkReport))",
                "  (defworkflow only",
                "    ((report_path WorkReport))",
                "    -> Out",
                "    (provider-result providers.execute",
                "      :prompt prompts.implementation.execute",
                "      :inputs (report_path)",
                "      :returns Out)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    request = request_cls(
        source_path=source_path,
        source_roots=(tmp_path,),
        entry_workflow=None,
        provider_externs_path=CLI_FIXTURES / "providers.json",
        prompt_externs_path=CLI_FIXTURES / "prompts.json",
        imported_workflow_bundles_path=None,
        command_boundaries_path=None,
        emit_debug_yaml=False,
        workspace_root=tmp_path,
    )

    result = build_frontend_bundle(request)

    assert result.selected_workflow_name == "single/entry::only"
    assert result.validated_bundle.surface.name.endswith("::only")


def test_build_service_requires_entry_workflow_for_multi_workflow_module(tmp_path: Path) -> None:
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    source_dir = tmp_path / "multiple"
    source_dir.mkdir()
    source_path = source_dir / "entry.orc"
    source_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule multiple/entry)",
                "  (export alpha beta)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord Out",
                "    (report WorkReport))",
                "  (defworkflow alpha",
                "    ((report_path WorkReport))",
                "    -> Out",
                "    (provider-result providers.execute",
                "      :prompt prompts.implementation.execute",
                "      :inputs (report_path)",
                "      :returns Out))",
                "  (defworkflow beta",
                "    ((report_path WorkReport))",
                "    -> Out",
                "    (provider-result providers.execute",
                "      :prompt prompts.implementation.execute",
                "      :inputs (report_path)",
                "      :returns Out)))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    request = request_cls(
        source_path=source_path,
        source_roots=(tmp_path,),
        entry_workflow=None,
        provider_externs_path=CLI_FIXTURES / "providers.json",
        prompt_externs_path=CLI_FIXTURES / "prompts.json",
        imported_workflow_bundles_path=None,
        command_boundaries_path=None,
        emit_debug_yaml=False,
        workspace_root=tmp_path,
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_frontend_bundle(request)

    assert excinfo.value.diagnostics[0].code == "entry_workflow_required"


def test_run_workflow_supports_orc_dry_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    report_path = tmp_path / "artifacts" / "work" / "existing-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("ok\n", encoding="utf-8")

    result = run_workflow(
        _orc_run_args(
            input_values=[
                "input__status=ready",
                "input__report=artifacts/work/existing-report.md",
                "report_path=artifacts/work/existing-report.md",
            ]
        )
    )

    assert result == 0
    assert not (tmp_path / ".orchestrate" / "runs").exists()


def test_run_workflow_orc_dry_run_requires_bound_inputs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = run_workflow(_orc_run_args())

    assert result == 2
    assert not (tmp_path / ".orchestrate" / "runs").exists()


def test_run_workflow_yaml_dry_run_requires_bound_inputs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = run_workflow(_yaml_run_args())

    assert result == 2
    assert not (tmp_path / ".orchestrate" / "runs").exists()


def test_explain_workflow_rejects_unknown_form(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = explain_workflow(_orc_explain_args(form="does-not-exist"))

    assert result == 2


def test_explain_workflow_selects_requested_form(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    result = explain_workflow(_orc_explain_args(form="provider-attempt"))
    captured = capsys.readouterr()

    assert result == 0
    assert "Form: provider-attempt" in captured.out
    assert '"workflow_name": "neurips/helper::provider-attempt"' in captured.out
    assert '"workflow_name": "neurips/entry::orchestrate"' not in captured.out


def test_explain_workflow_prints_core_ast_and_semantic_ir(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    result = explain_workflow(_orc_explain_args(form="orchestrate"))
    captured = capsys.readouterr()

    assert result == 0
    assert "Deferred artifacts:" not in captured.out
    assert "Core Workflow AST:" in captured.out
    assert '"schema_version": "core_workflow_ast.v1"' in captured.out
    assert "Semantic IR:" in captured.out
    assert '"schema_version": "workflow_semantic_ir.v1"' in captured.out
    assert '"workflow_name": "neurips/entry::orchestrate"' in captured.out
    assert "Emitted artifacts:" not in captured.out


def test_compile_workflow_exports_requested_artifacts_and_reports_them(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    result = compile_workflow(
        _orc_compile_args(
            emit_core_ast=[None],
            emit_semantic_ir=["exports/semantic_ir.snapshot.json"],
            emit_source_map=[None],
            emit_debug_yaml=[None],
        )
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert result == 0
    assert (tmp_path / "core_workflow_ast.json").exists()
    assert (tmp_path / "source_map.json").exists()
    assert (tmp_path / "expanded.debug.yaml").exists()
    assert (tmp_path / "exports" / "semantic_ir.snapshot.json").exists()
    assert payload["artifact_paths"]["core_workflow_ast"].endswith("/core_workflow_ast.json")
    assert payload["exported_artifacts"] == {
        "core_workflow_ast": str((tmp_path / "core_workflow_ast.json").resolve()),
        "expanded_debug_yaml": str((tmp_path / "expanded.debug.yaml").resolve()),
        "semantic_ir": str((tmp_path / "exports" / "semantic_ir.snapshot.json").resolve()),
        "source_map": str((tmp_path / "source_map.json").resolve()),
    }
    assert payload["artifact_paths"]["core_workflow_ast"] != payload["exported_artifacts"]["core_workflow_ast"]


def test_explain_workflow_exports_compilation_scoped_artifacts_for_selected_imported_target(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    result = explain_workflow(
        _orc_explain_args(
            form="selector-run",
            emit_core_ast=[None],
            emit_semantic_ir=["exports/semantic_ir.json"],
        )
    )
    captured = capsys.readouterr()
    exported_core_ast = json.loads((tmp_path / "core_workflow_ast.json").read_text(encoding="utf-8"))
    exported_semantic_ir = json.loads((tmp_path / "exports" / "semantic_ir.json").read_text(encoding="utf-8"))

    assert result == 0
    assert "Form: selector-run" in captured.out
    assert "Emitted artifacts:" in captured.out
    assert str((tmp_path / "core_workflow_ast.json").resolve()) in captured.out
    assert str((tmp_path / "exports" / "semantic_ir.json").resolve()) in captured.out
    assert exported_core_ast["workflow_name"] == "neurips/entry::orchestrate"
    assert exported_semantic_ir["workflows"]["neurips/entry::orchestrate"]["workflow_name"] == "neurips/entry::orchestrate"


def test_compile_workflow_rejects_duplicate_emit_requests(
    tmp_path: Path,
    monkeypatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.chdir(tmp_path)

    with caplog.at_level("ERROR"):
        result = compile_workflow(_orc_compile_args(emit_core_ast=[None, "exports/core.json"]))

    assert result == 2
    assert "requested more than once" in caplog.text
    assert "core_workflow_ast" in caplog.text


def test_compile_workflow_rejects_export_destination_directory(
    tmp_path: Path,
    monkeypatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.chdir(tmp_path)
    destination = tmp_path / "exports"
    destination.mkdir()

    with caplog.at_level("ERROR"):
        result = compile_workflow(_orc_compile_args(emit_source_map=["exports"]))

    assert result == 2
    assert "existing directory" in caplog.text


def test_compile_workflow_reports_export_copy_failure_without_removing_canonical_build(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.chdir(tmp_path)
    build = _build_module()
    emitted_build_roots: list[Path] = []
    original = getattr(build, "emit_requested_frontend_artifact_exports", None)

    def _failing_export(*args, **kwargs):
        result = kwargs["result"]
        emitted_build_roots.append(result.build_root)
        raise OSError("simulated export failure")

    monkeypatch.setattr(
        "orchestrator.cli.commands.compile.emit_requested_frontend_artifact_exports",
        _failing_export,
        raising=False,
    )

    with caplog.at_level("ERROR"):
        result = compile_workflow(_orc_compile_args(emit_core_ast=[None]))
    captured = capsys.readouterr()

    assert result == 2
    assert captured.out == ""
    assert "simulated export failure" in caplog.text
    assert emitted_build_roots
    assert emitted_build_roots[0].exists()


def test_explain_workflow_supports_imported_call_targets(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    result = explain_workflow(_orc_explain_args(form="selector-run"))
    captured = capsys.readouterr()

    assert result == 0
    assert "Form: selector-run" in captured.out
    assert '"canonical_key": "selector-run"' in captured.out
    assert '"workflow_path":' in captured.out
    assert '"executable_node_id": "root.neurips_entry_orchestrate__remote__call_selector_run"' in captured.out
    assert "Expansion frames:" in captured.out


def test_explain_workflow_supports_exported_procedures(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    result = explain_workflow(
        _orc_explain_args(
            workflow=CALLABLE_ENTRYPOINT,
            source_root=CALLABLE_SOURCE_ROOT,
            form="build-checks",
        )
    )
    captured = capsys.readouterr()

    assert result == 0
    assert "Form: build-checks" in captured.out
    assert '"procedure_name": "neurips/procedures::build-checks"' in captured.out
    assert '"neurips_entry_orchestrate__checks__neurips_procedures_build_checks_1__run_checks"' in captured.out
    assert '"defproc"' in captured.out


def test_run_workflow_reports_missing_imported_bundle_key(
    tmp_path: Path,
    monkeypatch,
) -> None:
    build = _build_module()
    load_imported_workflow_bundle_manifest = getattr(build, "load_imported_workflow_bundle_manifest")

    manifest_path = tmp_path / "missing_imported_bundle.json"
    manifest_path.write_text("{}", encoding="utf-8")
    report_path = tmp_path / "artifacts" / "work" / "existing-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("ok\n", encoding="utf-8")

    with pytest.raises(LispFrontendCompileError) as excinfo:
        load_imported_workflow_bundle_manifest(manifest_path, workspace_root=tmp_path)

    assert excinfo.value.diagnostics[0].code == "imported_workflow_bundle_manifest_empty"

    monkeypatch.chdir(tmp_path)
    result = run_workflow(
        _orc_run_args(
            imported_workflow_bundles_file=manifest_path,
            input_values=[
                "input__status=ready",
                "input__report=artifacts/work/existing-report.md",
                "report_path=artifacts/work/existing-report.md",
            ],
        )
    )

    assert result != 0


def test_compile_workflow_rejects_non_orc_inputs_with_frontend_diagnostic(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("ERROR"):
        result = compile_workflow(
            Namespace(
                workflow=str(CLI_FIXTURES / "imported_selector.yaml"),
                entry_workflow=None,
                source_root=None,
                provider_externs_file=None,
                prompt_externs_file=None,
                imported_workflow_bundles_file=None,
                command_boundaries_file=None,
                emit_debug_yaml=False,
            )
        )

    assert result == 2
    assert "[workflow_lisp_cli_input_unsupported]" in caplog.text


def test_compile_workflow_reports_missing_orc_path_as_frontend_diagnostic(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("ERROR"):
        result = compile_workflow(
            Namespace(
                workflow="does/not/exist.orc",
                entry_workflow="orchestrate",
                source_root=None,
                provider_externs_file=None,
                prompt_externs_file=None,
                imported_workflow_bundles_file=None,
                command_boundaries_file=None,
                emit_debug_yaml=False,
            )
        )

    assert result == 2
    assert "[workflow_lisp_cli_input_missing]" in caplog.text
    assert "Traceback" not in caplog.text


def test_explain_workflow_rejects_non_orc_inputs_with_frontend_diagnostic(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("ERROR"):
        result = explain_workflow(
            Namespace(
                workflow=str(CLI_FIXTURES / "imported_selector.yaml"),
                form=None,
                entry_workflow=None,
                source_root=None,
                provider_externs_file=None,
                prompt_externs_file=None,
                imported_workflow_bundles_file=None,
                command_boundaries_file=None,
            )
        )

    assert result == 2
    assert "[workflow_lisp_cli_input_unsupported]" in caplog.text


def test_explain_workflow_reports_missing_orc_path_as_frontend_diagnostic(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("ERROR"):
        result = explain_workflow(
            Namespace(
                workflow="does/not/exist.orc",
                form=None,
                entry_workflow="orchestrate",
                source_root=None,
                provider_externs_file=None,
                prompt_externs_file=None,
                imported_workflow_bundles_file=None,
                command_boundaries_file=None,
            )
        )

    assert result == 2
    assert "[workflow_lisp_cli_input_missing]" in caplog.text
    assert "Traceback" not in caplog.text


def test_explain_workflow_marks_canonical_entry_workflow_as_selected(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    args = _orc_explain_args(form="neurips/entry::orchestrate")
    args.entry_workflow = "neurips/entry::orchestrate"

    result = explain_workflow(args)
    captured = capsys.readouterr()

    assert result == 0
    assert "Entry workflow: neurips/entry::orchestrate" in captured.out
    assert '"workflow_name": "neurips/entry::orchestrate"' in captured.out
    assert '"selected_entry_workflow": true' in captured.out


@pytest.mark.parametrize(
    ("manifest_flag", "manifest_path"),
    [
        ("provider_externs_file", Path("does/not/exist.providers.json")),
        ("prompt_externs_file", Path("does/not/exist.prompts.json")),
        ("imported_workflow_bundles_file", Path("does/not/exist.imported.json")),
        ("command_boundaries_file", Path("does/not/exist.commands.json")),
    ],
)
def test_build_service_reports_missing_manifest_files_as_frontend_diagnostics(
    tmp_path: Path,
    manifest_flag: str,
    manifest_path: Path,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    compile_args = _orc_compile_args()
    request = getattr(build, "FrontendBuildRequest")(
        source_path=ENTRYPOINT,
        source_roots=(SOURCE_ROOT,),
        entry_workflow="orchestrate",
        provider_externs_path=Path(compile_args.provider_externs_file),
        prompt_externs_path=Path(compile_args.prompt_externs_file),
        imported_workflow_bundles_path=Path(compile_args.imported_workflow_bundles_file),
        command_boundaries_path=Path(compile_args.command_boundaries_file),
        emit_debug_yaml=False,
        workspace_root=tmp_path,
    )
    request = type(request)(
        **{
            **request.__dict__,
            manifest_flag.replace("_file", "_path"): manifest_path,
        }
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_frontend_bundle(request)

    assert excinfo.value.diagnostics[0].code == "workflow_lisp_manifest_missing"
    assert "does not exist" in excinfo.value.diagnostics[0].message


@pytest.mark.parametrize(
    "command_name",
    ["compile", "explain", "run"],
)
def test_orc_commands_report_missing_manifest_files_as_frontend_diagnostics(
    tmp_path: Path,
    command_name: str,
    monkeypatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.chdir(tmp_path)
    report_path = tmp_path / "artifacts" / "work" / "existing-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("ok\n", encoding="utf-8")

    if command_name == "compile":
        command = compile_workflow
        args = _orc_compile_args(provider_externs_file=Path("does/not/exist.providers.json"))
    elif command_name == "explain":
        command = explain_workflow
        args = _orc_explain_args()
        args.provider_externs_file = "does/not/exist.providers.json"
    else:
        command = run_workflow
        args = _orc_run_args(
            input_values=[
                "input__status=ready",
                "input__report=artifacts/work/existing-report.md",
                "report_path=artifacts/work/existing-report.md",
            ]
        )
        args.provider_externs_file = "does/not/exist.providers.json"

    with caplog.at_level("ERROR"):
        result = command(args)

    assert result == 2
    assert "[workflow_lisp_manifest_missing]" in caplog.text
    assert "provider externs manifest does not exist" in caplog.text
    assert "Traceback" not in caplog.text


@pytest.mark.parametrize(
    ("manifest_flag", "file_name"),
    [
        ("provider_externs_file", "providers.invalid.json"),
        ("prompt_externs_file", "prompts.invalid.json"),
        ("imported_workflow_bundles_file", "imported.invalid.json"),
        ("command_boundaries_file", "commands.invalid.json"),
    ],
)
def test_build_service_reports_malformed_manifest_files_as_frontend_diagnostics(
    tmp_path: Path,
    manifest_flag: str,
    file_name: str,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")

    invalid_manifest = tmp_path / file_name
    invalid_manifest.write_text("{bad json\n", encoding="utf-8")

    compile_args = _orc_compile_args()
    build_request = getattr(build, "FrontendBuildRequest")(
        source_path=ENTRYPOINT,
        source_roots=(SOURCE_ROOT,),
        entry_workflow="orchestrate",
        provider_externs_path=Path(compile_args.provider_externs_file),
        prompt_externs_path=Path(compile_args.prompt_externs_file),
        imported_workflow_bundles_path=Path(compile_args.imported_workflow_bundles_file),
        command_boundaries_path=Path(compile_args.command_boundaries_file),
        emit_debug_yaml=False,
        workspace_root=tmp_path,
    )
    build_request = type(build_request)(
        **{
            **build_request.__dict__,
            manifest_flag.replace("_file", "_path"): invalid_manifest,
        }
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_frontend_bundle(build_request)

    assert excinfo.value.diagnostics[0].code == "workflow_lisp_manifest_invalid_json"
    assert "must contain valid JSON" in excinfo.value.diagnostics[0].message


@pytest.mark.parametrize(
    "command_name",
    ["compile", "explain", "run"],
)
def test_orc_commands_report_malformed_manifest_files_as_frontend_diagnostics(
    tmp_path: Path,
    command_name: str,
    monkeypatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.chdir(tmp_path)
    invalid_manifest = tmp_path / "providers.invalid.json"
    invalid_manifest.write_text("{bad json\n", encoding="utf-8")
    report_path = tmp_path / "artifacts" / "work" / "existing-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("ok\n", encoding="utf-8")

    if command_name == "compile":
        command = compile_workflow
        args = _orc_compile_args(provider_externs_file=invalid_manifest)
    elif command_name == "explain":
        command = explain_workflow
        args = _orc_explain_args()
        args.provider_externs_file = str(invalid_manifest)
    else:
        command = run_workflow
        args = _orc_run_args(
            input_values=[
                "input__status=ready",
                "input__report=artifacts/work/existing-report.md",
                "report_path=artifacts/work/existing-report.md",
            ]
        )
        args.provider_externs_file = str(invalid_manifest)

    with caplog.at_level("ERROR"):
        result = command(args)

    assert result == 2
    assert "[workflow_lisp_manifest_invalid_json]" in caplog.text
    assert "provider externs manifest must contain valid JSON" in caplog.text
    assert "Traceback" not in caplog.text


@pytest.mark.parametrize(
    ("manifest_flag", "file_name", "payload", "expected_code", "expected_message"),
    [
        (
            "provider_externs_file",
            "providers.invalid-entry.json",
            {"providers.execute": {"bad": True}},
            "workflow_lisp_manifest_invalid",
            "provider externs manifest entries must map non-empty string names to string values",
        ),
        (
            "prompt_externs_file",
            "prompts.invalid-entry.json",
            {"prompts.implementation.execute": {"bad": True}},
            "workflow_lisp_manifest_invalid",
            "prompt externs manifest entries must map non-empty string names to string values",
        ),
        (
            "command_boundaries_file",
            "commands.invalid-entry.json",
            {"run_checks": 5},
            "command_boundary_manifest_invalid",
            "manifest entry for `run_checks` must be a JSON object",
        ),
        (
            "command_boundaries_file",
            "commands.invalid-stable-command.json",
            {"run_checks": {"kind": "external_tool", "stable_command": 5}},
            "command_boundary_manifest_invalid",
            "`stable_command` for `run_checks` must be an array of strings",
        ),
    ],
)
@pytest.mark.parametrize(
    "command_name",
    ["compile", "explain", "run"],
)
def test_orc_commands_report_invalid_manifest_entry_schema_as_frontend_diagnostics(
    tmp_path: Path,
    command_name: str,
    manifest_flag: str,
    file_name: str,
    payload: dict[str, object],
    expected_code: str,
    expected_message: str,
    monkeypatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.chdir(tmp_path)
    manifest_path = tmp_path / file_name
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    report_path = tmp_path / "artifacts" / "work" / "existing-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("ok\n", encoding="utf-8")

    if command_name == "compile":
        command = compile_workflow
        args = _orc_compile_args()
    elif command_name == "explain":
        command = explain_workflow
        args = _orc_explain_args()
    else:
        command = run_workflow
        args = _orc_run_args(
            input_values=[
                "input__status=ready",
                "input__report=artifacts/work/existing-report.md",
                "report_path=artifacts/work/existing-report.md",
            ]
        )

    setattr(args, manifest_flag, str(manifest_path))

    with caplog.at_level("ERROR"):
        result = command(args)

    assert result == 2
    assert f"[{expected_code}]" in caplog.text
    assert expected_message in caplog.text
    assert "Traceback" not in caplog.text
