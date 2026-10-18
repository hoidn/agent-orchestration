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
    """Compile with the runtime's orchestrator; output that is not JSON is a `compiler_crash` rejection."""
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
    lines = result.stdout.strip().splitlines()
    try:
        document = json.loads(lines[-1])
    except (IndexError, ValueError):
        return CompileOutcome("rejected", None, None, (
            {"code": "compiler_crash", "exit": result.returncode, "stderr": result.stderr[-CRASH_TAIL_CHARS:]},))
    if document.get("status") == "accepted" and result.returncode == 0:
        return CompileOutcome("accepted", document["build_key"], document["program_digest"], ())
    if document.get("status") == "rejected" and result.returncode != 0:
        return CompileOutcome("rejected", None, None, tuple(document["diagnostics"]))
    raise RuntimeError(f"unexpected compile result (exit {result.returncode}): {lines[-1]}")


# --- Edit validation -------------------------------------------------------------------------------------------

FROZEN_HEADS = frozenset({"import", "deftype", "defrecord", "defunion", "defenum", "export", "defmodule",
                          ":target-dsl", ":language"})
# What each condition permits to change (controller ruling, Task 3 review round 1). Role allocation (which provider
# extern a call names) is topology; `:model`/`:effort` values are provider tuning.
TOPOLOGY_CONDITIONS = frozenset({"topology-only", "joint"})
PROMPT_CONDITIONS = frozenset({"prompt-only", "joint"})
PROVIDER_CONDITIONS = frozenset({"provider-only", "joint"})
PROMPT_SIGNATURE_CONDITIONS = frozenset({"joint"})
TUNING_KEYWORDS = frozenset({":model", ":effort"})


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


def _split_forms(forms) -> tuple[list[object], dict[tuple[str, str], SExpr]]:
    """(frozen forms in order, named mutable-kind definitions keyed by (head, name)).

    A form is a definition when its head starts with `def`, is not a frozen head and names a symbol; every other
    form (directives, unrecognized forms) is frozen, which fails closed.
    """
    frozen: list[object] = []
    definitions: dict[tuple[str, str], SExpr] = {}
    for form in forms:
        head = _head(form)
        named = head and head.startswith("def") and len(form.items) > 1 and isinstance(form.items[1], SymbolAtom)
        if named and head not in FROZEN_HEADS:
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
                    ":model/:effort values": (tuning_changed, PROVIDER_CONDITIONS)}
    for surface, (changed, permitted) in surfaces.items():
        if changed and condition not in permitted:
            return _refuse("frozen_surface_changed", f"{surface} of {head} {name} changed under {condition}")
    return ACCEPTED


def _exported_names(forms) -> set[str]:
    return {item.value for form in forms if _head(form) == "export"
            for item in form.items[1:] if isinstance(item, SymbolAtom)}


def _module_verdict(parent_forms, child_forms, *, mutable: tuple[str, ...], condition: str,
                    allowed_new: frozenset[str]) -> Verdict:
    """Compare one module's forms; exported signatures (all items but the body) are frozen under every condition."""
    parent_frozen, parent_defs = _split_forms(parent_forms)
    child_frozen, child_defs = _split_forms(child_forms)
    if parent_frozen != child_frozen:
        return _refuse("frozen_surface_changed", "an import, type, export, module or language form differs")
    exported = _exported_names(parent_forms)
    parent_tuning = {value for form in parent_forms for value in _tuning_split(form)[1]}
    for key in parent_defs.keys() | child_defs.keys():
        verdict = _definition_verdict(key, parent_defs.get(key), child_defs.get(key), exported, mutable, condition,
                                      parent_tuning, allowed_new)
        if not verdict.accepted:
            return verdict
    return ACCEPTED


def _definition_verdict(key: tuple[str, str], before: SExpr | None, after: SExpr | None, exported: set,
                        mutable: tuple, condition: str, parent_tuning: set, allowed_new: frozenset) -> Verdict:
    """One definition of a module, parent `before` and child `after` (None where it does not exist)."""
    head, name = key
    if before is None and name in allowed_new:  # a fresh I2 helper: a change from an empty form of its kind
        return _condition_verdict(head, name, ListExpr(after.items[:1], after.span), after, condition, parent_tuning)
    if before is None or after is None:
        return _refuse("scope_exceeded", f"{head} {name} was {'added' if before is None else 'removed'}")
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
    verdict = _module_verdict(_parent_forms(before), _child_forms(after), condition=config.condition,
                              mutable=config.mutable_definitions if is_mutable else (),
                              allowed_new=allowed if is_mutable else frozenset())
    return verdict if verdict.accepted else _refuse(verdict.code, f"{name}: {verdict.detail}")


