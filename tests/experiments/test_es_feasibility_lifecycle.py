from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = REPOSITORY_ROOT / "scripts/experiments/es/feasibility_proofs.py"
CAPTURE_TEST_SUPPORT_PATH = (
    REPOSITORY_ROOT / "tests/experiments/test_es_feasibility_proofs.py"
)


def _runner() -> ModuleType:
    assert RUNNER_PATH.is_file()
    spec = importlib.util.spec_from_file_location(
        "es_feasibility_lifecycle_runner",
        RUNNER_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _git(*args: str, input_bytes: bytes | None = None) -> bytes:
    completed = subprocess.run(
        ("/usr/bin/git", *args),
        cwd=Path("/"),
        env={
            "HOME": "/",
            "LANG": "C",
            "LC_ALL": "C",
            "PATH": "/usr/bin:/bin",
        },
        check=False,
        shell=False,
        timeout=5,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    return completed.stdout


def _git_binding() -> dict[str, object]:
    literal = Path("/usr/bin/git")
    real = literal.resolve(strict=True)
    version = _git("--version").decode("utf-8", "strict")
    return {
        "literal_path": str(literal),
        "real_path": str(real),
        "sha256": _sha256(real.read_bytes()),
        "version_argv": [str(literal), "--version"],
        "version_output": version,
    }


def _write_object(repository: Path, object_type: str, payload: bytes) -> str:
    return _git(
        "--git-dir",
        str(repository),
        "hash-object",
        "-t",
        object_type,
        "-w",
        "--stdin",
        input_bytes=payload,
    ).decode("ascii").strip()


def _mixed_mode_variant(
    runner: ModuleType,
    tmp_path: Path,
) -> tuple[object, object, str]:
    repository = (tmp_path / "objects.git").resolve()
    _git("init", "--bare", str(repository))
    executable_oid = _write_object(repository, "blob", b"#!/bin/sh\nexit 0\n")
    link_oid = _write_object(repository, "blob", b"regular.txt")
    regular_oid = _write_object(repository, "blob", b"regular payload\n")
    tree_oid = _git(
        "--git-dir",
        str(repository),
        "mktree",
        input_bytes=(
            f"100755 blob {executable_oid}\texecutable\n"
            f"120000 blob {link_oid}\tlink\n"
            f"100644 blob {regular_oid}\tregular.txt\n"
        ).encode("ascii"),
    ).decode("ascii").strip()
    store = runner.GitObjectStore(repository, _git_binding())
    leaves = runner.read_tree_leaves(store, tree_oid)
    variant = runner.TreeVariant(
        variant_id="fixture-full",
        included_overlay_paths=tuple(leaf.path for leaf in leaves),
        omitted_cluster_id=None,
        tree=runner.DerivedTree(
            tree_oid=tree_oid,
            leaves=leaves,
            generated_tree_objects=(),
        ),
    )
    return store, variant, tree_oid


_CAPTURE_VARIANT_IDS = (
    "full",
    "test_only",
    "remove_one:IDENTITY_CONFIG",
    "remove_one:CONSTRUCTION_ADAPTERS",
    "remove_one:PERSISTENCE_REBUILD",
    "remove_one:INFERENCE_WORKFLOWS",
)

_AUTHORITY_BINDINGS = {
    "plan_sha256": "sha256:" + "1" * 64,
    "preedit_policy_sha256": "sha256:" + "2" * 64,
    "source_census_sha256": "sha256:" + "3" * 64,
    "selector_manifest_sha256": "sha256:" + "4" * 64,
    "a1_anchor_sha256": "sha256:" + "5" * 64,
}

_REVIEW_FINDING_TOKENS = (
    "anti_padding_accepted",
    "non_synthetic_baseline_and_remove_one_failures_accepted",
    "three_authenticated_ast_trace_cross_blob_edges_accepted",
    "four_independently_unmet_clusters_accepted",
    "non_collapse_requirement_accepted",
    "strict_reference_size_gate_5000_10000_deferred_to_task_3a",
    "operational_criterion_not_a_universal_provider_context_theorem",
)


def _six_variant_fixture(
    runner: ModuleType,
    tmp_path: Path,
) -> tuple[object, tuple[object, ...], Path, tuple[Path, ...], Path]:
    primary_repository = (tmp_path / "primary-objects.git").resolve()
    fallback_repository = (tmp_path / "fallback-objects.git").resolve()
    _git("init", "--bare", str(primary_repository))
    _git("init", "--bare", str(fallback_repository))
    binding = _git_binding()
    primary = runner.GitObjectStore(primary_repository, binding)
    fallback = runner.GitObjectStore(fallback_repository, binding)
    reader = runner.GitObjectPair(primary, fallback)
    variants: list[object] = []
    for ordinal, variant_id in enumerate(_CAPTURE_VARIANT_IDS):
        path = f"variant-{ordinal}.txt"
        blob_oid = _write_object(
            primary_repository,
            "blob",
            f"variant {ordinal}\n".encode("ascii"),
        )
        tree_oid = _git(
            "--git-dir",
            str(primary_repository),
            "mktree",
            input_bytes=f"100644 blob {blob_oid}\t{path}\n".encode("ascii"),
        ).decode("ascii").strip()
        leaf = runner.TreeLeaf(path=path, mode="100644", blob_oid=blob_oid)
        variants.append(
            runner.TreeVariant(
                variant_id=variant_id,
                included_overlay_paths=(path,),
                omitted_cluster_id=(
                    variant_id.removeprefix("remove_one:")
                    if variant_id.startswith("remove_one:")
                    else None
                ),
                tree=runner.DerivedTree(
                    tree_oid=tree_oid,
                    leaves=(leaf,),
                    generated_tree_objects=(),
                ),
            )
        )
    materialization_parent = (tmp_path / "materializations").resolve()
    materialization_parent.mkdir()
    sentinel = materialization_parent / "sibling-sentinel.txt"
    sentinel.write_bytes(b"preserve me\n")
    destinations = tuple(
        (materialization_parent / f"source-{ordinal}").resolve()
        for ordinal in range(6)
    )
    return (
        reader,
        tuple(variants),
        primary_repository,
        destinations,
        sentinel,
    )


def _root_id(
    runner: ModuleType,
    *,
    root_kind: str,
    canonical_path: Path,
    variant_id: str | None,
    content_name: str,
    content_value: str,
) -> str:
    identity = {
        "root_kind": root_kind,
        "canonical_path": str(canonical_path),
        "variant_id": variant_id,
        content_name: content_value,
    }
    return "root-" + hashlib.sha256(
        runner.canonical_json_bytes(identity)
    ).hexdigest()[:32]


def _expected_capture_roots(
    runner: ModuleType,
    *,
    variants: tuple[object, ...],
    destinations: tuple[Path, ...],
    object_store_root: Path,
) -> tuple[dict[str, object], ...]:
    source_roots = tuple(
        {
            "root_id": _root_id(
                runner,
                root_kind="source_tree",
                canonical_path=destination,
                variant_id=variant.variant_id,
                content_name="tree_oid",
                content_value=variant.tree.tree_oid,
            ),
            "root_kind": "source_tree",
            "canonical_path": str(destination),
            "variant_id": variant.variant_id,
            "pre_purge_lstat": "directory",
            "tree_oid": variant.tree.tree_oid,
        }
        for variant, destination in zip(variants, destinations, strict=True)
    )
    store_digest = runner.snapshot_directory_sha256(object_store_root)
    store_root = {
        "root_id": _root_id(
            runner,
            root_kind="git_object_store",
            canonical_path=object_store_root,
            variant_id=None,
            content_name="snapshot_sha256",
            content_value=store_digest,
        ),
        "root_kind": "git_object_store",
        "canonical_path": str(object_store_root),
        "pre_purge_lstat": "directory",
        "snapshot_sha256": store_digest,
    }
    return (*source_roots, store_root)


def _sealed_capture(
    runner: ModuleType,
    roots: tuple[dict[str, object], ...],
) -> dict[str, object]:
    record: dict[str, object] = {
        "capture_id": "capture-" + "1" * 32,
        "disposable_roots": [deepcopy(root) for root in roots],
    }
    record["record_sha256"] = _sha256(runner.canonical_json_bytes(record))
    return record


def _approved_reviews(
    review_root: Path,
    *,
    authority_bindings: dict[str, str] | None = None,
    reviewers: tuple[str, str] = ("reviewer-a", "reviewer-b"),
    reviewed_at: tuple[str, str] = (
        "2026-08-03T01:00:00Z",
        "2026-08-03T02:00:00Z",
    ),
) -> tuple[dict[str, str], dict[str, str]]:
    bindings = _AUTHORITY_BINDINGS if authority_bindings is None else authority_bindings
    rows: list[dict[str, str]] = []
    contracts = (
        (
            "specification",
            Path(
                "artifacts/review/"
                "es-f1-large-scope-amendment-plan-specification-review.md"
            ),
            "ES_F1_SCOPE_AMENDMENT_PLAN_SPEC_APPROVED",
        ),
        (
            "quality",
            Path(
                "artifacts/review/"
                "es-f1-large-scope-amendment-plan-quality-review.md"
            ),
            "ES_F1_SCOPE_AMENDMENT_PLAN_QUALITY_APPROVED",
        ),
    )
    for index, (review_kind, relative, verdict) in enumerate(contracts):
        target = review_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            f"# Fixture {review_kind} review",
            "",
            f"verdict: {verdict}",
            f"reviewer: {reviewers[index]}",
            f"reviewed_at: {reviewed_at[index]}",
            *(f"{key}: {bindings[key]}" for key in _AUTHORITY_BINDINGS),
            *_REVIEW_FINDING_TOKENS,
            "",
        ]
        raw = "\n".join(lines).encode("utf-8")
        target.write_bytes(raw)
        rows.append(
            {
                "review_kind": review_kind,
                "path": relative.as_posix(),
                "sha256": _sha256(raw),
            }
        )
    return rows[0], rows[1]


def _install_fixture_capture_validator(
    monkeypatch: pytest.MonkeyPatch,
    runner: ModuleType,
) -> None:
    def validate(
        record: dict[str, object],
        *,
        reobserve_roots: bool,
    ) -> dict[str, object]:
        body = deepcopy(record)
        record_sha256 = body.pop("record_sha256", None)
        if record_sha256 != _sha256(runner.canonical_json_bytes(body)):
            raise runner.FeasibilityProofError(
                "feasibility_capture_manifest_invalid",
                "record_sha256",
            )
        roots = body.get("disposable_roots")
        if not isinstance(roots, list) or len(roots) != 7:
            raise runner.FeasibilityProofError(
                "feasibility_capture_manifest_invalid",
                "disposable_roots",
            )
        paths: list[Path] = []
        for index, row in enumerate(roots):
            if not isinstance(row, dict):
                raise runner.FeasibilityProofError(
                    "feasibility_capture_manifest_invalid",
                    "disposable_roots",
                )
            path = Path(str(row.get("canonical_path")))
            if index < 6:
                content_name = "tree_oid"
                variant_id = str(row.get("variant_id"))
                if row.get("root_kind") != "source_tree":
                    raise runner.FeasibilityProofError(
                        "feasibility_capture_manifest_invalid",
                        "root_kind",
                    )
            else:
                content_name = "snapshot_sha256"
                variant_id = None
                if row.get("root_kind") != "git_object_store":
                    raise runner.FeasibilityProofError(
                        "feasibility_capture_manifest_invalid",
                        "root_kind",
                    )
            expected_id = _root_id(
                runner,
                root_kind=str(row["root_kind"]),
                canonical_path=path,
                variant_id=variant_id,
                content_name=content_name,
                content_value=str(row.get(content_name)),
            )
            if row.get("root_id") != expected_id:
                raise runner.FeasibilityProofError(
                    "feasibility_capture_manifest_invalid",
                    "root_id",
                )
            paths.append(path)
            if reobserve_roots:
                observed = (
                    runner.snapshot_project_tree_oid(path)
                    if index < 6
                    else runner.snapshot_directory_sha256(path)
                )
                if observed != row.get(content_name):
                    raise runner.FeasibilityProofError(
                        "feasibility_capture_root_invalid",
                        str(path),
                    )
        if len(set(paths)) != 7:
            raise runner.FeasibilityProofError(
                "feasibility_capture_manifest_invalid",
                "duplicate root",
            )
        return deepcopy(record)

    monkeypatch.setattr(
        runner,
        "validate_feasibility_capture_manifest_record",
        validate,
    )


def _materialized_capture_fixture(
    runner: ModuleType,
    tmp_path: Path,
) -> tuple[
    dict[str, object],
    tuple[dict[str, str], dict[str, str]],
    Path,
    Path,
]:
    reader, variants, object_store, destinations, sentinel = _six_variant_fixture(
        runner,
        tmp_path,
    )
    for variant, destination in zip(variants, destinations, strict=True):
        runner.materialize_tree_variant(reader, variant, destination)
    roots = _expected_capture_roots(
        runner,
        variants=variants,
        destinations=destinations,
        object_store_root=object_store,
    )
    capture = _sealed_capture(runner, roots)
    review_root = (tmp_path / "review-root").resolve()
    review_root.mkdir()
    reviews = _approved_reviews(review_root)
    return capture, reviews, review_root, sentinel


def _full_lifecycle_capture_fixture(
    runner: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[
    dict[str, object],
    tuple[dict[str, str], dict[str, str]],
    Path,
    Path,
    list[dict[str, object]],
]:
    support_spec = importlib.util.spec_from_file_location(
        "es_feasibility_capture_test_support",
        CAPTURE_TEST_SUPPORT_PATH,
    )
    assert support_spec is not None and support_spec.loader is not None
    support = importlib.util.module_from_spec(support_spec)
    sys.modules[support_spec.name] = support
    support_spec.loader.exec_module(support)
    manifest = support._capture_manifest_fixture(runner, tmp_path, monkeypatch)

    repository_root = runner._REPOSITORY_ROOT
    assert isinstance(repository_root, Path)
    fixture_runner = repository_root / runner.RUNNER_RELATIVE_PATH
    fixture_runner.parent.mkdir(parents=True, exist_ok=True)
    fixture_runner.write_bytes(RUNNER_PATH.read_bytes())
    runner_digest = runner.runner_sha256(fixture_runner)

    bindings = manifest["bindings"]
    roots = manifest["disposable_roots"]
    assert isinstance(bindings, dict) and isinstance(roots, list)
    primary_repository = Path(str(bindings["object_store"]["canonical_path"]))
    primary_repository.parent.mkdir(parents=True, exist_ok=True)
    fallback_repository = (tmp_path / "fixture-fallback.git").resolve()
    _git("init", "--bare", str(primary_repository))
    _git("init", "--bare", str(fallback_repository))
    binding = _git_binding()
    reader = runner.GitObjectPair(
        runner.GitObjectStore(primary_repository, binding),
        runner.GitObjectStore(fallback_repository, binding),
    )
    variants: list[object] = []
    for ordinal, variant_id in enumerate(_CAPTURE_VARIANT_IDS):
        relative = f"fixture-{ordinal}.txt"
        blob_oid = _write_object(
            primary_repository,
            "blob",
            f"authenticated variant {ordinal}\n".encode("ascii"),
        )
        tree_oid = _git(
            "--git-dir",
            str(primary_repository),
            "mktree",
            input_bytes=f"100644 blob {blob_oid}\t{relative}\n".encode("ascii"),
        ).decode("ascii").strip()
        leaf = runner.TreeLeaf(relative, "100644", blob_oid)
        variants.append(
            runner.TreeVariant(
                variant_id=variant_id,
                included_overlay_paths=(relative,),
                omitted_cluster_id=(
                    variant_id.removeprefix("remove_one:")
                    if variant_id.startswith("remove_one:")
                    else None
                ),
                tree=runner.DerivedTree(tree_oid, (leaf,), ()),
            )
        )
    destinations = tuple(
        Path(str(row["canonical_path"])) for row in roots[:6]
    )
    declarations = runner.materialize_capture_roots(
        reader,
        variants=tuple(variants),
        source_destinations=destinations,
        object_store_root=primary_repository,
    )
    manifest["disposable_roots"] = [deepcopy(row) for row in declarations]
    bindings["runner_sha256"] = runner_digest
    bindings["object_store"] = {
        "canonical_path": str(primary_repository),
        "snapshot_sha256": declarations[6]["snapshot_sha256"],
    }
    algebra = manifest["tree_algebra"]
    assert isinstance(algebra, dict)
    variant_rows = algebra["variants"]
    assert isinstance(variant_rows, list)
    by_variant = {variant.variant_id: variant for variant in variants}
    for row in variant_rows:
        assert isinstance(row, dict)
        variant = by_variant[str(row["variant_id"])]
        row["tree_oid"] = variant.tree.tree_oid
        row["leaf_count"] = len(variant.tree.leaves)

    ledger_rows = manifest["ledgers"]
    assert isinstance(ledger_rows, list) and len(ledger_rows) == 12
    for row in ledger_rows:
        assert isinstance(row, dict)
        authority = row["authority"]
        assert isinstance(authority, dict)
        variant_id = str(authority["variant_id"])
        tree_oid = by_variant[variant_id].tree.tree_oid
        authority["runner_sha256"] = runner_digest
        authority["expected_tree"] = tree_oid
        ledger_path = repository_root / str(row["path"])
        ledger_record = json.loads(ledger_path.read_text(encoding="utf-8"))
        ledger = runner._pytest_execution_ledger_from_record(ledger_record)
        updated = replace(
            ledger,
            runner_sha256=runner_digest,
            expected_tree=tree_oid,
            pre_tree=tree_oid,
            post_tree=tree_oid,
        )
        updated_record = runner.pytest_execution_ledger_record(updated)
        raw = runner.canonical_json_bytes(updated_record)
        ledger_path.write_bytes(raw)
        row["sha256"] = _sha256(raw)
        row["deterministic_sha256"] = updated_record["deterministic_sha256"]
        row["elapsed_ns"] = updated_record["elapsed_ns"]

    # The primary proof module owns byte-level base+overlay and AST reobservation.
    # This lifecycle integration keeps the real public validator, root probes, and
    # all twelve authorized ledger validators, but substitutes only that lowest
    # reobserver because its synthetic ledger fixture carries placeholder overlay
    # blob identities rather than a second full source-algebra fixture.
    algebra_calls: list[dict[str, object]] = []

    def retain_structural_algebra(**values: object) -> None:
        algebra_calls.append(dict(values))
        return None

    monkeypatch.setattr(
        runner,
        "_reobserve_capture_tree_algebra",
        retain_structural_algebra,
    )
    manifest = runner.build_feasibility_capture_manifest(
        captured_at=str(manifest["captured_at"]),
        bindings=bindings,
        disposable_roots=manifest["disposable_roots"],
        tree_algebra=algebra,
        ledgers=ledger_rows,
        directed_ast_edges=manifest["directed_ast_edges"],
    )
    sentinel = primary_repository.parent / "sibling-sentinel.txt"
    sentinel.write_bytes(b"preserve me\n")
    review_root = (tmp_path / "full-review-root").resolve()
    review_root.mkdir()
    reviews = _approved_reviews(review_root)
    return manifest, reviews, review_root, sentinel, algebra_calls


def test_public_capture_builder_seals_materialized_roots_and_ledgers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _runner()

    manifest, _, _, _, algebra_calls = _full_lifecycle_capture_fixture(
        runner,
        tmp_path,
        monkeypatch,
    )

    assert runner.validate_feasibility_capture_manifest_record(
        manifest,
        reobserve_roots=True,
    ) == manifest
    assert len(algebra_calls) == 2


def test_materialize_tree_variant_replays_authenticated_modes_and_bytes(
    tmp_path: Path,
) -> None:
    runner = _runner()
    store, variant, tree_oid = _mixed_mode_variant(runner, tmp_path)
    destination = (tmp_path / "materialized").resolve()

    runner.materialize_tree_variant(store, variant, destination)

    assert runner.snapshot_project_tree_oid(destination) == tree_oid
    assert (destination / "regular.txt").read_bytes() == b"regular payload\n"
    assert (destination / "executable").read_bytes() == b"#!/bin/sh\nexit 0\n"
    assert stat.S_IMODE((destination / "regular.txt").lstat().st_mode) == 0o644
    assert stat.S_IMODE((destination / "executable").lstat().st_mode) == 0o755
    assert (destination / "link").is_symlink()
    assert os.readlink(destination / "link") == "regular.txt"


def test_materialize_tree_variant_reconstructs_nested_prefix_ordered_git_tree(
    tmp_path: Path,
) -> None:
    runner = _runner()
    repository = (tmp_path / "objects.git").resolve()
    _git("init", "--bare", str(repository))
    item_payload = b"frozen backlog item\n"
    gaps_payload = b"backlog gaps\n"
    final_payload = b"final plan\n"
    item_oid = _write_object(repository, "blob", item_payload)
    gaps_oid = _write_object(repository, "blob", gaps_payload)
    final_oid = _write_object(repository, "blob", final_payload)
    active_tree_oid = _git(
        "--git-dir",
        str(repository),
        "mktree",
        input_bytes=f"100644 blob {item_oid}\tf1.md\n".encode("ascii"),
    ).decode("ascii").strip()
    backlog_tree_oid = _git(
        "--git-dir",
        str(repository),
        "mktree",
        input_bytes=(
            f"040000 tree {active_tree_oid}\tactive\n".encode("ascii")
        ),
    ).decode("ascii").strip()
    plans_tree_oid = _git(
        "--git-dir",
        str(repository),
        "mktree",
        input_bytes=(
            f"100644 blob {gaps_oid}\tbacklog-gaps\n"
            f"040000 tree {backlog_tree_oid}\tbacklog\n"
            f"100644 blob {final_oid}\tz-final\n"
        ).encode("ascii"),
    ).decode("ascii").strip()
    docs_tree_oid = _git(
        "--git-dir",
        str(repository),
        "mktree",
        input_bytes=f"040000 tree {plans_tree_oid}\tplans\n".encode("ascii"),
    ).decode("ascii").strip()
    tree_oid = _git(
        "--git-dir",
        str(repository),
        "mktree",
        input_bytes=f"040000 tree {docs_tree_oid}\tdocs\n".encode("ascii"),
    ).decode("ascii").strip()
    store = runner.GitObjectStore(repository, _git_binding())
    leaves = runner.read_tree_leaves(store, tree_oid)
    assert tuple(leaf.path for leaf in leaves) == (
        "docs/plans/backlog-gaps",
        "docs/plans/backlog/active/f1.md",
        "docs/plans/z-final",
    )
    variant = runner.TreeVariant(
        variant_id="nested-prefix-order",
        included_overlay_paths=tuple(leaf.path for leaf in leaves),
        omitted_cluster_id=None,
        tree=runner.DerivedTree(tree_oid, leaves, ()),
    )
    destination = (tmp_path / "materialized").resolve()

    runner.materialize_tree_variant(store, variant, destination)

    assert runner.snapshot_project_tree_oid(destination) == tree_oid
    assert (destination / "docs/plans/backlog-gaps").read_bytes() == gaps_payload
    assert (
        destination / "docs/plans/backlog/active/f1.md"
    ).read_bytes() == item_payload
    assert (destination / "docs/plans/z-final").read_bytes() == final_payload


@pytest.mark.parametrize("destination_kind", ("directory", "file", "symlink"))
def test_materialize_tree_variant_requires_an_absent_nonsymlink_destination(
    destination_kind: str,
    tmp_path: Path,
) -> None:
    runner = _runner()
    store, variant, _ = _mixed_mode_variant(runner, tmp_path)
    destination = (tmp_path / "materialized").resolve()
    if destination_kind == "directory":
        destination.mkdir()
    elif destination_kind == "file":
        destination.write_bytes(b"sentinel\n")
    else:
        target = tmp_path / "symlink-target"
        target.mkdir()
        destination.symlink_to(target, target_is_directory=True)

    with pytest.raises(runner.FeasibilityProofError) as caught:
        runner.materialize_tree_variant(store, variant, destination)

    assert caught.value.code == "feasibility_materialization_destination_invalid"


def test_materialize_capture_roots_creates_exact_six_sources_and_store_binding(
    tmp_path: Path,
) -> None:
    runner = _runner()
    reader, variants, object_store, destinations, sentinel = _six_variant_fixture(
        runner,
        tmp_path,
    )

    declarations = runner.materialize_capture_roots(
        reader,
        variants=variants,
        source_destinations=destinations,
        object_store_root=object_store,
    )

    expected = _expected_capture_roots(
        runner,
        variants=variants,
        destinations=destinations,
        object_store_root=object_store,
    )
    assert declarations == expected
    assert len({row["root_id"] for row in declarations}) == 7
    for variant, destination in zip(variants, destinations, strict=True):
        assert runner.snapshot_project_tree_oid(destination) == variant.tree.tree_oid
    assert object_store.is_dir()
    assert sentinel.read_bytes() == b"preserve me\n"


def test_materialize_capture_roots_cleans_only_new_sources_after_midbatch_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _runner()
    reader, variants, object_store, destinations, sentinel = _six_variant_fixture(
        runner,
        tmp_path,
    )
    original = runner.materialize_tree_variant

    def fail_on_fourth(
        active_reader: object,
        variant: object,
        destination: Path,
    ) -> dict[str, object]:
        if variant.variant_id == _CAPTURE_VARIANT_IDS[3]:
            raise runner.FeasibilityProofError(
                "feasibility_materialization_invalid",
                "fixture mid-batch failure",
            )
        return original(active_reader, variant, destination)

    monkeypatch.setattr(runner, "materialize_tree_variant", fail_on_fourth)

    with pytest.raises(runner.FeasibilityProofError):
        runner.materialize_capture_roots(
            reader,
            variants=variants,
            source_destinations=destinations,
            object_store_root=object_store,
        )

    assert all(not path.exists() and not path.is_symlink() for path in destinations)
    assert object_store.is_dir()
    assert sentinel.read_bytes() == b"preserve me\n"


def test_purge_capture_bound_roots_revalidates_and_removes_exact_seven_roots(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _runner()
    _install_fixture_capture_validator(monkeypatch, runner)
    capture, reviews, review_root, sentinel = _materialized_capture_fixture(
        runner,
        tmp_path,
    )
    roots = capture["disposable_roots"]
    assert isinstance(roots, list) and len(roots) == 7

    runner.purge_capture_bound_roots(
        capture,
        expected_authority_bindings=_AUTHORITY_BINDINGS,
        reviews=reviews,
        review_root=review_root,
    )

    for row in roots:
        path = Path(str(row["canonical_path"]))
        assert not path.exists() and not path.is_symlink()
    assert sentinel.read_bytes() == b"preserve me\n"


@pytest.mark.parametrize(
    "substitution",
    (
        "content",
        "root_identity",
        "review_bytes",
        "review_order",
        "unapproved",
        "wrong_authority_view",
        "decoy_mentions",
        "duplicate_reviewer",
        "quality_before_specification",
    ),
)
def test_purge_capture_bound_roots_rejects_substitution_before_mutation(
    substitution: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _runner()
    _install_fixture_capture_validator(monkeypatch, runner)
    capture, reviews, review_root, sentinel = _materialized_capture_fixture(
        runner,
        tmp_path,
    )
    roots = capture["disposable_roots"]
    assert isinstance(roots, list)
    active_reviews = reviews
    if substitution == "content":
        source = Path(str(roots[0]["canonical_path"])) / "variant-0.txt"
        source.write_bytes(b"substituted source\n")
    elif substitution == "root_identity":
        changed_roots = deepcopy(roots)
        changed_roots[0]["root_id"] = "root-" + "0" * 32
        capture = _sealed_capture(runner, tuple(changed_roots))
    elif substitution == "review_bytes":
        (review_root / reviews[0]["path"]).write_bytes(b"stale replacement\n")
    elif substitution == "review_order":
        active_reviews = (reviews[1], reviews[0])
    elif substitution == "unapproved":
        target = review_root / reviews[0]["path"]
        raw = b"# Fixture specification review\n\nresult: rejected\n"
        target.write_bytes(raw)
        replacement = deepcopy(reviews[0])
        replacement["sha256"] = _sha256(raw)
        active_reviews = (replacement, reviews[1])
    elif substitution == "wrong_authority_view":
        target = review_root / reviews[0]["path"]
        raw = target.read_bytes().replace(
            _AUTHORITY_BINDINGS["plan_sha256"].encode("ascii"),
            ("sha256:" + "9" * 64).encode("ascii"),
        )
        target.write_bytes(raw)
        replacement = deepcopy(reviews[0])
        replacement["sha256"] = _sha256(raw)
        active_reviews = (replacement, reviews[1])
    elif substitution == "decoy_mentions":
        target = review_root / reviews[0]["path"]
        correct_verdict = "ES_F1_SCOPE_AMENDMENT_PLAN_SPEC_APPROVED"
        correct_plan = _AUTHORITY_BINDINGS["plan_sha256"]
        raw = "\n".join(
            [
                "# Decoy fixture specification review",
                "",
                "verdict: REJECTED",
                f"Prose mentions {correct_verdict} but does not adopt it.",
                f"Prose mentions {correct_plan} but does not bind it.",
                f"plan_sha256: {'sha256:' + '9' * 64}",
                *(
                    f"{key}: {_AUTHORITY_BINDINGS[key]}"
                    for key in _AUTHORITY_BINDINGS
                    if key != "plan_sha256"
                ),
                *_REVIEW_FINDING_TOKENS,
                "",
            ]
        ).encode("utf-8")
        target.write_bytes(raw)
        replacement = deepcopy(reviews[0])
        replacement["sha256"] = _sha256(raw)
        active_reviews = (replacement, reviews[1])
    else:
        review_index = 1
        target = review_root / reviews[review_index]["path"]
        raw = target.read_bytes()
        if substitution == "duplicate_reviewer":
            raw = raw.replace(b"reviewer: reviewer-b", b"reviewer: reviewer-a")
        elif substitution == "quality_before_specification":
            raw = raw.replace(
                b"reviewed_at: 2026-08-03T02:00:00Z",
                b"reviewed_at: 2026-08-03T00:00:00Z",
            )
        else:  # pragma: no cover - exhaustive parameter guard
            raise AssertionError(substitution)
        target.write_bytes(raw)
        replacement = deepcopy(reviews[review_index])
        replacement["sha256"] = _sha256(raw)
        active_reviews = (reviews[0], replacement)

    with pytest.raises(runner.FeasibilityProofError):
        runner.purge_capture_bound_roots(
            capture,
            expected_authority_bindings=_AUTHORITY_BINDINGS,
            reviews=active_reviews,
            review_root=review_root,
        )

    assert all(Path(str(row["canonical_path"])).exists() for row in roots)
    assert sentinel.read_bytes() == b"preserve me\n"


def test_build_post_purge_tombstone_seals_exact_ordered_absence_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _runner()
    _install_fixture_capture_validator(monkeypatch, runner)
    capture, reviews, review_root, _ = _materialized_capture_fixture(
        runner,
        tmp_path,
    )
    runner.purge_capture_bound_roots(
        capture,
        expected_authority_bindings=_AUTHORITY_BINDINGS,
        reviews=reviews,
        review_root=review_root,
    )
    purged_at = "2026-08-04T12:00:00Z"

    tombstone = runner.build_post_purge_tombstone(
        capture,
        expected_authority_bindings=_AUTHORITY_BINDINGS,
        reviews=reviews,
        purged_at=purged_at,
        review_root=review_root,
    )

    roots = capture["disposable_roots"]
    assert isinstance(roots, list)
    assert tombstone["absent_roots"] == [
        {
            "root_id": row["root_id"],
            "canonical_path": row["canonical_path"],
            "lstat": "absent",
        }
        for row in roots
    ]
    assert tombstone["purged_at"] == purged_at
    body = deepcopy(tombstone)
    record_sha256 = body.pop("record_sha256")
    assert record_sha256 == _sha256(runner.canonical_json_bytes(body))


def test_build_post_purge_tombstone_rejects_partial_absence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _runner()
    _install_fixture_capture_validator(monkeypatch, runner)
    capture, reviews, review_root, _ = _materialized_capture_fixture(
        runner,
        tmp_path,
    )
    runner.purge_capture_bound_roots(
        capture,
        expected_authority_bindings=_AUTHORITY_BINDINGS,
        reviews=reviews,
        review_root=review_root,
    )
    roots = capture["disposable_roots"]
    assert isinstance(roots, list)
    Path(str(roots[0]["canonical_path"])).mkdir()

    with pytest.raises(runner.FeasibilityProofError):
        runner.build_post_purge_tombstone(
            capture,
            expected_authority_bindings=_AUTHORITY_BINDINGS,
            reviews=reviews,
            purged_at="2026-08-04T12:00:00Z",
            review_root=review_root,
        )


def test_public_capture_validation_and_fact_derivation_survive_exact_purge(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = _runner()
    manifest, reviews, review_root, sentinel, algebra_calls = (
        _full_lifecycle_capture_fixture(runner, tmp_path, monkeypatch)
    )
    ledger_rows = manifest["ledgers"]
    assert isinstance(ledger_rows, list) and len(ledger_rows) == 12
    assert all(
        (runner._REPOSITORY_ROOT / str(row["path"])).is_file()
        for row in ledger_rows
    )

    assert runner.validate_feasibility_capture_manifest_record(
        manifest,
        reobserve_roots=True,
    ) == manifest
    assert len(algebra_calls) == 2
    before_facts = runner.canonical_json_bytes(
        runner.derive_feasibility_facts(manifest)
    )

    absent_rows = runner.purge_capture_bound_roots(
        manifest,
        expected_authority_bindings=_AUTHORITY_BINDINGS,
        reviews=reviews,
        review_root=review_root,
    )

    assert len(algebra_calls) == 3
    after_facts = runner.canonical_json_bytes(
        runner.derive_feasibility_facts(manifest)
    )
    assert after_facts == before_facts
    tombstone = runner.build_post_purge_tombstone(
        manifest,
        expected_authority_bindings=_AUTHORITY_BINDINGS,
        reviews=reviews,
        purged_at="2026-08-04T13:00:00Z",
        review_root=review_root,
    )
    assert tuple(tombstone["absent_roots"]) == absent_rows
    source_census = importlib.import_module("scripts.experiments.es.source_census")
    assert source_census.validate_post_purge_tombstone(
        tombstone,
        capture_manifest=manifest,
        review_view_root=review_root,
    ) == tombstone

    roots = manifest["disposable_roots"]
    assert isinstance(roots, list) and len(roots) == 7
    for row in roots:
        with pytest.raises(FileNotFoundError):
            Path(str(row["canonical_path"])).lstat()
    assert sentinel.read_bytes() == b"preserve me\n"
