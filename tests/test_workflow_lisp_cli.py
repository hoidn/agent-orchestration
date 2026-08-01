from __future__ import annotations

import importlib
import json
import shutil
from argparse import Namespace
from pathlib import Path

import pytest

from orchestrator.cli.commands.compile import compile_workflow
from orchestrator.cli.commands.explain import explain_workflow
from orchestrator.cli.commands.run import run_workflow
from orchestrator.cli.main import create_parser, main
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp"
CLI_FIXTURES = FIXTURES / "cli"
ENTRYPOINT = FIXTURES / "modules" / "valid" / "imported_bundle_mix" / "neurips" / "entry.orc"
SOURCE_ROOT = FIXTURES / "modules" / "valid" / "imported_bundle_mix"
CALLABLE_ENTRYPOINT = FIXTURES / "modules" / "valid" / "callables" / "neurips" / "entry.orc"
CALLABLE_SOURCE_ROOT = FIXTURES / "modules" / "valid" / "callables"
KISS_ENTRYPOINT = REPO_ROOT / "workflows" / "examples" / "kiss_backlog_item.orc"
KISS_PROVIDERS = REPO_ROOT / "workflows" / "examples" / "inputs" / "kiss_backlog_item" / "providers.json"
KISS_PROMPTS = REPO_ROOT / "workflows" / "examples" / "inputs" / "kiss_backlog_item" / "prompts.json"
CYCLE_GUARD_ENTRYPOINT = REPO_ROOT / "workflows" / "examples" / "cycle_guard_demo.orc"
CYCLE_GUARD_SOURCE_ROOT = REPO_ROOT / "workflows" / "examples"


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
    emit_executable_ir: list[str | None] | None = None,
    emit_core_ast: list[str | None] | None = None,
    emit_runtime_plan: list[str | None] | None = None,
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
        emit_executable_ir=emit_executable_ir or [],
        emit_core_ast=emit_core_ast or [],
        emit_runtime_plan=emit_runtime_plan or [],
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
    emit_executable_ir: list[str | None] | None = None,
    emit_core_ast: list[str | None] | None = None,
    emit_runtime_plan: list[str | None] | None = None,
    emit_semantic_ir: list[str | None] | None = None,
    emit_source_map: list[str | None] | None = None,
    emit_debug_yaml: list[str | None] | None = None,
    diagnostics_json: bool = False,
) -> Namespace:
    return Namespace(
        workflow=str(workflow),
        entry_workflow="orchestrate",
        source_root=[str(source_root)],
        provider_externs_file=str(provider_externs_file),
        prompt_externs_file=str(prompt_externs_file),
        imported_workflow_bundles_file=str(imported_workflow_bundles_file),
        command_boundaries_file=str(command_boundaries_file),
        emit_executable_ir=emit_executable_ir or [],
        emit_core_ast=emit_core_ast or [],
        emit_runtime_plan=emit_runtime_plan or [],
        emit_semantic_ir=emit_semantic_ir or [],
        emit_source_map=emit_source_map or [],
        emit_debug_yaml=emit_debug_yaml or [],
        diagnostics_json=diagnostics_json,
    )


def _minimal_compile_args(
    workflow: Path,
    *,
    diagnostics_json: bool,
) -> Namespace:
    return Namespace(
        workflow=str(workflow),
        diagnostics_json=diagnostics_json,
        entry_workflow="run",
        source_root=[str(workflow.parent)],
        provider_externs_file=None,
        prompt_externs_file=None,
        imported_workflow_bundles_file=None,
        command_boundaries_file=None,
        emit_executable_ir=[],
        emit_core_ast=[],
        emit_runtime_plan=[],
        emit_semantic_ir=[],
        emit_source_map=[],
        emit_debug_yaml=[],
    )


def _minimal_compile_source(*, return_type: str = "Result") -> str:
    return f"""\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.24")
  (defmodule candidate)
  (export Result run)
  (defrecord Result
    (value String))
  (defworkflow run
    ()
    -> {return_type}
    (record Result
      :value "ok")))
"""


