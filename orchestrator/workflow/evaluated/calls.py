"""Checked in-memory transport for closed workflow calls."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .values import EvaluatedValue, EvaluatedValueError, LexicalEnvironment, coerce_evaluated_value


_MISSING = object()
_INACTIVE = object()


def call_environment(
    node: Mapping[str, Any],
    definition: Mapping[str, Any],
    arguments: Sequence[EvaluatedValue],
    *,
    run_id: str | None,
) -> LexicalEnvironment:
    """Bind cached caller values to native parameters through the checked relation."""

    boundary = node.get("boundary")
    if boundary is None:
        return _strict_environment(node, definition["params"], arguments, run_id)
    caller_params = boundary["params"]
    native_params = definition["params"]
    if len(arguments) != len(caller_params):
        raise _error("call_boundary", "caller arguments differ from checked boundary slots", node)

    native_values, dependencies, source_targets, target_sources = _project_inputs(
        node, boundary, caller_params, native_params, arguments
    )
    sidecars = _input_sidecars(
        boundary, caller_params, native_params, arguments, source_targets, target_sources,
    )
    return _projected_environment(node, native_params, native_values, dependencies, sidecars, run_id)


def _strict_environment(node, params, arguments, run_id):
    if len(arguments) != len(params):
        raise _error("closed_call_arity", "call arity differs from its checked definition", node)
    bindings = {
        name: _coerce(value, descriptor, node)
        for value, (name, descriptor) in zip(arguments, params, strict=True)
    }
    return LexicalEnvironment(bindings, run_id=run_id)


def _project_inputs(node, boundary, caller_params, native_params, arguments):
    caller_indices = {row[0]: index for index, row in enumerate(caller_params)}
    native_indices = {row[0]: index for index, row in enumerate(native_params)}
    native_values: list[EvaluatedValue | object] = [_MISSING] * len(native_params)
    dependencies: list[set[str]] = [set() for _ in native_params]
    source_targets: dict[int, set[int]] = {}
    target_sources: dict[int, set[int]] = {}
    for caller_index, native_index in boundary["direct"]:
        source = arguments[caller_index]
        native_values[native_index] = source.value
        dependencies[native_index].update(source.dependencies)

    rows = _paired_rows(boundary["inputs"], node)
    for caller_row, native_row in rows:
        caller_root = caller_row["path"][0]
        native_root = native_row["path"][0]
        caller_index, native_index = _projection_indices(
            node, caller_indices, native_indices, caller_root, native_root
        )
        source_targets.setdefault(caller_index, set()).add(native_index)
        target_sources.setdefault(native_index, set()).add(caller_index)
        source = arguments[caller_index]
        piece = _read_path(source.value, caller_params[caller_index][1], caller_row["path"][1:], node)
        if piece is _INACTIVE:
            continue
        _store_projection(node, native_values, native_index, native_row["path"][1:], piece)
        dependencies[native_index].update(source.dependencies)
    return native_values, dependencies, source_targets, target_sources


def _projection_indices(node, caller_indices, native_indices, caller_root, native_root):
    try:
        return caller_indices[caller_root], native_indices[native_root]
    except KeyError as exc:
        raise _error("call_boundary", "projection row names an unknown parameter", node) from exc


def _store_projection(node, native_values, native_index, path, piece):
    current = native_values[native_index]
    if not path:
        if current is not _MISSING:
            raise _error("call_boundary", "projection rows assign a parameter more than once", node)
        native_values[native_index] = piece
        return
    if current is _MISSING:
        current = {}
        native_values[native_index] = current
    if not _write_path(current, path, piece):
        raise _error("call_boundary", "projection rows assign a parameter more than once", node)


def _input_sidecars(
    boundary, caller_params, native_params, arguments, source_targets, target_sources,
):
    """Keep a producer path on complete roots; partial roots keep only dependency lineage."""

    # The checker requires each endpoint to equal its exhaustive descriptor rows and
    # pairs those rows by generated name. One root on each side plus equal leaf-row
    # counts therefore means the checked relation carries the whole root; 1:N or
    # partial root mappings retain dependencies but cannot reuse the whole-file path.
    caller_row_counts = _rows_by_root(boundary["inputs"]["caller"])
    native_row_counts = _rows_by_root(boundary["inputs"]["callee"])
    sidecars: list[str | None] = [None] * len(native_params)
    for caller_index, native_targets in source_targets.items():
        if len(native_targets) != 1:
            continue
        native_index = next(iter(native_targets))
        if target_sources.get(native_index) != {caller_index}:
            continue
        if caller_row_counts.get(caller_params[caller_index][0]) != native_row_counts.get(native_params[native_index][0]):
            continue
        source = arguments[caller_index]
        if source.committed_result_path is not None:
            sidecars[native_index] = source.committed_result_path
    for caller_index, native_index in boundary["direct"]:
        sidecars[native_index] = arguments[caller_index].committed_result_path
    return sidecars


def _projected_environment(node, params, values, dependencies, sidecars, run_id):
    if any(value is _MISSING for value in values):
        raise _error("call_boundary", "checked projection left a native parameter unbound", node)
    bindings = {}
    for index, (value, (name, descriptor)) in enumerate(zip(values, params, strict=True)):
        try:
            bindings[name] = coerce_evaluated_value(
                value,
                descriptor,
                dependencies=dependencies[index],
                committed_result_path=sidecars[index],
                context="checked call projection",
            )
        except (TypeError, ValueError, RecursionError) as exc:
            raise _error("call_boundary", f"projected argument violates its native descriptor: {exc}", node) from exc
    return LexicalEnvironment(bindings, run_id=run_id)


def call_result(
    node: Mapping[str, Any],
    definition: Mapping[str, Any],
    result: EvaluatedValue,
) -> EvaluatedValue:
    """Return a native result in the caller view, preserving value lineage."""

    boundary = node.get("boundary")
    if boundary is None:
        return _coerce(result, node["type"], node)

    raw: Any = _MISSING
    dependencies: set[str] = set()
    for caller_row, native_row in _paired_rows(boundary["outputs"], node):
        piece = _read_path(
            result.value, definition["result"], native_row["path"][1:], node
        )
        if piece is _INACTIVE:
            continue
        if caller_row["path"] == ["return"]:
            if raw is not _MISSING:
                raise _error("call_boundary", "output rows assign the result more than once", node)
            raw = piece
        else:
            if raw is _MISSING:
                raw = {}
            if not _write_path(raw, caller_row["path"][1:], piece):
                raise _error("call_boundary", "output rows assign the result more than once", node)
        dependencies.update(result.dependencies)
    if raw is _MISSING:
        raise _error("call_boundary", "checked output projection produced no result", node)
    try:
        return coerce_evaluated_value(
            raw,
            node["type"],
            dependencies=dependencies,
            committed_result_path=result.committed_result_path,
            context="checked call output projection",
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise _error("call_boundary", f"projected result violates its caller descriptor: {exc}", node) from exc


def _paired_rows(partition: Mapping[str, Any], node: Mapping[str, Any]):
    caller = partition["caller"]
    native = partition["callee"]
    caller_by_name = {row["name"]: row for row in caller}
    native_by_name = {row["name"]: row for row in native}
    if caller_by_name.keys() != native_by_name.keys():
        raise _error("call_boundary", "caller and native projection rows differ", node)
    return tuple((caller_by_name[name], native_by_name[name]) for name in caller_by_name)


def _rows_by_root(rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        root = row["path"][0]
        counts[root] = counts.get(root, 0) + 1
    return counts


def _read_path(value: Any, descriptor: Mapping[str, Any], path: Sequence[str], node):
    current_value, current_descriptor = value, descriptor
    for field in path:
        current_value, current_descriptor = _read_field(
            current_value, current_descriptor, field, node
        )
        if current_value is _INACTIVE:
            return _INACTIVE
    return current_value


def _read_field(value, descriptor, field, node):
    kind = descriptor["kind"]
    if kind == "union":
        return _read_union_field(value, descriptor, field, node)
    if kind in {"record", "variant_case"}:
        return _read_record_field(value, descriptor, field, node)
    raise _error("call_boundary", "projection path descends through a leaf value", node)


def _read_union_field(value, descriptor, field, node):
    variant = value.get("variant") if isinstance(value, Mapping) else None
    if field == "variant":
        return variant, {
            "kind": "enum", "name": descriptor["name"] + ".variant",
            "allowed": [row["name"] for row in descriptor["variants"]],
        }
    selected = _named_row(descriptor["variants"], variant)
    if selected is None:
        raise _error("call_boundary", "union value has an unknown active variant", node)
    field_row = _named_row(selected["fields"], field)
    if field_row is None:
        return _INACTIVE, None
    if not isinstance(value, Mapping) or field not in value:
        return _INACTIVE, None
    return value[field], field_row["type"]


def _read_record_field(value, descriptor, field, node):
    field_row = _named_row(descriptor["fields"], field)
    if field_row is None:
        raise _error("call_boundary", "projection path is absent from its descriptor", node)
    if not isinstance(value, Mapping) or field not in value:
        raise _error("call_boundary", "projection path is absent from its value", node)
    return value[field], field_row["type"]


def _named_row(rows, name):
    return next((row for row in rows if row["name"] == name), None)


def _write_path(target: Any, path: Sequence[str], value: Any) -> bool:
    current = target
    for field in path[:-1]:
        if not isinstance(current, dict):
            return False
        current = current.setdefault(field, {})
    if not isinstance(current, dict) or path[-1] in current:
        return False
    current[path[-1]] = value
    return True


def _coerce(value: EvaluatedValue, descriptor: Mapping[str, Any], node) -> EvaluatedValue:
    try:
        return coerce_evaluated_value(
            value.value,
            descriptor,
            dependencies=value.dependencies,
            committed_result_path=value.committed_result_path,
            context="checked call argument",
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise _error("call_boundary", f"argument violates its checked descriptor: {exc}", node) from exc


def _error(code: str, message: str, node: Mapping[str, Any]) -> EvaluatedValueError:
    location = node.get("@", {}).get("span") if isinstance(node.get("@"), Mapping) else None
    return EvaluatedValueError(code, message, location=location)
