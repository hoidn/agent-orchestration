"""Candidate identity, immutable snapshots, compilation and edit validation.

A candidate is a directory. The top-level `.orchestrate/` (the compiler's build cache) is derived, not content.
`compile_candidate` runs the frozen runtime's orchestrator (`python -P -m orchestrator` with PYTHONPATH set to the
runtime checkout, the commit `candidate_id` binds and evaluations run) with cwd=root, so the build cache lands inside
the candidate.

Edit validation (docs/design/orc_structural_search_driver.md, "Edit Validation And Transactions") reads parent and
child with the ordinary reader (`read_sexpr_file`, which normalizes CRLF) and compares forms modulo spans, so
comments and formatting never count as changes.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from experiments.orc_structural_search.config import ExperimentConfig
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.reader import read_sexpr_file, read_sexpr_text
from orchestrator.workflow_lisp.sexpr import KeywordAtom, ListExpr, SExpr, StringAtom, SymbolAtom

BUILD_CACHE = ".orchestrate"
CRASH_TAIL_CHARS = 4000


@dataclass(frozen=True)
class CompileOutcome:
    status: str  # "accepted" | "rejected"
    build_key: str | None
    program_digest: str | None
    diagnostics: tuple[dict, ...]


def _content_files(root: Path) -> list[Path]:
    """Every regular file under `root` except the top-level build cache, sorted."""
    return sorted(p for p in root.rglob("*") if p.is_file() and p.relative_to(root).parts[0] != BUILD_CACHE)


def candidate_id(root: Path, *, orchestrator_commit: str) -> str:
    """sha256 over every regular file (relative path, NUL, bytes) in sorted order, then the commit."""
    digest = hashlib.sha256()
    for path in _content_files(root):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0" + path.read_bytes())
    digest.update(orchestrator_commit.encode())
    return f"sha256:{digest.hexdigest()}"


def snapshot(parent: Path, edited_files: Mapping[str, bytes], dest: Path) -> Path:
    """Copy `parent` to a new `dest` and overwrite the edited files there; `parent` is never written.

    Raises ValueError (before copying) for an edited name that resolves outside `dest`.
    """
    for name in edited_files:
        if not (dest / name).resolve().is_relative_to(dest.resolve()):
            raise ValueError(f"edited file {name!r} resolves outside {dest}")
    top_cache = (parent / BUILD_CACHE).resolve()

    def top_level_cache(directory: str, names: list[str]) -> list[str]:
        return [name for name in names if (Path(directory) / name).resolve() == top_cache]

    shutil.copytree(parent, dest, ignore=top_level_cache)  # FileExistsError if dest exists
    for name, data in edited_files.items():
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return dest


def compile_candidate(root: Path, config: ExperimentConfig, *, runtime: Path) -> CompileOutcome:
    """Compile with the frozen runtime; invalid compiler output carries `compiler_crash` for incident reporting."""
    source_root = root / config.source_root
    module = config.entry_workflow.split("::")[0]
    command = [
        sys.executable, "-P", "-m", "orchestrator", "compile", str((source_root / module).with_suffix(".orc")),
        "--entry-workflow", config.entry_workflow,
        "--source-root", str(source_root),
        "--provider-externs-file", str(root / config.providers_file),
    ]
    if config.command_boundaries_file is not None:
        command += ["--command-boundaries-file", str(root / config.command_boundaries_file)]
    command.append("--diagnostics-json")
    env = {**os.environ, "PYTHONPATH": str(runtime)}
    result = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True)
    return _compile_result(result)


def _compile_result(result: subprocess.CompletedProcess) -> CompileOutcome:
    lines = result.stdout.strip().splitlines()
    try:
        document = json.loads(lines[-1])
        if _accepted_compile_document(document, result.returncode):
            return CompileOutcome("accepted", document["build_key"], document["program_digest"], ())
        if _rejected_compile_document(document, result.returncode):
            return CompileOutcome("rejected", None, None, tuple(document["diagnostics"]))
    except (IndexError, ValueError):
        pass
    return CompileOutcome("rejected", None, None, (
        {"code": "compiler_crash", "exit": result.returncode, "stderr": result.stderr[-CRASH_TAIL_CHARS:],
         "message": f"invalid compiler response: {result.stdout[-CRASH_TAIL_CHARS:]}"},))


def _accepted_compile_document(document, returncode: int) -> bool:
    return (isinstance(document, dict) and document.get("status") == "accepted" and returncode == 0
            and all(isinstance(document.get(key), str) and document[key]
                    for key in ("build_key", "program_digest")))


def _rejected_compile_document(document, returncode: int) -> bool:
    return (isinstance(document, dict) and document.get("status") == "rejected" and returncode != 0
            and isinstance(document.get("diagnostics"), list) and document["diagnostics"]
            and all(isinstance(diagnostic, dict) for diagnostic in document["diagnostics"]))


# --- Edit validation -------------------------------------------------------------------------------------------

FROZEN_HEADS = frozenset({"import", "deftype", "defrecord", "defunion", "defenum", "export", "defmodule",
                          ":target-dsl", ":language"})
# What each condition permits to change (controller ruling, Task 3 review round 1). Role allocation (which provider
# extern a call names) is topology; `:model`/`:effort` values are provider tuning.
TOPOLOGY_CONDITIONS = frozenset({"topology-only", "joint", "module"})
PROMPT_CONDITIONS = frozenset({"prompt-only", "joint", "module"})
PROVIDER_CONDITIONS = frozenset({"provider-only", "joint"})
PROMPT_SIGNATURE_CONDITIONS = frozenset({"joint", "module"})
TUNING_KEYWORDS = frozenset({":model", ":effort"})
PRIVATE_TYPE_HEADS = frozenset({"defrecord", "defunion", "defenum"})
MODULE_DEFINITION_HEADS = PRIVATE_TYPE_HEADS | {"defproc", "defworkflow", "defprompt"}


@dataclass(frozen=True)
class Verdict:
    accepted: bool
    code: str | None  # None when accepted
    detail: str


@dataclass(frozen=True)
class Receipt:
    parent_candidate_id: str
    site_id: str  # "<owner canonical name>@<path relative to root>:<line>:<column>"
    expected_file_digest: str  # "sha256:..." of the parent file named in site_id
    replacement_expression: str
    supporting_declarations: tuple[str, ...]
    condition: str
    hypothesis: str


ACCEPTED = Verdict(True, None, "")


def _refuse(code: str, detail: str) -> Verdict:
    return Verdict(False, code, detail)


class _UnreadableChild(Exception):
    """A child file or receipt text the ordinary reader rejects; reported as `unreadable_child`."""


def _child_forms(path: Path) -> tuple[SExpr, ...]:
    try:
        return _top_level_forms(read_sexpr_file(path))
    except (LispFrontendCompileError, UnicodeDecodeError) as error:
        raise _UnreadableChild(f"{path.name}: {error}") from error


def _parent_forms(path: Path) -> tuple[SExpr, ...]:
    return _top_level_forms(read_sexpr_file(path))


def canonical_form(node: SExpr) -> object:
    """Spans dropped: a list is a tuple of its items' forms, an atom is (atom type name, value)."""
    if isinstance(node, ListExpr):
        return tuple(canonical_form(item) for item in node.items)
    return (type(node).__name__, node.value)


