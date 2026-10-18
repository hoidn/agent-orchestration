"""Candidate identity, immutable snapshots, compilation and edit validation.

A candidate is a directory. The top-level `.orchestrate/` (the compiler's build cache) is derived, not content.
`compile_candidate` runs this checkout's orchestrator (`python -P -m orchestrator` with PYTHONPATH set to the
repository root) with cwd=root, so the build cache lands inside the candidate.

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
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from experiments.orc_structural_search.config import ExperimentConfig
from orchestrator.workflow_lisp.reader import read_sexpr_file, read_sexpr_text
from orchestrator.workflow_lisp.sexpr import KeywordAtom, ListExpr, SExpr, StringAtom, SymbolAtom

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_CACHE = ".orchestrate"


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


def compile_candidate(root: Path, config: ExperimentConfig) -> CompileOutcome:
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
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    result = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True)
    lines = result.stdout.strip().splitlines()
    if not lines:
        raise RuntimeError(f"compile printed nothing (exit {result.returncode}): {result.stderr}")
    document = json.loads(lines[-1])
    if document.get("status") == "accepted" and result.returncode == 0:
        return CompileOutcome("accepted", document["build_key"], document["program_digest"], ())
    if document.get("status") == "rejected" and result.returncode != 0:
        return CompileOutcome("rejected", None, None, tuple(document["diagnostics"]))
    raise RuntimeError(f"unexpected compile result (exit {result.returncode}): {lines[-1]}")


# --- Edit validation -------------------------------------------------------------------------------------------

FROZEN_HEADS = frozenset({"import", "deftype", "defrecord", "defunion", "defenum", "export", "defmodule",
                          ":target-dsl", ":language"})
PROMPT_CONDITIONS = frozenset({"prompt-only", "joint"})
PROVIDER_CONDITIONS = frozenset({"provider-only", "joint"})


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


def canonical_form(node: SExpr) -> object:
    """Spans dropped: a list is a tuple of its items' forms, an atom is (atom type name, value)."""
    if isinstance(node, ListExpr):
        return tuple(canonical_form(item) for item in node.items)
    return (type(node).__name__, node.value)


def _head(form: SExpr) -> str | None:
    if isinstance(form, ListExpr) and form.items and isinstance(form.items[0], (SymbolAtom, KeywordAtom)):
        return form.items[0].value
    return None


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


def _module_verdict(parent_forms, child_forms, *, mutable: tuple[str, ...], condition: str,
                    allowed_new: frozenset[str]) -> Verdict:
    parent_frozen, parent_defs = _split_forms(parent_forms)
    child_frozen, child_defs = _split_forms(child_forms)
    if parent_frozen != child_frozen:
        return _refuse("frozen_surface_changed", "an import, type, export, module or language form differs")
    for key in parent_defs.keys() | child_defs.keys():
        head, name = key
        before, after = parent_defs.get(key), child_defs.get(key)
        if before is None and name in allowed_new:
            continue
        if before is None or after is None:
            return _refuse("scope_exceeded", f"{head} {name} was {'added' if before is None else 'removed'}")
        if canonical_form(before) == canonical_form(after):
            continue
        if name not in mutable:
            return _refuse("scope_exceeded", f"{head} {name} is not a mutable definition")
        if head == "defprompt" and condition not in PROMPT_CONDITIONS and \
                _prompt_parts(before)[1] != _prompt_parts(after)[1]:
            return _refuse("frozen_surface_changed", f"prompt body of {name} changed under {condition}")
    return ACCEPTED


def _frozen_verdict(parent: Path, child: Path, config: ExperimentConfig, *, allowed_new: frozenset[str]) -> Verdict:
    names = {p.relative_to(parent).as_posix() for p in _content_files(parent)}
    names |= {p.relative_to(child).as_posix() for p in _content_files(child)}
    for name in sorted(names):
        before, after = parent / name, child / name
        if not (before.is_file() and after.is_file()):
            return _refuse("scope_exceeded", f"{name} was {'added' if after.is_file() else 'removed'}")
        is_mutable = name in config.mutable_files
        if name.endswith(".orc"):
            verdict = _module_verdict(
                _top_level_forms(read_sexpr_file(before)), _top_level_forms(read_sexpr_file(after)),
                mutable=config.mutable_definitions if is_mutable else (), condition=config.condition,
                allowed_new=allowed_new if is_mutable else frozenset())
            if not verdict.accepted:
                return _refuse(verdict.code, f"{name}: {verdict.detail}")
            continue
        if before.read_bytes() == after.read_bytes():
            continue
        frozen_file = name == config.command_boundaries_file or (
            name == config.providers_file and config.condition not in PROVIDER_CONDITIONS)
        if frozen_file:
            return _refuse("frozen_surface_changed", f"{name} changed under {config.condition}")
        if not is_mutable:
            return _refuse("scope_exceeded", f"{name} is not a mutable file")
    return ACCEPTED


