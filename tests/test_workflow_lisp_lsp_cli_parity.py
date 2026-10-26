from __future__ import annotations

from dataclasses import fields, replace
import hashlib
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrator.lsp import compile_driver, state as lsp_state
from orchestrator.workflow_lisp import build
from orchestrator.workflow_lisp.diagnostics import (
    LispFrontendDiagnostic,
    with_diagnostic_metadata,
)
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.syntax import ExpansionFrame, HelperExpansionFrame


REPO_ROOT = Path(__file__).resolve().parent.parent
ENTRY_FIXTURE = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "workflow_lisp"
    / "valid"
    / "entry_publication_runtime.orc"
)
IMPORTED_SOURCE_ROOT = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "workflow_lisp"
    / "modules"
    / "valid"
    / "imported_bundle_mix"
)
IMPORTED_ENTRY = IMPORTED_SOURCE_ROOT / "neurips" / "entry.orc"
CLI_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp" / "cli"
L3_ENTRY_SELECTION_ROOT = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "workflow_lisp"
    / "modules"
    / "valid"
    / "lsp_l3_entry_selection"
)
REQUEST_IDENTITY_FIELDS = (
    "source_path",
    "workspace_root",
    "source_roots",
    "entry_workflow",
    "validation_profile",
    "boundary_admission_profile",
    "lint_profile",
    "provider_externs",
    "prompt_externs",
    "command_boundaries",
    "imported_workflow_bundles",
)
_MISSING = object()


def _make_cli_lsp_workspace(
    tmp_path: Path,
    *,
    explicit_source_roots: bool,
) -> tuple[Path, Path, tuple[Path, ...]]:
    workspace = tmp_path / "workspace"
    source_root = workspace / "src" if explicit_source_roots else workspace
    source_root.mkdir(parents=True)
    entry_path = source_root / ENTRY_FIXTURE.name
    entry_path.write_text('''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule entry_publication_runtime) (export entry-publication-runtime)
      (defworkflow entry-publication-runtime () -> Int 1))''')
    caller_roots = (
        (source_root.resolve(), workspace.resolve())
        if explicit_source_roots
        else ()
    )
    return workspace.resolve(), entry_path.resolve(), caller_roots


def _observe_real_cli_and_lsp_captures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    explicit_source_roots: bool,
    command_boundaries_payload: dict[str, object] | None = None,
):
    workspace, entry_path, caller_roots = _make_cli_lsp_workspace(
        tmp_path, explicit_source_roots=explicit_source_roots,
    )
    run_command = importlib.import_module("orchestrator.cli.commands.run")
    evaluated_command = importlib.import_module("orchestrator.cli.commands.evaluated")
    cli_main = importlib.import_module("orchestrator.cli.main")
    compiler = importlib.import_module("orchestrator.workflow_lisp.compiler")
    production_build = evaluated_command.build_closed_program_bundle
    observed_builds = []
    effective_root_observations = []
    production_roots = compiler._effective_source_roots

    def observe_roots(path, **kwargs):
        result = production_roots(path, **kwargs)
        effective_root_observations.append(result)
        return result

    def observe_build(request, **kwargs):
        result = production_build(request, **kwargs)
        observed_builds.append((request, result))
        return result

    monkeypatch.setattr(evaluated_command, "build_closed_program_bundle", observe_build)
    monkeypatch.setattr(compiler, "_effective_source_roots", observe_roots)
    monkeypatch.chdir(workspace)
    argv = ["run", str(entry_path), "--entry-workflow", "entry-publication-runtime", "--dry-run", "--quiet"]
    command_boundaries_path = None
    if command_boundaries_payload is not None:
        command_boundaries_path = workspace / "commands.json"
        command_boundaries_path.write_text(json.dumps(command_boundaries_payload), encoding="utf-8")
        argv.extend(("--command-boundaries-file", str(command_boundaries_path)))
    for root in caller_roots:
        argv.extend(("--source-root", str(root)))
    assert run_command.run_workflow(cli_main.create_parser().parse_args(argv)).exit_code == 0
    [(cli_request, cli_result)] = observed_builds
    before_lsp = {path.relative_to(workspace): path.read_bytes()
        for path in workspace.rglob("*") if path.is_file()}
    driver = compile_driver.initialize_compile_driver(lsp_state.initialize_lsp_state(
        root_uri=workspace.as_uri(), initialization_options={
            "entry_workflows": {str(entry_path): "entry-publication-runtime"},
            "source_roots": caller_roots,
            **({"command_boundaries_path": command_boundaries_path} if command_boundaries_path else {}),
        },
    ))
    driver.apply_transition(lsp_state.open_entry(driver.state,
        document_uri=entry_path.as_uri(), editor_text=entry_path.read_text(),
        disk_snapshot=compile_driver.probe_disk_source(entry_path)))
    driver.drain()
    accepted = driver.state.entries[0].accepted_snapshot
    assert accepted is not None
    assert before_lsp == {path.relative_to(workspace): path.read_bytes()
        for path in workspace.rglob("*") if path.is_file()}
    assert not (workspace / ".orchestrate" / "runs").exists()
    return (
        cli_request,
        cli_result,
        accepted.build_value,
        tuple(effective_root_observations),
        workspace,
        entry_path,
        caller_roots,
        driver,
    )