def _head(form: SExpr) -> str | None:
    if isinstance(form, ListExpr) and form.items and isinstance(form.items[0], (SymbolAtom, KeywordAtom)):
        return form.items[0].value
    return None


def imports(path: Path) -> list[str]:
    """The module names a `.orc` file imports, in source order."""
    return [form.items[1].value for form in _top_level_forms(read_sexpr_file(path))
            if _head(form) == "import" and len(form.items) > 1 and isinstance(form.items[1], SymbolAtom)]


def _top_level_forms(tree: ListExpr) -> tuple[SExpr, ...]:
    """The module's top-level forms, inside the `(workflow-lisp ...)` wrapper when there is one."""
    if len(tree.items) == 1 and _head(tree.items[0]) == "workflow-lisp":
        return tree.items[0].items[1:]
    return tree.items


def _named_definition(form: SExpr, head: str | None) -> bool:
    return bool(head and head.startswith("def") and len(form.items) > 1 and isinstance(form.items[1], SymbolAtom))


def _form_is_mutable(form: SExpr, head: str | None, public: set[str], whole_module: bool) -> bool:
    if not _named_definition(form, head):
        return False
    private_type = head in PRIVATE_TYPE_HEADS and form.items[1].value not in public
    if whole_module:
        return bool(head in MODULE_DEFINITION_HEADS and (head not in PRIVATE_TYPE_HEADS or private_type))
    return head not in FROZEN_HEADS


