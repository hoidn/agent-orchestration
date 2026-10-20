"""One-site edit transactions and source position helpers."""

import hashlib
from collections import Counter
from pathlib import Path

from experiments.orc_structural_search.candidates import (
    ACCEPTED, Receipt, Verdict, _UnreadableChild, _child_forms, _file_names, _frozen_verdict,
    _head, _import_names, _parent_forms, _refuse, _same_file, _split_forms, canonical_form,
)
from experiments.orc_structural_search.config import ExperimentConfig
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.sexpr import ListExpr, SExpr, SymbolAtom


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