@pytest.mark.parametrize("explicit_source_roots", (False, True))
def test_real_evaluated_dry_run_and_lsp_consume_the_same_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, explicit_source_roots: bool,
) -> None:
    cli_request, cli_result, lsp_result, observations, workspace, entry_path, caller_roots, _driver = _observe_real_cli_and_lsp_captures(
        tmp_path, monkeypatch, explicit_source_roots=explicit_source_roots,
    )
    capture = lsp_result.compile_request_capture
    assert (cli_request.source_path, cli_request.workspace_root, cli_request.source_roots,
        cli_request.entry_workflow) == (capture.source_path, capture.workspace_root,
        capture.source_roots, capture.entry_workflow)
    configuration = cli_result.typed_program.configuration_bindings
    assert configuration["provider_externs"] == capture.provider_externs
    assert configuration["prompt_externs"] == capture.prompt_externs
    assert configuration["command_boundaries"] == capture.command_boundaries
    assert cli_result.typed_program.imported_programs == capture.imported_workflow_bundles == {}
    assert cli_result.typed_program.source_file_digests == lsp_result.compile_result.entry_result.typed_program.source_file_digests
    assert cli_result.typed_program.target == lsp_result.compile_result.entry_result.typed_program.target == "2.35"
    assert cli_result.entry_workflow == lsp_result.selected_workflow_name
    assert _diagnostic_identities(cli_result.compile_diagnostics) == _diagnostic_identities(lsp_result.diagnostics)
    builtin_root = compile_driver.compiler._builtin_stdlib_source_root().resolve()
    expected = ((caller_roots[0], builtin_root, caller_roots[1])
        if explicit_source_roots else (workspace, builtin_root))
    assert observations == (expected, expected)
    assert capture.source_path == entry_path
    assert capture.source_roots == caller_roots
    assert builtin_root not in capture.source_roots
    assert builtin_root != workspace


def test_shared_command_manifest_is_frozen_and_expanded_for_real_cli_and_lsp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "$schema": "workflow-command-boundaries.v1",
        "shared_closure": ["common.py"],
        "commands": {
            "unused": {"stable_command": ["python", "unused.py"]},
        },
    }
    cli_request, cli_result, lsp_result, _observations, workspace, _entry, _roots, driver = (
        _observe_real_cli_and_lsp_captures(
            tmp_path,
            monkeypatch,
            explicit_source_roots=False,
            command_boundaries_payload=payload,
        )
    )
    initialization = driver.initialization_configuration
    frozen_manifest = initialization.command_boundary_manifest
    [command] = initialization.command_boundaries.values()
    capture = lsp_result.compile_request_capture
    manifest_path = (workspace / "commands.json").resolve()
    vector = driver.state.configuration_vector
    assert vector is not None

    assert cli_request.command_boundaries_path == manifest_path
    assert frozen_manifest["$schema"] == payload["$schema"]
    assert frozen_manifest["shared_closure"] == ("common.py",)
    assert frozen_manifest["commands"]["unused"]["stable_command"] == ("python", "unused.py")
    assert command.closure == ("common.py",)
    assert cli_result.typed_program.configuration_bindings["command_boundaries"] == capture.command_boundaries
    assert capture.command_boundaries["unused"].closure == ("common.py",)
    assert (
        manifest_path,
        f"sha256:{hashlib.sha256(manifest_path.read_bytes()).hexdigest()}",
    ) in vector.configuration_revisions