def _bound_names(forms) -> set[str]:
    return _exported_names(forms) | {name for form in forms if _head(form) == "import" and len(form.items) > 1
                                      and isinstance(form.items[1], SymbolAtom)
                                      for name in _import_names(form)}


def _split_forms(forms, *, whole_module: bool = False) -> tuple[list[object], dict[tuple[str, str], SExpr]]:
    """(frozen forms in order, named mutable-kind definitions keyed by (head, name)).

    Legacy conditions use non-frozen `def*` heads. Whole-module editing admits only private types, prompts and
    callables; exported types, directives and unrecognized forms stay frozen.
    """
    frozen: list[object] = []
    definitions: dict[tuple[str, str], SExpr] = {}
    public = _bound_names(forms)
    for form in forms:
        head = _head(form)
        if _form_is_mutable(form, head, public, whole_module):
            definitions[(head, form.items[1].value)] = form
        else:
            frozen.append(canonical_form(form))
    return frozen, definitions


def _prompt_parts(form: ListExpr) -> tuple[object, object]:
    """(signature, body) of a defprompt: the body is its trailing string atom."""
    if isinstance(form.items[-1], StringAtom):
        return canonical_form(ListExpr(form.items[:-1], form.span)), canonical_form(form.items[-1])
    return canonical_form(form), None


def _tuning_split(node: SExpr) -> tuple[object, list[object]]:
    """(canonical form with every `:model`/`:effort` value replaced by a hole, those values in source order)."""
    values: list[object] = []

    def walk(item: SExpr) -> object:
        if not isinstance(item, ListExpr):
            return canonical_form(item)
        forms = []
        for index, child in enumerate(item.items):
            previous = item.items[index - 1] if index else None
            if isinstance(previous, KeywordAtom) and previous.value in TUNING_KEYWORDS:
                values.append((previous.value, canonical_form(child)))
                forms.append("<tuning>")
            else:
                forms.append(walk(child))
        return tuple(forms)

    return walk(node), values


def _condition_verdict(head: str, name: str, before: ListExpr, after: ListExpr, condition: str,
                       parent_tuning: set[object]) -> Verdict:
    """Refuse a changed mutable definition whose change touches a surface `condition` does not permit.

    Under topology-only, calls may be added, removed or moved and may reuse any `:model`/`:effort` value already
    used in the parent module (`parent_tuning`); only a value new to the module counts as a tuning change.
    """
    if head == "defprompt":
        (signature_before, body_before), (signature_after, body_after) = _prompt_parts(before), _prompt_parts(after)
        surfaces = {"prompt signature": (signature_before != signature_after, PROMPT_SIGNATURE_CONDITIONS),
                    "prompt body": (body_before != body_after, PROMPT_CONDITIONS)}
    else:
        (shape_before, tuning_before), (shape_after, tuning_after) = _tuning_split(before), _tuning_split(after)
        tuning_changed = bool(set(tuning_after) - parent_tuning) if condition == "topology-only" else (
            tuning_before != tuning_after)
        surfaces = {"topology": (shape_before != shape_after, TOPOLOGY_CONDITIONS),
                    ":model/:effort values": (tuning_changed, PROVIDER_CONDITIONS | {"module"})}
    for surface, (changed, permitted) in surfaces.items():
        if changed and condition not in permitted:
            return _refuse("frozen_surface_changed", f"{surface} of {head} {name} changed under {condition}")
    return ACCEPTED


def _exported_names(forms) -> set[str]:
    return {item.value for form in forms if _head(form) == "export"
            for item in form.items[1:] if isinstance(item, SymbolAtom)}