def _plain_file_verdict(name: str, before: Path, after: Path, config: ExperimentConfig) -> Verdict:
    if before.read_bytes() == after.read_bytes() or (
            name == config.providers_file and config.condition in PROVIDER_CONDITIONS):
        return ACCEPTED  # the condition permits the providers file whether or not it is in mutable_files
    if name in (config.command_boundaries_file, config.providers_file):
        return _refuse("frozen_surface_changed", f"{name} changed under {config.condition}")
    if name not in config.mutable_files:
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


def _parse_site(site_id: str) -> tuple[str, str, int, int] | None:
    """(owner definition name, file, line, column), or None when malformed; the owner is the part after `::`."""
    owner, _, location = site_id.rpartition("@")
    try:
        path, line, column = location.rsplit(":", 2)
        return owner.rpartition("::")[2], path, int(line), int(column)
    except ValueError:
        return None


def _site_path(node: SExpr, line: int, column: int) -> tuple[int, ...] | None:
    """Index path from `node` to the subform whose span starts at (line, column), or None."""
    if (node.span.start.line, node.span.start.column) == (line, column):
        return ()
    for index, item in enumerate(node.items if isinstance(node, ListExpr) else ()):
        path = _site_path(item, line, column)
        if path is not None:
            return (index, *path)
    return None


def _subform(node: SExpr, path: tuple[int, ...]) -> SExpr | None:
    for index in path:
        if not isinstance(node, ListExpr) or index >= len(node.items):
            return None
        node = node.items[index]
    return node


def _masked_form(node: SExpr, path: tuple[int, ...]) -> object:
    """canonical_form of `node` with the subform at `path` replaced by a hole."""
    if not path:
        return "<site>"
    if not isinstance(node, ListExpr) or path[0] >= len(node.items):
        return canonical_form(node)
    return tuple(_masked_form(item, path[1:]) if index == path[0] else canonical_form(item)
                 for index, item in enumerate(node.items))


def _one_form(text: str) -> SExpr | None:
    try:
        forms = read_sexpr_text(text, source_path="<receipt>").items
    except LispFrontendCompileError as error:
        raise _UnreadableChild(f"receipt text: {error}") from error
    return forms[0] if len(forms) == 1 else None


def _bound_names(forms) -> set[str]:
    """Names a module's top-level forms bind: definitions and types, plus each import's alias and `:only` names."""
    names: set[str] = set()
    for form in forms:
        head = _head(form)
        if head == "import" and len(form.items) > 1 and isinstance(form.items[1], SymbolAtom):
            names |= _import_names(form)
        elif head and head.startswith("def") and len(form.items) > 1 and isinstance(form.items[1], SymbolAtom):
            names.add(form.items[1].value)
    return names


def _import_names(form: ListExpr) -> set[str]:
    """An import's alias (else its module's last path segment) and its `:only` names."""
    options = dict(zip([getattr(item, "value", None) for item in form.items[2::2]], form.items[3::2]))
    alias = options.get(":as")
    only = options.get(":only")
    return {alias.value if isinstance(alias, SymbolAtom) else form.items[1].value.rsplit("/", 1)[-1],
            *(item.value for item in (only.items if isinstance(only, ListExpr) else ())
              if isinstance(item, SymbolAtom))}


def _owner_form(forms, name: str) -> SExpr | None:
    _, definitions = _split_forms(forms)
    owners = [form for (_, owner), form in definitions.items() if owner == name]
    return owners[0] if len(owners) == 1 else None