@pytest.mark.parametrize(
    ("source_name", "entry_workflow", "expected_cli_status"),
    (
        ("application.orc", "selected", 0),
        ("library.orc", None, 2),
    ),
    ids=("listed-application", "unlisted-library"),
)
def test_l3_listed_and_unlisted_requests_match_real_evaluated_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source_name: str,
    entry_workflow: str | None, expected_cli_status: int,
) -> None:
    workspace = (tmp_path / "workspace").resolve()
    source_root = workspace / "src"
    source_root.mkdir(parents=True)
    for fixture_name in ("application.orc", "library.orc"):
        (source_root / fixture_name).write_text((L3_ENTRY_SELECTION_ROOT / fixture_name).read_text())
    source_path = source_root / source_name
    roots = (source_root, workspace)
    run_command = importlib.import_module("orchestrator.cli.commands.run")
    evaluated_command = importlib.import_module("orchestrator.cli.commands.evaluated")
    cli_main = importlib.import_module("orchestrator.cli.main")
    compiler = importlib.import_module("orchestrator.workflow_lisp.compiler")
    production_build = evaluated_command.build_closed_program_bundle
    production_roots = compiler._effective_source_roots
    results, errors, requests, observations = [], [], [], []

    def observe_build(request, **kwargs):
        requests.append(request)
        try:
            result = production_build(request, **kwargs)
        except Exception as error:
            errors.append(error)
            raise
        results.append(result)
        return result

    def observe_roots(path, **kwargs):
        result = production_roots(path, **kwargs)
        observations.append(result)
        return result



    monkeypatch.setattr(evaluated_command, "build_closed_program_bundle", observe_build)
    monkeypatch.setattr(compiler, "_effective_source_roots", observe_roots)
    monkeypatch.chdir(workspace)
    argv = ["run", str(source_path), "--dry-run", "--quiet"]
    if entry_workflow is not None:
        argv.extend(("--entry-workflow", entry_workflow))
    for root in roots:
        argv.extend(("--source-root", str(root)))
    assert run_command.run_workflow(cli_main.create_parser().parse_args(argv)).exit_code == expected_cli_status
    before_lsp = {path.relative_to(workspace): path.read_bytes()
        for path in workspace.rglob("*") if path.is_file()}
    driver = compile_driver.initialize_compile_driver(lsp_state.initialize_lsp_state(
        root_uri=workspace.as_uri(), initialization_options={
            "source_roots": roots,
            "entry_workflows": {str(source_root / "application.orc"): "selected"},
        },
    ))
    driver.apply_transition(lsp_state.open_entry(driver.state,
        document_uri=source_path.as_uri(), editor_text=source_path.read_text(),
        disk_snapshot=compile_driver.probe_disk_source(source_path)))
    driver.drain()
    [entry] = driver.state.entries
    assert entry.compile_status == "success"
    lsp_result = entry.accepted_snapshot.build_value
    capture = lsp_result.compile_request_capture
    [request] = requests
    assert (request.source_path, request.workspace_root, request.source_roots, request.entry_workflow) == (
        capture.source_path, capture.workspace_root, capture.source_roots, capture.entry_workflow)
    assert capture.entry_workflow == entry_workflow
    assert before_lsp == {path.relative_to(workspace): path.read_bytes()
        for path in workspace.rglob("*") if path.is_file()}
    assert not (workspace / ".orchestrate" / "runs").exists()
    builtin_root = compiler._builtin_stdlib_source_root().resolve()
    assert observations == [(roots[0], builtin_root, roots[1])] * 2
    assert builtin_root not in capture.source_roots


