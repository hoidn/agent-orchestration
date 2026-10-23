"""Fresh-process source generation; JSON files are the only build protocol."""
from __future__ import annotations

from dataclasses import asdict
import importlib.abc
import importlib.machinery
import importlib.util
import json
import linecache
from pathlib import Path
import site
import sys
import sysconfig
import traceback

from .diagnostics import PythonFrontendError, PythonSite


class _ByteLoader(importlib.machinery.SourceFileLoader):
    def __init__(self, name, path, captures):
        super().__init__(name, str(path))
        self.captures = captures

    def get_source(self, fullname):
        path = Path(self.path).resolve()
        if path not in self.captures:
            self.captures[path] = path.read_bytes()
        return importlib.util.decode_source(self.captures[path])

    def get_code(self, fullname):
        text = self.get_source(fullname)
        raw = self.captures[Path(self.path).resolve()]
        # inspect must see the executed source even if author code edits its file.
        linecache.cache[self.path] = (len(raw), None, text.splitlines(True), self.path)
        return compile(raw, self.path, "exec", dont_inherit=True)


class _LocalSources(importlib.abc.MetaPathFinder):
    def __init__(self, roots, captures):
        self.roots = roots
        self.captures = captures
        self.compiler = Path(__file__).resolve().parents[1]
        paths = sysconfig.get_paths()
        installed = [paths.get(key) for key in ("stdlib", "platstdlib", "purelib", "platlib")]
        installed.extend(site.getsitepackages())
        installed.append(site.getusersitepackages())
        self.installed_roots = tuple(Path(path).resolve() for path in installed if path)

    def find_spec(self, fullname, path=None, target=None):
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or not spec.origin or Path(spec.origin).suffix not in {".py", ".pyc"}:
            return None
        origin = Path(spec.origin).resolve()
        if self.compiler == origin or self.compiler in origin.parents:
            return None
        if any(root == origin or root in origin.parents for root in self.installed_roots):
            return None
        if any(root == origin or root in origin.parents for root in self.roots):
            if origin.suffix != ".py":
                raise PythonFrontendError("python_source_required", "Local Python imports require source bytes",
                                          site=PythonSite(str(origin), 1))
            spec.loader = _ByteLoader(fullname, origin, self.captures)
            return spec
        return None


def _module_identity(source, roots):
    for root in roots:
        if source.is_relative_to(root):
            relative = source.relative_to(root).with_suffix("")
            parts = list(relative.parts)
            if parts[-1] == "__init__": parts.pop()
            if parts and all(name.isidentifier() for name in parts):
                return ".".join(parts), root
    parts = [] if source.name == "__init__.py" else [source.stem]
    parent = source.parent
    while (parent / "__init__.py").is_file():
        parts.insert(0, parent.name)
        parent = parent.parent
    if not parts or any(not name.isidentifier() for name in parts):
        raise PythonFrontendError("python_module_name", "Python source needs a stable importable file/package name",
                                  site=PythonSite(str(source), 1))
    return ".".join(parts), parent


def _exception_result(error, source, python_sources):
    from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
    if isinstance(error, LispFrontendCompileError):
        from orchestrator.workflow.provider_phased_delivery.protocol import diagnostic_to_dict
        rows = []
        for diagnostic in error.diagnostics:
            row = asdict(diagnostic) | {"cause": None}
            if diagnostic.phased_delivery_diagnostic is not None:
                row["phased_delivery_diagnostic"] = diagnostic_to_dict(diagnostic.phased_delivery_diagnostic)
            rows.append(row)
        return {"error": "compile", "diagnostics": rows,
                "traceback": traceback.format_exc()}
    if isinstance(error, PythonFrontendError):
        code, site, message = error.code, error.site, error.message
    elif isinstance(error, SyntaxError):
        code, site, message = "python_syntax_error", PythonSite(
            error.filename or str(source), error.lineno or 1, error.offset or 1), str(error.msg)
    else:
        code, site, message = "python_import_or_trace_error", PythonSite(str(source), 1), str(error)
        for frame in traceback.extract_tb(error.__traceback__):
            candidate = Path(frame.filename)
            if candidate.resolve() in python_sources:
                site = PythonSite(frame.filename, frame.lineno)
    return {"error": "python", "code": code, "message": message,
            "site": asdict(site), "traceback": traceback.format_exc()}


