"""Source-owned corpus preparation for evaluated-execution coverage tests.

This is a helper module, not a pytest test module. It discovers exports from the
Workflow Lisp syntax/module owners and prepares compile-only copies without
changing imported modules' target declarations.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import json
from pathlib import Path
import shutil
from typing import Any, Mapping

from orchestrator.workflow_lisp import syntax
from orchestrator.workflow_lisp.command_boundaries import (
    CertifiedAdapterBinding,
    ExternalToolBinding,
    PROMOTED_CALL_REQUIRED_METADATA_FIELDS,
)
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.closed.build import build_closed_program
from orchestrator.workflow_lisp.closed.program import ClosedProgram, _sites_from_nodes
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.sexpr import KeywordAtom, ListExpr
from orchestrator.workflow_lisp.syntax import (
    build_syntax_module,
    syntax_node_datum,
    syntax_head_name,
)
from orchestrator.workflow_lisp.workflows import PromptExtern


REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS_ROOTS = (
    Path("workflows/examples"),
    Path("workflows/library"),
    Path("workflows/experiments"),
    Path("experiments/orc_vs_single_call"),
    Path("experiments/mlevolve_pair"),
)


@dataclass(frozen=True)
class Workflow:
    source: Path
    source_root: Path
    module: str
    name: str

    @property
    def canonical_name(self) -> str:
        return f"{self.module}::{self.name}"

    @property
    def key(self) -> str:
        return f"{self.source.relative_to(REPO_ROOT).as_posix()}::{self.name}"

    def __str__(self) -> str:
        return self.key


@dataclass(frozen=True)
class Prepared:
    workflow: Workflow
    entry: Path
    source_roots: tuple[Path, ...]
    workspace_root: Path
    providers: Mapping[str, str]
    prompts: Mapping[str, PromptExtern]
    commands: Mapping[str, ExternalToolBinding | CertifiedAdapterBinding]
    synthetic: tuple[str, ...]
    imported_workflow_manifest: Path | None = None


@dataclass(frozen=True)
class Built:
    site_count: int
    program: ClosedProgram | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True)
class Gap:
    form: str


@dataclass(frozen=True)
class Refused:
    code: str


@dataclass(frozen=True)
class NotSynthesizable:
    missing_facts: tuple[str, ...]


Outcome = Built | Gap | Refused | NotSynthesizable


class NotSynthesizableError(ValueError):
    def __init__(self, *missing_facts: str) -> None:
        self.missing_facts = tuple(missing_facts)
        super().__init__("; ".join(self.missing_facts))


@dataclass(frozen=True)
class BuildResult:
    outcome: Outcome
    program: ClosedProgram | None = None
    diagnostic: object | None = None
    prepared: Prepared | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True)
class _Facts:
    providers: frozenset[str]
    prompts: frozenset[str]
    commands: Mapping[str, tuple[str, ...]]
    adapters: frozenset[str]
    assets: frozenset[tuple[str, Path]]
    modules: frozenset[str]


def _source_owner(path: Path, module: str) -> Path:
    parts = module.split("/")
    owner = path.parents[len(parts) - 1]
    expected = owner / Path(*parts).with_suffix(".orc")
    if expected != path:
        raise ValueError(f"module {module!r} does not own {path}: expected {expected}")
    return owner


def corpus(repo_root: Path = REPO_ROOT) -> list[Workflow]:
    """Enumerate exported workflow definitions through parsed syntax owners."""

    found: list[Workflow] = []
    for relative_root in CORPUS_ROOTS:
        root = repo_root / relative_root
        for path in sorted(root.rglob("*.orc")):
            module = build_syntax_module(read_sexpr_file(path))
            if module.module_name is None:
                continue
            definitions: set[str] = set()
            for form in module.forms:
                if syntax_head_name(syntax_node_datum(form)) != "defworkflow":
                    continue
                datum = syntax_node_datum(form)
                if len(datum.items) > 1 and isinstance(datum.items[1], syntax.SyntaxIdentifier):
                    definitions.add(datum.items[1].display_name)
            owner = _source_owner(path, module.module_name)
            found.extend(
                Workflow(path, owner, module.module_name, name)
                for name in module.exports
                if name in definitions
            )
    return sorted(found, key=lambda row: (row.source.as_posix(), row.name))


def _syntax_lists(node: Any):
    if isinstance(node, syntax.SyntaxList):
        yield node
        for child in node.items:
            yield from _syntax_lists(child)


def _identifiers(node: Any):
    if isinstance(node, syntax.SyntaxIdentifier):
        yield node.display_name
    elif isinstance(node, syntax.SyntaxList):
        for child in node.items:
            yield from _identifiers(child)


def _facts_from_graph(entry: Path, source_roots: tuple[Path, ...]) -> _Facts:
    from orchestrator.workflow_lisp.modules import resolve_module_graph

    stdlib = REPO_ROOT / "orchestrator/workflow_lisp/stdlib_modules"
    graph = resolve_module_graph(entry, source_roots=(*source_roots, stdlib))
    providers: set[str] = set()
    prompts: set[str] = set()
    commands: dict[str, tuple[str, ...]] = {}
    adapters: set[str] = set()
    assets: set[tuple[str, Path]] = set()
    for module in graph.modules_by_name.values():
        syntax_module = module.syntax_module
        for form in syntax_module.forms:
            datum = syntax_node_datum(form)
            for identifier in _identifiers(datum):
                if identifier.startswith("providers."):
                    providers.add(identifier)
                elif identifier.startswith("prompts."):
                    prompts.add(identifier)
            for expression in _syntax_lists(datum):
                if syntax.syntax_head_name(expression) == "command-result" and len(expression.items) >= 2:
                    boundary_node = expression.items[1]
                    if not isinstance(boundary_node, syntax.SyntaxIdentifier):
                        continue
                    boundary = boundary_node.display_name
                    fields = _keyword_fields(expression.items[2:])
                    adapter_node = fields.get(":adapter")
                    if isinstance(adapter_node, syntax.SyntaxIdentifier):
                        adapters.add(adapter_node.display_name)
                        commands[adapter_node.display_name] = ()
                        continue
                    argv_node = fields.get(":argv")
                    prefix: list[str] = []
                    if isinstance(argv_node, syntax.SyntaxList):
                        for value in argv_node.items:
                            if not isinstance(value, syntax.SyntaxString):
                                break
                            prefix.append(value.value)
                    commands[boundary] = tuple(prefix)
            for expression in _syntax_lists(datum):
                items = expression.items
                for index, child in enumerate(items[:-1]):
                    if isinstance(child, syntax.SyntaxKeyword) and child.value == ":provider":
                        value = items[index + 1]
                        if isinstance(value, syntax.SyntaxString):
                            providers.add(value.value)
                    if isinstance(child, syntax.SyntaxKeyword) and child.value == ":rubric-asset":
                        value = items[index + 1]
                        if isinstance(value, syntax.SyntaxString):
                            assets.add((value.value, Path(module.path).parent))
    return _Facts(
        frozenset(providers), frozenset(prompts), commands,
        frozenset(adapters), frozenset(assets),
        frozenset(graph.modules_by_name),
    )


def _keyword_fields(items: tuple[Any, ...]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    index = 0
    while index + 1 < len(items):
        key = items[index]
        if isinstance(key, syntax.SyntaxKeyword):
            fields[key.value] = items[index + 1]
            index += 2
        else:
            index += 1
    return fields


def _manifest_candidates(workflow: Workflow, kind: str) -> tuple[Path, ...]:
    """Return only manifests owned by this workflow's source/input directory."""

    source = workflow.source
    name = source.stem
    local = workflow.name
    shared_name = (
        ("commands_compact.json" if "compact" in source.stem else "commands.json")
        if kind == "commands"
        else f"{kind}.json"
    )
    candidates = [
        source.with_name(f"{source.stem}.{kind}.json"),
        source.parent / shared_name,
        source.parent / "inputs" / name / f"{kind}.json",
        source.parent / "inputs" / local / f"{kind}.json",
        source.parent / "inputs" / "workflow_lisp_migrations" / f"{name}.{kind}.json",
        source.parent / "inputs" / "workflow_lisp_migrations" / f"{local}.{kind}.json",
        workflow.source_root / "inputs" / name / f"{kind}.json",
        workflow.source_root / "inputs" / local / f"{kind}.json",
        workflow.source_root / "inputs" / "workflow_lisp_migrations" / f"{name}.{kind}.json",
        workflow.source_root / "inputs" / "workflow_lisp_migrations" / f"{local}.{kind}.json",
        workflow.source_root / f"{name}.{kind}.json",
    ]
    if kind == "commands" and not (source.parent / shared_name).is_file():
        # Nested source owners may keep one shared command manifest one level up.
        candidates.append(source.parent.parent / shared_name)
    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate not in seen and candidate.is_file():
            seen.add(candidate)
            unique.append(candidate)
    return tuple(unique)