@pytest.mark.parametrize("entry_text, expected_code", (
    ("(workflow-lisp\n", "frontend_parse_error"),
    ('''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule broken) (export run) (defworkflow run () -> Int "bad"))''', "return_type_mismatch"),
), ids=("parse-preflight", "typed-235"))
def test_real_broken_dry_run_and_lsp_share_request_and_diagnostic_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, entry_text: str, expected_code: str,
) -> None:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir()
    source_path = workspace / "broken.orc"
    source_path.write_text(entry_text)
    run_command = importlib.import_module("orchestrator.cli.commands.run")
    evaluated_command = importlib.import_module("orchestrator.cli.commands.evaluated")
    cli_main = importlib.import_module("orchestrator.cli.main")
    cli_errors, cli_requests = [], []
    production_refusal = run_command.refuse_retired_entry_target
    production_build = evaluated_command.build_closed_program_bundle

    def observe_refusal(*args, **kwargs):
        try:
            return production_refusal(*args, **kwargs)
        except build.LispFrontendCompileError as error:
            cli_errors.append(error)
            raise

    def observe_build(request, **kwargs):
        cli_requests.append(request)
        try:
            return production_build(request, **kwargs)
        except build.LispFrontendCompileError as error:
            cli_errors.append(error)
            raise

    monkeypatch.setattr(run_command, "refuse_retired_entry_target", observe_refusal)
    monkeypatch.setattr(evaluated_command, "build_closed_program_bundle", observe_build)
    monkeypatch.chdir(workspace)
    before = {path.relative_to(workspace): path.read_bytes() for path in workspace.rglob("*") if path.is_file()}
    args = cli_main.create_parser().parse_args(("run", str(source_path), "--dry-run", "--quiet"))
    assert run_command.run_workflow(args).exit_code == 2
    [cli_error] = cli_errors
    production_analysis = build.build_frontend_bundle_in_memory
    lsp_errors, lsp_requests = [], []

    def observe_analysis(request, **kwargs):
        lsp_requests.append(request)
        try:
            return production_analysis(request, **kwargs)
        except build.LispFrontendCompileError as error:
            lsp_errors.append(error)
            raise

    driver = compile_driver.initialize_compile_driver(lsp_state.initialize_lsp_state(root_uri=workspace.as_uri()),
        build_in_memory=observe_analysis)
    driver.apply_transition(lsp_state.open_entry(driver.state,
        document_uri=source_path.as_uri(), editor_text=entry_text,
        disk_snapshot=compile_driver.probe_disk_source(source_path)))
    driver.drain()
    [lsp_error] = lsp_errors
    assert cli_error.diagnostics[0].code == lsp_error.diagnostics[0].code == expected_code
    assert _diagnostic_identities(cli_error.diagnostics) == _diagnostic_identities(lsp_error.diagnostics)
    [lsp_request] = lsp_requests
    assert lsp_request.source_path == source_path
    assert lsp_request.workspace_root == workspace
    if expected_code == "frontend_parse_error":
        assert cli_requests == []
        assert _diagnostic_identities(cli_error.diagnostics)[0][1:6] == ("validation", "error", "read", "parse", "frontend")
    else:
        [cli_request] = cli_requests
        assert (cli_request.source_path, cli_request.workspace_root, cli_request.source_roots, cli_request.entry_workflow) == (
            lsp_request.source_path, lsp_request.workspace_root, lsp_request.source_roots, lsp_request.entry_workflow)
    assert before == {path.relative_to(workspace): path.read_bytes() for path in workspace.rglob("*") if path.is_file()}
    assert not (workspace / ".orchestrate").exists()


@pytest.fixture(scope="module")
def loaded_request_result(
    tmp_path_factory: pytest.TempPathFactory,
) -> build.FrontendInMemoryBuildResult:
    workspace = tmp_path_factory.mktemp("lsp-request-capture")
    return build.build_frontend_bundle_in_memory(
        build.FrontendBuildRequest(
            source_path=IMPORTED_ENTRY,
            source_roots=(IMPORTED_SOURCE_ROOT, CLI_FIXTURES),
            entry_workflow="orchestrate",
            provider_externs_path=CLI_FIXTURES / "providers.json",
            prompt_externs_path=CLI_FIXTURES / "prompts.json",
            imported_workflow_bundles_path=(
                CLI_FIXTURES / "imported_workflow_bundles.json"
            ),
            command_boundaries_path=CLI_FIXTURES / "commands.json",
            workspace_root=workspace,
        )
    )