def validate_frozen_surfaces(parent: Path, child: Path, config: ExperimentConfig) -> Verdict:
    """Refuse a child whose forms differ from the parent's outside the configured mutable scope.

    `frozen_surface_changed`: an import/type/export/module/language form, a prompt body outside the prompt-only
    and joint conditions, the command boundary file, or the provider file outside provider-only and joint.
    `scope_exceeded`: a definition or file outside `mutable_definitions`/`mutable_files` changed, or a definition
    or file was added or removed.
    """
    return _frozen_verdict(parent, child, config, allowed_new=frozenset())


def _parse_site(site_id: str) -> tuple[str, str, int, int]:
    """(owner definition name, file, line, column); the owner name is the part after the last `::`."""
    owner, _, location = site_id.rpartition("@")
    path, line, column = location.rsplit(":", 2)
    return owner.rpartition("::")[2], path, int(line), int(column)


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
    forms = read_sexpr_text(text, source_path="<receipt>").items
    return forms[0] if len(forms) == 1 else None


def _bound_names(forms) -> set[str]:
    """Names a module's top-level forms bind: definitions and types, plus each import's alias and `:only` names."""
    names: set[str] = set()
    for form in forms:
        head = _head(form)
        if head == "import" and len(form.items) > 1 and isinstance(form.items[1], SymbolAtom):
            options = dict(zip([getattr(item, "value", None) for item in form.items[2::2]], form.items[3::2]))
            alias = options.get(":as")
            names.add(alias.value if isinstance(alias, SymbolAtom) else form.items[1].value.rsplit("/", 1)[-1])
            only = options.get(":only")
            names |= {item.value for item in (only.items if isinstance(only, ListExpr) else ())
                      if isinstance(item, SymbolAtom)}
        elif head and head.startswith("def") and len(form.items) > 1 and isinstance(form.items[1], SymbolAtom):
            names.add(form.items[1].value)
    return names


def _owner_form(forms, name: str) -> SExpr | None:
    _, definitions = _split_forms(forms)
    owners = [form for (_, owner), form in definitions.items() if owner == name]
    return owners[0] if len(owners) == 1 else None


def validate_one_site(parent: Path, child: Path, receipt: Receipt, config: ExperimentConfig) -> Verdict:
    """Accept a child that differs from the parent only at the receipt's site and in its declared fresh helpers.

    Checks in order: `digest_mismatch` (parent file bytes), `site_unlocatable` (no form starts at the site's
    line:column inside the owner definition), `declaration_collision` (a helper name already bound in the parent
    module, imports included), the frozen-surface rule, then `scope_exceeded` (anything but the site subtree and
    the declared helpers differs, or the child's site subtree is not the receipt's replacement expression).
    The receipt's parent_candidate_id is not checked here.
    """
    owner_name, file_name, line, column = _parse_site(receipt.site_id)
    parent_file, child_file = parent / file_name, child / file_name
    actual = "sha256:" + hashlib.sha256(parent_file.read_bytes()).hexdigest()
    if actual != receipt.expected_file_digest:
        return _refuse("digest_mismatch", f"{file_name} is {actual}, receipt expects {receipt.expected_file_digest}")
    parent_forms = _top_level_forms(read_sexpr_file(parent_file))
    owner = _owner_form(parent_forms, owner_name)
    site = _site_path(owner, line, column) if owner is not None else None
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
    return _scope_verdict(parent_forms, _top_level_forms(read_sexpr_file(child_file)), owner, site, receipt, helpers)


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
    added = sorted(canonical_form(child_defs[key]) for key in child_defs.keys() - parent_defs.keys())
    if added != sorted(canonical_form(helper) for helper in helpers):
        return _refuse("scope_exceeded", "added forms are not exactly the declared supporting declarations")
    child_owner = child_defs[owner_key]
    if _masked_form(owner, site) != _masked_form(child_owner, site):
        return _refuse("scope_exceeded", "the owner changed outside the site subtree")
    child_site = _subform(child_owner, site)
    if replacement is None or child_site is None or canonical_form(child_site) != canonical_form(replacement):
        return _refuse("scope_exceeded", "the child's site subtree is not the receipt's replacement expression")
    return ACCEPTED