def _manifest_entries(workflow: Workflow, kind: str) -> dict[str, object]:
    found: dict[str, object] = {}
    for path in _manifest_candidates(workflow, kind):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"invalid {kind} manifest {path}: {exc}") from exc
        if not isinstance(payload, Mapping):
            raise ValueError(f"{kind} manifest {path} must be an object")
        for name, value in payload.items():
            if name in found and found[name] != value:
                raise ValueError(f"conflicting {kind} manifests for {name!r}")
            found[str(name)] = value
    return found


def _checked_command_entries() -> dict[str, list[tuple[Path, object]]]:
    """Index checked command metadata by name without hiding owner conflicts."""

    entries: dict[str, list[tuple[Path, object]]] = {}
    for relative_root in CORPUS_ROOTS:
        for path in sorted((REPO_ROOT / relative_root).rglob("*.json")):
            if "command" not in path.name.lower() or "tests" in path.parts:
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(payload, Mapping):
                continue
            for name, value in payload.items():
                entries.setdefault(str(name), []).append((path, value))
    return entries


def _select_checked_command(
    name: str,
    rows: list[tuple[Path, object]],
    modules: frozenset[str],
) -> object:
    owner_matches = [
        row
        for row in rows
        if isinstance(row[1], Mapping) and row[1].get("owner_module") in modules
    ]
    choices = owner_matches or rows
    unique = {json.dumps(value, sort_keys=True): value for _path, value in choices}
    if len(unique) != 1:
        paths = sorted(path.as_posix() for path, _value in choices)
        raise ValueError(f"checked command {name!r} has conflicting owner manifests: {paths}")
    return next(iter(unique.values()))