def generate(request, python_sources):
    from .emit import generate_graph
    from orchestrator.workflow_lisp.build import _load_imported_workflow_bundle_manifest
    from orchestrator.workflow_lisp.build_manifest_io import (
        ConfigurationReadTrace, _load_command_boundaries_manifest_payload,
        _load_prompt_extern_mapping, _load_string_mapping, _parse_command_boundaries_manifest,
    )
    from orchestrator.workflow_lisp.reader import SourceReadTrace

    source = Path(request["source"])
    workspace = Path(request["workspace"])
    output = Path(request["output"])
    roots = tuple(Path(path) for path in request["source_roots"])
    paths = {key: Path(path) if path else None for key, path in request["manifests"].items()}
    configuration_trace = ConfigurationReadTrace()
    options = {"configuration_read_trace": configuration_trace}
    providers = _load_string_mapping(paths["providers"], label="provider externs manifest", **options)
    prompts = _load_prompt_extern_mapping(paths["prompts"], **options)
    commands = _parse_command_boundaries_manifest(
        _load_command_boundaries_manifest_payload(paths["commands"], **options),
        manifest_path=paths["commands"])
    bundle_trace = SourceReadTrace()
    bundles = _load_imported_workflow_bundle_manifest(paths["bundles"], workspace_root=workspace,
        source_roots=roots, provider_externs_path=paths["providers"], prompt_externs_path=paths["prompts"],
        command_boundaries_path=paths["commands"], source_read_trace=bundle_trace,
        configuration_read_trace=configuration_trace)
    name, import_root = _module_identity(source, roots)
    finder = _LocalSources((workspace, import_root, *roots), python_sources)
    sys.meta_path.insert(0, finder)
    sys.path.insert(0, str(import_root))
    sys.path.insert(1, str(workspace))
    sys.path[2:2] = [str(root) for root in roots if root not in {workspace, import_root}]
    if "." in name:
        importlib.import_module(name.rpartition(".")[0])
    module = sys.modules.get(name)
    if module is None or Path(getattr(module, "__file__", "")).resolve() != source or source not in python_sources:
        loader = _ByteLoader(name, source, python_sources)
        spec = importlib.util.spec_from_file_location(name, source, loader=loader,
            submodule_search_locations=[str(source.parent)] if source.name == "__init__.py" else None)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        loader.exec_module(module)
    kwargs = dict(source_roots=roots, python_sources=python_sources,
                  provider_externs=providers, prompt_externs=prompts,
                  command_boundaries=commands, workspace_root=workspace)
    if bundles:
        kwargs["imported_programs"] = {binding.canonical_key: binding.typed_program for binding in bundles}
    graph = generate_graph(module, output / "generated", **kwargs)
    for path, raw in graph.python_sources.items():
        if python_sources.get(path) != raw:
            raise PythonFrontendError("python_source_not_captured", "Source bytes were not captured by the executing loader",
                                      site=PythonSite(str(path), 1))
    captures = {}
    kinds = {}

    def capture(path, raw, kind):
        path = str(path)
        if path in captures and captures[path] != raw:
            raise PythonFrontendError("python_source_changed", "Source changed during generation",
                                      site=PythonSite(path, 1))
        captures[path] = raw
        kinds.setdefault(path, kind)

    for path, raw in python_sources.items(): capture(path, raw, "python")
    for path, raw in graph.prompt_assets.items(): capture(path, raw, "prompt")
    for mapping in (graph.source_reads, bundle_trace.raw_bytes_by_path):
        for path, raw in mapping.items(): capture(path, raw, "orc")
    from hashlib import sha256
    for path, revision in configuration_trace.revision_vector:
        raw = path.read_bytes()
        if "sha256:" + sha256(raw).hexdigest() != revision:
            raise PythonFrontendError("python_source_changed", "Configuration changed during generation",
                                      site=PythonSite(str(path), 1))
        capture(path, raw, "manifest")
    capture_root = output / "captures"
    capture_root.mkdir()
    metadata = []
    for index, (path, raw) in enumerate(sorted(captures.items())):
        relative = f"captures/{index}"
        (output / relative).write_bytes(raw)
        metadata.append({"path": path, "file": relative, "kind": kinds[path]})
    return {"source_path": str(graph.source_path), "source_root": str(graph.source_root),
            "source_roots": [str(path) for path in graph.source_roots],
            "source_map": asdict(graph.source_map), "captures": metadata,
            "generated_to_python": {str(k): str(v) for k, v in graph.generated_to_python.items()},
            "entry_aliases": graph.entry_aliases, "asset_bindings": graph.asset_bindings}


def main():
    request_path, result_path = map(Path, sys.argv[1:])
    request = json.loads(request_path.read_text())
    python_sources = {}
    try:
        result = generate(request, python_sources)
    except BaseException as error:
        result = _exception_result(error, request["source"], python_sources)
    result_path.write_text(json.dumps(result, default=str))


if __name__ == "__main__":
    main()
