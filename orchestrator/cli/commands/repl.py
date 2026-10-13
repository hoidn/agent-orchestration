"""Interactive inspection for evaluated Workflow Lisp runs."""

from __future__ import annotations

import argparse
from contextlib import closing, redirect_stderr, redirect_stdout
from dataclasses import dataclass
from io import StringIO
import shlex
import sys
from pathlib import Path
from typing import Any

from orchestrator._common.safe_tree import resolve_path_preserving_fd
from orchestrator.workflow.evaluated.capture import (
    CapturedRun,
    capture_run_environment,
    load_run_for_capture,
    visible_bindings,
)
from orchestrator.workflow.evaluated.views import has_evaluated_authority
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes
from orchestrator.workflow_lisp.closed.build import _strip_provenance
from orchestrator.workflow_lisp.closed.artifact import (
    ClosedProgramBuildResult,
    build_closed_program_bundle,
    prepare_closed_program_bundle,
)
from orchestrator.workflow_lisp.diagnostics import (
    LispFrontendCompileError,
    render_diagnostic,
)
from orchestrator.workflow_lisp.reader import SourceReadTrace
from orchestrator.workflow_lisp.repl_expr import (
    LoadedModule,
    ReplRefusal,
    binding_type_refs,
    evaluate_repl_expression,
)
from orchestrator.workflow_lisp.type_env import render_type_ref
from orchestrator.contracts.output_contract import strict_json_loads
from orchestrator.workflow.workspace_files import WorkspaceFiles
from orchestrator.workflow.dynamic.capture import (
    NativeCapturedRun, capture_run_environment as capture_native_environment,
    visible_bindings as native_visible_bindings,
)
from orchestrator.workflow_lisp.dynamic.build import prepare_dynamic_program_bundle
from orchestrator.workflow_lisp.dynamic.repl_expr import (
    NativeLoadedModule, evaluate_repl_expression as evaluate_native_expression,
    printable_value, runtime_kind,
)
from orchestrator.workflow_lisp.closed.target import entry_target_dsl_version


@dataclass
class ReplSession:
    workspace: Path
    state_dir: Path | None
    module: LoadedModule | NativeLoadedModule | None = None
    captured: CapturedRun | NativeCapturedRun | None = None


def _frontend_argv(args: Any) -> tuple[str, ...]:
    argv: list[str] = []
    if args.entry_workflow:
        argv.extend(("--entry-workflow", args.entry_workflow))
    for path in args.source_root or ():
        argv.extend(("--source-root", path))
    for name, flag in (
        ("provider_externs_file", "--provider-externs-file"),
        ("prompt_externs_file", "--prompt-externs-file"),
        ("imported_workflow_bundles_file", "--imported-workflow-bundles-file"),
        ("command_boundaries_file", "--command-boundaries-file"),
    ):
        value = getattr(args, name, None)
        if value:
            argv.extend((flag, value))
    return tuple(argv)


def _request_frontend_argv(request: Any) -> tuple[str, ...]:
    argv: list[str] = []
    if request.entry_workflow:
        argv.extend(("--entry-workflow", request.entry_workflow))
    for path in request.source_roots:
        argv.extend(("--source-root", str(path)))
    for field, flag in (
        ("provider_externs_path", "--provider-externs-file"),
        ("prompt_externs_path", "--prompt-externs-file"),
        ("imported_workflow_bundles_path", "--imported-workflow-bundles-file"),
        ("command_boundaries_path", "--command-boundaries-file"),
    ):
        value = getattr(request, field)
        if value is not None:
            argv.extend((flag, str(value)))
    return tuple(argv)


def _load_parser() -> argparse.ArgumentParser:
    from orchestrator.cli.main import _add_frontend_flags

    parser = argparse.ArgumentParser(prog=":load")
    parser.add_argument("workflow", help="Workflow Lisp .orc source file")
    _add_frontend_flags(parser)
    return parser


