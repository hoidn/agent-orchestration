"""Pure renderer registry for materialized workflow value views."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from types import MappingProxyType
from typing import Any

from .pure_expr import canonical_json_for_pure_value


VIEW_RENDERER_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ViewRendererDescriptor:
    """One registered renderer contract."""

    renderer_id: str
    renderer_version: int
    accepted_shape: str
    media_kind: str
    file_extension: str


class ViewRendererError(ValueError):
    """Raised when one value view cannot be rendered deterministically."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.metadata = dict(metadata or {})


_RENDERER_REGISTRY = MappingProxyType(
    {
        ("canonical-json", 1): ViewRendererDescriptor(
            renderer_id="canonical-json",
            renderer_version=1,
            accepted_shape="any_pure_value",
            media_kind="json",
            file_extension=".json",
        ),
        ("posix-path-line", 1): ViewRendererDescriptor(
            renderer_id="posix-path-line",
            renderer_version=1,
            accepted_shape="path_value",
            media_kind="text",
            file_extension=".txt",
        ),
    }
)


def resolve_view_renderer(renderer_id: str, renderer_version: int) -> ViewRendererDescriptor:
    """Return one registered renderer descriptor or raise."""

    descriptor = _RENDERER_REGISTRY.get((renderer_id, renderer_version))
    if descriptor is None:
        raise ViewRendererError(
            "view_renderer_unknown",
            "view renderer id/version is not registered",
            metadata={"renderer_id": renderer_id, "renderer_version": renderer_version},
        )
    return descriptor


def render_view(renderer_id: str, renderer_version: int, value_document: Any) -> bytes:
    """Render one canonical value document into deterministic bytes."""

    descriptor = resolve_view_renderer(renderer_id, renderer_version)
    if descriptor.accepted_shape == "any_pure_value":
        _validate_pure_value_shape(value_document)
        return f"{canonical_json_for_pure_value(value_document)}\n".encode("utf-8")
    if descriptor.accepted_shape == "path_value":
        if not isinstance(value_document, str) or not value_document or "\n" in value_document or "\r" in value_document:
            raise ViewRendererError(
                "view_value_shape_invalid",
                "posix-path-line requires one POSIX path string value",
                metadata={"renderer_id": renderer_id, "renderer_version": renderer_version},
            )
        return f"{value_document}\n".encode("utf-8")
    raise ViewRendererError(
        "view_renderer_unknown",
        "view renderer descriptor is invalid",
        metadata={"renderer_id": renderer_id, "renderer_version": renderer_version},
    )


def view_bytes_digest(data: bytes) -> str:
    """Return one deterministic content digest for rendered bytes."""

    return f"sha256:{sha256(data).hexdigest()}"


def view_evidence_key(
    renderer_id: str,
    renderer_version: int,
    schema_version: int,
    value_digest: str,
) -> str:
    """Return one stable evidence key for resume and drift detection."""

    return (
        "sha256:"
        + sha256(
            "|".join(
                (
                    str(VIEW_RENDERER_SCHEMA_VERSION),
                    renderer_id,
                    str(renderer_version),
                    str(schema_version),
                    value_digest,
                )
            ).encode("utf-8")
        ).hexdigest()
    )


def _validate_pure_value_shape(value: Any) -> None:
    if value is None or isinstance(value, (bool, int, float, str)):
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ViewRendererError(
                    "view_value_shape_invalid",
                    "canonical-json view values require string mapping keys",
                )
            _validate_pure_value_shape(item)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _validate_pure_value_shape(item)
        return
    raise ViewRendererError(
        "view_value_shape_invalid",
        "canonical-json view values must be JSON-like pure values",
        metadata={"type": type(value).__name__},
    )