def _legacy_run_args(
    *,
    workflow: Path = Path("legacy-workflow.yaml"),
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


def _kiss_run_args(*, dry_run: bool = True, input_values: list[str] | None = None) -> Namespace:
    return Namespace(
        workflow=str(KISS_ENTRYPOINT),
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
        entry_workflow="run-backlog-item",
        source_root=None,
        provider_externs_file=str(KISS_PROVIDERS),
        prompt_externs_file=str(KISS_PROMPTS),
        imported_workflow_bundles_file=None,
        command_boundaries_file=None,
        emit_debug_yaml=False,
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
            "--emit-executable-ir",
            "--emit-core-ast",
            "--emit-runtime-plan",
            "exports/runtime_plan.json",
            "--emit-semantic-ir",
            "exports/semantic_ir.json",
            "--emit-source-map",
            "out/maps/source_map.json",
            "--emit-debug-yaml",
            "--diagnostics-json",
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
            "--emit-executable-ir",
            "exports/executable_ir.json",
            "--emit-core-ast",
            "--emit-runtime-plan",
            "--emit-core-ast",
        ]
    )

    assert compile_args.command == "compile"
    assert compile_args.emit_executable_ir == [None]
    assert compile_args.emit_core_ast == [None]
    assert compile_args.emit_runtime_plan == ["exports/runtime_plan.json"]
    assert compile_args.emit_semantic_ir == ["exports/semantic_ir.json"]
    assert compile_args.emit_source_map == ["out/maps/source_map.json"]
    assert compile_args.emit_debug_yaml == [None]
    assert compile_args.diagnostics_json is True
    assert explain_args.command == "explain"
    assert explain_args.form == "orchestrate"
    assert explain_args.emit_debug_yaml == [None]
    assert explain_args.emit_executable_ir == ["exports/executable_ir.json"]
    assert explain_args.emit_core_ast == [None, None]
    assert explain_args.emit_runtime_plan == [None]
    assert not hasattr(explain_args, "diagnostics_json")


