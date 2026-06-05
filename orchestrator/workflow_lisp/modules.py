"""Workflow Lisp module graph discovery and import/export resolution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .definitions import WorkflowLispModule
from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .macros import MacroCatalog, MacroDef
from .reader import read_sexpr_file
from .spans import SourceSpan
from .syntax import ImportDirective, WorkflowLispSyntaxModule, build_syntax_module


@dataclass(frozen=True)
class ResolvedModuleSource:
    """Parsed module source as discovered in the import graph.

    `source_root` records which configured root produced the file so later
    imports can report ambiguity and path mismatches against the same search
    model the compiler used.
    """

    module_name: str
    path: Path
    source_root: Path
    syntax_module: WorkflowLispSyntaxModule
    imports: tuple[str, ...]


@dataclass(frozen=True)
class ModuleMemberBinding:
    """Binding from an imported name to a module-qualified member.

    The `kind` keeps type, macro, procedure, and workflow namespaces separate;
    `canonical_name` is the stable name downstream catalogs use after import
    resolution.
    """

    kind: str
    module_name: str
    member_name: str
    canonical_name: str


@dataclass(frozen=True)
class ModuleExportSurface:
    """Public types, macros, procedures, and workflows visible to importers.

    This object is derived before dependent modules compile so import
    resolution can reject missing exports, ambiguous imports, and
    cross-namespace mistakes without reading executable bodies.
    """

    module_name: str
    types_by_name: Mapping[str, ModuleMemberBinding]
    schemas_by_name: Mapping[str, ModuleMemberBinding]
    macros_by_name: Mapping[str, ModuleMemberBinding]
    functions_by_name: Mapping[str, ModuleMemberBinding]
    procedures_by_name: Mapping[str, ModuleMemberBinding]
    workflows_by_name: Mapping[str, ModuleMemberBinding]

    def binding_for(self, name: str) -> ModuleMemberBinding | None:
        """Return the exported binding for a name across all member namespaces."""

        for bindings in (
            self.types_by_name,
            self.schemas_by_name,
            self.macros_by_name,
            self.functions_by_name,
            self.procedures_by_name,
            self.workflows_by_name,
        ):
            binding = bindings.get(name)
            if binding is not None:
                return binding
        return None


@dataclass(frozen=True)
class ModuleImportScope:
    """All imported names visible while compiling one module.

    Type names support `:only` unqualified imports because they appear in type
    signatures; procedures and workflows remain canonicalized through explicit
    bindings so call expressions carry stable module-qualified identities.
    """

    module_name: str
    alias_to_module: Mapping[str, str]
    explicitly_imported_modules: frozenset[str]
    type_bindings: Mapping[str, ModuleMemberBinding]
    schema_bindings: Mapping[str, ModuleMemberBinding]
    macro_bindings: Mapping[str, ModuleMemberBinding]
    function_bindings: Mapping[str, ModuleMemberBinding]
    procedure_bindings: Mapping[str, ModuleMemberBinding]
    workflow_bindings: Mapping[str, ModuleMemberBinding]
    unqualified_type_bindings: Mapping[str, ModuleMemberBinding]
    unqualified_schema_bindings: Mapping[str, ModuleMemberBinding]

    def resolve_type_name(self, name: str, *, span: SourceSpan, form_path: tuple[str, ...]) -> str:
        """Resolve a type reference or leave it local when no import matches."""

        if name in self.unqualified_type_bindings:
            return self.unqualified_type_bindings[name].canonical_name
        self_prefix = f"{self.module_name}/"
        if name.startswith(self_prefix):
            return name[len(self_prefix) :]
        qualified = _resolve_qualified_binding(
            name,
            alias_to_module=self.alias_to_module,
            explicitly_imported_modules=self.explicitly_imported_modules,
            imported_bindings=self.type_bindings,
            kind_label="type",
            span=span,
            form_path=form_path,
        )
        if qualified is not None:
            return qualified.canonical_name
        return name

    def resolve_schema_name(self, name: str, *, span: SourceSpan, form_path: tuple[str, ...]) -> str:
        """Resolve a schema include target or leave it local when no import matches."""

        if name in self.unqualified_schema_bindings:
            return self.unqualified_schema_bindings[name].canonical_name
        qualified = _resolve_qualified_binding(
            name,
            alias_to_module=self.alias_to_module,
            explicitly_imported_modules=self.explicitly_imported_modules,
            imported_bindings=self.schema_bindings,
            kind_label="schema",
            span=span,
            form_path=form_path,
        )
        if qualified is not None:
            return qualified.canonical_name
        return name

    def has_visible_schema_name(self, name: str) -> bool:
        """Return whether `name` is an imported schema alias or qualified reference."""

        return name in self.unqualified_schema_bindings or name in self.schema_bindings

    def resolve_procedure_name(self, name: str, *, span: SourceSpan, form_path: tuple[str, ...]) -> str:
        """Resolve a procedure call head to the canonical callable key."""

        binding = self.procedure_bindings.get(name)
        if binding is not None:
            return binding.canonical_name
        qualified = _resolve_qualified_binding(
            name,
            alias_to_module=self.alias_to_module,
            explicitly_imported_modules=self.explicitly_imported_modules,
            imported_bindings=self.procedure_bindings,
            kind_label="procedure",
            span=span,
            form_path=form_path,
        )
        if qualified is not None:
            return qualified.canonical_name
        return name

    def resolve_function_name(self, name: str, *, span: SourceSpan, form_path: tuple[str, ...]) -> str:
        """Resolve a helper call head to the canonical callable key."""

        binding = self.function_bindings.get(name)
        if binding is not None:
            return binding.canonical_name
        qualified = _resolve_qualified_binding(
            name,
            alias_to_module=self.alias_to_module,
            explicitly_imported_modules=self.explicitly_imported_modules,
            imported_bindings=self.function_bindings,
            kind_label="function",
            span=span,
            form_path=form_path,
        )
        if qualified is not None:
            return qualified.canonical_name
        return name

    def resolve_workflow_name(self, name: str, *, span: SourceSpan, form_path: tuple[str, ...]) -> str:
        """Resolve a workflow call target to the canonical callable key."""

        binding = self.workflow_bindings.get(name)
        if binding is not None:
            return binding.canonical_name
        qualified = _resolve_qualified_binding(
            name,
            alias_to_module=self.alias_to_module,
            explicitly_imported_modules=self.explicitly_imported_modules,
            imported_bindings=self.workflow_bindings,
            kind_label="workflow",
            span=span,
            form_path=form_path,
        )
        if qualified is not None:
            return qualified.canonical_name
        return name


@dataclass(frozen=True)
class LinkedModuleGraph:
    """Reachable module graph ordered so imports compile before importers."""

    entry_module_name: str
    modules_by_name: Mapping[str, ResolvedModuleSource]
    topological_order: tuple[str, ...]
    export_surfaces_by_name: Mapping[str, ModuleExportSurface]


def canonical_callable_key(module_name: str, member_name: str) -> str:
    """Return the stable module-qualified key for a procedure or workflow."""

    return f"{module_name}::{member_name}"


def resolve_module_graph(
    path: Path,
    *,
    source_roots: tuple[Path, ...] | None = None,
) -> LinkedModuleGraph:
    """Discover, parse, and topologically order modules reachable from `path`.

    Import paths are resolved against `source_roots`; duplicate module names from
    different roots are rejected so later call/type resolution has one authority
    for each module name.
    """

    resolved_roots = tuple(source_roots or (path.parent,))
    modules_by_name: dict[str, ResolvedModuleSource] = {}
    visiting: list[str] = []
    topological: list[str] = []

    def load_module(module_path: Path) -> ResolvedModuleSource:
        syntax_module = build_syntax_module(read_sexpr_file(module_path))
        if syntax_module.module_name is None:
            raise LispFrontendCompileError(
                (
                    LispFrontendDiagnostic(
                        code="module_declaration_missing",
                        message="linked module compilation requires one `defmodule` directive",
                        span=syntax_module.span,
                        form_path=("workflow-lisp",),
                    ),
                )
            )
        source_root = _resolve_source_root(module_path, source_roots=resolved_roots)
        expected_path = source_root / Path(*syntax_module.module_name.split("/"))
        expected_path = expected_path.with_suffix(".orc")
        if expected_path != module_path:
            raise LispFrontendCompileError(
                (
                    LispFrontendDiagnostic(
                        code="module_path_mismatch",
                        message=(
                            f"module `{syntax_module.module_name}` must live at "
                            f"`{expected_path.as_posix()}`"
                        ),
                        span=syntax_module.module_directive.span if syntax_module.module_directive else syntax_module.span,
                        form_path=syntax_module.module_directive.form_path if syntax_module.module_directive else ("workflow-lisp",),
                    ),
                )
            )
        return ResolvedModuleSource(
            module_name=syntax_module.module_name,
            path=module_path,
            source_root=source_root,
            syntax_module=syntax_module,
            imports=tuple(import_directive.module_name for import_directive in syntax_module.imports),
        )

    def visit_module_path(module_path: Path) -> None:
        resolved = load_module(module_path)
        if resolved.module_name in visiting:
            cycle_start = visiting.index(resolved.module_name)
            cycle = visiting[cycle_start:] + [resolved.module_name]
            raise LispFrontendCompileError(
                tuple(
                    LispFrontendDiagnostic(
                        code="module_cycle",
                        message=f"module cycle detected through `{module_name}`",
                        span=resolved.syntax_module.span,
                        form_path=("workflow-lisp",),
                    )
                    for module_name in cycle
                )
            )
        existing = modules_by_name.get(resolved.module_name)
        if existing is not None:
            if existing.path != resolved.path:
                raise LispFrontendCompileError(
                    (
                        LispFrontendDiagnostic(
                            code="module_import_ambiguous",
                            message=f"module `{resolved.module_name}` resolves to multiple source files",
                            span=resolved.syntax_module.span,
                            form_path=("workflow-lisp",),
                        ),
                    )
                )
            return
        visiting.append(resolved.module_name)
        modules_by_name[resolved.module_name] = resolved
        for imported_module_name in resolved.imports:
            visit_module_path(_resolve_import_path(imported_module_name, source_roots=resolved_roots))
        visiting.pop()
        topological.append(resolved.module_name)

    visit_module_path(path)
    export_surfaces = {
        module_name: derive_export_surface(
            module_source.syntax_module,
            allow_unknown_exports=True,
        )
        for module_name, module_source in modules_by_name.items()
    }
    return LinkedModuleGraph(
        entry_module_name=load_module(path).module_name,
        modules_by_name=modules_by_name,
        topological_order=tuple(topological),
        export_surfaces_by_name=export_surfaces,
    )


def derive_export_surface(
    syntax_module: WorkflowLispSyntaxModule,
    *,
    local_macros: MacroCatalog | None = None,
    local_module: WorkflowLispModule | None = None,
    procedure_names: tuple[str, ...] = (),
    function_names: tuple[str, ...] = (),
    workflow_names: tuple[str, ...] = (),
    allow_unknown_exports: bool = False,
) -> ModuleExportSurface:
    """Build and validate the public names exported by one module.

    During graph discovery `allow_unknown_exports` lets the compiler sketch the
    export list before all bodies are elaborated. During real compilation the
    same function tightens the check so exports must name a local type, macro,
    procedure, or workflow.
    """

    module_name = syntax_module.module_name
    assert module_name is not None
    type_names = {
        definition.name
        for definition in (local_module.definitions if local_module is not None else ())
    }
    schema_names = {
        schema.name
        for schema in (local_module.schemas if local_module is not None else ())
    }
    macro_catalog = local_macros or MacroCatalog(definitions_by_name={})
    local_form_names = {
        "defun": set(function_names),
        "defproc": set(procedure_names),
        "defworkflow": set(workflow_names),
    }
    if not function_names or not procedure_names or not workflow_names:
        for form in syntax_module.forms:
            items = form.items
            if len(items) < 2:
                continue
            head = getattr(items[0], "resolved_name", None)
            name = getattr(items[1], "resolved_name", None)
            if head == "defrecord" or head == "defenum" or head == "defunion" or head == "defpath":
                if name is not None:
                    type_names.add(name)
            if head == "defschema" and name is not None:
                schema_names.add(name)
            if head in local_form_names and name is not None:
                local_form_names[head].add(name)
    exported_types: dict[str, ModuleMemberBinding] = {}
    exported_schemas: dict[str, ModuleMemberBinding] = {}
    exported_macros: dict[str, ModuleMemberBinding] = {}
    exported_functions: dict[str, ModuleMemberBinding] = {}
    exported_procedures: dict[str, ModuleMemberBinding] = {}
    exported_workflows: dict[str, ModuleMemberBinding] = {}
    seen_exports: set[str] = set()
    for exported_name in syntax_module.exports:
        if exported_name in seen_exports:
            raise LispFrontendCompileError(
                (
                    LispFrontendDiagnostic(
                        code="module_export_duplicate",
                        message=f"duplicate export `{exported_name}`",
                        span=syntax_module.export_directive.span if syntax_module.export_directive else syntax_module.span,
                        form_path=syntax_module.export_directive.form_path if syntax_module.export_directive else ("workflow-lisp",),
                    ),
                )
            )
        seen_exports.add(exported_name)
        if exported_name in type_names:
            exported_types[exported_name] = ModuleMemberBinding(
                kind="type",
                module_name=module_name,
                member_name=exported_name,
                canonical_name=f"{module_name}::{exported_name}",
            )
            continue
        if exported_name in schema_names:
            exported_schemas[exported_name] = ModuleMemberBinding(
                kind="schema",
                module_name=module_name,
                member_name=exported_name,
                canonical_name=canonical_callable_key(module_name, exported_name),
            )
            continue
        if exported_name in macro_catalog.definitions_by_name:
            exported_macros[exported_name] = ModuleMemberBinding(
                kind="macro",
                module_name=module_name,
                member_name=exported_name,
                canonical_name=exported_name,
            )
            continue
        if exported_name in local_form_names["defun"]:
            exported_functions[exported_name] = ModuleMemberBinding(
                kind="function",
                module_name=module_name,
                member_name=exported_name,
                canonical_name=canonical_callable_key(module_name, exported_name),
            )
            continue
        if exported_name in local_form_names["defproc"]:
            exported_procedures[exported_name] = ModuleMemberBinding(
                kind="procedure",
                module_name=module_name,
                member_name=exported_name,
                canonical_name=canonical_callable_key(module_name, exported_name),
            )
            continue
        if exported_name in local_form_names["defworkflow"]:
            exported_workflows[exported_name] = ModuleMemberBinding(
                kind="workflow",
                module_name=module_name,
                member_name=exported_name,
                canonical_name=canonical_callable_key(module_name, exported_name),
            )
            continue
        if not allow_unknown_exports:
            raise LispFrontendCompileError(
                (
                    LispFrontendDiagnostic(
                        code="module_export_missing",
                        message=f"export `{exported_name}` is not a locally defined type, macro, function, procedure, or workflow",
                        span=syntax_module.export_directive.span if syntax_module.export_directive else syntax_module.span,
                        form_path=syntax_module.export_directive.form_path if syntax_module.export_directive else ("workflow-lisp",),
                    ),
                )
            )
    return ModuleExportSurface(
        module_name=module_name,
        types_by_name=exported_types,
        schemas_by_name=exported_schemas,
        macros_by_name=exported_macros,
        functions_by_name=exported_functions,
        procedures_by_name=exported_procedures,
        workflows_by_name=exported_workflows,
    )


def build_import_scope(
    module: WorkflowLispModule,
    *,
    export_surfaces_by_name: Mapping[str, ModuleExportSurface],
) -> ModuleImportScope:
    """Resolve import directives into module-qualified lookup tables.

    This is where aliases, `:only` names, qualified module paths, and ambiguous
    unqualified imports become explicit bindings used by definitions, macros,
    procedure calls, and workflow calls.
    """

    alias_to_module: dict[str, str] = {}
    type_bindings: dict[str, ModuleMemberBinding] = {}
    schema_bindings: dict[str, ModuleMemberBinding] = {}
    macro_bindings: dict[str, ModuleMemberBinding] = {}
    function_bindings: dict[str, ModuleMemberBinding] = {}
    procedure_bindings: dict[str, ModuleMemberBinding] = {}
    workflow_bindings: dict[str, ModuleMemberBinding] = {}
    unqualified_type_bindings: dict[str, ModuleMemberBinding] = {}
    unqualified_schema_bindings: dict[str, ModuleMemberBinding] = {}
    for import_directive in module.imports:
        if import_directive.alias in alias_to_module:
            raise LispFrontendCompileError(
                (
                    LispFrontendDiagnostic(
                        code="module_alias_duplicate",
                        message=f"duplicate import alias `{import_directive.alias}`",
                        span=import_directive.span,
                        form_path=import_directive.form_path,
                    ),
                )
            )
        alias_to_module[import_directive.alias] = import_directive.module_name
        surface = export_surfaces_by_name.get(import_directive.module_name)
        if surface is None:
            raise LispFrontendCompileError(
                (
                    LispFrontendDiagnostic(
                        code="module_not_found",
                        message=f"unable to resolve imported module `{import_directive.module_name}`",
                        span=import_directive.span,
                        form_path=import_directive.form_path,
                    ),
                )
            )
        _register_alias_bindings(
            import_directive.alias,
            surface,
            type_bindings,
            schema_bindings,
            macro_bindings,
            function_bindings,
            procedure_bindings,
            workflow_bindings,
        )
        if not import_directive.only:
            continue
        for member_name in import_directive.only:
            binding = surface.binding_for(member_name)
            if binding is None:
                raise LispFrontendCompileError(
                    (
                        LispFrontendDiagnostic(
                            code="module_export_missing",
                            message=f"module `{surface.module_name}` does not export `{member_name}`",
                            span=import_directive.span,
                            form_path=import_directive.form_path,
                        ),
                    )
                )
            if binding.kind == "type":
                existing = unqualified_type_bindings.get(member_name)
                if existing is not None and existing.canonical_name != binding.canonical_name:
                    raise LispFrontendCompileError(
                        (
                            LispFrontendDiagnostic(
                                code="module_import_ambiguous",
                                message=f"ambiguous imported name `{member_name}`",
                                span=import_directive.span,
                                form_path=import_directive.form_path,
                            ),
                        )
                    )
                unqualified_type_bindings[member_name] = binding
                continue
            if binding.kind == "schema":
                existing = unqualified_schema_bindings.get(member_name)
                if existing is not None and existing.canonical_name != binding.canonical_name:
                    raise LispFrontendCompileError(
                        (
                            LispFrontendDiagnostic(
                                code="module_import_ambiguous",
                                message=f"ambiguous imported name `{member_name}`",
                                span=import_directive.span,
                                form_path=import_directive.form_path,
                            ),
                        )
                    )
                unqualified_schema_bindings[member_name] = binding
                continue
            target_bindings = {
                "macro": macro_bindings,
                "function": function_bindings,
                "procedure": procedure_bindings,
                "workflow": workflow_bindings,
            }[binding.kind]
            if binding.kind in {"function", "procedure"}:
                other_bindings = procedure_bindings if binding.kind == "function" else function_bindings
                existing_other = other_bindings.get(member_name)
                if existing_other is not None and existing_other.canonical_name != binding.canonical_name:
                    raise LispFrontendCompileError(
                        (
                            LispFrontendDiagnostic(
                                code="callable_name_collision",
                                message=f"ambiguous callable name `{member_name}`",
                                span=import_directive.span,
                                form_path=import_directive.form_path,
                            ),
                        )
                    )
            existing = target_bindings.get(member_name)
            if existing is not None:
                same_import_binding = existing.canonical_name == binding.canonical_name
                if binding.kind == "macro":
                    same_import_binding = (
                        existing.kind == binding.kind
                        and existing.module_name == binding.module_name
                        and existing.member_name == binding.member_name
                    )
                if not same_import_binding:
                    raise LispFrontendCompileError(
                        (
                            LispFrontendDiagnostic(
                                code="module_import_ambiguous",
                                message=f"ambiguous imported name `{member_name}`",
                                span=import_directive.span,
                                form_path=import_directive.form_path,
                            ),
                        )
                    )
            target_bindings[member_name] = binding
    return ModuleImportScope(
        module_name=module.module_name or "<anonymous>",
        alias_to_module=alias_to_module,
        explicitly_imported_modules=frozenset(import_directive.module_name for import_directive in module.imports),
        type_bindings=type_bindings,
        schema_bindings=schema_bindings,
        macro_bindings=macro_bindings,
        function_bindings=function_bindings,
        procedure_bindings=procedure_bindings,
        workflow_bindings=workflow_bindings,
        unqualified_type_bindings=unqualified_type_bindings,
        unqualified_schema_bindings=unqualified_schema_bindings,
    )


def imported_macro_catalog(
    scope: ModuleImportScope,
    *,
    exported_macros_by_module: Mapping[str, Mapping[str, MacroDef]],
) -> Mapping[str, MacroDef]:
    """Collect imported macro definitions under their accessible local names."""

    imported: dict[str, MacroDef] = {}
    for accessible_name, binding in scope.macro_bindings.items():
        module_macros = exported_macros_by_module.get(binding.module_name, {})
        macro_def = module_macros.get(binding.member_name)
        if macro_def is not None:
            imported[accessible_name] = macro_def
    return imported


def _register_alias_bindings(
    alias: str,
    surface: ModuleExportSurface,
    type_bindings: dict[str, ModuleMemberBinding],
    schema_bindings: dict[str, ModuleMemberBinding],
    macro_bindings: dict[str, ModuleMemberBinding],
    function_bindings: dict[str, ModuleMemberBinding],
    procedure_bindings: dict[str, ModuleMemberBinding],
    workflow_bindings: dict[str, ModuleMemberBinding],
) -> None:
    for member_name, binding in surface.types_by_name.items():
        type_bindings[f"{alias}.{member_name}"] = binding
        type_bindings[f"{surface.module_name}/{member_name}"] = binding
    for member_name, binding in surface.schemas_by_name.items():
        schema_bindings[f"{alias}.{member_name}"] = binding
        schema_bindings[f"{surface.module_name}/{member_name}"] = binding
    for member_name, binding in surface.macros_by_name.items():
        macro_bindings[f"{alias}.{member_name}"] = binding
        macro_bindings[f"{surface.module_name}/{member_name}"] = binding
    for member_name, binding in surface.functions_by_name.items():
        function_bindings[f"{alias}.{member_name}"] = binding
        function_bindings[f"{surface.module_name}/{member_name}"] = binding
    for member_name, binding in surface.procedures_by_name.items():
        procedure_bindings[f"{alias}.{member_name}"] = binding
        procedure_bindings[f"{surface.module_name}/{member_name}"] = binding
    for member_name, binding in surface.workflows_by_name.items():
        workflow_bindings[f"{alias}.{member_name}"] = binding
        workflow_bindings[f"{surface.module_name}/{member_name}"] = binding


def _resolve_qualified_binding(
    name: str,
    *,
    alias_to_module: Mapping[str, str],
    explicitly_imported_modules: frozenset[str],
    imported_bindings: Mapping[str, ModuleMemberBinding],
    kind_label: str,
    span: SourceSpan,
    form_path: tuple[str, ...],
) -> ModuleMemberBinding | None:
    if name in imported_bindings:
        return imported_bindings[name]
    if "." in name and "/" in name:
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="module_reference_invalid",
                    message=f"invalid {kind_label} reference `{name}`",
                    span=span,
                    form_path=form_path,
                ),
            )
        )
    if name.count(".") > 1:
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="module_reference_invalid",
                    message=f"invalid {kind_label} reference `{name}`",
                    span=span,
                    form_path=form_path,
                ),
            )
        )
    if "/" not in name:
        return None
    module_name, _, member_name = name.rpartition("/")
    if module_name in explicitly_imported_modules:
        return imported_bindings.get(name)
    return None


def _resolve_import_path(module_name: str, *, source_roots: tuple[Path, ...]) -> Path:
    candidates = [(source_root / Path(*module_name.split("/"))).with_suffix(".orc") for source_root in source_roots]
    existing = tuple(candidate for candidate in candidates if candidate.exists())
    if len(existing) == 1:
        return existing[0]
    if len(existing) > 1:
        raise LispFrontendCompileError(
            (
                LispFrontendDiagnostic(
                    code="module_import_ambiguous",
                    message=f"module `{module_name}` resolves to multiple source files",
                    span=_synthetic_span(f"<module:{module_name}>"),
                    form_path=("workflow-lisp", "import"),
                ),
            )
        )
    raise LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code="module_not_found",
                message=f"unable to resolve imported module `{module_name}`",
                span=_synthetic_span(f"<module:{module_name}>"),
                form_path=("workflow-lisp", "import"),
            ),
        )
    )


def _resolve_source_root(path: Path, *, source_roots: tuple[Path, ...]) -> Path:
    for source_root in source_roots:
        try:
            path.relative_to(source_root)
        except ValueError:
            continue
        return source_root
    return path.parent


def _synthetic_span(path: str) -> SourceSpan:
    from .spans import SourcePosition

    return SourceSpan(
        start=SourcePosition(path=path, line=1, column=1, offset=0),
        end=SourcePosition(path=path, line=1, column=1, offset=0),
    )
