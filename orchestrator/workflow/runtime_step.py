"""Immutable runtime step views backed directly by executable IR nodes."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from .executable_ir import (
    AdjudicatedProviderStepConfig,
    CallBoundaryNode,
    CallStepConfig,
    CommandStepConfig,
    ExecutableNode,
    ExecutableNodeKind,
    FinalizationStepNode,
    ForEachStepConfig,
    IncrementScalarStepConfig,
    ProviderStepConfig,
    RepeatUntilStepConfig,
    SetScalarStepConfig,
    StepCommonConfig,
    WaitForStepConfig,
)


_MISSING = object()


def thaw_runtime_value(value: Any) -> Any:
    """Convert frozen IR payloads into plain JSON-like values on demand."""
    if isinstance(value, Mapping):
        return {str(key): thaw_runtime_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_runtime_value(item) for item in value]
    if isinstance(value, list):
        return [thaw_runtime_value(item) for item in value]
    return value


def _include_value(value: Any, *, include_empty: bool = False) -> bool:
    if value is None:
        return False
    if include_empty:
        return True
    if isinstance(value, Mapping):
        return bool(value)
    if isinstance(value, (list, tuple)):
        return bool(value)
    return True


def _common_value(common: StepCommonConfig, key: str) -> Any:
    if key == "on":
        return thaw_runtime_value(common.on) if _include_value(common.on) else _MISSING
    if key == "consumes":
        return thaw_runtime_value(common.consumes) if _include_value(common.consumes) else _MISSING
    if key == "consume_bundle":
        return thaw_runtime_value(common.consume_bundle) if _include_value(common.consume_bundle) else _MISSING
    if key == "publishes":
        return thaw_runtime_value(common.publishes) if _include_value(common.publishes) else _MISSING
    if key == "expected_outputs":
        return (
            thaw_runtime_value(common.expected_outputs)
            if _include_value(common.expected_outputs)
            else _MISSING
        )
    if key == "output_bundle":
        return thaw_runtime_value(common.output_bundle) if _include_value(common.output_bundle) else _MISSING
    if key == "persist_artifacts_in_state":
        return common.persist_artifacts_in_state if common.persist_artifacts_in_state is not None else _MISSING
    if key == "provider_session":
        return thaw_runtime_value(common.provider_session) if _include_value(common.provider_session) else _MISSING
    if key == "max_visits":
        return common.max_visits if common.max_visits is not None else _MISSING
    if key == "retries":
        return thaw_runtime_value(common.retries) if _include_value(common.retries) else _MISSING
    if key == "env":
        return thaw_runtime_value(common.env) if _include_value(common.env) else _MISSING
    if key == "secrets":
        return thaw_runtime_value(common.secrets) if _include_value(common.secrets) else _MISSING
    if key == "timeout_sec":
        return thaw_runtime_value(common.timeout_sec) if _include_value(common.timeout_sec) else _MISSING
    if key == "output_capture":
        return (
            thaw_runtime_value(common.output_capture)
            if _include_value(common.output_capture)
            else _MISSING
        )
    if key == "output_file":
        return thaw_runtime_value(common.output_file) if _include_value(common.output_file) else _MISSING
    if key == "allow_parse_error":
        return common.allow_parse_error if common.allow_parse_error is not None else _MISSING
    return _MISSING


def _common_keys(common: StepCommonConfig) -> Iterator[str]:
    for key in (
        "on",
        "consumes",
        "consume_bundle",
        "publishes",
        "expected_outputs",
        "output_bundle",
        "persist_artifacts_in_state",
        "provider_session",
        "max_visits",
        "retries",
        "env",
        "secrets",
        "timeout_sec",
        "output_capture",
        "output_file",
        "allow_parse_error",
    ):
        if _common_value(common, key) is not _MISSING:
            yield key


@dataclass(frozen=True)
class RuntimeStep(Mapping[str, Any]):
    """Mapping-style runtime view over one executable node."""

    node: ExecutableNode
    name: str
    step_id: str

    @property
    def node_id(self) -> str:
        return self.node.node_id

    @property
    def execution_kind(self) -> ExecutableNodeKind:
        if isinstance(self.node, FinalizationStepNode):
            return self.node.execution_kind
        return self.node.kind

    def _config(self) -> Any:
        return self.node.execution_config

    def _common(self) -> StepCommonConfig | None:
        config = self._config()
        return getattr(config, "common", None) if config is not None else None

    def __getitem__(self, key: str) -> Any:
        if key == "name":
            return self.name
        if key == "step_id":
            return self.step_id

        common = self._common()
        if common is not None:
            common_value = _common_value(common, key)
            if common_value is not _MISSING:
                return common_value

        config = self._config()
        if isinstance(config, CommandStepConfig):
            if key == "command":
                return thaw_runtime_value(config.command)
            raise KeyError(key)

        if isinstance(config, ProviderStepConfig):
            if key == "provider":
                return config.provider
            if key == "provider_params":
                value = thaw_runtime_value(config.provider_params)
                if _include_value(value):
                    return value
            if key == "input_file":
                value = thaw_runtime_value(config.input_file)
                if _include_value(value):
                    return value
            if key == "asset_file":
                value = thaw_runtime_value(config.asset_file)
                if _include_value(value):
                    return value
            if key == "depends_on":
                value = thaw_runtime_value(config.depends_on)
                if _include_value(value):
                    return value
            if key == "asset_depends_on":
                value = thaw_runtime_value(config.asset_depends_on)
                if _include_value(value):
                    return value
            if key == "inject_output_contract" and config.inject_output_contract is not None:
                return config.inject_output_contract
            if key == "inject_consumes" and config.inject_consumes is not None:
                return config.inject_consumes
            if key == "prompt_consumes":
                if config.prompt_consumes is not None:
                    return thaw_runtime_value(config.prompt_consumes)
            if key == "consumes_injection_position" and config.consumes_injection_position is not None:
                return config.consumes_injection_position
            raise KeyError(key)

        if isinstance(config, AdjudicatedProviderStepConfig):
            if key == "adjudicated_provider":
                return thaw_runtime_value(config.adjudicated_provider)
            if key == "input_file":
                value = thaw_runtime_value(config.input_file)
                if _include_value(value):
                    return value
            if key == "asset_file":
                value = thaw_runtime_value(config.asset_file)
                if _include_value(value):
                    return value
            if key == "depends_on":
                value = thaw_runtime_value(config.depends_on)
                if _include_value(value):
                    return value
            if key == "asset_depends_on":
                value = thaw_runtime_value(config.asset_depends_on)
                if _include_value(value):
                    return value
            if key == "inject_output_contract" and config.inject_output_contract is not None:
                return config.inject_output_contract
            if key == "inject_consumes" and config.inject_consumes is not None:
                return config.inject_consumes
            if key == "prompt_consumes":
                if config.prompt_consumes is not None:
                    return thaw_runtime_value(config.prompt_consumes)
            if key == "consumes_injection_position" and config.consumes_injection_position is not None:
                return config.consumes_injection_position
            raise KeyError(key)

        if isinstance(config, WaitForStepConfig):
            if key == "wait_for":
                return thaw_runtime_value(config.wait_for)
            raise KeyError(key)

        if isinstance(config, SetScalarStepConfig):
            if key == "set_scalar":
                return thaw_runtime_value(config.set_scalar)
            raise KeyError(key)

        if isinstance(config, IncrementScalarStepConfig):
            if key == "increment_scalar":
                return thaw_runtime_value(config.increment_scalar)
            raise KeyError(key)

        if isinstance(config, CallStepConfig):
            if key == "call":
                if isinstance(self.node, CallBoundaryNode) and self.node.call_alias:
                    return self.node.call_alias
                return config.call
            raise KeyError(key)

        if isinstance(config, ForEachStepConfig):
            if key == "for_each":
                for_each: dict[str, Any] = {}
                if config.items_from is not None:
                    for_each["items_from"] = config.items_from
                else:
                    for_each["items"] = thaw_runtime_value(config.items)
                if config.item_name != "item":
                    for_each["as"] = config.item_name
                return for_each
            raise KeyError(key)

        if isinstance(config, RepeatUntilStepConfig):
            if key == "repeat_until":
                return {
                    "id": config.body_id,
                    "max_iterations": config.max_iterations,
                }
            raise KeyError(key)

        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        yield "name"
        yield "step_id"

        common = self._common()
        if common is not None:
            yield from _common_keys(common)

        config = self._config()
        if isinstance(config, CommandStepConfig):
            yield "command"
            return

        if isinstance(config, ProviderStepConfig):
            yield "provider"
            for key in (
                "provider_params",
                "input_file",
                "asset_file",
                "depends_on",
                "asset_depends_on",
                "inject_output_contract",
                "inject_consumes",
                "prompt_consumes",
                "consumes_injection_position",
            ):
                try:
                    self[key]
                except KeyError:
                    continue
                yield key
            return

        if isinstance(config, AdjudicatedProviderStepConfig):
            yield "adjudicated_provider"
            for key in (
                "input_file",
                "asset_file",
                "depends_on",
                "asset_depends_on",
                "inject_output_contract",
                "inject_consumes",
                "prompt_consumes",
                "consumes_injection_position",
            ):
                try:
                    self[key]
                except KeyError:
                    continue
                yield key
            return

        if isinstance(config, WaitForStepConfig):
            yield "wait_for"
            return

        if isinstance(config, SetScalarStepConfig):
            yield "set_scalar"
            return

        if isinstance(config, IncrementScalarStepConfig):
            yield "increment_scalar"
            return

        if isinstance(config, CallStepConfig):
            yield "call"
            return

        if isinstance(config, ForEachStepConfig):
            yield "for_each"
            return

        if isinstance(config, RepeatUntilStepConfig):
            yield "repeat_until"

    def __len__(self) -> int:
        return sum(1 for _ in self)

    def to_compat_dict(self) -> dict[str, Any]:
        """Materialize a mutable compatibility mapping for tests or reports."""
        return {key: self[key] for key in self}
