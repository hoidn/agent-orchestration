"""Capture Python authoring inputs and retain an ordinary closed-build recipe."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Any

from orchestrator._common.io_atomic import atomic_write_text_at, rename_noreplace_at
from orchestrator._common.safe_tree import (
    SafeTreeError, open_directory, read_regular_file, walk_regular_files,
)
from orchestrator.workflow.assets import WorkflowAssetResolver
from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.build_manifest_io import _require_build_path_within_workspace
from orchestrator.workflow_lisp.closed.artifact import (
    build_closed_program_bundle, prepare_closed_program_bundle,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from orchestrator.workflow_lisp.reader import SourceReadTrace
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan

from .diagnostics import (PythonFrontendError, PythonSite, PythonSourceMap,
                          SourceMapEntry, remap_compiler_error)

if TYPE_CHECKING:
    from orchestrator.cli.commands.run import RunWorkflowResult


FORMAT = "workflow-python/build/1"
_MANIFEST_OPTIONS = {"providers": "provider_externs_path", "prompts": "prompt_externs_path",
                     "commands": "command_boundaries_path", "bundles": "imported_workflow_bundles_path"}
_STDLIB = Path(__file__).resolve().parents[1] / "workflow_lisp/stdlib_modules"


def _json(value):
    return json.dumps(value, sort_keys=True, indent=2) + "\n"


def _digest(raw):
    return "sha256:" + sha256(raw).hexdigest()


def _input_path(path):
    return Path("inputs") / Path(path).relative_to(Path(path).anchor)


def _read_pin(root_fd, name, path):
    try:
        os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        return json.loads(read_regular_file(root_fd, name))
    except FileNotFoundError:
        return None
    except (ValueError, OSError, SafeTreeError) as exc:
        raise PythonFrontendError("python_frozen_pin_invalid", "Frozen pin is not a regular valid JSON file",
                                  site=PythonSite(str(path), 1)) from exc


def _python_root(workspace):
    root = workspace / ".orchestrate/python"
    _require_build_path_within_workspace(root, workspace_root=workspace)
    descriptor = open_directory(str(workspace))
    try:
        for part in (".orchestrate", "python"):
            try: os.mkdir(part, dir_fd=descriptor)
            except FileExistsError: pass
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return root, descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _source_map(payload, *, generated_root=None, normalized=False):
    result = PythonSourceMap(schema_version=payload["schema_version"],
                             source_hashes=dict(payload["source_hashes"]))
    for row in payload["entries"]:
        generated = dict(row["generated"])
        if generated_root is not None:
            path = Path(generated["path"])
            generated["path"] = str(Path("generated") / path.relative_to(generated_root)) if normalized else str(path)
        result.entries.append(SourceMapEntry(PythonSite(**row["python"]), PythonSite(**generated), row["kind"]))
    return result


def _worker_error(payload):
    if payload["error"] == "compile":
        from orchestrator.workflow.provider_phased_delivery.protocol import diagnostic_from_dict
        from orchestrator.workflow_lisp.syntax import ExpansionFrame, HelperExpansionFrame, ProcedureExpansionFrame
        def span(row):
            return SourceSpan(**{key: SourcePosition(**value) for key, value in row.items()})
        def frame(row):
            row = dict(row)
            for key in ("call_span", "definition_span"): row[key] = span(row[key])
            if "macro_name" in row:
                row["template_path"] = tuple(row["template_path"])
                return ExpansionFrame(**row)
            return (HelperExpansionFrame if "function_name" in row else ProcedureExpansionFrame)(**row)
        allowed = {field.name for field in fields(LispFrontendDiagnostic)}
        diagnostics = []
        for row in payload["diagnostics"]:
            row = {key: value for key, value in row.items() if key in allowed}
            row["span"] = span(row["span"])
            row["expansion_stack"] = tuple(frame(item) for item in row["expansion_stack"])
            for key in ("form_path", "notes"):
                row[key] = tuple(row.get(key, ()))
            if row.get("phased_delivery_diagnostic") is not None:
                row["phased_delivery_diagnostic"] = diagnostic_from_dict(row["phased_delivery_diagnostic"])
            row["cause"] = None
            diagnostics.append(LispFrontendDiagnostic(**row))
        error = LispFrontendCompileError(tuple(diagnostics))
    else:
        error = PythonFrontendError(payload["code"], payload["message"], site=PythonSite(**payload["site"]))
    error.traceback = payload.get("traceback", "")
    return error


def _generate(source, workspace, source_roots, manifests, stage):
    request = {"source": str(source), "workspace": str(workspace), "output": str(stage),
               "source_roots": list(map(str, source_roots)),
               "manifests": {key: str(path) if path else None for key, path in manifests.items()}}
    request_path, result_path = stage / "request.json", stage / "result.json"
    request_path.write_text(_json(request))
    package_root = str(Path(__file__).resolve().parents[2])
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHONPATH": os.pathsep.join(filter(None, (package_root, os.environ.get("PYTHONPATH"))))}
    process = subprocess.run([sys.executable, "-m", "orchestrator.py._worker", str(request_path), str(result_path)],
                             cwd=workspace, env=env, capture_output=True, text=True)
    if process.returncode or not result_path.is_file():
        error = PythonFrontendError("python_worker_failed", "Python generation worker did not finish successfully",
                                    site=PythonSite(str(source), 1))
        error.traceback = process.stderr
        raise error
    payload = json.loads(result_path.read_text())
    if "error" in payload: raise _worker_error(payload)
    return payload


@dataclass(frozen=True)
class PythonBuildResult:
    source_path: Path
    source_root: Path
    source_roots: tuple[Path, ...]
    source_map_path: Path
    provider_externs_path: Path | None
    prompt_externs_path: Path | None
    command_boundaries_path: Path | None
    imported_workflow_bundles_path: Path | None
    artifact_path: Path
    manifest_path: Path
    build_key: str
    program_digest: str
    entry_workflow: str
    workspace_root: Path
    snapshot_path: Path
    pin_path: Path
    request: FrontendBuildRequest
    compile_diagnostics: tuple[LispFrontendDiagnostic, ...] = ()


def _capture(captures, path, raw):
    path = Path(path)
    if path in captures and captures[path] != raw:
        raise PythonFrontendError("python_source_changed", "An input changed during this build",
                                  site=PythonSite(str(path), 1))
    captures[path] = raw


def _capture_assets(built, generated_to_python, captures, files, generated_root):
    from orchestrator.workflow_lisp.expression_traversal import walk_expr
    from orchestrator.workflow_lisp.expressions import NameExpr, ProviderResultExpr
    for program in built.builder._programs():
        used = {}
        for definition in (*program.workflows.values(), *program.procedures.values()):
            module = built.builder._module_for_owner(program, definition.definition.name, definition)
            for expression in walk_expr(definition.typed_body.expr):
                if isinstance(expression, ProviderResultExpr) and isinstance(expression.prompt, NameExpr):
                    used.setdefault(module, set()).add(expression.prompt.name)
        for module, names in used.items():
            owner = program._io_source_paths[module]
            configuration = built.builder.configuration_for(program, module)
            physical_owner = generated_to_python.get(str(owner), owner)
            for name in names:
                binding = configuration["prompts"][name]
                if binding["source_kind"] != "asset_file": continue
                source = WorkflowAssetResolver(Path(physical_owner)).resolve(binding["path"])
                raw = captures.get(source)
                if raw is None: raw = source.read_bytes()
                _capture(captures, source, raw)
                if generated_root in owner.parents:
                    target = Path("generated") / owner.relative_to(generated_root).parent / binding["path"]
                    if target in files and files[target] != raw:
                        raise PythonFrontendError("python_prompt_asset_conflict", "Different assets share a generated source locator",
                                                  site=PythonSite(str(physical_owner), 1))
                    files[target] = raw


def _write_snapshot(root, files):
    root.mkdir()
    for relative, raw in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor = open_directory(str(target.parent))
        try:
            file_descriptor = os.open(target.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                      0o644, dir_fd=descriptor)
            with os.fdopen(file_descriptor, "wb") as output: output.write(raw)
        finally:
            os.close(descriptor)


def _verify_snapshot(path, files):
    descriptor = open_directory(str(path))
    try:
        rows = tuple(walk_regular_files(descriptor))
        if {row.relative_path for row in rows} != {path.as_posix() for path in files}:
            raise PythonFrontendError("python_snapshot_changed", "Existing immutable snapshot has different files",
                                      site=PythonSite(str(path), 1))
        for row in rows:
            if read_regular_file(descriptor, row.relative_path, expected=row) != files[Path(row.relative_path)]:
                raise PythonFrontendError("python_snapshot_changed", "Existing immutable snapshot bytes changed",
                                          site=PythonSite(str(path / row.relative_path), 1))
    finally:
        os.close(descriptor)


def _build(source_file, *, entry_workflow=None, source_roots=(), workspace_root=None,
           provider_externs_file=None, prompt_externs_file=None,
           command_boundaries_file=None, imported_workflow_bundles_file=None,
           frozen=False, update_pin=True):
    source = Path(source_file).resolve()
    workspace = Path(workspace_root or Path.cwd()).resolve()
    if source.suffix != ".py" or not source.is_file():
        raise PythonFrontendError("python_source_required", "Expected a source-backed Python file",
                                  site=PythonSite(str(source), 1))
    roots = tuple(Path(path).resolve() for path in source_roots)
    if len(set(roots)) != len(roots):
        raise PythonFrontendError("python_source_root_duplicate", "Source roots must be distinct",
                                  site=PythonSite(str(source), 1))
    manifests = {key: Path(path).resolve() if path is not None else None for key, path in {
        "providers": provider_externs_file, "prompts": prompt_externs_file,
        "commands": command_boundaries_file, "bundles": imported_workflow_bundles_file}.items()}
    root_fd = None
    try:
        root, root_fd = _python_root(workspace)
        with TemporaryDirectory(prefix=".stage-", dir=root) as directory:
            stage = Path(directory)
            payload = _generate(source, workspace, roots, manifests, stage)
            generated_root = Path(payload["source_root"])
            source_map = _source_map(payload["source_map"])
            captures = {}
            for row in payload["captures"]:
                _capture(captures, Path(row["path"]), (stage / row["file"]).read_bytes())
            aliases = payload["entry_aliases"]
            selected = entry_workflow
            if selected is None and len(aliases) == 1: selected = next(iter(aliases))
            generated_source = Path(payload["source_path"])
            selected_module, separator, selected_member = (selected or "").partition("::")
            if separator:
                root_module = generated_source.relative_to(generated_root).with_suffix("").as_posix()
                if selected_module == root_module and selected_member in aliases:
                    selected = selected_member
                else:
                    selected = next((alias for alias, (owner, name) in aliases.items()
                                     if (owner, name) == (selected_module, selected_member)), selected)
            if selected in aliases:
                owner, selected = aliases[selected]
                generated_source = generated_root / (owner + ".orc")
            request = FrontendBuildRequest(source_path=generated_source,
                source_roots=tuple(Path(path) for path in payload["source_roots"]),
                entry_workflow=selected, workspace_root=workspace,
                **{_MANIFEST_OPTIONS[key]: path for key, path in manifests.items()})
            trace = SourceReadTrace()
            try:
                prepared = prepare_closed_program_bundle(request, source_read_trace=trace)
            except LispFrontendCompileError as error:
                raise remap_compiler_error(error, source_map) from None
            pin_name = "pin-" + sha256(_json([str(source), prepared.entry_workflow]).encode()).hexdigest()[:24] + ".json"
            pin = _read_pin(root_fd, pin_name, root / pin_name) if frozen else None
            if frozen and pin is None:
                raise PythonFrontendError("python_frozen_pin_missing", "Frozen build requires a successful normal build pin",
                                          site=PythonSite(str(source), 1))
            files = {Path("generated") / path.relative_to(generated_root): path.read_bytes()
                     for path in generated_root.rglob("*") if path.is_file()}
            for path, raw in trace.raw_bytes_by_path.items():
                if generated_root not in path.parents: _capture(captures, path, raw)
            _capture_assets(prepared, payload["generated_to_python"], captures, files, generated_root)
            for key, path in manifests.items():
                if path is not None:
                    raw = path.read_bytes()
                    _capture(captures, path, raw)
            for path, raw in captures.items():
                if _STDLIB not in path.parents: files[_input_path(path)] = raw
            # Source maps use snapshot-relative generated paths, independent of staging names.
            from dataclasses import asdict
            normalized_map = _source_map(payload["source_map"], generated_root=generated_root, normalized=True)
            normalized_map.source_hashes = {str(path): _digest(raw) for path, raw in captures.items()}
            files[Path("source-map.json")] = _json(asdict(normalized_map)).encode()
            manifest_recipe = {key: _input_path(path) if path else None for key, path in manifests.items()}
            provenance = {}
            if manifests["bundles"] is not None:
                original = manifests["bundles"]
                bundles = json.loads(captures[original])
                for binding in bundles.values():
                    original_locator = binding["path"]
                    original_path = Path(original_locator)
                    original_path = (original.parent / original_path).resolve() if not original_path.is_absolute() else original_path.resolve()
                    if original_path not in captures:
                        raise PythonFrontendError("python_source_not_captured", "Imported bundle source was not captured",
                                                  site=PythonSite(str(original_path), 1))
                    binding["path"] = "../" + _input_path(original_path).as_posix()
                    provenance[str(original_path)] = binding["path"]
                manifest_recipe["bundles"] = Path("recipe/imported-workflow-bundles.json")
                files[manifest_recipe["bundles"]] = _json(bundles).encode()
            retained_roots = [Path("generated"), *(_input_path(path) for path in request.source_roots[1:])]
            recipe = {"source": str(Path("generated") / generated_source.relative_to(generated_root)),
                      "roots": list(map(str, retained_roots)),
                      "manifests": {key: str(path) if path else None for key, path in manifest_recipe.items()},
                      "entry_workflow": prepared.entry_workflow}
            identity = {"schema_version": FORMAT, "source": str(source), "entry_workflow": prepared.entry_workflow,
                        "authoring_inputs": {str(path): _digest(raw) for path, raw in sorted(captures.items())},
                        "source_roots": list(map(str, request.source_roots[1:])),
                        "build_key": prepared.build_key, "program_digest": prepared.program.digest,
                        "recipe": recipe, "bundle_locator_provenance": provenance,
                        "files": {str(path): _digest(raw) for path, raw in sorted(files.items())}}
            snapshot_key = sha256(_json(identity).encode()).hexdigest()
            files[Path("manifest.json")] = _json(identity).encode()
            snapshot = root / snapshot_key
            expected_pin = {"schema_version": FORMAT, "snapshot": snapshot_key,
                            "build_key": prepared.build_key, "program_digest": prepared.program.digest}
            if frozen and pin != expected_pin:
                raise PythonFrontendError("python_frozen_changed", "Captured authoring inputs or ordinary build identity changed",
                                          site=PythonSite(str(source), 1))

            def retained_request(base):
                return replace(request, source_path=base / recipe["source"],
                    source_roots=tuple(base / path for path in recipe["roots"]),
                    **{_MANIFEST_OPTIONS[key]: base / path if path else None
                       for key, path in manifest_recipe.items()})

            draft = stage / "snapshot"
            _write_snapshot(draft, files)
            retained = prepare_closed_program_bundle(retained_request(draft))
            if (retained.build_key, retained.program.digest) != (prepared.build_key, prepared.program.digest):
                raise PythonFrontendError("python_snapshot_identity_changed", "Retaining the source recipe changed ordinary build identity",
                                          site=PythonSite(str(source), 1))
            if snapshot.exists() or snapshot.is_symlink():
                _verify_snapshot(snapshot, files)
            else:
                if frozen:
                    raise PythonFrontendError("python_snapshot_missing", "Pinned immutable source snapshot is missing",
                                              site=PythonSite(str(snapshot), 1))
                stage_fd = open_directory(str(stage))
                try:
                    try: rename_noreplace_at(stage_fd, "snapshot", root_fd, snapshot_key)
                    except FileExistsError: _verify_snapshot(snapshot, files)
                finally:
                    os.close(stage_fd)
            saved_request = retained_request(snapshot)
            built = build_closed_program_bundle(saved_request)
            if (built.build_key, built.program.digest) != (prepared.build_key, prepared.program.digest):
                raise PythonFrontendError("python_snapshot_identity_changed", "Published ordinary build changed retained identity",
                                          site=PythonSite(str(source), 1))
            display_map = replace(normalized_map, entries=[replace(entry,
                generated=replace(entry.generated, path=str(snapshot / entry.generated.path)))
                for entry in normalized_map.entries])
            compile_diagnostics = remap_compiler_error(
                LispFrontendCompileError(tuple(built.compile_diagnostics or ())), display_map).diagnostics
            if update_pin and not frozen:
                atomic_write_text_at(root_fd, pin_name, _json(expected_pin))
            return PythonBuildResult(saved_request.source_path, snapshot / "generated", saved_request.source_roots,
                snapshot / "source-map.json", saved_request.provider_externs_path, saved_request.prompt_externs_path,
                saved_request.command_boundaries_path, saved_request.imported_workflow_bundles_path,
                built.artifact_path, built.manifest_path, built.build_key, built.program.digest, built.entry_workflow,
                workspace, snapshot, root / pin_name, saved_request, compile_diagnostics)
    except (SafeTreeError, OSError) as error:
        raise PythonFrontendError("python_build_path_error", f"Cannot safely retain Python build paths: {error}",
                                  site=PythonSite(str(source), 1)) from error
    finally:
        if root_fd is not None: os.close(root_fd)


def build(source_file, **kwargs):
    """Build source in a fresh process and pin the successful retained recipe."""
    return _build(source_file, **kwargs)


def check(source_file, **kwargs):
    """Trace and compile without executing effects or changing the entry pin."""
    return _build(source_file, update_pin=False, **kwargs)


def _cli_input_items(inputs: Mapping[str, Any] | None) -> list[str]:
    if inputs is None:
        return []
    if not isinstance(inputs, Mapping):
        raise TypeError("inputs must be a mapping of workflow input names to values")

    items = []
    for name, value in inputs.items():
        if not isinstance(name, str) or not name or "=" in name:
            raise ValueError("workflow input names must be non-empty strings without '='")
        if isinstance(value, str):
            encoded = value
        else:
            try:
                encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            except (TypeError, ValueError) as exc:
                raise TypeError(f"workflow input {name!r} is not a JSON value") from exc
        items.append(f"{name}={encoded}")
    return items


def run(
    source_file,
    *,
    entry_workflow=None,
    inputs: Mapping[str, Any] | None = None,
    source_roots=(),
    provider_externs_file=None,
    prompt_externs_file=None,
    command_boundaries_file=None,
    imported_workflow_bundles_file=None,
    frozen=False,
    **runtime_options,
) -> "RunWorkflowResult":
    """Build and run a Python-authored workflow through the ordinary runtime.

    Runtime keyword options are the ordinary ``run`` CLI options written with
    underscores (for example ``debug=True`` or ``max_retries=2``). Runtime
    workspace is the current working directory, matching ``run_workflow``.
    """
    from orchestrator.cli.main import create_parser

    runtime_args = create_parser().parse_args(["run", str(source_file)])
    frontend_fields = {
        "command", "workflow", "entry_workflow", "source_root",
        "provider_externs_file", "prompt_externs_file",
        "command_boundaries_file", "imported_workflow_bundles_file",
        "input",
    }
    supported_runtime_options = set(vars(runtime_args)) - frontend_fields
    unsupported = set(runtime_options) - supported_runtime_options
    if unsupported:
        names = ", ".join(sorted(unsupported))
        raise TypeError(f"run() got unsupported runtime option(s): {names}")
    input_file = runtime_options.get("input_file")
    if input_file is not None:
        if isinstance(input_file, os.PathLike):
            input_file = os.fspath(input_file)
        if not isinstance(input_file, str):
            raise TypeError("input_file must be a string or path-like value")
        runtime_options["input_file"] = input_file

    input_items = _cli_input_items(inputs)
    for name, value in runtime_options.items():
        setattr(runtime_args, name, value)
    runtime_args.input = input_items

    result = build(
        source_file,
        entry_workflow=entry_workflow,
        source_roots=source_roots,
        workspace_root=Path.cwd(),
        provider_externs_file=provider_externs_file,
        prompt_externs_file=prompt_externs_file,
        command_boundaries_file=command_boundaries_file,
        imported_workflow_bundles_file=imported_workflow_bundles_file,
        frozen=frozen,
    )
    from orchestrator.cli.commands.python import _runtime_args, _show_run_compile_warnings
    from orchestrator.cli.commands.run import run_workflow

    _show_run_compile_warnings(result.compile_diagnostics, runtime_args)
    return run_workflow(_runtime_args(runtime_args, result))