def _assert_bidirectionally_distinct(left: object, right: object) -> None:
    assert left != right
    assert right != left


def test_request_capture_contains_all_loaded_identity_values(
    loaded_request_result: build.FrontendInMemoryBuildResult,
) -> None:
    capture = getattr(
        loaded_request_result,
        "compile_request_capture",
        _MISSING,
    )

    assert capture is not _MISSING, "the production build has no request capture"
    assert type(capture).__module__ == build.__name__
    assert tuple(field.name for field in fields(capture)) == REQUEST_IDENTITY_FIELDS
    assert capture.provider_externs
    assert capture.prompt_externs
    assert capture.command_boundaries
    assert capture.imported_workflow_bundles


@pytest.mark.parametrize(
    "root_mutation",
    (
        lambda roots, marker: (*roots, marker),
        lambda roots, _marker: roots[:-1],
        lambda roots, marker: (roots[0], marker),
        lambda roots, _marker: tuple(reversed(roots)),
    ),
    ids=("extra", "missing", "replaced", "reordered"),
)
def test_request_capture_rejects_every_source_root_shape_delta_in_both_directions(
    loaded_request_result: build.FrontendInMemoryBuildResult,
    tmp_path: Path,
    root_mutation,
) -> None:
    capture = getattr(
        loaded_request_result,
        "compile_request_capture",
        _MISSING,
    )
    assert capture is not _MISSING, "the production build has no request capture"
    mutated = replace(
        capture,
        source_roots=root_mutation(
            capture.source_roots,
            (tmp_path / "replacement-root").resolve(),
        ),
    )

    _assert_bidirectionally_distinct(capture, mutated)


@pytest.mark.parametrize(
    ("field_name", "replacement_value"),
    (
        ("source_path", Path("/replacement/source.orc")),
        ("workspace_root", Path("/replacement/workspace")),
        ("entry_workflow", "replacement-entry"),
        ("validation_profile", "frontend_only"),
        ("boundary_admission_profile", "transportable_child"),
        ("lint_profile", "replacement-lint"),
        ("provider_externs", (("replacement-provider", "value"),)),
        ("prompt_externs", (("replacement-prompt", "value"),)),
        ("command_boundaries", (("replacement-command", "value"),)),
        ("imported_workflow_bundles", (("replacement-import", "value"),)),
    ),
)
def test_request_capture_rejects_every_non_root_identity_delta_in_both_directions(
    loaded_request_result: build.FrontendInMemoryBuildResult,
    field_name: str,
    replacement_value: object,
) -> None:
    capture = getattr(
        loaded_request_result,
        "compile_request_capture",
        _MISSING,
    )
    assert capture is not _MISSING, "the production build has no request capture"
    mutated = replace(capture, **{field_name: replacement_value})

    _assert_bidirectionally_distinct(capture, mutated)


def _span(path: Path, *, start_offset: int, end_offset: int) -> SourceSpan:
    return SourceSpan(
        start=SourcePosition(
            path=str(path),
            line=2,
            column=3,
            offset=start_offset,
        ),
        end=SourcePosition(
            path=str(path),
            line=4,
            column=5,
            offset=end_offset,
        ),
    )


def _classified_diagnostic(tmp_path: Path) -> LispFrontendDiagnostic:
    source_span = _span(
        tmp_path / "source.orc",
        start_offset=7,
        end_offset=41,
    )
    macro_frame = ExpansionFrame(
        macro_name="expand-it",
        expansion_id="expansion-1",
        call_span=_span(
            tmp_path / "macro-call.orc",
            start_offset=11,
            end_offset=19,
        ),
        definition_span=_span(
            tmp_path / "macro-definition.orc",
            start_offset=23,
            end_offset=37,
        ),
        template_path=("template", "field"),
    )
    helper_frame = HelperExpansionFrame(
        function_name="normalize-it",
        call_span=_span(
            tmp_path / "helper-call.orc",
            start_offset=43,
            end_offset=47,
        ),
        definition_span=_span(
            tmp_path / "helper-definition.orc",
            start_offset=53,
            end_offset=61,
        ),
    )
    return with_diagnostic_metadata(
        LispFrontendDiagnostic(
            code="record_field_missing",
            message="wording is not identity",
            span=source_span,
            form_path=("workflow-lisp", "entry", "body"),
            expansion_stack=(macro_frame, helper_frame),
            notes=("notes are not identity",),
        ),
        validation_pass="type",
        authority_layer="frontend",
    )