def _show_compile_error(exc: LispFrontendCompileError) -> None:
    for diagnostic in exc.diagnostics:
        print(render_diagnostic(diagnostic), file=sys.stderr)


def _report_error(exc: BaseException, *, fallback: str = "repl_command_failed") -> None:
    code = getattr(exc, "code", None)
    if not code:
        code = "repl_io_error" if isinstance(exc, OSError) else fallback
    print(f"[{code}] {exc}", file=sys.stderr)


def _load_module(
    session: ReplSession,
    args: Any,
) -> None:
    from orchestrator.cli.commands.evaluated import _request

    source_path = resolve_path_preserving_fd(args.workflow)
    trace = SourceReadTrace()
    native = entry_target_dsl_version(source_path, source_read_trace=trace) == "3.0"
    build = prepare_dynamic_program_bundle if native else build_closed_program_bundle
    built = build(_request(args, source_path, session.workspace), source_read_trace=trace)
    module = (NativeLoadedModule if native else LoadedModule)(built, source_path, _frontend_argv(args))
    session.module = module
    if (
        session.captured is not None
        and (session.captured.authority.program.digest != built.program.digest
             or isinstance(session.captured, NativeCapturedRun) != native)
    ):
        session.captured = None


def _run_root(session: ReplSession, run_id: str) -> Path:
    if (
        not run_id
        or run_id in {".", ".."}
        or Path(run_id).name != run_id
        or "\x00" in run_id
    ):
        raise ReplRefusal("repl_run_not_found", "run id is not a single path component")
    runs_root = session.state_dir or session.workspace / ".orchestrate" / "runs"
    return runs_root / run_id


def _module_for_attachment(
    session: ReplSession,
    header: Any,
) -> LoadedModule:
    if session.module is not None:
        return session.module
    if "resume_request" not in header:
        raise ReplRefusal(
            "resume_request_missing", "run header has no durable rebuild request"
        )
    from orchestrator.cli.commands.evaluated import _resume_build_request

    request = _resume_build_request(header, session.workspace)
    built: ClosedProgramBuildResult = prepare_closed_program_bundle(
        request, source_read_trace=SourceReadTrace()
    )
    return LoadedModule(
        built,
        request.source_path,
        _request_frontend_argv(request),
    )


def _attach_root(session: ReplSession, run_root: Path) -> None:
    if not run_root.exists():
        raise ReplRefusal("repl_run_not_found", f"run directory not found: {run_root}")
    if not has_evaluated_authority(run_root):
        raise ReplRefusal("repl_profile_unsupported", "run does not use evaluated execution")
    with closing(WorkspaceFiles(run_root)) as files:
        header = strict_json_loads(files.read("run.json"))
    if not isinstance(header, dict):
        raise ReplRefusal("repl_profile_unsupported", "run header is not an execution profile")
    profile = (header.get("schema_version"), header.get("result_persistence_profile"))
    if profile == ("3.1", "dynamic_execution.v1"):
        if not isinstance(session.module, NativeLoadedModule):
            raise ReplRefusal("repl_module_required", "use :load to load the native workflow before :attach")
        try:
            captured = capture_native_environment(run_root, session.module.build.program)
        except ReplRefusal as exc:
            if exc.code == "resume_program_changed":
                session.captured = None
            raise
        session.captured = captured
        return
    if profile != ("3.0", "evaluated_execution.v1"):
        raise ReplRefusal("repl_profile_unsupported", "run has an unknown or mixed execution profile")
    if isinstance(session.module, NativeLoadedModule):
        session.captured = None
        raise ReplRefusal("resume_program_changed", "loaded program differs from the run profile")
    authority, snapshot = load_run_for_capture(run_root)
    module = _module_for_attachment(session, authority.header)
    if authority.header.get("program_digest") != module.build.program.digest:
        session.captured = None
        raise ReplRefusal(
            "resume_program_changed", "current program differs from the run header"
        )
    captured = capture_run_environment(authority, snapshot)
    session.module = module
    session.captured = captured


