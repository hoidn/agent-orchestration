from __future__ import annotations

import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import zlib

import pytest


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = (
    ROOT
    / "experiments"
    / "orc_effectiveness"
    / "f1_es"
    / "projection-manifest.json"
)
SCHEMA_PATH = MANIFEST_PATH.with_name("projection-manifest.schema.json")


def _projection_module():
    return importlib.import_module("scripts.experiments.es.projection")


def test_checked_in_manifest_binds_exact_frozen_source_and_commit_vectors() -> None:
    projection = _projection_module()

    manifest = projection.load_projection_manifest(MANIFEST_PATH)

    assert manifest.source_commit == "c081b7b6cd160b3da7031ee325bbf0ade1025d7a"
    assert manifest.source_tree == "9193ae2f81116d1bac4cf3cb74395613c1220dbe"
    assert manifest.retained_leaf_count == 1_948
    assert manifest.retained_tree == "e64f3c05f5a0894f41c047d128a9040a2cda6764"
    assert manifest.exclusion_digest == (
        "sha256:8f7b02d2fe83700990f133e523e25c7a808c4057c15710567896d7496cee4141"
    )
    assert manifest.retained_inventory_digest == (
        "sha256:6fc936c54977d9adc7bdbae02bfa69592c55722e5cf5eddbd1b958ee1bc71404"
    )
    assert len(manifest.commit_message) == 204
    assert hashlib.sha256(manifest.commit_message).hexdigest() == (
        "b183cb771aca6398acdcb01f4983f110c92b43ad7cc148a01ca48f7719e464be"
    )
    content = projection.render_commit_content(manifest)
    assert len(content) == 430
    assert hashlib.sha256(content).hexdigest() == (
        "c2989a3daeb32130711591a4941b0eaf3345e1a3f3816430dd8583d945411e31"
    )
    assert projection.git_object_id("commit", content) == (
        "8f191031f233d50a4d020d8a988036e99487f570"
    )
    assert manifest.projection_commit == "8f191031f233d50a4d020d8a988036e99487f570"
    assert manifest.canonical_storage_root == Path(
        "/home/ollie/.local/state/orchestrator/es-source-projections"
    )
    assert projection.projection_locator(manifest) == (
        manifest.canonical_storage_root
        / "git-sha1"
        / manifest.projection_commit
    )


def test_manifest_schema_is_valid_and_closes_every_nested_record() -> None:
    from jsonschema import Draft202012Validator, ValidationError

    schema = json.loads(SCHEMA_PATH.read_bytes())
    payload = json.loads(MANIFEST_PATH.read_bytes())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    validator.validate(payload)

    mutations = []
    for path in (
        ("source",),
        ("exclusions",),
        ("exclusions", "rows", 0),
        ("retained",),
        ("retained", "mode_counts"),
        ("recipe",),
        ("recipe", "author"),
        ("policies",),
        ("locator",),
    ):
        candidate = json.loads(MANIFEST_PATH.read_bytes())
        target = candidate
        for component in path:
            target = target[component]
        target["unexpected"] = None
        mutations.append(candidate)
    for candidate in mutations:
        with pytest.raises(ValidationError):
            validator.validate(candidate)


@pytest.mark.parametrize("mutation", ["duplicate-key", "bad-scalar", "trailing-bytes"])
def test_manifest_loader_rejects_duplicate_keys_bad_scalars_and_trailing_bytes(
    tmp_path: Path,
    mutation: str,
) -> None:
    projection = _projection_module()
    raw = MANIFEST_PATH.read_bytes()
    if mutation == "duplicate-key":
        encoded = raw.replace(
            b'{"exclusions":',
            b'{"schema_version":"es_source_projection.v1","schema_version":"es_source_projection.v1","exclusions":',
            1,
        )
    elif mutation == "trailing-bytes":
        encoded = raw + b" \n"
    else:
        payload = json.loads(raw)
        payload["recipe"]["commit_content_bytes"] = "430"
        encoded = projection.canonical_json_bytes(payload)
    candidate = tmp_path / "projection-manifest.json"
    candidate.write_bytes(encoded)

    with pytest.raises(projection.ProjectionError) as caught:
        projection.load_projection_manifest(candidate)

    assert caught.value.code == "projection_manifest_noncanonical"