def _diagnostic_identities(
    diagnostics: tuple[LispFrontendDiagnostic, ...],
) -> tuple[object, ...]:
    diagnostics_module = importlib.import_module(
        "orchestrator.workflow_lisp.diagnostics"
    )
    capture = getattr(
        diagnostics_module,
        "capture_frontend_diagnostic_identities",
        None,
    )
    assert callable(capture), (
        "workflow_lisp diagnostics lacks the production post-metadata "
        "diagnostic identity capture"
    )
    return capture(diagnostics)


def test_diagnostic_capture_preserves_complete_ordered_post_metadata_identity(
    tmp_path: Path,
) -> None:
    diagnostic = _classified_diagnostic(tmp_path)
    identity = _diagnostic_identities((diagnostic,))
    span_identity = (
        str(Path(diagnostic.span.start.path).resolve()),
        (2, 3, 7),
        (4, 5, 41),
    )

    assert identity == (
        (
            diagnostic.code,
            diagnostic.diagnostic_kind,
            diagnostic.severity or "error",
            diagnostic.phase,
            diagnostic.validation_pass,
            diagnostic.authority_layer,
            span_identity,
            diagnostic.form_path,
            (
                (
                    "macro",
                    "expand-it",
                    "expansion-1",
                    (
                        str((tmp_path / "macro-call.orc").resolve()),
                        (2, 3, 11),
                        (4, 5, 19),
                    ),
                    (
                        str((tmp_path / "macro-definition.orc").resolve()),
                        (2, 3, 23),
                        (4, 5, 37),
                    ),
                ),
                (
                    "helper",
                    "normalize-it",
                    None,
                    (
                        str((tmp_path / "helper-call.orc").resolve()),
                        (2, 3, 43),
                        (4, 5, 47),
                    ),
                    (
                        str((tmp_path / "helper-definition.orc").resolve()),
                        (2, 3, 53),
                        (4, 5, 61),
                    ),
                ),
            ),
        ),
    )


def test_diagnostic_capture_accepts_structural_frames_with_nullable_metadata(
    tmp_path: Path,
) -> None:
    diagnostic = replace(
        _classified_diagnostic(tmp_path),
        expansion_stack=(
            SimpleNamespace(
                macro_name="structural-macro",
                expansion_id=None,
                call_span=None,
                definition_span=_span(
                    tmp_path / "structural-macro-definition.orc",
                    start_offset=67,
                    end_offset=71,
                ),
            ),
            SimpleNamespace(
                function_name="structural-helper",
                call_span=_span(
                    tmp_path / "structural-helper-call.orc",
                    start_offset=73,
                    end_offset=79,
                ),
                definition_span=None,
            ),
        ),
    )

    identities = _diagnostic_identities((diagnostic,))

    assert identities[0][-1] == (
        (
            "macro",
            "structural-macro",
            None,
            None,
            (
                str(
                    (
                        tmp_path / "structural-macro-definition.orc"
                    ).resolve()
                ),
                (2, 3, 67),
                (4, 5, 71),
            ),
        ),
        (
            "helper",
            "structural-helper",
            None,
            (
                str((tmp_path / "structural-helper-call.orc").resolve()),
                (2, 3, 73),
                (4, 5, 79),
            ),
            None,
        ),
    )


