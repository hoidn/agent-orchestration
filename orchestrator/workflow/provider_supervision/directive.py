"""Exact wire contract for one provider steering directive."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from orchestrator._common.canonical import compact_ascii_json_dumps


PROVIDER_STEERING_DIRECTIVE_TYPE_NAME = "ProviderSteeringDirective"
PROVIDER_STEERING_DIRECTIVE_CONTRACT_KIND = "union"
PROVIDER_STEERING_DIRECTIVE_CONTRACT_VALUE_TYPE = (
    PROVIDER_STEERING_DIRECTIVE_TYPE_NAME
)


class ProviderSteeringDirectiveVariant(str, Enum):
    CONTINUE = "CONTINUE"
    STEER = "STEER"


@dataclass(frozen=True)
class ProviderSteeringDirectiveFieldDescriptor:
    """One immutable field in the compiler-owned directive type."""

    name: str
    type_kind: str
    type_name: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": {
                "kind": self.type_kind,
                "name": self.type_name,
            },
        }


@dataclass(frozen=True)
class ProviderSteeringDirectiveVariantDescriptor:
    """One immutable variant in the compiler-owned directive type."""

    name: str
    fields: tuple[ProviderSteeringDirectiveFieldDescriptor, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "fields": [field.to_dict() for field in self.fields],
        }


@dataclass(frozen=True)
class ProviderSteeringDirectiveTypeDescriptor:
    """The one exact nominal union descriptor accepted by the runtime."""

    kind: str
    name: str
    variants: tuple[ProviderSteeringDirectiveVariantDescriptor, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "variants": [variant.to_dict() for variant in self.variants],
        }

    def canonical_json(self) -> str:
        return compact_ascii_json_dumps(self.to_dict())


PROVIDER_STEERING_DIRECTIVE_TYPE_DESCRIPTOR = (
    ProviderSteeringDirectiveTypeDescriptor(
        kind="union",
        name=PROVIDER_STEERING_DIRECTIVE_TYPE_NAME,
        variants=(
            ProviderSteeringDirectiveVariantDescriptor(
                name=ProviderSteeringDirectiveVariant.CONTINUE.value,
                fields=(),
            ),
            ProviderSteeringDirectiveVariantDescriptor(
                name=ProviderSteeringDirectiveVariant.STEER.value,
                fields=(
                    ProviderSteeringDirectiveFieldDescriptor(
                        name="guidance",
                        type_kind="primitive",
                        type_name="String",
                    ),
                ),
            ),
        ),
    )
)


def provider_steering_directive_type_descriptor() -> dict[str, Any]:
    """Return a fresh JSON-like projection of the immutable exact descriptor."""

    return PROVIDER_STEERING_DIRECTIVE_TYPE_DESCRIPTOR.to_dict()


def provider_steering_directive_type_descriptor_canonical_json() -> str:
    """Return the exact descriptor's compact canonical JSON."""

    return PROVIDER_STEERING_DIRECTIVE_TYPE_DESCRIPTOR.canonical_json()


@dataclass(frozen=True)
class ProviderSteeringDirective:
    """Validated compiler-owned supervisor control value."""

    variant: ProviderSteeringDirectiveVariant
    guidance: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.variant, ProviderSteeringDirectiveVariant):
            raise ValueError("directive.variant must be CONTINUE or STEER")
        if self.variant is ProviderSteeringDirectiveVariant.CONTINUE:
            if self.guidance is not None:
                raise ValueError("CONTINUE forbids guidance")
            return
        if not isinstance(self.guidance, str) or not self.guidance:
            raise ValueError("STEER requires non-empty guidance")

    @classmethod
    def from_dict(cls, value: Any) -> "ProviderSteeringDirective":
        if not isinstance(value, Mapping):
            raise ValueError("directive must be an object")
        raw_variant = value.get("variant")
        try:
            variant = ProviderSteeringDirectiveVariant(raw_variant)
        except (TypeError, ValueError) as exc:
            raise ValueError("directive.variant must be CONTINUE or STEER") from exc
        expected = (
            {"variant"}
            if variant is ProviderSteeringDirectiveVariant.CONTINUE
            else {"variant", "guidance"}
        )
        if set(value) != expected:
            raise ValueError(
                f"{variant.value} directive must be a closed object with keys "
                f"{sorted(expected)}"
            )
        return cls(variant=variant, guidance=value.get("guidance"))

    def to_dict(self) -> dict[str, str]:
        payload = {"variant": self.variant.value}
        if self.variant is ProviderSteeringDirectiveVariant.STEER:
            assert self.guidance is not None
            payload["guidance"] = self.guidance
        return payload

    def canonical_json(self) -> str:
        return compact_ascii_json_dumps(self.to_dict())