def test_manifest_loader_rejects_float_message_byte_count(tmp_path: Path) -> None:
    projection = _projection_module()
    payload = json.loads(MANIFEST_PATH.read_bytes())
    payload["recipe"]["message_bytes"] = 204.0
    candidate = tmp_path / "projection-manifest.json"
    candidate.write_bytes(projection.canonical_json_bytes(payload))

    with pytest.raises(projection.ProjectionError) as caught:
        projection.load_projection_manifest(candidate)

    assert caught.value.code == "projection_manifest_noncanonical"


def test_manifest_loader_rejects_unsupported_recipe_policy(tmp_path: Path) -> None:
    projection = _projection_module()
    payload = json.loads(MANIFEST_PATH.read_bytes())
    payload["recipe"]["policy"] = "unsupported-projection-policy.v1"
    candidate = tmp_path / "projection-manifest.json"
    candidate.write_bytes(projection.canonical_json_bytes(payload))

    with pytest.raises(projection.ProjectionError) as caught:
        projection.load_projection_manifest(candidate)

    assert caught.value.code == "projection_manifest_noncanonical"


@pytest.mark.parametrize("mutation", ["pretty", "extra-field"])
def test_manifest_loader_rejects_noncanonical_or_open_records(
    tmp_path: Path,
    mutation: str,
) -> None:
    projection = _projection_module()
    payload = json.loads(MANIFEST_PATH.read_bytes())
    if mutation == "pretty":
        encoded = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    else:
        payload["unexpected"] = None
        encoded = projection.canonical_json_bytes(payload)
    candidate = tmp_path / "projection-manifest.json"
    candidate.write_bytes(encoded)

    with pytest.raises(projection.ProjectionError) as caught:
        projection.load_projection_manifest(candidate)

    assert caught.value.code == "projection_manifest_noncanonical"


def test_frozen_source_inventory_matches_every_bound_row_mode_and_symlink() -> None:
    projection = _projection_module()
    manifest = projection.load_projection_manifest(MANIFEST_PATH)
    repository = Path(manifest.source_repository)
    if not repository.is_dir():
        pytest.skip(f"frozen F1 repository is unavailable: {repository}")

    inspection = projection.inspect_source(repository, manifest)

    assert inspection.source_commit == manifest.source_commit
    assert inspection.source_tree == manifest.source_tree
    assert inspection.source_leaf_count == 1_954
    assert inspection.excluded_rows == manifest.exclusions
    assert inspection.retained_leaf_count == 1_948
    assert inspection.retained_inventory_digest == manifest.retained_inventory_digest
    assert inspection.retained_mode_counts == manifest.retained_mode_counts
    assert len(inspection.symlinks) == 37
    assert all(row.mode == "120000" for row in inspection.symlinks)
    assert all(row.link_target is not None for row in inspection.symlinks)


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("source-tree", "projection_source_tree_mismatch"),
        ("exclusion", "projection_exclusion_set_mismatch"),
        ("retained", "projection_retained_inventory_mismatch"),
    ],
)
def test_source_verification_rejects_identity_exclusion_and_retained_row_drift(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
) -> None:
    projection = _projection_module()
    payload = json.loads(MANIFEST_PATH.read_bytes())
    if mutation == "source-tree":
        payload["source"]["tree"] = "0" * 40
    elif mutation == "exclusion":
        payload["exclusions"]["rows"][0]["oid"] = "0" * 40
        payload["exclusions"]["sha256"] = "sha256:" + hashlib.sha256(
            projection.canonical_json_bytes(payload["exclusions"]["rows"])
        ).hexdigest()
    else:
        payload["retained"]["inventory_sha256"] = "sha256:" + "0" * 64
    candidate = tmp_path / "projection-manifest.json"
    candidate.write_bytes(projection.canonical_json_bytes(payload))
    manifest = projection.load_projection_manifest(candidate)
    source = Path(manifest.source_repository)
    if not source.is_dir():
        pytest.skip(f"frozen F1 repository is unavailable: {source}")

    with pytest.raises(projection.ProjectionError) as caught:
        projection.inspect_source(source, manifest)

    assert caught.value.code == expected_code