@pytest.mark.parametrize(
    "mutate",
    (
        lambda diagnostic: replace(diagnostic, code="replacement-code"),
        lambda diagnostic: replace(
            diagnostic,
            diagnostic_kind="replacement-kind",
        ),
        lambda diagnostic: replace(diagnostic, severity="warning"),
        lambda diagnostic: replace(diagnostic, phase="replacement-phase"),
        lambda diagnostic: replace(
            diagnostic,
            validation_pass="replacement-pass",
        ),
        lambda diagnostic: replace(
            diagnostic,
            authority_layer="replacement-layer",
        ),
        lambda diagnostic: replace(
            diagnostic,
            span=replace(
                diagnostic.span,
                end=replace(diagnostic.span.end, offset=999),
            ),
        ),
        lambda diagnostic: replace(
            diagnostic,
            form_path=(*diagnostic.form_path, "replacement-form"),
        ),
        lambda diagnostic: replace(
            diagnostic,
            expansion_stack=tuple(reversed(diagnostic.expansion_stack)),
        ),
    ),
    ids=(
        "code",
        "diagnostic-kind",
        "severity",
        "phase",
        "validation-pass",
        "authority-layer",
        "raw-span-end",
        "form-path",
        "expansion-order",
    ),
)
def test_diagnostic_capture_rejects_every_identity_delta_in_both_directions(
    tmp_path: Path,
    mutate,
) -> None:
    diagnostic = _classified_diagnostic(tmp_path)
    original = _diagnostic_identities((diagnostic,))
    mutated = _diagnostic_identities((mutate(diagnostic),))

    _assert_bidirectionally_distinct(original, mutated)


def test_diagnostic_capture_preserves_diagnostic_sequence_order(
    tmp_path: Path,
) -> None:
    first = _classified_diagnostic(tmp_path)
    second = replace(first, code="second-code")

    _assert_bidirectionally_distinct(
        _diagnostic_identities((first, second)),
        _diagnostic_identities((second, first)),
    )


def test_diagnostic_capture_excludes_message_and_note_wording(
    tmp_path: Path,
) -> None:
    diagnostic = _classified_diagnostic(tmp_path)
    wording_only = replace(
        diagnostic,
        message="different user-facing wording",
        notes=("different user-facing note wording",),
    )

    assert _diagnostic_identities((diagnostic,)) == _diagnostic_identities(
        (wording_only,)
    )


def test_lsp_translation_retains_exact_cli_diagnostic_identity(
    tmp_path: Path,
) -> None:
    from orchestrator.lsp.diagnostics import translate_frontend_diagnostics

    diagnostic = _classified_diagnostic(tmp_path)
    accepted_text = {
        Path(diagnostic.span.start.path).resolve(): (
            "xxxx\n"
            + ("x" * 15)
            + "\n"
            + ("x" * 15)
            + "\n"
            + ("x" * 10)
        )
    }

    contribution = translate_frontend_diagnostics(
        (diagnostic,),
        compile_entry_uri=(tmp_path / "entry.orc").resolve().as_uri(),
        accepted_generation=3,
        accepted_text_by_path=accepted_text,
    )[0]

    assert contribution.parity_identity == _diagnostic_identities(
        (diagnostic,)
    )[0]

# Keep the selected helper API observable through the public compile and LSP paths.
def _write_std_improve_parity_workspace(
    root: Path,
    *,
    target: str = "2.36",
    explicit_source_roots: bool = False,
) -> tuple[Path, Path, tuple[Path, ...]]:
    workspace = root.resolve()
    source_root = workspace / "src" if explicit_source_roots else workspace
    entry_path = source_root / "lsp_parity" / "entry.orc"
    entry_path.parent.mkdir(parents=True)
    if target == "2.35":
        review = '''(defproc review
  ((candidate Candidate) (context String)) -> Decision[Feedback Blocker]
  :effects () :lowering inline
  (variant Decision[Feedback Blocker] REVISE
    :feedback (record Feedback :text context)))'''
        revise = '''(defproc revise
  ((candidate Candidate) (context String) (feedback Feedback)) -> Candidate
  :effects () :lowering inline candidate)'''
        improve_call = (
            '(improve (record Candidate :value 1) "context" '
            '(proc-ref review) (proc-ref revise) 1)'
        )
    else:
        review = '''(defproc review
  ((candidate Candidate)) -> Decision[Feedback Blocker]
  :effects () :lowering inline
  (variant Decision[Feedback Blocker] REVISE
    :feedback (record Feedback :text "revise")))'''
        revise = '''(defproc revise
  ((candidate Candidate) (feedback Feedback)) -> Candidate
  :effects () :lowering inline candidate)'''
        improve_call = (
            '(improve (record Candidate :value 1) '
            '(proc-ref review) (proc-ref revise) 1)'
        )
    source = f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{target}")
  (defmodule lsp_parity/entry)
  (import std/improve :only (Decision improve))
  (export run)
  (defrecord Candidate (value Int))
  (defrecord Feedback (text String))
  (defrecord Blocker (reason String))
  {review}
  {revise}
  (defworkflow run () -> Int
    (let* ((result {improve_call}))
      0)))