def validate_one_site(parent: Path, child: Path, receipt: Receipt, config: ExperimentConfig) -> Verdict:
    """Accept a child that differs from the parent only at the receipt's site and in its declared fresh helpers.

    Checks in order: `condition_mismatch` (receipt vs. config condition), `site_unlocatable` (malformed site_id
    or missing parent file), `digest_mismatch` (parent file bytes), `site_unlocatable` (no form starts at the
    site's line:column inside the owner definition), `declaration_collision` (a helper name already bound in the
    parent module, imports included), the frozen-surface rule, then `scope_exceeded` (any other file differs, or
    anything but the site subtree and the declared helpers differs, or the child's site subtree is not the
    receipt's replacement expression). `unreadable_child`: the reader rejects a child file or receipt text.
    The receipt's parent_candidate_id is not checked here.
    """
    if receipt.condition != config.condition:
        return _refuse("condition_mismatch", f"receipt {receipt.condition!r}, configuration {config.condition!r}")
    site_parts = _parse_site(receipt.site_id)
    if site_parts is None or not (parent / site_parts[1]).is_file():
        return _refuse("site_unlocatable", f"site_id {receipt.site_id!r} names no parent file position")
    try:
        return _one_site_verdict(parent, child, receipt, config, *site_parts)
    except _UnreadableChild as error:
        return _refuse("unreadable_child", str(error))


def _one_site_verdict(parent: Path, child: Path, receipt: Receipt, config: ExperimentConfig, owner_name: str,
                      file_name: str, line: int, column: int) -> Verdict:
    parent_file, child_file = parent / file_name, child / file_name
    actual = "sha256:" + hashlib.sha256(parent_file.read_bytes()).hexdigest()
    if actual != receipt.expected_file_digest:
        return _refuse("digest_mismatch", f"{file_name} is {actual}, receipt expects {receipt.expected_file_digest}")
    parent_forms = _parent_forms(parent_file)
    owner, site = _owner_and_site(parent_forms, owner_name, line, column)
    if site is None:
        return _refuse("site_unlocatable", f"no form of {owner_name} starts at {file_name}:{line}:{column}")
    helpers = [_one_form(text) for text in receipt.supporting_declarations]
    if any(helper is None for helper in helpers):
        return _refuse("scope_exceeded", "a supporting declaration is not exactly one form")
    helper_names = _bound_names(helpers)
    if len(helper_names) != len(helpers):
        return _refuse("scope_exceeded", "every supporting declaration must define exactly one fresh name")
    collisions = helper_names & _bound_names(parent_forms)
    if collisions:
        return _refuse("declaration_collision", f"already bound in the parent: {sorted(collisions)}")
    verdict = _frozen_verdict(parent, child, config, allowed_new=frozenset(helper_names))
    if not verdict.accepted:
        return verdict
    for name in _file_names(parent, child):
        if name != file_name and not _same_file(parent / name, child / name):
            return _refuse("scope_exceeded", f"{name} changed outside the site's file")
    return _scope_verdict(parent_forms, _child_forms(child_file), owner, site, receipt, helpers)


def _owner_and_site(forms, owner_name: str, line: int, column: int) -> tuple[SExpr | None, tuple[int, ...] | None]:
    owner = _owner_form(forms, owner_name)
    return owner, (_site_path(owner, line, column) if owner is not None else None)


def _same_file(before: Path, after: Path) -> bool:
    """Equal parsed forms for `.orc` files, equal bytes otherwise; a file missing on either side differs."""
    if not (before.is_file() and after.is_file()):
        return False
    if before.suffix == ".orc":
        return [canonical_form(f) for f in _parent_forms(before)] == [canonical_form(f) for f in _child_forms(after)]
    return before.read_bytes() == after.read_bytes()


def _scope_verdict(parent_forms, child_forms, owner: SExpr, site: tuple[int, ...], receipt: Receipt,
                   helpers: list[SExpr]) -> Verdict:
    replacement = _one_form(receipt.replacement_expression)
    owner_key = (_head(owner), owner.items[1].value)
    _, parent_defs = _split_forms(parent_forms)
    _, child_defs = _split_forms(child_forms)
    changed = [key for key in parent_defs if key != owner_key
               and canonical_form(parent_defs[key]) != canonical_form(child_defs[key])]
    if changed:
        return _refuse("scope_exceeded", f"definitions other than the owner changed: {changed}")
    added = Counter(canonical_form(child_defs[key]) for key in child_defs.keys() - parent_defs.keys())
    if added != Counter(canonical_form(helper) for helper in helpers):
        return _refuse("scope_exceeded", "added forms are not exactly the declared supporting declarations")
    child_owner = child_defs[owner_key]
    if _masked_form(owner, site) != _masked_form(child_owner, site):
        return _refuse("scope_exceeded", "the owner changed outside the site subtree")
    child_site = _subform(child_owner, site)
    if replacement is None or child_site is None or canonical_form(child_site) != canonical_form(replacement):
        return _refuse("scope_exceeded", "the child's site subtree is not the receipt's replacement expression")
    return ACCEPTED