@pytest.mark.parametrize(
    ("mode", "object_type", "path", "payload", "expected_code"),
    [
        (
            "120000",
            "blob",
            "nested/escape",
            b"../../outside",
            "projection_source_symlink_unsupported",
        ),
        (
            "100644",
            "blob",
            "weights.bin",
            b"version https://git-lfs.github.com/spec/v1\n"
            b"oid sha256:0000000000000000000000000000000000000000000000000000000000000000\n"
            b"size 1\n",
            "projection_source_lfs_unsupported",
        ),
        (
            "100644",
            "blob",
            ".gitattributes",
            b"*.bin filter=lfs diff=lfs merge=lfs -text\n",
            "projection_source_lfs_unsupported",
        ),
        (
            "160000",
            "commit",
            "vendor/dependency",
            None,
            "projection_source_entry_unsupported",
        ),
        (
            "100664",
            "blob",
            "special-mode.txt",
            b"payload\n",
            "projection_source_entry_unsupported",
        ),
    ],
)
def test_retained_entry_policy_rejects_unsafe_symlink_lfs_and_special_entries(
    mode: str,
    object_type: str,
    path: str,
    payload: bytes | None,
    expected_code: str,
) -> None:
    projection = _projection_module()
    row = projection.RetainedRow(mode, object_type, "0" * 40, path)

    with pytest.raises(projection.ProjectionError) as caught:
        projection.validate_retained_entry(row, payload)

    assert caught.value.code == expected_code


def test_retained_symlink_cannot_depend_on_an_excluded_root() -> None:
    projection = _projection_module()
    row = projection.RetainedRow("120000", "blob", "0" * 40, "docs/link")

    with pytest.raises(projection.ProjectionError) as caught:
        projection.validate_retained_entry(
            row,
            b"../ptycho/FRC",
            excluded_paths=("ptycho/FRC",),
        )

    assert caught.value.code == "projection_source_symlink_unsupported"