'''
    entry_path.write_text(source, encoding="utf-8")
    caller_roots = (
        (source_root.resolve(), workspace)
        if explicit_source_roots
        else ()
    )
    return workspace, entry_path.resolve(), caller_roots


def _observe_std_improve_graphs(monkeypatch: pytest.MonkeyPatch):
    compiler = importlib.import_module("orchestrator.workflow_lisp.compiler")
    production_resolver = compiler.resolve_module_graph
    observations: list[tuple[Path, Path, str, tuple[Path, ...]]] = []

    def observe_resolver(
        path: Path,
        *,
        source_roots: tuple[Path, ...] | None = None,
        source_read_trace: object = None,
        standalone_entry_namespace: str | None = None,
    ):
        graph = production_resolver(
            path,
            source_roots=source_roots,
            source_read_trace=source_read_trace,
            standalone_entry_namespace=standalone_entry_namespace,
        )
        selected = graph.modules_by_name["std/improve"]
        selected_path = selected.path.resolve()
        trace_paths = tuple(
            sorted(
                record.canonical_path
                for record in source_read_trace.records
            )
        )
        raw = source_read_trace.raw_bytes_by_path[selected_path]
        observations.append(
            (
                selected_path,
                selected.source_root.resolve(),
                hashlib.sha256(raw).hexdigest(),
                trace_paths,
            )
        )
        return graph

    monkeypatch.setattr(compiler, "resolve_module_graph", observe_resolver)
    return observations


@pytest.mark.parametrize("target", ("2.35", "2.36"))
@pytest.mark.parametrize("explicit_source_roots", (False, True))
def test_real_cli_and_lsp_select_same_std_improve_graph_source_and_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    explicit_source_roots: bool,
) -> None:
    workspace, entry_path, caller_roots = _write_std_improve_parity_workspace(
        tmp_path / "workspace",
        target=target,
        explicit_source_roots=explicit_source_roots,
    )
    observations = _observe_std_improve_graphs(monkeypatch)
    cli_main = importlib.import_module("orchestrator.cli.main")
    compile_command = importlib.import_module("orchestrator.cli.commands.compile")
    monkeypatch.chdir(workspace)
    argv = [
        "compile",
        str(entry_path),
        "--entry-workflow",
        "run",
        "--diagnostics-json",
    ]
    for root in caller_roots:
        argv.extend(("--source-root", str(root)))
    args = cli_main.create_parser().parse_args(argv)

    assert compile_command.compile_workflow(args) == 0

    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(
            root_uri=workspace.as_uri(),
            initialization_options={
                "entry_workflows": {str(entry_path): "run"},
                "source_roots": tuple(str(root) for root in caller_roots),
            },
        )
    )
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=entry_path.read_text(encoding="utf-8"),
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )
    driver.drain()
    [entry] = driver.state.entries

    assert entry.compile_status == "success"
    assert entry.accepted_snapshot is not None
    assert entry.diagnostic_contributions == ()
    # Both entry paths resolve this graph once.
    assert len(observations) == 2

    builtin_root = compile_driver.compiler._builtin_stdlib_source_root().resolve()
    expected_path = (
        builtin_root / "std" / "improve.orc"
        if target == "2.35"
        else builtin_root / "w3" / "std" / "improve.orc"
    )
    expected_root = builtin_root if target == "2.35" else builtin_root / "w3"
    expected_path = expected_path.resolve()
    assert observations[0][:2] == observations[1][:2] == (
        expected_path,
        expected_root.resolve(),
    )
    expected_digest = hashlib.sha256(expected_path.read_bytes()).hexdigest()
    assert observations[0][2] == observations[1][2] == expected_digest
    assert all(expected_path in observation[3] for observation in observations)