def _module_verdict(parent_forms, child_forms, *, mutable: tuple[str, ...], condition: str,
                    allowed_new: frozenset[str], whole_module: bool = False) -> Verdict:
    """Compare one module's forms; exported signatures (all items but the body) are frozen under every condition."""
    if whole_module:
        collisions = _module_collisions(parent_forms, child_forms)
        if collisions:
            return _refuse("declaration_collision", f"private declarations collide with bound names: {sorted(collisions)}")
    parent_frozen, parent_defs = _split_forms(parent_forms, whole_module=whole_module)
    child_frozen, child_defs = _split_forms(child_forms, whole_module=whole_module)
    if parent_frozen != child_frozen:
        return _refuse("frozen_surface_changed", "an import, type, export, module or language form differs")
    exported = _exported_names(parent_forms)
    parent_tuning = {value for form in parent_forms for value in _tuning_split(form)[1]}
    if whole_module:
        mutable = tuple(set(mutable) | {name for _, name in parent_defs.keys() | child_defs.keys()
                                        if name not in exported})
    for key in sorted(parent_defs.keys() | child_defs.keys()):
        verdict = _definition_verdict(key, parent_defs.get(key), child_defs.get(key), exported, mutable, condition,
                                      parent_tuning, allowed_new)
        if not verdict.accepted:
            return verdict
    return ACCEPTED


def _parent_module_bindings(parent_forms) -> tuple[set[str], set[tuple[str, str]], set[str]]:
    exported = _exported_names(parent_forms)
    imported: set[str] = set()
    parent_public: set[tuple[str, str]] = set()
    for form in parent_forms:
        head = _head(form)
        if head == "import":
            imported.update(_import_names(form))
        if (head in MODULE_DEFINITION_HEADS and len(form.items) > 1 and isinstance(form.items[1], SymbolAtom)
                and form.items[1].value in exported):
            parent_public.add((head, form.items[1].value))
    return imported, parent_public, exported


def _module_declarations(forms) -> list[tuple[str, str]]:
    return [(_head(form), form.items[1].value) for form in forms
            if _head(form) in MODULE_DEFINITION_HEADS and len(form.items) > 1
            and isinstance(form.items[1], SymbolAtom)]


def _module_collisions(parent_forms, child_forms) -> set[str]:
    imported, parent_public, exported = _parent_module_bindings(parent_forms)
    declarations = _module_declarations(child_forms)
    counts = Counter(name for _, name in declarations)
    collisions = set()
    for head, name in declarations:
        if name in imported or counts[name] > 1 or (name in exported and (head, name) not in parent_public):
            collisions.add(name)
    return collisions


def _definition_presence_verdict(key: tuple[str, str], before: SExpr | None, after: SExpr | None,
                                 exported: set, mutable: tuple, condition: str, parent_tuning: set,
                                 allowed_new: frozenset) -> Verdict | None:
    head, name = key
    if condition == "module" and name in mutable and name not in exported and (before is None or after is None):
        return ACCEPTED
    if before is None and name in allowed_new:
        # A fresh helper is checked against an empty form of its own kind.
        return _condition_verdict(head, name, ListExpr(after.items[:1], after.span), after, condition, parent_tuning)
    if before is None or after is None:
        return _refuse("scope_exceeded", f"{head} {name} was {'added' if before is None else 'removed'}")
    return None


def _definition_verdict(key: tuple[str, str], before: SExpr | None, after: SExpr | None, exported: set,
                        mutable: tuple, condition: str, parent_tuning: set, allowed_new: frozenset) -> Verdict:
    """One definition of a module, parent `before` and child `after` (None where it does not exist)."""
    head, name = key
    presence = _definition_presence_verdict(key, before, after, exported, mutable, condition,
                                            parent_tuning, allowed_new)
    if presence is not None:
        return presence
    if canonical_form(before) == canonical_form(after):
        return ACCEPTED
    if name in exported and [canonical_form(i) for i in before.items[:-1]] != [
            canonical_form(i) for i in after.items[:-1]]:
        return _refuse("frozen_surface_changed", f"exported signature of {head} {name} changed")
    if name not in mutable:
        return _refuse("scope_exceeded", f"{head} {name} is not a mutable definition")
    return _condition_verdict(head, name, before, after, condition, parent_tuning)