def _print_value(value: Any, type_ref: Any) -> None:
    print(canonical_json_bytes(value.json_value()).decode("utf-8"))
    print(f": {render_type_ref(type_ref)}")


def _binding_lines(captured: CapturedRun, module: LoadedModule) -> list[str]:
    if isinstance(captured, NativeCapturedRun):
        lines = [f"{name} : {runtime_kind(value)}" for name, value in native_visible_bindings(captured).items()]
        lines.extend((f"position: {captured.position}", f"run: {captured.authority.header['run_id']}"))
        return lines
    visible = visible_bindings(captured)
    refs = binding_type_refs(module, visible)
    frames = []
    frame = captured.environment
    owners: dict[str, Any] = {}
    while frame is not None:
        frames.append(frame)
        for name in frame.bindings:
            if not name.startswith("%"):
                owners.setdefault(name, frame)
        frame = frame.parent
    lines = []
    emitted: set[str] = set()
    for frame in reversed(frames):
        for name in frame.bindings:
            if name.startswith("%") or owners.get(name) is not frame or name in emitted:
                continue
            emitted.add(name)
            type_ref = refs.get(name)
            rendered = (
                render_type_ref(type_ref)
                if type_ref is not None
                else canonical_json_bytes(
                    _strip_provenance(visible[name].descriptor)
                ).decode("utf-8")
            )
            lines.append(f"{name} : {rendered}")
    lines.extend((f"position: {captured.position}", f"run: {captured.authority.header['run_id']}"))
    return lines


def _parse_command(parser: argparse.ArgumentParser, argv: list[str]) -> Any | None:
    stdout, stderr = StringIO(), StringIO()
    try:
        with redirect_stdout(stdout), redirect_stderr(stderr):
            parsed = parser.parse_args(argv)
    except SystemExit as exc:
        if exc.code == 0:
            print(stdout.getvalue(), end="")
            return None
        detail = stderr.getvalue().strip().splitlines()
        raise ReplRefusal(
            "repl_command_invalid", detail[-1] if detail else "invalid command arguments"
        ) from None
    return parsed


def _run(session: ReplSession, tail: list[str]) -> None:
    if session.module is None:
        raise ReplRefusal("repl_module_required", "load a workflow before :run")
    from orchestrator.cli.main import create_parser
    from orchestrator.cli.commands.run import run_workflow

    argv = ["run", str(session.module.source_path), *session.module.frontend_argv, *tail]
    if session.state_dir is not None and not any(
        token == "--state-dir" or token.startswith("--state-dir=") for token in tail
    ):
        argv.extend(("--state-dir", str(session.state_dir)))
    parsed = _parse_command(create_parser(), argv)
    if parsed is None:
        return
    result = run_workflow(parsed)
    if result.run_id is not None and result.run_root is not None:
        try:
            _attach_root(session, result.run_root)
        except (OSError, UnicodeError, ValueError) as exc:
            _report_error(exc)
        print(f"run_id: {result.run_id}")
        print(f"exit_code: {result.exit_code}")
    else:
        print(f"run_id: none")
        print(f"exit_code: {result.exit_code}")


