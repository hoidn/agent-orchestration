from __future__ import annotations

from dataclasses import fields, replace
import importlib
from pathlib import Path
import shutil
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
REQUEST_IDENTITY_FIELDS = (
    "source_path",
    "workspace_root",
    "source_roots",
    "entry_workflow",
    "validation_profile",
    "lint_profile",
    "lowering_route",
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
    shutil.copyfile(ENTRY_FIXTURE, entry_path)
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
) -> tuple[
    object,
    object,
    tuple[object, ...],
    tuple[object, ...],
    tuple[tuple[Path, ...], ...],
    Path,
    Path,
    tuple[Path, ...],
]:
    workspace, entry_path, caller_roots = _make_cli_lsp_workspace(
        tmp_path,
        explicit_source_roots=explicit_source_roots,
    )
    run_command = importlib.import_module("orchestrator.cli.commands.run")
    cli_main = importlib.import_module("orchestrator.cli.main")
    compiler = importlib.import_module("orchestrator.workflow_lisp.compiler")
    persistent_build = run_command.build_frontend_bundle
    cli_captures: list[object] = []
    cli_diagnostic_identities: list[tuple[object, ...]] = []
    effective_root_observations: list[tuple[Path, ...]] = []
    production_effective_source_roots = compiler._effective_source_roots

    def observing_effective_source_roots(
        path: Path,
        *,
        source_roots: tuple[Path, ...] | None = None,
        source_read_trace: object = None,
    ) -> tuple[Path, ...]:
        result = production_effective_source_roots(
            path,
            source_roots=source_roots,
            source_read_trace=source_read_trace,
        )
        effective_root_observations.append(result)
        return result

    def observing_build(request: build.FrontendBuildRequest):
        result = persistent_build(request)
        cli_captures.append(
            getattr(result, "compile_request_capture", _MISSING)
        )
        cli_diagnostic_identities.append(
            _diagnostic_identities(result.diagnostics)
        )
        return result

    monkeypatch.setattr(run_command, "build_frontend_bundle", observing_build)
    monkeypatch.setattr(
        compiler,
        "_effective_source_roots",
        observing_effective_source_roots,
    )
    monkeypatch.chdir(workspace)
    cli_argv = [
        "run",
        str(entry_path),
        "--entry-workflow",
        "entry-publication-runtime",
        "--dry-run",
        "--quiet",
    ]
    for source_root in caller_roots:
        cli_argv.extend(("--source-root", str(source_root)))
    cli_args = cli_main.create_parser().parse_args(cli_argv)

    assert run_command.run_workflow(cli_args) == 0
    assert len(cli_captures) == 1

    state = lsp_state.initialize_lsp_state(
        root_uri=workspace.as_uri(),
        initialization_options={
            "entry_workflows": {
                str(entry_path): "entry-publication-runtime",
            },
            "source_roots": caller_roots,
        },
    )
    driver = compile_driver.initialize_compile_driver(state)
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=entry_path.read_text(encoding="utf-8"),
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )
    driver.drain()
    accepted = driver.state.entries[0].accepted_snapshot
    assert accepted is not None
    lsp_capture = getattr(
        accepted.build_value,
        "compile_request_capture",
        _MISSING,
    )
    lsp_diagnostic_identities = _diagnostic_identities(
        accepted.build_value.diagnostics
    )
    return (
        cli_captures[0],
        lsp_capture,
        cli_diagnostic_identities[0],
        lsp_diagnostic_identities,
        tuple(effective_root_observations),
        workspace,
        entry_path,
        caller_roots,
    )


@pytest.mark.parametrize("explicit_source_roots", (False, True))
def test_real_dry_run_and_lsp_share_the_build_owned_request_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    explicit_source_roots: bool,
) -> None:
    (
        cli_capture,
        lsp_capture,
        cli_diagnostic_identities,
        lsp_diagnostic_identities,
        effective_root_observations,
        workspace,
        entry_path,
        caller_roots,
    ) = _observe_real_cli_and_lsp_captures(
        tmp_path,
        monkeypatch,
        explicit_source_roots=explicit_source_roots,
    )

    assert cli_capture is not _MISSING, (
        "the persistent dry-run result lacks the production compile-request capture"
    )
    assert lsp_capture is not _MISSING, (
        "the LSP result lacks the production compile-request capture"
    )
    assert type(cli_capture) is type(lsp_capture)
    assert type(cli_capture).__module__ == build.__name__
    assert tuple(field.name for field in fields(cli_capture)) == REQUEST_IDENTITY_FIELDS
    assert cli_capture == lsp_capture
    assert cli_diagnostic_identities == lsp_diagnostic_identities
    builtin_root = compile_driver.compiler._builtin_stdlib_source_root().resolve()
    expected_effective_roots = (
        (caller_roots[0], builtin_root, caller_roots[1])
        if explicit_source_roots
        else (workspace, builtin_root)
    )
    assert effective_root_observations == (
        expected_effective_roots,
        expected_effective_roots,
    )
    assert cli_capture.source_path == entry_path
    assert cli_capture.workspace_root == workspace
    assert cli_capture.source_roots == caller_roots
    if not explicit_source_roots:
        assert cli_capture.source_roots == ()
        assert cli_capture.workspace_root not in cli_capture.source_roots
    assert (driver_builtin_root := builtin_root) not in cli_capture.source_roots
    assert driver_builtin_root != workspace


def test_real_broken_dry_run_and_lsp_share_request_and_diagnostic_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir()
    entry_path = workspace / "broken.orc"
    entry_text = "(workflow-lisp\n"
    entry_path.write_text(entry_text, encoding="utf-8")
    run_command = importlib.import_module("orchestrator.cli.commands.run")
    cli_main = importlib.import_module("orchestrator.cli.main")
    persistent_build = run_command.build_frontend_bundle
    cli_errors: list[build.LispFrontendCompileError] = []

    def observing_cli_build(request: build.FrontendBuildRequest):
        try:
            return persistent_build(request)
        except build.LispFrontendCompileError as error:
            cli_errors.append(error)
            raise

    monkeypatch.setattr(
        run_command,
        "build_frontend_bundle",
        observing_cli_build,
    )
    monkeypatch.chdir(workspace)
    cli_args = cli_main.create_parser().parse_args(
        ("run", str(entry_path), "--dry-run", "--quiet")
    )

    assert run_command.run_workflow(cli_args) == 2
    assert len(cli_errors) == 1

    read_only_build = build.build_frontend_bundle_in_memory
    lsp_errors: list[build.LispFrontendCompileError] = []

    def observing_lsp_build(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: object,
    ):
        try:
            return read_only_build(
                request,
                source_read_trace=source_read_trace,
            )
        except build.LispFrontendCompileError as error:
            lsp_errors.append(error)
            raise

    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(root_uri=workspace.as_uri()),
        build_in_memory=observing_lsp_build,
    )
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=entry_text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )
    driver.drain()

    assert len(lsp_errors) == 1
    cli_error = cli_errors[0]
    lsp_error = lsp_errors[0]
    assert cli_error.compile_request_capture == lsp_error.compile_request_capture
    cli_identities = _diagnostic_identities(cli_error.diagnostics)
    lsp_identities = _diagnostic_identities(lsp_error.diagnostics)
    assert cli_identities
    assert cli_identities == lsp_identities
    assert cli_identities[0][1:6] == (
        "validation",
        "error",
        "read",
        "parse",
        "frontend",
    )


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
        ("lint_profile", "replacement-lint"),
        ("lowering_route", "legacy"),
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