def _git(
    repository: Path,
    *arguments: str,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ("git", "-C", str(repository), *arguments),
        check=True,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_builds_exact_parentless_projection_and_passes_actual_e1_materialization(
    tmp_path: Path,
) -> None:
    projection = _projection_module()
    manifest = projection.load_projection_manifest(MANIFEST_PATH)
    source = Path(manifest.source_repository)
    if not source.is_dir():
        pytest.skip(f"frozen F1 repository is unavailable: {source}")
    storage_root = (tmp_path / "projection-store").resolve()

    locator = projection.projection_locator(manifest, storage_root=storage_root)
    result = projection.materialize_projection(
        manifest,
        source_repository=source,
        storage_root=storage_root,
    )
    verified = projection.verify_projection(locator, manifest)

    assert result.locator == locator
    assert locator.is_absolute()
    assert not locator.is_relative_to(ROOT)
    assert not locator.is_relative_to(source)
    assert result.commit == manifest.projection_commit
    assert result.tree == manifest.retained_tree
    assert result.reused is False
    assert verified.commit == manifest.projection_commit
    assert verified.tree == manifest.retained_tree
    assert verified.parent_count == 0
    assert verified.unreachable_object_count == 0
    assert _git(locator, "cat-file", "commit", result.commit).stdout == (
        projection.render_commit_content(manifest)
    )
    assert manifest.source_commit not in verified.object_ids
    assert projection.materialize_projection(
        manifest,
        source_repository=source,
        storage_root=storage_root,
    ).reused is True

    from orchestrator.workflow.run_ref.contracts import RunRefSourceRefusal
    from orchestrator.workflow.run_ref.source import SourceRequest, materialize_source

    original_root = (tmp_path / "original-run-ref").resolve()
    original_workspace = (tmp_path / "original-workspace").resolve()
    with pytest.raises(RunRefSourceRefusal) as original_refusal:
        materialize_source(
            SourceRequest(locator=str(source), commit=manifest.source_commit),
            run_ref_root=original_root,
            workspace=original_workspace,
        )
    assert original_refusal.value.code == "trial_source_submodules_unsupported"
    assert not original_workspace.exists()
    assert list(original_root.rglob("run-ref-seal.json")) == []
    assert not (original_root / "mirrors").exists() or list(
        (original_root / "mirrors").iterdir()
    ) == []

    materialized = materialize_source(
        SourceRequest(locator=str(locator), commit=manifest.projection_commit),
        run_ref_root=(tmp_path / "projection-run-ref").resolve(),
        workspace=(tmp_path / "projection-workspace").resolve(),
    )
    assert materialized.resolved_commit_sha == manifest.projection_commit
    assert materialized.verified_git_tree.value == f"git-tree:{manifest.retained_tree}"

    assert _git(locator, "symbolic-ref", "HEAD").stdout == b"refs/heads/projection\n"
    alternates = locator / "objects" / "info" / "alternates"
    alternates.write_text(str(source / ".git" / "objects") + "\n", encoding="utf-8")
    with pytest.raises(projection.ProjectionError) as alternate:
        projection.verify_projection(locator, manifest)
    assert alternate.value.code == "projection_repository_escape"
    alternates.unlink()

    _git(locator, "symbolic-ref", "HEAD", "refs/heads/missing")
    with pytest.raises(projection.ProjectionError) as bad_head:
        projection.verify_projection(locator, manifest)
    assert bad_head.value.code == "projection_history_leakage"
    _git(locator, "symbolic-ref", "HEAD", "refs/heads/projection")

    child = _git(
        locator,
        "commit-tree",
        manifest.retained_tree,
        "-p",
        manifest.projection_commit,
        input_bytes=b"forbidden child\n",
    ).stdout.decode("ascii").strip()
    _git(locator, "update-ref", "refs/heads/projection", child)
    with pytest.raises(projection.ProjectionError) as history:
        projection.verify_projection(locator, manifest)
    assert history.value.code == "projection_history_leakage"

    _git(
        locator,
        "update-ref",
        "refs/heads/projection",
        manifest.projection_commit,
    )
    with pytest.raises(projection.ProjectionError) as unreachable:
        projection.verify_projection(locator, manifest)
    assert unreachable.value.code == "projection_extra_object"
    with pytest.raises(projection.ProjectionError) as preexisting:
        projection.materialize_projection(
            manifest,
            source_repository=source,
            storage_root=storage_root,
        )
    assert preexisting.value.code == "projection_extra_object"


def test_projection_verification_rejects_reachable_loose_blob_hash_mismatch(
    tmp_path: Path,
) -> None:
    projection = _projection_module()
    manifest = projection.load_projection_manifest(MANIFEST_PATH)
    locator = projection.projection_locator(manifest)
    if not locator.is_dir():
        pytest.skip("frozen projection locator is unavailable")
    disposable = (tmp_path / "projection.git").resolve()
    subprocess.run(
        (
            "git",
            "clone",
            "--quiet",
            "--bare",
            "--no-local",
            str(locator),
            str(disposable),
        ),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    projection.verify_projection(disposable, manifest)
    pack_directory = disposable / "objects" / "pack"
    pack_payloads = tuple(
        path.read_bytes() for path in sorted(pack_directory.glob("*.pack"))
    )
    assert pack_payloads
    for path in tuple(pack_directory.iterdir()):
        path.unlink()
    for payload in pack_payloads:
        subprocess.run(
            ("git", "-C", str(disposable), "unpack-objects", "-r"),
            check=True,
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    projection.verify_projection(disposable, manifest)

    selected: tuple[str, bytes] | None = None
    inventory = _git(
        disposable,
        "ls-tree",
        "-r",
        manifest.projection_commit,
    ).stdout
    for raw_row in inventory.splitlines():
        metadata, _ = raw_row.split(b"\t", 1)
        _, object_type, raw_oid = metadata.split(b" ", 2)
        if object_type != b"blob":
            continue
        oid = raw_oid.decode("ascii")
        payload = _git(disposable, "cat-file", "blob", oid).stdout
        if payload:
            selected = (oid, payload)
            break
    assert selected is not None
    oid, payload = selected
    loose_object = disposable / "objects" / oid[:2] / oid[2:]
    assert loose_object.is_file()

    corrupted = bytes((payload[0] ^ 1,)) + payload[1:]
    corrupted_framed = (
        b"blob " + str(len(corrupted)).encode("ascii") + b"\0" + corrupted
    )
    loose_object.chmod(0o644)
    loose_object.write_bytes(zlib.compress(corrupted_framed))
    assert _git(disposable, "cat-file", "blob", oid).stdout == corrupted

    with pytest.raises(projection.ProjectionError) as caught:
        projection.verify_projection(disposable, manifest)

    assert caught.value.code == "projection_repository_invalid"


def test_ptycho311_collect_probe_removes_editable_hooks_and_audits_all_origins(
    tmp_path: Path,
) -> None:
    projection = _projection_module()
    manifest = projection.load_projection_manifest(MANIFEST_PATH)
    python = Path("/home/ollie/miniconda3/envs/ptycho311/bin/python")
    locator = projection.projection_locator(manifest)
    if not python.is_file() or not locator.is_dir():
        pytest.skip("frozen ptycho311 environment or projection locator is unavailable")
    workspace = (tmp_path / "projected-workspace").resolve()
    subprocess.run(
        ("git", "clone", "--quiet", "--no-local", str(locator), str(workspace)),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    result = projection.run_import_origin_probe(
        python=python,
        workspace=workspace,
        selectors=projection.FOCUSED_TEST_PATHS,
        report_path=(tmp_path / "collect-origin-report.json").resolve(),
        collect_only=True,
    )

    assert result.exit_code == 0
    assert result.collected == 205
    assert result.loaded_forbidden_modules == ()
    assert result.forbidden_origin_rows == ()
    assert any(name.startswith("__editable___ptychopinn_") for name in result.removed_hooks)
    assert Path("/home/ollie/Documents/tmp/PtychoPINN") in result.forbidden_roots
    assert result.projected_origin_rows
    assert all(
        Path(origin).is_relative_to(workspace)
        for _, origin in result.projected_origin_rows
    )
    assert result.cache_artifacts == ()
    assert result.plugin_autoload_disabled is True
    assert result.outside_project_origin_rows == ()


def test_project_owned_origin_classification_accepts_projection_and_rejects_external(
    tmp_path: Path,
) -> None:
    projection = _projection_module()
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir()
    rows = (
        ("ptycho.models", str(workspace / "ptycho" / "models.py")),
        ("ptycho_torch", "/opt/site-packages/ptycho_torch/__init__.py"),
        ("numpy", "/opt/site-packages/numpy/__init__.py"),
    )

    assert projection.outside_project_owned_origins(
        rows,
        workspace=workspace,
        prefixes=("ptycho", "ptycho_torch", "test_generator_registry"),
    ) == (("ptycho_torch", "/opt/site-packages/ptycho_torch/__init__.py"),)


def test_exact_ten_module_projected_baseline_passes_without_cache_writes(
    tmp_path: Path,
) -> None:
    projection = _projection_module()
    manifest = projection.load_projection_manifest(MANIFEST_PATH)
    python = Path("/home/ollie/miniconda3/envs/ptycho311/bin/python")
    locator = projection.projection_locator(manifest)
    if not python.is_file() or not locator.is_dir():
        pytest.skip("frozen ptycho311 environment or projection locator is unavailable")
    workspace = (tmp_path / "projected-workspace").resolve()
    subprocess.run(
        ("git", "clone", "--quiet", "--no-local", str(locator), str(workspace)),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    result = projection.run_focused_baseline(
        python=python,
        workspace=workspace,
        report_path=(tmp_path / "focused-baseline-origin-report.json").resolve(),
        forbidden_roots=(Path(manifest.source_repository),),
    )

    assert result.exit_code == 0
    assert result.collected == 205
    assert dict(result.outcomes) == {
        "passed": 205,
        "failed": 0,
        "skipped": 0,
        "errors": 0,
    }
    assert result.loaded_forbidden_modules == ()
    assert result.forbidden_origin_rows == ()
    assert result.cache_artifacts == ()


def test_static_import_closure_is_digest_bound_and_excludes_deferred_surfaces(
    tmp_path: Path,
) -> None:
    projection = _projection_module()
    manifest = projection.load_projection_manifest(MANIFEST_PATH)
    locator = projection.projection_locator(manifest)
    if not locator.is_dir():
        pytest.skip("frozen projection locator is unavailable")
    workspace = (tmp_path / "projected-workspace").resolve()
    subprocess.run(
        ("git", "clone", "--quiet", "--no-local", str(locator), str(workspace)),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    result = projection.compute_static_import_closure(
        workspace=workspace,
        selectors=projection.FOCUSED_TEST_PATHS,
    )

    assert set(projection.FOCUSED_TEST_PATHS).issubset(
        {path for path, _ in result.file_rows}
    )
    assert len(result.file_rows) > len(projection.FOCUSED_TEST_PATHS)
    assert result.digest.startswith("sha256:")
    assert len(result.digest) == 71
    assert result.forbidden_imports == ()
    assert result.excluded_path_rows == ()
    assert all(not path.startswith("ptycho/FRC/") for path, _ in result.file_rows)
    assert all(path != "ptycho/evaluation.py" for path, _ in result.file_rows)