def _dispatch(session: ReplSession, line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if not stripped.startswith(":"):
        if session.captured is None:
            raise ReplRefusal("repl_not_attached", "attach to an evaluated run first")
        if session.module is None:
            raise ReplRefusal("repl_module_required", "load a workflow before entering expressions")
        if isinstance(session.module, NativeLoadedModule):
            value = evaluate_native_expression(stripped, session.module, session.captured)
            print(printable_value(value))
            print(f": {runtime_kind(value)}")
        else:
            value, typed = evaluate_repl_expression(stripped, session.module, session.captured)
            _print_value(value, typed.type_ref)
        return True

    parts = stripped.split(maxsplit=1)
    command = parts[0]
    words = shlex.split(parts[1]) if len(parts) == 2 else []
    if command == ":quit":
        if words:
            raise ReplRefusal("repl_command_invalid", ":quit takes no arguments")
        return False
    if command == ":help":
        if words:
            raise ReplRefusal("repl_command_invalid", ":help takes no arguments")
        print(
            ":load PATH [frontend flags]   load or replace a Workflow Lisp module\n"
            ":run [--input NAME=VALUE] [--input-file JSON] [run flags]\n"
            ":attach RUN_ID               attach to a checked evaluated run\n"
            ":bindings                    list captured lexical bindings and types\n"
            ":result                      show the completed entry result\n"
            ":help                        show this help\n"
            ":quit                        exit the REPL\n"
            "Any other nonempty line is one pure Workflow Lisp expression."
        )
        return True
    if command == ":load":
        args = _parse_command(_load_parser(), words)
        if args is not None:
            _load_module(session, args)
        return True
    if command == ":run":
        _run(session, words)
        return True
    if command == ":attach":
        if len(words) != 1:
            raise ReplRefusal("repl_command_invalid", ":attach requires one run id")
        _attach_root(session, _run_root(session, words[0]))
        return True
    if command == ":bindings":
        if words:
            raise ReplRefusal("repl_command_invalid", ":bindings takes no arguments")
        if session.captured is None or session.module is None:
            raise ReplRefusal("repl_not_attached", "attach to an evaluated run first")
        print("\n".join(_binding_lines(session.captured, session.module)))
        return True
    if command == ":result":
        if words:
            raise ReplRefusal("repl_command_invalid", ":result takes no arguments")
        if session.captured is None or session.module is None:
            raise ReplRefusal("repl_not_attached", "attach to an evaluated run first")
        native = isinstance(session.captured, NativeCapturedRun)
        has_result = session.captured.has_result if native else session.captured.result is not None
        if not has_result:
            raise ReplRefusal(
                "repl_no_result",
                f"entry has no completed result at position {session.captured.position}",
            )
        if native:
            program = session.module.build.program
            schema = program.schemas[program.definitions[program.entry]["boundary"]["result"]]
            print(printable_value(session.captured.result))
            rendered = schema.get('name') or canonical_json_bytes(_strip_provenance(schema)).decode('utf-8')
            print(f": {rendered}")
        else:
            signature = session.module.typed_program.entry.signature
            _print_value(session.captured.result, signature.return_type_ref)
        return True
    raise ReplRefusal("repl_command_unknown", f"unknown command {command}")


def repl_workflow(args: Any) -> int:
    """Load and inspect an evaluated Workflow Lisp module interactively."""
    session = ReplSession(
        workspace=Path.cwd(),
        state_dir=Path(args.state_dir).expanduser().resolve() if args.state_dir else None,
    )
    try:
        if args.workflow:
            _load_module(session, args)
        if args.run_id:
            _attach_root(session, _run_root(session, args.run_id))
    except LispFrontendCompileError as exc:
        _show_compile_error(exc)
        return 2
    except (OSError, UnicodeError, ValueError) as exc:
        _report_error(exc, fallback="repl_startup_failed")
        return 2
    except Exception as exc:
        _report_error(exc, fallback="repl_internal_error")
        return 1

    tty = sys.stdin.isatty()
    if tty:
        try:
            import readline  # noqa: F401
        except ImportError:
            pass
    while True:
        try:
            line = input("orc> " if tty else "")
        except EOFError:
            return 0
        try:
            if not _dispatch(session, line):
                return 0
        except LispFrontendCompileError as exc:
            _show_compile_error(exc)
        except (OSError, UnicodeError, ValueError) as exc:
            _report_error(exc)
        except Exception as exc:
            _report_error(exc, fallback="repl_internal_error")
            return 1
