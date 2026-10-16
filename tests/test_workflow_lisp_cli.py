from __future__ import annotations

import importlib
import json
import shutil
from argparse import Namespace
from pathlib import Path

import pytest

from orchestrator.cli.commands.compile import compile_workflow
from orchestrator.cli.commands.run import run_workflow
from orchestrator.cli.main import create_parser, main
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
from orchestrator.contracts.closed_program.program import ClosedProgram
from orchestrator.contracts.closed_program.sites import _ast_nodes


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp"
CLI_FIXTURES = FIXTURES / "cli"
ENTRYPOINT = CLI_FIXTURES / "current" / "neurips" / "entry.orc"
SOURCE_ROOT = FIXTURES / "modules" / "valid" / "imported_bundle_mix"
CALLABLE_SOURCE_ROOT = FIXTURES / "modules" / "valid" / "callables"
RETIRED_EXAMPLES = FIXTURES / "retired_examples"
CURRENT_EXAMPLES = FIXTURES / "current_examples"
KISS_ENTRYPOINT = CURRENT_EXAMPLES / "kiss_backlog_item.orc"
KISS_PROVIDERS = RETIRED_EXAMPLES / "inputs" / "kiss_backlog_item" / "providers.json"
KISS_PROMPTS = RETIRED_EXAMPLES / "inputs" / "kiss_backlog_item" / "prompts.json"
CYCLE_GUARD_ENTRYPOINT = CURRENT_EXAMPLES / "cycle_guard_demo.orc"
CYCLE_GUARD_SOURCE_ROOT = CURRENT_EXAMPLES


def _build_module():
    return importlib.import_module("orchestrator.workflow_lisp.build")


def _write_current_inputs(tmp_path: Path) -> Path:
    report = "artifacts/work/existing-report.md"
    path = tmp_path / "inputs.json"
    path.write_text(json.dumps({
        "input": {"status": "ready", "report": report}, "report_path": report,
    }))
    return path


def _orc_run_args(
    *,
    workflow: Path = ENTRYPOINT,
    source_root: Path = SOURCE_ROOT,
    imported_workflow_bundles_file: Path = CLI_FIXTURES / "imported_workflow_bundles.json",
    dry_run: bool = True,
    input_values: list[str] | None = None,
    input_file: Path | None = None,
) -> Namespace:
    return Namespace(
        workflow=str(workflow),
        context=None,
        context_file=None,
        input=input_values,
        input_file=str(input_file) if input_file else None,
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
        command_boundaries_file=str(CLI_FIXTURES / "commands.closed.json"),
        emit_debug_yaml=False,
    )


def _orc_compile_args(
    *,
    workflow: Path = ENTRYPOINT,
    source_root: Path = SOURCE_ROOT,
    provider_externs_file: Path = CLI_FIXTURES / "providers.json",
    prompt_externs_file: Path = CLI_FIXTURES / "prompts.json",
    imported_workflow_bundles_file: Path = CLI_FIXTURES / "imported_workflow_bundles.json",
    command_boundaries_file: Path = CLI_FIXTURES / "commands.closed.json",
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
  (:target-dsl "2.35")
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
            str(CLI_FIXTURES / "commands.closed.json"),
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
            str(CLI_FIXTURES / "commands.closed.json"),
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
    assert set(payload) == {"status", "program_digest", "build_key"}
    assert payload["status"] == "accepted"
    assert payload["program_digest"].startswith("sha256:")
    assert len(payload["build_key"]) == 16


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
        identities.append({key: payload[key] for key in ("program_digest", "build_key")})

    assert identities[0] == identities[1]


def test_compile_diagnostics_json_accepts_absolute_source_outside_cwd_without_source_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cwd = tmp_path / "caller"
    cwd.mkdir()
    monkeypatch.chdir(cwd)

    source_root = tmp_path / "absolute-source"
    shutil.copytree(SOURCE_ROOT, source_root)
    source = source_root / "neurips" / "entry.orc"

    ordinary_args = _orc_compile_args(workflow=source, diagnostics_json=False)
    ordinary_args.source_root = None
    assert compile_workflow(ordinary_args) == 0
    capsys.readouterr()

    machine_args = _orc_compile_args(workflow=source, diagnostics_json=True)
    machine_args.source_root = None
    assert compile_workflow(machine_args) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "accepted"
    assert payload["program_digest"].startswith("sha256:")
    assert len(payload["build_key"]) == 16


def test_compile_diagnostics_json_build_key_binds_imported_source_bytes(
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
        entry = source_root / "neurips" / "entry.orc"

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
                command_boundaries_file=cli_root / "commands.closed.json",
                diagnostics_json=True,
            )
        )
        payload = json.loads(capsys.readouterr().out)

        assert result == 0, payload
        identities.append({key: payload[key] for key in ("program_digest", "build_key")})

    assert identities[0]["program_digest"] == identities[1]["program_digest"]
    assert identities[0]["build_key"] != identities[1]["build_key"]


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
        entry = source_root / "neurips" / "entry.orc"

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
        identities.append({key: payload[key] for key in ("program_digest", "build_key")})

    assert identities[0] == identities[1]


