from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.lowering import pure_projection
from orchestrator.workflow_lisp.reader import SourceReadTrace


def _module_source(*, module_name: str, exported_name: str) -> bytes:
    return (
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                f"  (defmodule {module_name})",
                f"  (export {exported_name}))",
                "",
            ]
        )
    ).encode("utf-8")


@pytest.fixture(autouse=True)
def _clear_module_export_cache() -> None:
    pure_projection._cached_module_export_info.cache_clear()


def test_untraced_export_cache_reloads_same_path_when_exact_bytes_change(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "module.orc"
    source_path.write_bytes(
        _module_source(module_name="cache_probe", exported_name="Before")
    )

    assert pure_projection._module_export_info(str(source_path)) == (
        "cache_probe",
        frozenset({"Before"}),
    )

    source_path.write_bytes(
        _module_source(module_name="cache_probe", exported_name="After")
    )

    assert pure_projection._module_export_info(str(source_path)) == (
        "cache_probe",
        frozenset({"After"}),
    )


def test_untraced_export_cache_reuses_same_path_with_unchanged_exact_bytes(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "module.orc"
    source_bytes = _module_source(
        module_name="cache_probe",
        exported_name="Stable",
    )
    source_path.write_bytes(source_bytes)

    first = pure_projection._module_export_info(str(source_path))
    after_first = pure_projection._cached_module_export_info.cache_info()
    source_path.write_bytes(source_bytes)
    second = pure_projection._module_export_info(str(source_path))
    after_second = pure_projection._cached_module_export_info.cache_info()

    assert first == second == ("cache_probe", frozenset({"Stable"}))
    assert after_first.misses == 1
    assert after_second.misses == 1
    assert after_second.hits == after_first.hits + 1




def test_traced_export_read_bypasses_untraced_cache_and_records_exact_revision(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "module.orc"
    source_bytes = _module_source(
        module_name="cache_probe",
        exported_name="Traced",
    )
    source_path.write_bytes(source_bytes)
    expected = ("cache_probe", frozenset({"Traced"}))

    assert pure_projection._module_export_info(str(source_path)) == expected
    before_trace = pure_projection._cached_module_export_info.cache_info()
    trace = SourceReadTrace()

    assert (
        pure_projection._module_export_info(
            str(source_path),
            source_read_trace=trace,
        )
        == expected
    )

    assert pure_projection._cached_module_export_info.cache_info() == before_trace
    assert [
        (record.canonical_path, record.revision, record.ordinal)
        for record in trace.records
    ] == [
        (
            source_path.resolve(),
            f"sha256:{hashlib.sha256(source_bytes).hexdigest()}",
            0,
        )
    ]
