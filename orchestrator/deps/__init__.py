"""Dependency resolution and injection module."""

from .resolver import DependencyResolver
from .injector import DependencyInjector
from .content_snapshot import (
    MAX_INJECTION_BYTES,
    MAX_INSTRUCTION_BYTES,
    TRUNCATION_SUMMARY_RESERVE_BYTES,
    AuthoredDependencyRow,
    CanonicalDependencyGroup,
    DependencyContent,
    DependencyContentSnapshot,
    DependencyGroupTruncation,
    RenderedContentSnapshot,
    build_content_snapshot,
    render_content_snapshot,
)

__all__ = [
    "DependencyResolver",
    "DependencyInjector",
    "MAX_INJECTION_BYTES",
    "MAX_INSTRUCTION_BYTES",
    "TRUNCATION_SUMMARY_RESERVE_BYTES",
    "AuthoredDependencyRow",
    "CanonicalDependencyGroup",
    "DependencyContent",
    "DependencyContentSnapshot",
    "DependencyGroupTruncation",
    "RenderedContentSnapshot",
    "build_content_snapshot",
    "render_content_snapshot",
]