def test_compile_diagnostics_json_closes_io_failures_as_machine_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    compile_module = importlib.import_module("orchestrator.cli.commands.compile")

    def fail_build(_request: object, **_kwargs: object) -> None:
        raise OSError("fixture I/O failure")

    monkeypatch.setattr(compile_module, "build_closed_program_bundle", fail_build)

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
            str(CLI_FIXTURES / "commands.closed.json"),
            "--dry-run",
        ]
    )

    assert args.entry_workflow == "orchestrate"
    assert args.source_root == [str(SOURCE_ROOT)]
    assert args.provider_externs_file == str(CLI_FIXTURES / "providers.json")
    assert args.imported_workflow_bundles_file == str(CLI_FIXTURES / "imported_workflow_bundles.json")
    assert args.command_boundaries_file == str(CLI_FIXTURES / "commands.closed.json")
    assert args.dry_run is True


def test_help_omits_retired_migration_generators_but_keeps_route_readiness() -> None:
    help_text = create_parser().format_help()

    assert "migration-parity" not in help_text
    assert "workflow-lisp-migration-parity" not in help_text
    assert "workflow-lisp-post-wcc-inventory" not in help_text
    assert "workflow-lisp-route-readiness" in help_text


def test_run_workflow_supports_orc_dry_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    report_path = tmp_path / "artifacts" / "work" / "existing-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("ok\n", encoding="utf-8")

    result = run_workflow(
        _orc_run_args(
            input_file=_write_current_inputs(tmp_path)
        )
    )

    assert result.exit_code == 0
    assert not (tmp_path / ".orchestrate" / "runs").exists()


def test_run_workflow_orc_dry_run_requires_bound_inputs(tmp_path: Path, monkeypatch, caplog) -> None:
    monkeypatch.chdir(tmp_path)

    result = run_workflow(_orc_run_args())

    assert result.exit_code == 2
    assert "Workflow input binding failed" in caplog.text
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
                    "closure": [],
                }
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    current_entry = tmp_path / "cycle_guard_demo.orc"
    current_entry.write_text(CYCLE_GUARD_ENTRYPOINT.read_text())
    args = _orc_run_args(
        workflow=current_entry,
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

    assert result.exit_code == 0
    assert not (tmp_path / ".orchestrate" / "runs").exists()


def test_run_workflow_kiss_backlog_item_dry_run_accepts_only_typed_backlog_inputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    # New public consumer; std/phase and all original producer modules stay intact.
    source = tmp_path / "kiss_backlog_item.orc"
    source.write_text(KISS_ENTRYPOINT.read_text())
    inputs = tmp_path / "backlog-inputs.json"
    inputs.write_text(json.dumps({"backlog-inputs": {
        "backlog_item": "docs/backlog/active/2026-05-29-workflow-lisp-effectful-composition-lowering.md",
        "work_instructions": "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md",
    }}))
    args = _kiss_run_args()
    args.workflow = str(source)
    args.input_file = str(inputs)
    result = run_workflow(args)
    assert result.exit_code == 0


def test_run_workflow_rejects_non_orc_before_creating_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    result = run_workflow(_legacy_run_args())

    assert result.exit_code == 1
    assert not (tmp_path / ".orchestrate" / "runs").exists()


@pytest.mark.parametrize("command_name", ["compile", "run"])
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
    else:
        report_path = tmp_path / "artifacts" / "work" / "existing-report.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("ok\n", encoding="utf-8")
        args = _orc_run_args(
            input_file=_write_current_inputs(tmp_path)
        )
        command = run_workflow

    args.prompt_externs_file = str(prompt_manifest)
    result = command(args)
    capsys.readouterr()
    assert getattr(result, "exit_code", result) == 0
    [artifact] = (tmp_path / ".orchestrate" / "build").glob("*/closed_program.json")
    program = ClosedProgram.from_artifact(artifact.read_text())
    effects = [node for definition in program.tree["definitions"].values()
               for node in _ast_nodes(definition["body"])
               if node.get("class") == "provider"]
    assert len(effects) == 1
    assert effects[0]["provider"] == "test-provider"
    expected_kind = "input_file" if prompt_manifest.name == "prompts.input-file.json" else "asset_file"
    assert effects[0]["prompt"]["source_kind"] == expected_kind


@pytest.mark.parametrize("command_name", ["compile", "run"])
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
    else:
        report_path = tmp_path / "artifacts" / "work" / "existing-report.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("ok\n", encoding="utf-8")
        args = _orc_run_args(
            input_file=_write_current_inputs(tmp_path)
        )
    args.prompt_externs_file = str(manifest_path)

    command = compile_workflow if command_name == "compile" else run_workflow
    with caplog.at_level("ERROR"):
        result = command(args)

    assert getattr(result, "exit_code", result) == 2
    assert "[workflow_lisp_manifest_invalid]" in caplog.text
    assert "prompt externs manifest entries" in caplog.text
    assert "Traceback" not in caplog.text


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
            input_file=_write_current_inputs(tmp_path),
        )
    )

    assert result.exit_code != 0


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