def _file_names(*roots: Path) -> list[str]:
    return sorted({p.relative_to(root).as_posix() for root in roots for p in _content_files(root)})


def _frozen_verdict(parent: Path, child: Path, config: ExperimentConfig, *, allowed_new: frozenset[str]) -> Verdict:
    for name in _file_names(parent, child):
        before, after = parent / name, child / name
        if not (before.is_file() and after.is_file()):
            return _refuse("scope_exceeded", f"{name} was {'added' if after.is_file() else 'removed'}")
        verdict = (_orc_file_verdict(name, before, after, config, allowed_new) if name.endswith(".orc")
                   else _plain_file_verdict(name, before, after, config))
        if not verdict.accepted:
            return verdict
    return ACCEPTED


def _orc_file_verdict(name: str, before: Path, after: Path, config: ExperimentConfig, allowed: frozenset) -> Verdict:
    is_mutable = name in config.mutable_files
    mutable = config.mutable_definitions if is_mutable else ()
    if is_mutable and config.condition == "module":
        mutable = (*mutable, config.entry_workflow.split("::")[1])
    verdict = _module_verdict(_parent_forms(before), _child_forms(after), condition=config.condition,
                              mutable=mutable,
                              allowed_new=allowed if is_mutable else frozenset(),
                              whole_module=is_mutable and config.condition == "module")
    return verdict if verdict.accepted else _refuse(verdict.code, f"{name}: {verdict.detail}")


def _plain_file_verdict(name: str, before: Path, after: Path, config: ExperimentConfig) -> Verdict:
    if before.read_bytes() == after.read_bytes() or (
            name == config.providers_file and config.condition in PROVIDER_CONDITIONS):
        return ACCEPTED  # the condition permits the providers file whether or not it is in mutable_files
    if name in (config.command_boundaries_file, config.providers_file):
        return _refuse("frozen_surface_changed", f"{name} changed under {config.condition}")
    if name not in config.mutable_files or config.condition == "module":
        return _refuse("scope_exceeded", f"{name} is not a mutable file")
    return ACCEPTED


def validate_frozen_surfaces(parent: Path, child: Path, config: ExperimentConfig) -> Verdict:
    """Refuse a child whose forms differ from the parent's outside the configured mutable scope.

    `frozen_surface_changed`: an import/type/export/module/language form, an exported definition's signature, the
    command boundary file, or a surface the condition does not permit: topology (definition shape, including which
    provider extern a call names) outside topology-only/joint; `:model`/`:effort` values and the providers file
    outside provider-only/joint, except that topology-only may reuse values the parent module already uses; prompt bodies outside prompt-only/joint; prompt signatures outside joint.
    `scope_exceeded`: a definition or file outside `mutable_definitions`/`mutable_files` changed, or a definition
    or file was added or removed. `unreadable_child`: the reader rejects a child `.orc` file.
    """
    try:
        return _frozen_verdict(parent, child, config, allowed_new=frozenset())
    except _UnreadableChild as error:
        return _refuse("unreadable_child", str(error))


def _import_names(form: ListExpr) -> set[str]:
    """An import's alias (else its module's last path segment) and its `:only` names."""
    options = dict(zip([getattr(item, "value", None) for item in form.items[2::2]], form.items[3::2]))
    alias = options.get(":as")
    only = options.get(":only")
    return {alias.value if isinstance(alias, SymbolAtom) else form.items[1].value.rsplit("/", 1)[-1],
            *(item.value for item in (only.items if isinstance(only, ListExpr) else ())
              if isinstance(item, SymbolAtom))}


def _same_file(before: Path, after: Path) -> bool:
    """Equal parsed forms for `.orc` files, equal bytes otherwise; a file missing on either side differs."""
    if not (before.is_file() and after.is_file()):
        return False
    if before.suffix == ".orc":
        return [canonical_form(f) for f in _parent_forms(before)] == [canonical_form(f) for f in _child_forms(after)]
    return before.read_bytes() == after.read_bytes()
