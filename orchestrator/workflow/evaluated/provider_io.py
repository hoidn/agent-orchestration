"""Prepared physical readers and checked routing for evaluated provider IO."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType


@dataclass(frozen=True)
class WorkflowIOReader:
    """Current physical workflow selection; never part of a program identity."""

    workflow_path: Path
    imports: Mapping[str, object] = field(default_factory=dict)
    workflows: Mapping[str, object] = field(default_factory=dict)
    source_paths: Mapping[str, Path] = field(default_factory=dict)

    def select(self, target, module):
        bundle = self.imports.get(target) or self.workflows.get(target)
        if bundle is not None:
            if not isinstance(bundle, WorkflowIOReader):
                raise ValueError("workflow IO selection must be a prepared reader")
            return bundle
        path = self.source_paths.get(module)
        if path is None:
            raise ValueError(f"workflow IO binding {target!r} is unavailable in the current reader")
        return replace(self, workflow_path=Path(path))


@dataclass(frozen=True)
class ProviderIOActivation:
    owner: str
    reader: WorkflowIOReader
    references: Mapping[tuple[str, ...], WorkflowIOReader] = field(default_factory=dict)


def resolve_io_route(route, activation):
    kind = route[0]
    if kind == "reader":
        return activation.reader
    if kind == "slot":
        try:
            return activation.references[route[1]]
        except KeyError as exc:
            raise ValueError(f"workflow IO reference slot {route[1]!r} is unavailable") from exc
    if kind == "workflow":
        return activation.reader.select(route[1], route[2])
    if kind == "procedure":
        return resolve_io_route(route[3], activation).select(route[1], route[2])
    raise ValueError(f"unknown workflow IO route {kind!r}")


@dataclass(frozen=True)
class ProviderIOCall:
    callee: str
    reader: tuple
    references: Mapping[tuple[str, ...], tuple] = field(default_factory=dict)

    def __post_init__(self):
        object.__setattr__(self, "references", MappingProxyType(dict(self.references)))


def _checked_io_reference_slots(key, prefix=()):
    for formal, _ in key[5]:
        yield (*prefix, formal)
    for formal, reference in key[4]:
        yield (*prefix, formal)
        yield from _checked_io_reference_slots(reference["target"], (*prefix, formal))


def _checked_io_calls(program):
    from orchestrator.contracts.closed_program.sites import _ast_nodes

    calls = {}
    bodies = [(program.tree["entry"], program.tree["body"])]
    bodies.extend((owner, row["body"]) for owner, row in program.tree["definitions"].items())
    for owner, body in bodies:
        for node in _ast_nodes(body):
            if node["k"] == "call" and node.get("frame") is not None:
                coordinate = owner, node["frame"]
                if coordinate in calls:
                    raise ValueError("workflow IO call coordinate is repeated")
                calls[coordinate] = node["callee"]
    return calls


def _check_io_route(route, slots):
    sizes = {"reader": 1, "slot": 2, "workflow": 3, "procedure": 4}
    if not isinstance(route, tuple) or not route or sizes.get(route[0]) != len(route):
        raise ValueError("workflow IO route has an invalid shape")
    if route[0] == "slot":
        if route[1] not in slots:
            raise ValueError("workflow IO route uses an unavailable reference slot")
    elif route[0] in {"workflow", "procedure"}:
        if not all(isinstance(value, str) and value for value in route[1:3]):
            raise ValueError("workflow IO route has an invalid selector")
        if route[0] == "procedure":
            _check_io_route(route[3], slots)


@dataclass(frozen=True)
class ProviderIOContext:
    """Transient selections bound to checked owner/frame/site coordinates."""

    entry: ProviderIOActivation
    calls: Mapping[tuple[str, str], ProviderIOCall]
    sites: frozenset[tuple[str, str]]
    program_digest: str

    def bind(self, program):
        calls = _checked_io_calls(program)
        supplied = {coordinate: binding.callee for coordinate, binding in self.calls.items()}
        if (calls != supplied or frozenset(program.sites) != self.sites
                or program.digest != self.program_digest or program.tree["entry"] != self.entry.owner):
            raise ValueError("workflow IO carrier does not match the checked program")
        for (owner, _), binding in self.calls.items():
            key = program.tree["definitions"][binding.callee]["key"]
            if set(binding.references) != set(_checked_io_reference_slots(key)):
                raise ValueError("workflow IO reference slots do not match the checked callee")
            owner_key = program.tree["definitions"].get(owner, {}).get("key")
            slots = set() if owner_key is None else set(_checked_io_reference_slots(owner_key))
            for route in (binding.reader, *binding.references.values()):
                _check_io_route(route, slots)
        return replace(self, calls=MappingProxyType(dict(self.calls)))

    def call(self, owner, frame, activation):
        if activation.owner != owner:
            raise ValueError("workflow IO activation does not match the checked call owner")
        try:
            binding = self.calls[owner, frame]
        except KeyError as exc:
            raise ValueError("workflow IO call binding is unavailable") from exc
        references = {path: resolve_io_route(route, activation)
            for path, route in binding.references.items()}
        return ProviderIOActivation(binding.callee, resolve_io_route(binding.reader, activation),
            MappingProxyType(references))

    def effect(self, owner, site, activation):
        if activation.owner != owner or (owner, site) not in self.sites:
            raise ValueError("workflow IO effect binding does not match its checked owner/site")
        return activation.reader