@pytest.mark.parametrize(
    "command_name",
    ["compile", "run"],
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
    else:
        command = run_workflow
        args = _orc_run_args(
            input_file=_write_current_inputs(tmp_path)
        )
        args.provider_externs_file = "does/not/exist.providers.json"

    with caplog.at_level("ERROR"):
        result = command(args)

    assert getattr(result, "exit_code", result) == 2
    assert "[workflow_lisp_manifest_missing]" in caplog.text
    assert "provider externs manifest does not exist" in caplog.text
    assert "Traceback" not in caplog.text


@pytest.mark.parametrize(
    "command_name",
    ["compile", "run"],
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
    else:
        command = run_workflow
        args = _orc_run_args(
            input_file=_write_current_inputs(tmp_path)
        )
        args.provider_externs_file = str(invalid_manifest)

    with caplog.at_level("ERROR"):
        result = command(args)

    assert getattr(result, "exit_code", result) == 2
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
    ["compile", "run"],
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
    else:
        command = run_workflow
        args = _orc_run_args(
            input_file=_write_current_inputs(tmp_path)
        )

    setattr(args, manifest_flag, str(manifest_path))

    with caplog.at_level("ERROR"):
        result = command(args)

    assert getattr(result, "exit_code", result) == 2
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


def test_build_service_infers_single_exported_entry_workflow(tmp_path: Path) -> None:
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")

    source_dir = tmp_path / "single"
    source_dir.mkdir()
    source_path = source_dir / "entry.orc"
    source_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
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
        workspace_root=tmp_path,
    )

    result = build_closed_program_bundle(request)

    assert result.entry_workflow == "single/entry::only"
    assert result.typed_program.entry.definition.name == result.entry_workflow


def test_build_service_requires_entry_workflow_for_multi_workflow_module(tmp_path: Path) -> None:
    build = _build_module()
    request_cls = getattr(build, "FrontendBuildRequest")

    source_dir = tmp_path / "multiple"
    source_dir.mkdir()
    source_path = source_dir / "entry.orc"
    source_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.35")',
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
        workspace_root=tmp_path,
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_closed_program_bundle(request)

    assert excinfo.value.diagnostics[0].code == "entry_workflow_required"


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

    compile_args = _orc_compile_args()
    request = getattr(build, "FrontendBuildRequest")(
        source_path=ENTRYPOINT,
        source_roots=(SOURCE_ROOT,),
        entry_workflow="orchestrate",
        provider_externs_path=Path(compile_args.provider_externs_file),
        prompt_externs_path=Path(compile_args.prompt_externs_file),
        imported_workflow_bundles_path=Path(compile_args.imported_workflow_bundles_file),
        command_boundaries_path=Path(compile_args.command_boundaries_file),
        workspace_root=tmp_path,
    )
    request = type(request)(
        **{
            **request.__dict__,
            manifest_flag.replace("_file", "_path"): manifest_path,
        }
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_closed_program_bundle(request)

    assert excinfo.value.diagnostics[0].code == "workflow_lisp_manifest_missing"
    assert "does not exist" in excinfo.value.diagnostics[0].message


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
        workspace_root=tmp_path,
    )
    build_request = type(build_request)(
        **{
            **build_request.__dict__,
            manifest_flag.replace("_file", "_path"): invalid_manifest,
        }
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_closed_program_bundle(build_request)

    assert excinfo.value.diagnostics[0].code == "workflow_lisp_manifest_invalid_json"
    assert "must contain valid JSON" in excinfo.value.diagnostics[0].message
