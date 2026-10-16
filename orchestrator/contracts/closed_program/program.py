"""Strict loading and canonical artifacts for checked closed programs."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any

from .check import CheckedFormError, validate
from .sites import _ast_nodes, _definition_order


SCHEMA = "workflow-lisp/closed-program/1"
REPRESENTATION = "table/1"


class ClosedProgramInvalid(ValueError):
    """A stored closed program failed strict parsing or checked-form validation."""

    def __init__(self, rule: str, message: str, *, location: str = "<artifact>") -> None:
        super().__init__(f"closed_program_invalid ({rule}) at {location}: {message}")
        self.code = "closed_program_invalid"
        self.rule = rule
        self.location = location


@dataclass(frozen=True)
class ClosedProgram:
    tree: dict[str, Any]
    sites: tuple[tuple[str, str], ...]
    digest: str

    def artifact(self) -> str:
        """Return canonical JSON with source provenance and one final newline."""

        return _canonical_json(self.tree) + "\n"

    @classmethod
    def from_artifact(cls, text: str) -> ClosedProgram:
        try:
            tree = json.loads(
                text,
                object_pairs_hook=_unique_object,
                parse_constant=_reject_non_json_constant,
            )
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            line = getattr(exc, "lineno", None)
            column = getattr(exc, "colno", None)
            location = f"<artifact>:{line}:{column}" if line is not None else "<artifact>"
            raise ClosedProgramInvalid("json", f"invalid strict JSON: {exc}", location=location) from exc

        if not isinstance(tree, dict) or tree.get("schema") != SCHEMA:
            raise ClosedProgramInvalid(
                "representation",
                f"expected closed-program schema {SCHEMA!r}",
            )
        if tree.get("representation") != REPRESENTATION:
            raise ClosedProgramInvalid(
                "representation",
                f"expected representation {REPRESENTATION!r}, got {tree.get('representation')!r}",
        )
        try:
            _canonical_json(tree)
            validate(tree)
        except CheckedFormError as exc:
            rule = "sites" if exc.rule.startswith(("site_", "site_table")) else exc.rule
            raise ClosedProgramInvalid(rule, str(exc), location=exc.location or "<artifact>") from exc
        except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
            raise ClosedProgramInvalid("checked_form", str(exc)) from exc

        rows = _sites_from_nodes(tree)
        declared = tuple(tuple(row) for row in tree["sites"])
        if rows != declared:
            raise ClosedProgramInvalid("sites", "site rows differ from perform node annotations")
        try:
            digest = program_digest(tree)
        except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
            raise ClosedProgramInvalid("json", str(exc)) from exc
        return cls(tree=tree, sites=rows, digest=digest)


def canonical_digest(value: Any) -> str:
    """Hash canonical, finite JSON without a trailing newline."""

    return "sha256:" + sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def program_digest(tree: dict[str, Any]) -> str:
    """Hash program semantics while excluding only source-node provenance."""

    return canonical_digest(strip_provenance(tree))


def strip_provenance(node: Any) -> Any:
    """Copy a closed program and omit `@` only at schema-authorized AST rows."""

    result = deepcopy(node)
    if not isinstance(result, dict):
        return result
    bodies = [result.get("body")]
    definitions = result.get("definitions")
    if isinstance(definitions, Mapping):
        bodies.extend(
            definition.get("body")
            for definition in definitions.values()
            if isinstance(definition, Mapping)
        )
    for body in bodies:
        if not isinstance(body, dict):
            continue
        for ast_node in _ast_nodes(body):
            ast_node.pop("@", None)
            if ast_node.get("k") == "case":
                for arm in ast_node.get("arms", ()):
                    if isinstance(arm, dict):
                        arm.pop("@", None)
            elif ast_node.get("k") == "select":
                for branch_name in ("then", "else"):
                    branch = ast_node.get(branch_name)
                    if not isinstance(branch, dict):
                        continue
                    branch.pop("@", None)
                    for row in branch.get("prefix", ()):
                        if isinstance(row, dict):
                            row.pop("@", None)
    return result


def logical_asset_base_for_module(module_name: str) -> str:
    """Return the logical directory encoded by a canonical Workflow Lisp module."""

    if not isinstance(module_name, str) or not module_name or module_name.startswith("/"):
        raise ValueError("module name must be a nonempty relative logical path")
    parts = module_name.split("/")
    if any(part in {"", ".", ".."} or "\\" in part for part in parts):
        raise ValueError("module name must use canonical logical path components")
    return "/".join(parts[:-1]) or "."


def _sites_from_nodes(tree: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    definitions = tree["definitions"]
    owners = [(tree["entry"], tree["body"])]
    owners.extend(
        (name, definitions[name]["body"])
        for name in _definition_order(tree, definitions)
    )
    return tuple(
        (owner, node["site"])
        for owner, body in owners
        for node in _ast_nodes(body)
        if node.get("k") == "perform"
    )


def _canonical_json(value: Any) -> str:
    text = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("canonical JSON contains an unpaired Unicode surrogate") from exc
    return text


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def _reject_non_json_constant(value: str) -> Any:
    raise ValueError(f"non-JSON numeric constant {value!r}")