def _copy_file(source: Path, workspace: Path) -> str:
    try:
        relative = source.resolve().relative_to(REPO_ROOT)
    except ValueError as exc:
        raise ValueError(f"implementation is outside the checked source tree: {source}") from exc
    target = workspace / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return relative.as_posix()


def _implementation_path(argv: tuple[str, ...]) -> Path | None:
    if "-m" in argv:
        index = argv.index("-m")
        if index + 1 < len(argv):
            module_path = Path(*argv[index + 1].split(".")).with_suffix(".py")
            candidate = REPO_ROOT / module_path
            return candidate if candidate.is_file() else None
    candidate = next((Path(token) for token in argv if token.endswith(".py")), None)
    if candidate is None:
        return None
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    return candidate if candidate.is_file() else None


def _copy_command_implementation(
    name: str,
    binding: ExternalToolBinding | CertifiedAdapterBinding,
    *,
    workspace: Path,
    synthetic: list[str],
) -> ExternalToolBinding | CertifiedAdapterBinding:
    if binding.closure is not None:
        for closure_path in binding.closure:
            if closure_path in {".", "orchestrator"}:
                if closure_path == "orchestrator":
                    shutil.copytree(
                        REPO_ROOT / "orchestrator",
                        workspace / "orchestrator",
                        dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                    )
                continue
            source = REPO_ROOT / closure_path
            if not source.is_file():
                raise NotSynthesizableError(
                    f"checked command closure path {closure_path!r} has no source file"
                )
            _copy_file(source, workspace)
        return binding

    argv = binding.stable_command
    if len(argv) >= 3 and argv[:2] == ("python", "-m") and argv[2].startswith("orchestrator."):
        shutil.copytree(
            REPO_ROOT / "orchestrator",
            workspace / "orchestrator",
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        closure = ("orchestrator",)
    else:
        implementation = _implementation_path(argv)
        if implementation is None and name == "launch_experiment":
            implementation = workspace / "scripts/launch_experiment.py"
            implementation.parent.mkdir(parents=True, exist_ok=True)
            implementation.write_text(
                '''import json, os, sys
from pathlib import Path
with open(Path(__file__).with_suffix(".log"), "a", encoding="utf-8") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps({"status": "launched"}), encoding="utf-8")
''',
                encoding="utf-8",
            )
            closure = ("scripts/launch_experiment.py",)
            synthetic.append(f"command:{name}:compile-only-script-stand-in")
            return replace(binding, closure=closure)
        if implementation is None and name == "run_checks" and argv == (
            "python",
            "scripts/run_checks.py",
        ):
            implementation = workspace / "scripts/run_checks.py"
            implementation.parent.mkdir(parents=True, exist_ok=True)
            implementation.write_text(
                '''"""Task10 compile-only result-shape stand-in; never executed."""
import json
import sys

print(json.dumps({"report": sys.argv[1]}))
''',
                encoding="utf-8",
            )
            closure = ("scripts/run_checks.py",)
            synthetic.append(f"command:{name}:compile-only-script-stand-in")
            return replace(binding, closure=closure)
        if implementation is None:
            missing = (
                f"command {name!r} has literal argv prefix {argv!r}, but no checked implementation source and closure"
            )
            if name == "pilot_product_manifest" and argv == ("python",):
                missing = (
                    "command 'pilot_product_manifest' is parameterized by workflow input "
                ) + "'controller_script', whose concrete script path, source bytes, and closure are missing"
            raise NotSynthesizableError(missing)
        closure_rows = [_copy_file(implementation, workspace)]
        if name == "materialize_lisp_frontend_work_item_inputs":
            neighbor = implementation.with_name("neurips_markdown_frontmatter.py")
            if not neighbor.is_file():
                raise NotSynthesizableError(
                    f"command {name!r} requires local helper {neighbor.relative_to(REPO_ROOT).as_posix()}"
                )
            closure_rows.append(_copy_file(neighbor, workspace))
        closure = tuple(closure_rows)
    return replace(binding, closure=closure)


def _copy_imported_workflow_manifest(
    workflow: Workflow,
    *,
    destination_root: Path,
    library_copy: Path | None,
) -> Path | None:
    candidates = _manifest_candidates(workflow, "imported_workflow_bundles")
    if not candidates:
        return None
    if len(candidates) != 1:
        raise NotSynthesizableError(
            "multiple imported-workflow manifests require one Task9 manifest path"
        )
    source = candidates[0]
    try:
        relative = source.relative_to(workflow.source_root.resolve())
        copied = destination_root / relative
    except ValueError:
        library = (REPO_ROOT / "workflows/library").resolve()
        if library_copy is None:
            raise NotSynthesizableError(
                f"imported-workflow manifest {source} is outside the copied source roots"
            )
        try:
            relative = source.relative_to(library)
        except ValueError as exc:
            raise NotSynthesizableError(
                f"imported-workflow manifest {source} is outside the copied source roots"
            ) from exc
        copied = library_copy / relative
    if not copied.is_file():
        raise NotSynthesizableError(
            f"imported-workflow manifest {source} was not retained in the prepared source copy"
        )
    return copied


def _prompt_extern(name: str, value: object) -> PromptExtern:
    if isinstance(value, str):
        return PromptExtern(name=name, asset_file=value)
    if isinstance(value, Mapping):
        if set(value) == {"asset_file"} and isinstance(value["asset_file"], str):
            return PromptExtern(name=name, asset_file=value["asset_file"])
        if set(value) == {"input_file"} and isinstance(value["input_file"], str):
            return PromptExtern(name=name, input_file=value["input_file"])
    raise ValueError(f"unsupported prompt manifest value for {name!r}: {value!r}")


def _materialize_prompt_path(
    path: str,
    *,
    workspace: Path,
    source_directories: tuple[Path, ...],
) -> None:
    destination = workspace / path
    if destination.is_file():
        return
    source = next(
        (directory / path for directory in source_directories if (directory / path).is_file()),
        None,
    )
    if source is None:
        raise ValueError(f"checked prompt asset {path!r} has no source file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _target_form(source: Path):
    parsed = read_sexpr_file(source)
    root = parsed.items[0]
    return next(
        form
        for form in root.items[1:]
        if isinstance(form, ListExpr)
        and len(form.items) == 2
        and isinstance(form.items[0], KeywordAtom)
        and form.items[0].value == ":target-dsl"
    )


def target_dsl_version(source: Path) -> str:
    return build_syntax_module(read_sexpr_file(source)).target_dsl_version


def entry_with_target(source: Path, target: str) -> str:
    target_form = _target_form(source)
    start, end = target_form.span.start.offset, target_form.span.end.offset
    text = source.read_text(encoding="utf-8")
    replacement = f'(:target-dsl "{target}")'
    return text[:start] + replacement + text[end:]


def _replace_entry_target(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        entry_with_target(source, syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION),
        encoding="utf-8",
    )


def prepare(workflow: Workflow, scratch: Path) -> Prepared:
    """Copy a workflow's owner root and synthesize only explicit compile facts."""

    destination_root = scratch / "source"
    if destination_root.exists():
        shutil.rmtree(destination_root)
    shutil.copytree(workflow.source_root, destination_root)
    source_relative = workflow.source.relative_to(workflow.source_root)
    entry = destination_root / source_relative
    _replace_entry_target(workflow.source, entry)
    roots = [destination_root]
    library = REPO_ROOT / "workflows/library"
    library_copy: Path | None = None
    if workflow.source_root != library and library.is_dir():
        library_copy = scratch / "workflow-library"
        shutil.copytree(library, library_copy, dirs_exist_ok=True)
        roots.append(library_copy)
    imported_manifest = _copy_imported_workflow_manifest(
        workflow,
        destination_root=destination_root,
        library_copy=library_copy,
    )

    facts = _facts_from_graph(entry, tuple(roots))
    provider_rows = _manifest_entries(workflow, "providers")
    prompt_rows = _manifest_entries(workflow, "prompts")
    command_rows = _manifest_entries(workflow, "commands")
    global_commands = _checked_command_entries()
    for name in facts.commands:
        if name not in command_rows and name in global_commands:
            command_rows[name] = _select_checked_command(
                name, global_commands[name], facts.modules
            )
    synthetic: list[str] = []
    providers: dict[str, str] = {}
    for name, value in provider_rows.items():
        if not isinstance(value, str):
            raise ValueError(f"provider manifest entry {name!r} is not a provider name")
        providers[name] = value
    for name in facts.providers:
        if name not in providers:
            providers[name] = "codex"
            synthetic.append(f"provider:{name}:compile-only-alias")

    prompts: dict[str, PromptExtern] = {}
    for name, value in prompt_rows.items():
        prompts[name] = _prompt_extern(name, value)
    for name in sorted(facts.prompts - prompts.keys()):
        path = f"task10_compile_only/prompts/{name.removeprefix('prompts.').replace('.', '/')}.md"
        target = destination_root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("", encoding="utf-8")
        synthetic.append(f"prompt:{name}:compile-only-input")
        prompts[name] = PromptExtern(name=name, input_file=path)

    source_directories = tuple(
        dict.fromkeys(
            [workflow.source.parent]
            + [module_parent for _path, module_parent in facts.assets]
            + [workflow.source_root]
            + [REPO_ROOT]
        )
    )
    for name, extern in prompts.items():
        if name not in facts.prompts:
            continue
        try:
            _materialize_prompt_path(
                extern.path, workspace=destination_root, source_directories=source_directories
            )
        except ValueError as exc:
            raise NotSynthesizableError(str(exc)) from exc
    for asset, _module_parent in facts.assets:
        try:
            _materialize_prompt_path(
                asset, workspace=destination_root, source_directories=source_directories
            )
        except ValueError as exc:
            raise NotSynthesizableError(str(exc)) from exc

    from orchestrator.workflow_lisp.build_manifest_io import _parse_command_boundaries_manifest

    commands: dict[str, ExternalToolBinding | CertifiedAdapterBinding] = {}
    from orchestrator.workflow_lisp.stdlib_contracts import STDLIB_CERTIFIED_ADAPTER_BINDINGS_BY_NAME

    rows: dict[str, object] = dict(command_rows)
    for name in facts.adapters - rows.keys():
        binding = STDLIB_CERTIFIED_ADAPTER_BINDINGS_BY_NAME.get(name)
        if binding is None:
            raise ValueError(f"certified adapter {name!r} has no checked metadata")
        rows[name] = binding
    for name, argv in facts.commands.items():
        if name in rows:
            continue
        if name in facts.adapters:
            continue
        if not argv:
            raise NotSynthesizableError(
                f"command {name!r} has no checked manifest or leading literal :argv"
            )
        rows[name] = ExternalToolBinding(name=name, stable_command=argv)
    manifest_rows = {name: value for name, value in rows.items() if isinstance(value, Mapping)}
    parsed_rows = dict(
        _parse_command_boundaries_manifest(manifest_rows, manifest_path=None)
    )
    parsed_rows.update(
        {
            name: value
            for name, value in rows.items()
            if isinstance(value, (ExternalToolBinding, CertifiedAdapterBinding))
        }
    )
    for name, binding in parsed_rows.items():
        commands[name] = _copy_command_implementation(
            name, binding, workspace=destination_root, synthetic=synthetic
        )

    return Prepared(
        workflow=workflow,
        entry=entry,
        source_roots=tuple(roots),
        workspace_root=destination_root,
        providers=providers,
        prompts=prompts,
        commands=commands,
        synthetic=tuple(synthetic),
        imported_workflow_manifest=imported_manifest,
    )


def compile(prepared: Prepared):
    """Compile source to the public typed evaluated-execution program."""

    imported_bundles: Mapping[str, object] = {}
    imported_programs: Mapping[str, object] = {}
    if prepared.imported_workflow_manifest is not None:
        from orchestrator.workflow_lisp.build import FrontendBuildRequest
        from orchestrator.workflow_lisp.build_manifest_io import (
            ConfigurationReadTrace,
            _json_data,
        )
        from orchestrator.workflow_lisp.closed.artifact import _load_closed_imports

        config_root = prepared.workspace_root / "task10-configuration"
        config_root.mkdir(parents=True, exist_ok=True)
        providers_path = config_root / "providers.json"
        providers_path.write_text(
            json.dumps(dict(prepared.providers), sort_keys=True), encoding="utf-8"
        )
        prompts_path = config_root / "prompts.json"
        prompts_path.write_text(
            json.dumps(
                {
                    name: {extern.source_kind: extern.path}
                    for name, extern in prepared.prompts.items()
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        command_rows = {}
        for name, binding in prepared.commands.items():
            if binding.closure is None:
                raise NotSynthesizableError(
                    f"command {name!r} has no audited closure for imported-producer routing"
                )
            row = _json_data(binding)
            row["kind"] = (
                "certified_adapter"
                if isinstance(binding, CertifiedAdapterBinding)
                else "external_tool"
            )
            row["closure"] = list(binding.closure)
            if isinstance(binding, CertifiedAdapterBinding):
                row.pop("declared_promoted_fields", None)
                for field_name in PROMOTED_CALL_REQUIRED_METADATA_FIELDS - (
                    binding.declared_promoted_fields
                ):
                    row.pop(field_name, None)
            command_rows[name] = row
        commands_path = config_root / "commands.json"
        commands_path.write_text(
            json.dumps(command_rows, sort_keys=True), encoding="utf-8"
        )
        request = FrontendBuildRequest(
            source_path=prepared.entry,
            source_roots=prepared.source_roots,
            entry_workflow=prepared.workflow.canonical_name,
            provider_externs_path=providers_path,
            prompt_externs_path=prompts_path,
            imported_workflow_bundles_path=prepared.imported_workflow_manifest,
            command_boundaries_path=commands_path,
            workspace_root=prepared.workspace_root,
        )
        imported_bundles, imported_programs = _load_closed_imports(
            request,
            provider_externs=prepared.providers,
            prompt_externs=prepared.prompts,
            command_boundaries=prepared.commands,
            configuration_trace=ConfigurationReadTrace(),
        )
    return compile_typed_program(
        prepared.entry,
        entry_workflow=prepared.workflow.canonical_name,
        source_roots=prepared.source_roots,
        command_boundaries=prepared.commands,
        provider_externs=prepared.providers,
        prompt_externs=prepared.prompts,
        imported_workflow_bundles=imported_bundles,
        imported_programs=imported_programs,
        workspace_root=prepared.workspace_root,
    )


def try_build(workflow: Workflow, scratch: Path) -> BuildResult:
    try:
        prepared = prepare(workflow, scratch)
    except NotSynthesizableError as exc:
        return BuildResult(NotSynthesizable(exc.missing_facts))
    try:
        typed = compile(prepared)
        program = build_closed_program(typed)
    except LispFrontendCompileError as exc:
        diagnostic = exc.diagnostics[0]
        if diagnostic.code == "closed_program_gap":
            form = next(
                (note.removeprefix("form=") for note in diagnostic.notes if note.startswith("form=")),
                "",
            )
            if not form:
                raise AssertionError("closed-program gap did not name its form") from exc
            return BuildResult(Gap(form), diagnostic=diagnostic, prepared=prepared)
        if diagnostic.phase == "typecheck" or diagnostic.code == "macro_arity_error":
            return BuildResult(Refused(diagnostic.code), diagnostic=diagnostic, prepared=prepared)
        raise
    return BuildResult(Built(len(program.sites), program), program=program, prepared=prepared)
