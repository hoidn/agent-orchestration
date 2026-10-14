"""Source revision evidence for typed frontend compilation."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from orchestrator._common.safe_tree import resolve_path_preserving_fd
from .reader import SourceReadRecord

if TYPE_CHECKING:
    from .compiler import LinkedStage3CompileResult


def _source_file_digests_from_trace(
    *,
    compile_result: LinkedStage3CompileResult,
    source_read_records: tuple[SourceReadRecord, ...],
    source_revision_vector: tuple[tuple[Path, str], ...],
) -> dict[str, str]:
    """Resolve graph digests from the exact compiler-read revision vector."""

    return _source_file_digests_for_modules(
        {
            module_name: module_source.path
            for module_name, module_source in compile_result.graph.modules_by_name.items()
        },
        source_read_records=source_read_records,
        source_revision_vector=source_revision_vector,
    )


def _source_file_digests_for_modules(
    module_paths: Mapping[str, Path],
    *,
    source_read_records: tuple[SourceReadRecord, ...],
    source_revision_vector: tuple[tuple[Path, str], ...],
) -> dict[str, str]:
    """Resolve module digests without requiring a linked graph result."""

    revisions_by_path: dict[Path, str] = {}
    for canonical_path, revision in source_revision_vector:
        if canonical_path in revisions_by_path:
            raise ValueError("source read trace revision vector contains a duplicate path")
        if not _is_sha256_revision(revision):
            raise ValueError("source read trace revision vector contains a non-SHA-256 revision")
        revisions_by_path[canonical_path] = revision

    observed_revisions: dict[Path, str] = {}
    for record in source_read_records:
        previous = observed_revisions.setdefault(record.canonical_path, record.revision)
        if previous != record.revision:
            raise ValueError("source read trace records contain a revision mismatch")
    if observed_revisions != revisions_by_path:
        raise ValueError("source read trace records and revision vector mismatch")

    source_file_digests: dict[str, str] = {}
    for module_name, module_path in sorted(module_paths.items()):
        revision = revisions_by_path.get(resolve_path_preserving_fd(module_path))
        if revision is None:
            raise ValueError(
                f"source read trace is missing compiled module `{module_name}`"
            )
        source_file_digests[module_name] = revision.removeprefix("sha256:")
    return source_file_digests


def _is_sha256_revision(revision: object) -> bool:
    if not isinstance(revision, str) or not revision.startswith("sha256:"):
        return False
    digest = revision.removeprefix("sha256:")
    return len(digest) == 64 and all(character in "0123456789abcdef" for character in digest)