def test_compile_diagnostics_json_acceptance_is_one_closed_machine_document(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.chdir(tmp_path)

    with caplog.at_level("ERROR"):
        result = compile_workflow(
            _orc_compile_args(diagnostics_json=True)
        )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert result == 0
    assert captured.err == ""
    assert caplog.text == ""
    assert set(payload) == {
        "schema_version",
        "status",
        "selected_entry",
        "normalized_program_identity",
        "diagnostics",
    }
    assert payload["schema_version"] == "workflow_lisp_compile_diagnostics.v1"
    assert payload["status"] == "accepted"
    assert payload["diagnostics"] == []
    assert set(payload["selected_entry"]) == {
        "selected_name",
        "canonical_name",
        "signature",
    }
    assert payload["selected_entry"]["selected_name"] == "orchestrate"
    assert payload["selected_entry"]["canonical_name"].endswith("::orchestrate")
    assert set(payload["selected_entry"]["signature"]) == {
        "parameters",
        "return_type",
        "input_contracts",
        "output_contracts",
    }
    assert payload["selected_entry"]["signature"]["input_contracts"]
    assert payload["selected_entry"]["signature"]["output_contracts"]
    identity = payload["normalized_program_identity"]
    assert set(identity) == {
        "schema_version",
        "digest",
        "compiler_runtime_identity",
        "module_source_revisions",
        "compiler_source_revisions",
        "imported_bundle_bindings",
        "selected_entry_sha256",
        "lowering_route",
        "lowering_schema_version",
        "configuration_payload_digests",
        "configuration_revisions",
    }
    assert identity["schema_version"] == "workflow_lisp_program_identity.v1"
    assert identity["digest"].startswith("sha256:")
    assert identity["compiler_runtime_identity"].startswith("sha256:")
    assert identity["module_source_revisions"]


def test_compile_diagnostics_json_rejection_suppresses_human_rendering(
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    args = Namespace(
        workflow="legacy-workflow.yaml",
        diagnostics_json=True,
        entry_workflow=None,
        source_root=None,
        provider_externs_file=None,
        prompt_externs_file=None,
        imported_workflow_bundles_file=None,
        command_boundaries_file=None,
        emit_executable_ir=[],
        emit_core_ast=[],
        emit_runtime_plan=[],
        emit_semantic_ir=[],
        emit_source_map=[],
        emit_debug_yaml=[],
    )

    with caplog.at_level("ERROR"):
        result = compile_workflow(args)
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert result == 2
    assert captured.err == ""
    assert caplog.text == ""
    assert set(payload) == {"schema_version", "status", "diagnostics"}
    assert payload["schema_version"] == "workflow_lisp_compile_diagnostics.v1"
    assert payload["status"] == "rejected"
    assert [row["code"] for row in payload["diagnostics"]] == [
        "workflow_lisp_cli_input_unsupported"
    ]


def test_compile_diagnostics_json_preserves_full_compiler_rejection_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "candidate.orc"
    source.write_text(
        _minimal_compile_source(return_type="MissingResult"),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    result = compile_workflow(
        _minimal_compile_args(source, diagnostics_json=True)
    )
    payload = json.loads(capsys.readouterr().out)

    assert result == 2
    assert payload["status"] == "rejected"
    assert [row["code"] for row in payload["diagnostics"]] == ["type_unknown"]
    diagnostic = payload["diagnostics"][0]
    assert diagnostic["path"] == str(source)
    assert diagnostic["phase"] == "typecheck"
    assert diagnostic["validation_pass"] == "type"


def test_compile_diagnostics_json_identity_is_clone_root_independent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    identities: list[dict[str, object]] = []
    for name in ("clone-a", "clone-b"):
        root = tmp_path / name
        shutil.copytree(CALLABLE_SOURCE_ROOT, root)
        source = root / "neurips" / "entry.orc"
        monkeypatch.chdir(root)

        result = compile_workflow(
            _orc_compile_args(
                workflow=source,
                source_root=root,
                diagnostics_json=True,
            )
        )
        payload = json.loads(capsys.readouterr().out)

        assert result == 0, payload
        identities.append(payload["normalized_program_identity"])

    assert identities[0] == identities[1]


def test_compile_diagnostics_json_accepts_absolute_source_outside_cwd_without_source_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cwd = tmp_path / "caller"
    cwd.mkdir()
    monkeypatch.chdir(cwd)

    ordinary_args = _orc_compile_args(diagnostics_json=False)
    ordinary_args.source_root = None
    assert compile_workflow(ordinary_args) == 0
    capsys.readouterr()

    machine_args = _orc_compile_args(diagnostics_json=True)
    machine_args.source_root = None
    assert compile_workflow(machine_args) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "accepted"
    source_rows = payload["normalized_program_identity"][
        "compiler_source_revisions"
    ]
    assert any(row["root_role"] == "entry_source_root" for row in source_rows)
    assert all(not Path(row["relative_path"]).is_absolute() for row in source_rows)


def test_compile_diagnostics_json_identity_binds_imported_bundle_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    identities: list[dict[str, object]] = []
    for name in ("baseline", "changed-import"):
        root = tmp_path / name
        source_root = root / "source"
        cli_root = root / "cli"
        shutil.copytree(SOURCE_ROOT, source_root)
        shutil.copytree(CLI_FIXTURES, cli_root)
        if name == "changed-import":
            imported_source = cli_root / "imported_selector.orc"
            imported_source.write_text(
                imported_source.read_text(encoding="utf-8") + "\n",
                encoding="utf-8",
            )
        monkeypatch.chdir(root)

        result = compile_workflow(
            _orc_compile_args(
                workflow=source_root / "neurips" / "entry.orc",
                source_root=source_root,
                provider_externs_file=cli_root / "providers.json",
                prompt_externs_file=cli_root / "prompts.json",
                imported_workflow_bundles_file=(
                    cli_root / "imported_workflow_bundles.json"
                ),
                command_boundaries_file=cli_root / "commands.json",
                diagnostics_json=True,
            )
        )
        payload = json.loads(capsys.readouterr().out)

        assert result == 0, payload
        identities.append(payload["normalized_program_identity"])

    assert identities[0] != identities[1]


def test_compile_diagnostics_json_normalizes_absolute_imported_bundle_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    identities: list[dict[str, object]] = []
    for name in ("clone-a", "clone-b"):
        root = tmp_path / name
        source_root = root / "source"
        shutil.copytree(SOURCE_ROOT, source_root)
        imported_source = root / "imported_selector.orc"
        shutil.copy2(CLI_FIXTURES / "imported_selector.orc", imported_source)
        imported_manifest = root / "imports.json"
        imported_manifest.write_text(
            json.dumps(
                {
                    "selector-run": {
                        "kind": "compiled",
                        "path": str(imported_source),
                    }
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(root)

        result = compile_workflow(
            _orc_compile_args(
                workflow=source_root / "neurips" / "entry.orc",
                source_root=source_root,
                imported_workflow_bundles_file=imported_manifest,
                diagnostics_json=True,
            )
        )
        payload = json.loads(capsys.readouterr().out)

        assert result == 0, payload
        identities.append(payload["normalized_program_identity"])

    assert identities[0] == identities[1]


def test_compile_diagnostics_json_closes_io_failures_as_machine_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    compile_module = importlib.import_module("orchestrator.cli.commands.compile")

    def fail_build(_request: object) -> None:
        raise OSError("fixture I/O failure")

    monkeypatch.setattr(compile_module, "build_frontend_bundle", fail_build)

    with caplog.at_level("ERROR"):
        result = compile_workflow(
            _orc_compile_args(diagnostics_json=True)
        )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert result == 2
    assert captured.err == ""
    assert caplog.text == ""
    assert [row["code"] for row in payload["diagnostics"]] == [
        "workflow_lisp_cli_io_error"
    ]


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


def test_help_omits_retired_migration_generators_but_keeps_route_readiness() -> None:
    help_text = create_parser().format_help()

    assert "migration-parity" not in help_text
    assert "workflow-lisp-migration-parity" not in help_text
    assert "workflow-lisp-post-wcc-inventory" not in help_text
    assert "workflow-lisp-route-readiness" in help_text


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


def test_run_workflow_orc_public_binding_excludes_managed_write_roots(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    commands_manifest = tmp_path / "cycle_guard.commands.json"
    commands_manifest.write_text(
        json.dumps(
            {
                "emit_cycle_guard_summary": {
                    "kind": "external_tool",
                    "stable_command": [
                        "python",
                        "scripts/workflow_lisp_migrations/emit_cycle_guard_summary.py",
                    ],
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    args = _orc_run_args(
        workflow=CYCLE_GUARD_ENTRYPOINT,
        source_root=CYCLE_GUARD_SOURCE_ROOT,
        input_values=[
            "terminal_status=FAILED_CLOSED_BY_GUARD",
            "guard_cycles=2",
        ],
    )
    args.entry_workflow = "cycle-guard-demo"
    args.provider_externs_file = None
    args.prompt_externs_file = None
    args.imported_workflow_bundles_file = None
    args.command_boundaries_file = str(commands_manifest)

    result = run_workflow(args)

    assert result == 0
    assert not (tmp_path / ".orchestrate" / "runs").exists()


def test_run_workflow_kiss_backlog_item_dry_run_accepts_only_typed_backlog_inputs(
    monkeypatch,
) -> None:
    monkeypatch.chdir(REPO_ROOT)

    result = run_workflow(
        _kiss_run_args(
            input_values=[
                "backlog-inputs__backlog_item=docs/backlog/active/2026-05-29-workflow-lisp-effectful-composition-lowering.md",
                "backlog-inputs__work_instructions=docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md",
            ]
        )
    )

    assert result == 0


def test_run_workflow_rejects_non_orc_before_creating_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = run_workflow(_legacy_run_args())

    assert result == 1
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
            emit_executable_ir=[None],
            emit_core_ast=[None],
            emit_runtime_plan=["exports/runtime_plan.snapshot.json"],
            emit_semantic_ir=["exports/semantic_ir.snapshot.json"],
            emit_source_map=[None],
            emit_debug_yaml=[None],
        )
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert result == 0
    assert captured.out == json.dumps(payload, indent=2, sort_keys=True) + "\n"
    assert (tmp_path / "executable_ir.json").exists()
    assert (tmp_path / "core_workflow_ast.json").exists()
    assert (tmp_path / "exports" / "runtime_plan.snapshot.json").exists()
    assert (tmp_path / "source_map.json").exists()
    assert (tmp_path / "expanded.debug.yaml").exists()
    assert (tmp_path / "exports" / "semantic_ir.snapshot.json").exists()
    assert payload["artifact_paths"]["executable_ir"].endswith("/executable_ir.json")
    assert payload["artifact_paths"]["core_workflow_ast"].endswith("/core_workflow_ast.json")
    assert payload["exported_artifacts"] == {
        "executable_ir": str((tmp_path / "executable_ir.json").resolve()),
        "core_workflow_ast": str((tmp_path / "core_workflow_ast.json").resolve()),
        "expanded_debug_yaml": str((tmp_path / "expanded.debug.yaml").resolve()),
        "runtime_plan": str((tmp_path / "exports" / "runtime_plan.snapshot.json").resolve()),
        "semantic_ir": str((tmp_path / "exports" / "semantic_ir.snapshot.json").resolve()),
        "source_map": str((tmp_path / "source_map.json").resolve()),
    }
    assert payload["artifact_paths"]["executable_ir"] != payload["exported_artifacts"]["executable_ir"]
    assert payload["artifact_paths"]["core_workflow_ast"] != payload["exported_artifacts"]["core_workflow_ast"]


@pytest.mark.parametrize("command_name", ["compile", "explain", "run"])
@pytest.mark.parametrize(
    "prompt_manifest",
    [
        CLI_FIXTURES / "prompts.asset-file-object.json",
        CLI_FIXTURES / "prompts.input-file.json",
    ],
)
def test_prompt_extern_object_manifest_cli_commands_accept_explicit_source_fixtures(
    tmp_path: Path,
    command_name: str,
    prompt_manifest: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    workspace_prompt = tmp_path / "prompts" / "workspace" / "implementation" / "execute.md"
    workspace_prompt.parent.mkdir(parents=True, exist_ok=True)
    workspace_prompt.write_text("workspace prompt\n", encoding="utf-8")

    if command_name == "compile":
        args = _orc_compile_args(prompt_externs_file=prompt_manifest)
        command = compile_workflow
    elif command_name == "explain":
        args = _orc_explain_args()
        command = explain_workflow
    else:
        report_path = tmp_path / "artifacts" / "work" / "existing-report.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("ok\n", encoding="utf-8")
        args = _orc_run_args(
            input_values=[
                "input__status=ready",
                "input__report=artifacts/work/existing-report.md",
                "report_path=artifacts/work/existing-report.md",
            ]
        )
        command = run_workflow

    args.prompt_externs_file = str(prompt_manifest)
    result = command(args)
    capsys.readouterr()
    assert result == 0


@pytest.mark.parametrize("command_name", ["compile", "explain", "run"])
def test_prompt_extern_object_entry_invalid_cli_commands_report_frontend_diagnostics(
    tmp_path: Path,
    command_name: str,
    monkeypatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.chdir(tmp_path)
    manifest_path = tmp_path / "prompts.invalid-object.json"
    manifest_path.write_text(
        json.dumps(
            {
                "prompts.implementation.execute": {
                    "asset_file": "tests/fixtures/workflow_lisp/valid/prompts/implementation/execute.md",
                    "input_file": "prompts/workspace/implementation/execute.md",
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    if command_name == "compile":
        args = _orc_compile_args()
    elif command_name == "explain":
        args = _orc_explain_args()
    else:
        report_path = tmp_path / "artifacts" / "work" / "existing-report.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("ok\n", encoding="utf-8")
        args = _orc_run_args(
            input_values=[
                "input__status=ready",
                "input__report=artifacts/work/existing-report.md",
                "report_path=artifacts/work/existing-report.md",
            ]
        )
    args.prompt_externs_file = str(manifest_path)

    command = compile_workflow if command_name == "compile" else explain_workflow if command_name == "explain" else run_workflow
    with caplog.at_level("ERROR"):
        result = command(args)

    assert result == 2
    assert "[workflow_lisp_manifest_invalid]" in caplog.text
    assert "prompt externs manifest entries" in caplog.text
    assert "Traceback" not in caplog.text


def test_explain_workflow_exports_compilation_scoped_artifacts_for_selected_imported_target(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    result = explain_workflow(
        _orc_explain_args(
            form="selector-run",
            emit_executable_ir=[None],
            emit_core_ast=[None],
            emit_runtime_plan=["exports/runtime_plan.json"],
            emit_semantic_ir=["exports/semantic_ir.json"],
        )
    )
    captured = capsys.readouterr()
    exported_executable_ir = json.loads((tmp_path / "executable_ir.json").read_text(encoding="utf-8"))
    exported_core_ast = json.loads((tmp_path / "core_workflow_ast.json").read_text(encoding="utf-8"))
    exported_runtime_plan = json.loads((tmp_path / "exports" / "runtime_plan.json").read_text(encoding="utf-8"))
    exported_semantic_ir = json.loads((tmp_path / "exports" / "semantic_ir.json").read_text(encoding="utf-8"))

    assert result == 0
    assert "Form: selector-run" in captured.out
    assert "Emitted artifacts:" in captured.out
    assert str((tmp_path / "executable_ir.json").resolve()) in captured.out
    assert str((tmp_path / "core_workflow_ast.json").resolve()) in captured.out
    assert str((tmp_path / "exports" / "runtime_plan.json").resolve()) in captured.out
    assert str((tmp_path / "exports" / "semantic_ir.json").resolve()) in captured.out
    assert exported_executable_ir["schema_version"] == "workflow_executable_ir.v1"
    assert exported_core_ast["workflow_name"] == "neurips/entry::orchestrate"
    assert exported_runtime_plan["schema_version"] == "workflow_runtime_plan.v1"
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
                workflow="legacy-workflow.yaml",
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
                workflow="legacy-workflow.yaml",
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
            (
                "prompt externs manifest entries must map non-empty string names to string values "
                "or objects with exactly one of `asset_file` or `input_file`"
            ),
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


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["peer-ready"], {"command": "peer-ready"}),
        (
            ["peer-send", "target-binding", "hello peer"],
            {
                "command": "peer-send",
                "target_binding": "target-binding",
                "message": "hello peer",
            },
        ),
        (
            ["peer-ack", "message-1"],
            {"command": "peer-ack", "message_id": "message-1"},
        ),
        (["peer-finish"], {"command": "peer-finish"}),
    ],
)
def test_peer_cli_parser_exposes_only_bound_member_arguments(
    argv: list[str],
    expected: dict[str, str],
) -> None:
    parser = create_parser()
    command_action = next(
        action for action in parser._actions if action.dest == "command"
    )

    assert {
        name for name in command_action.choices if name.startswith("peer-")
    } == {"peer-ready", "peer-send", "peer-ack", "peer-finish"}
    assert vars(parser.parse_args(argv)) == expected
    assert {
        option
        for action in command_action.choices[argv[0]]._actions
        for option in action.option_strings
    } == {"-h", "--help"}


@pytest.mark.parametrize(
    ("argv", "handler_name", "expected_kwargs"),
    [
        (["peer-ready"], "peer_ready_workflow", {}),
        (
            ["peer-send", "target-binding", "hello peer"],
            "peer_send_workflow",
            {"target_binding": "target-binding", "message": "hello peer"},
        ),
        (
            ["peer-ack", "message-1"],
            "peer_ack_workflow",
            {"message_id": "message-1"},
        ),
        (["peer-finish"], "peer_finish_workflow", {}),
    ],
)
def test_peer_cli_dispatches_to_thin_client_handler(
    argv: list[str],
    handler_name: str,
    expected_kwargs: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, str]] = []

    def fake_handler(**kwargs: str) -> int:
        calls.append(kwargs)
        return 23

    monkeypatch.setattr(
        f"orchestrator.cli.commands.{handler_name}",
        fake_handler,
    )

    assert main(argv) == 23
    assert calls == [expected_kwargs]


def test_peer_cli_handler_prints_the_coordinator_receipt(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from orchestrator.cli.commands import peer as peer_commands
    from orchestrator.workflow.provider_peer_group.models import (
        PeerReadyReceipt,
    )

    monkeypatch.setattr(
        peer_commands,
        "peer_ready",
        lambda *, request_id: PeerReadyReceipt(request_id),
    )

    assert peer_commands.peer_ready_workflow() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "schema_version": "provider_peer_protocol.v1",
        "kind": "ready",
        "request_id": payload["request_id"],
        "status": "active",
    }
    assert payload["request_id"].startswith("peer-client-")


def test_peer_cli_handler_maps_a_closed_endpoint_to_nonzero(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from orchestrator.cli.commands import peer as peer_commands
    from orchestrator.workflow.provider_peer_group.protocol import (
        PeerProtocolClosedError,
    )

    def closed(*, request_id: str):
        del request_id
        raise PeerProtocolClosedError("closed")

    monkeypatch.setattr(peer_commands, "peer_ready", closed)

    assert peer_commands.peer_ready_workflow() == 2
    assert "peer request failed: closed" in capsys.readouterr().err
