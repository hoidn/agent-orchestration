"""Admission, provisioning and child authority of `run_ref_confinement.v1` children.

Child authority (header, checked program, memo, child recipe) lives only in the
external control root beneath the parent run root; the clone is provisioned with
sanitized host Git, the image comes from a sealed store admitted through a
retained descriptor, and the confinement profile is never a registered backend.
No sandbox is launched here: these children are pure (real launches live in
tests/e2e).
"""

from __future__ import annotations

from base64 import b64decode
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

import pytest

from orchestrator.contracts.closed_program.program import ClosedProgram
from orchestrator.providers.isolation_backend import (
    ProviderIsolationBackendUnavailable,
    get_provider_isolation_backend,
)
from orchestrator.workflow.evaluated.machine import site_nodes
from orchestrator.workflow.evaluated.memo import reduce_memo
from orchestrator.workflow.run_ref import image_store
from orchestrator.workflow.run_ref.confined_config import decode_run_ref_confined_static_config
from orchestrator.workflow.run_ref.confinement import (
    ConfinedAttemptLayout,
    HostFacts,
    admit_confined_child,
    confined_attempt_layout,
    confined_child_accounting,
    provision_confined_child,
    refuse_overlapping_roots,
)
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes
from orchestrator.workflow.run_ref.evaluated_child import (
    _captured_child_authority,
    confined_child_header,
    execute_confined_child,
    validate_confined_child_terminal,
)
from orchestrator.workflow.run_ref.ledger import RunRefVisitKey
from orchestrator.workflow.run_ref.runtime import RunRefRuntimeError
from orchestrator.workflow.run_ref.source import RunRefSourceRefusal
from orchestrator.workflow.run_ref.wire import confined_child_request
from orchestrator.workflow_lisp.closed.build import Builder, build_closed_program
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program


HOST = HostFacts(bwrap=True, systemd_run=True, ptrace_scope=1, machine="x86_64")
REJECTED_IN_CLONE = {".orchestrate", "workspace.guard", "workspace.lock"}


# --- OCI layout fixture ------------------------------------------------------------

def _tar(members: list[tuple[str, str, object, int]]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name, kind, data, mode in members:
            info = tarfile.TarInfo(name)
            info.mode = mode
            if kind == "dir":
                info.type = tarfile.DIRTYPE
                archive.addfile(info)
            elif kind == "symlink":
                info.type, info.linkname = tarfile.SYMTYPE, str(data)
                archive.addfile(info)
            elif kind == "hardlink":
                info.type, info.linkname = tarfile.LNKTYPE, str(data)
                archive.addfile(info)
            elif kind == "chr":
                info.type = tarfile.CHRTYPE
                archive.addfile(info)
            else:
                payload = bytes(data)
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


BASE_LAYER = [
    ("usr", "dir", None, 0o755), ("usr/bin", "dir", None, 0o755),
    ("usr/bin/dash", "file", b"#!dash\n", 0o755), ("usr/bin/sh", "symlink", "dash", 0o777),
    ("usr/bin/env", "file", b"#!env\n", 0o755), ("usr/bin/setsid", "file", b"#!setsid\n", 0o755),
    ("usr/bin/su", "file", b"su\n", 0o4755),
    ("bin", "symlink", "usr/bin", 0o777), ("etc", "dir", None, 0o755),
    ("etc/passwd", "file", b"root\n", 0o644), ("run", "dir", None, 0o755),
    ("run/lock", "dir", None, 0o755), ("dev", "dir", None, 0o755), ("dev/null", "chr", None, 0o666),
]
TOP_LAYER = [("etc/.wh.passwd", "file", b"", 0o644), ("etc/hostname", "file", b"guest\n", 0o644)]


def _blob(layout: Path, payload: bytes) -> str:
    digest = hashlib.sha256(payload).hexdigest()
    (layout / "blobs" / "sha256").mkdir(parents=True, exist_ok=True)
    (layout / "blobs" / "sha256" / digest).write_bytes(payload)
    return "sha256:" + digest


def _oci_layout(root: Path, layers=(BASE_LAYER, TOP_LAYER), architecture="amd64") -> tuple[Path, str]:
    layout = root / "layout"
    config = _blob(layout, json.dumps({"os": "linux", "architecture": architecture,
                                       "config": {"Env": ["PATH=/usr/bin"]}}).encode())
    manifest = {"schemaVersion": 2, "config": {"digest": config},
                "layers": [{"mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
                            "digest": _blob(layout, _tar(list(layer)))} for layer in layers]}
    digest = _blob(layout, json.dumps(manifest).encode())
    return layout, f"registry.example/project@{digest}"


@pytest.fixture(autouse=True)
def _removable_tmp(tmp_path: Path):
    """Sealed rootfs trees are read-only; reopen them so pytest can delete its basetemp."""
    yield
    for directory, dirs, _files in os.walk(tmp_path):
        for name in dirs:
            path = os.path.join(directory, name)
            if not os.path.islink(path):
                os.chmod(path, 0o700)


@pytest.fixture
def store_image(tmp_path: Path) -> tuple[Path, str]:
    layout, image = _oci_layout(tmp_path)
    store = tmp_path / "store"
    image_store.import_oci_layout(store, image, layout)
    return store, image


def _rootfs(store: Path, image: str) -> Path:
    return store / "rootfs" / image.rsplit("@sha256:", 1)[1]


def _rewrite_rootfs(store: Path, image: str, edit) -> None:
    rootfs = _rootfs(store, image)
    image_store._set_writable(rootfs, True)
    edit(rootfs)
    image_store._set_writable(rootfs, False)


def _rerecord(store: Path, image: str, **fields: object) -> None:
    path = store / "records" / (image.rsplit("@sha256:", 1)[1] + ".json")
    record = {**json.loads(path.read_bytes()), **fields}
    path.chmod(0o600)
    path.write_bytes(canonical_json_bytes(record))


# --- image store -------------------------------------------------------------------

def test_import_seals_a_read_only_rootfs_with_empty_profile_mount_points(store_image):
    store, image = store_image
    rootfs = _rootfs(store, image)

    assert ({name: sorted(os.listdir(rootfs / name)) for name in image_store.MOUNT_POINTS},
            os.stat(rootfs).st_mode & 0o777, os.access(rootfs / "etc" / "hostname", os.W_OK)) == (
        {name: [] for name in image_store.MOUNT_POINTS}, 0o555, False)


def test_import_pins_the_spawner_executables_through_image_symlinks(store_image):
    store, image = store_image
    record = image_store._read_record(store / "records" / (image.rsplit("@sha256:", 1)[1] + ".json"), image)

    assert [(pin["path"], pin["resolved"]) for pin in record["executable_pins"]["executables"]] == [
        ("/bin/sh", "/usr/bin/dash"), ("/usr/bin/env", "/usr/bin/env"), ("/usr/bin/setsid", "/usr/bin/setsid")]


def test_import_applies_whiteouts_and_drops_setuid_bits_and_devices(store_image):
    rootfs = _rootfs(*store_image)

    assert ((rootfs / "etc" / "passwd").exists(), (rootfs / "etc" / "hostname").read_text(),
            os.stat(rootfs / "usr" / "bin" / "su").st_mode & 0o7000, os.listdir(rootfs / "dev")) == (
        False, "guest\n", 0, [])


def test_import_runs_once_per_digest(store_image, tmp_path):
    store, image = store_image
    before = os.stat(_rootfs(store, image)).st_ino
    shutil.rmtree(tmp_path / "layout")

    image_store.import_oci_layout(store, image, tmp_path / "layout")

    assert os.stat(_rootfs(store, image)).st_ino == before


def test_import_refuses_a_layout_blob_that_differs_from_its_digest(tmp_path):
    layout, image = _oci_layout(tmp_path)
    [layer] = [path for path in (layout / "blobs" / "sha256").iterdir() if path.stat().st_size > 200][:1]
    layer.write_bytes(layer.read_bytes() + b"x")

    with pytest.raises(image_store.ImageStoreError, match="does not match its digest"):
        image_store.import_oci_layout(tmp_path / "store", image, layout)


def test_import_refuses_an_image_without_the_pinned_executables(tmp_path):
    layout, image = _oci_layout(tmp_path, layers=([("etc", "dir", None, 0o755)],))

    with pytest.raises(image_store.ImageStoreError, match="/bin/sh is absent"):
        image_store.import_oci_layout(tmp_path / "store", image, layout)


def _host_secret(tmp_path: Path) -> Path:
    secret = tmp_path / "host-secret"
    secret.write_text("HOST SECRET\n")
    secret.chmod(0o600)
    return secret


@pytest.mark.parametrize("linkname", ["absolute", "parent"])
def test_import_refuses_a_hardlink_to_a_host_file(tmp_path, linkname):
    secret = _host_secret(tmp_path)
    target = str(secret) if linkname == "absolute" else "../../../host-secret"
    layout, image = _oci_layout(tmp_path, layers=(BASE_LAYER, [("etc/stolen", "hardlink", target, 0o644)]))

    with pytest.raises(image_store.ImageStoreError):
        image_store.import_oci_layout(tmp_path / "store", image, layout)

    assert (os.stat(secret).st_nlink, os.stat(secret).st_mode & 0o777) == (1, 0o600)


def test_import_refuses_a_member_written_through_a_symlink_to_the_host(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    layout, image = _oci_layout(tmp_path, layers=(
        BASE_LAYER, [("escape", "symlink", str(outside), 0o777), ("escape/planted", "file", b"x", 0o644)]))

    with pytest.raises(image_store.ImageStoreError):
        image_store.import_oci_layout(tmp_path / "store", image, layout)

    assert list(outside.iterdir()) == []


def test_import_keeps_a_hardlink_between_image_files(tmp_path):
    layout, image = _oci_layout(tmp_path, layers=(BASE_LAYER, [("usr/bin/env2", "hardlink", "usr/bin/env", 0o755)]))

    image_store.import_oci_layout(tmp_path / "store", image, layout)

    assert (_rootfs(tmp_path / "store", image) / "usr" / "bin" / "env2").read_bytes() == b"#!env\n"


@pytest.mark.parametrize("whiteout", ["etc/.wh..", "etc/.wh...", ".wh...", ".wh."])
def test_import_refuses_a_whiteout_of_dot_names(tmp_path, whiteout):
    layout, image = _oci_layout(tmp_path, layers=(BASE_LAYER, [(whiteout, "file", b"", 0o644)]))
    sentinel = tmp_path / "store" / "staging" / "sentinel"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text("kept")

    with pytest.raises(image_store.ImageStoreError, match="whiteout"):
        image_store.import_oci_layout(tmp_path / "store", image, layout)

    assert sentinel.read_text() == "kept"


def test_import_refuses_a_manifest_for_another_platform(tmp_path):
    layout, image = _oci_layout(tmp_path, architecture="arm64")

    with pytest.raises(image_store.ImageStoreError, match="linux/amd64"):
        image_store.import_oci_layout(tmp_path / "store", image, layout)


def test_import_refuses_a_malformed_manifest_with_a_coded_error(tmp_path):
    layout = tmp_path / "layout"
    digest = _blob(layout, json.dumps({"schemaVersion": 2}).encode())

    with pytest.raises(image_store.ImageStoreError) as caught:
        image_store.import_oci_layout(tmp_path / "store", f"registry.example/project@{digest}", layout)

    assert caught.value.code == "run_ref_environment_unavailable"


def test_reimport_verifies_the_existing_tree_instead_of_returning_a_stale_record(store_image, tmp_path):
    store, image = store_image
    _rewrite_rootfs(store, image, lambda rootfs: (rootfs / "etc" / "hostname").write_text("x\n"))

    with pytest.raises(image_store.ImageStoreError, match="digest differs"):
        image_store.import_oci_layout(store, image, tmp_path / "layout")


def test_admission_rehash_follows_the_retained_descriptor_not_a_renamed_store_path(store_image, tmp_path):
    store, image = store_image
    sealed = image_store.open_sealed_image(store, image)
    rootfs = _rootfs(store, image)
    try:
        rootfs.rename(rootfs.with_name("moved"))  # same parent: a sealed directory can move
        shutil.copytree(rootfs.with_name("moved"), rootfs, symlinks=True)
        image_store._set_writable(rootfs, True)
        (rootfs / "etc" / "hostname").write_text("swapped\n")
        image_store._set_writable(rootfs, False)

        sealed.rehash()
        with pytest.raises(image_store.ImageStoreError, match="digest differs"):
            image_store.open_sealed_image(store, image)
    finally:
        sealed.close()


def test_admission_refuses_a_tampered_rootfs(store_image):
    store, image = store_image
    _rewrite_rootfs(store, image, lambda rootfs: (rootfs / "etc" / "hostname").write_text("x\n"))

    with pytest.raises(image_store.ImageStoreError) as caught:
        image_store.open_sealed_image(store, image)

    assert caught.value.code == "run_ref_environment_unavailable"


def _resealed_record(store: Path, image: str) -> dict:
    fd = os.open(_rootfs(store, image), os.O_RDONLY | os.O_DIRECTORY)
    try:
        return {"tree_digest": image_store.tree_digest(fd), "executable_pins": image_store.executable_pins(fd)}
    finally:
        os.close(fd)


def test_admission_refuses_a_nonempty_mount_point_even_with_a_matching_record(store_image):
    store, image = store_image
    _rewrite_rootfs(store, image, lambda rootfs: (rootfs / "workspace" / "planted").write_text("x"))
    _rerecord(store, image, **_resealed_record(store, image))

    with pytest.raises(image_store.ImageStoreError, match="mount point /workspace is not empty"):
        image_store.open_sealed_image(store, image)


def test_admission_refuses_executable_pins_that_differ_from_the_record(store_image):
    store, image = store_image
    pins = json.loads(json.dumps(_resealed_record(store, image)["executable_pins"]))
    pins["executables"][0]["sha256"] = "0" * 64
    _rerecord(store, image, executable_pins=pins)

    with pytest.raises(image_store.ImageStoreError, match="pins differ"):
        image_store.open_sealed_image(store, image)


# --- parent program, admission and provisioning ------------------------------------

def _repository(root: Path) -> str:
    root.mkdir()
    git = lambda *args: subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)  # noqa: E731
    git("init", "--quiet")
    git("config", "user.name", "Run Ref Test")
    git("config", "user.email", "run-ref@example.invalid")
    (root / "payload.txt").write_text("baseline\n")
    git("add", "payload.txt")
    git("commit", "--quiet", "-m", "baseline")
    return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True,
                          capture_output=True, text=True).stdout.strip()


PARENT = '''(workflow-lisp (:language "0.1") (:target-dsl "2.38")
  (defmodule controller) (export run)
  (defworkflow candidate-body ((seed Int) (task String)) -> Int (+ seed 41))
  (defworkflow run ((seed Int) (revision String)) -> Int
    (let* ((child (run-ref :source (:repo "REPO" :commit revision)
                    :program (:workflow candidate-body) :inputs (:seed seed :task "t")
                    :policy (:environment :confined :image "IMAGE" :network :none
                             :limits (:wall-seconds 60 :memory-mib 1024 :cpus 1 :pids 64
                                      :workspace-mib 64 :output-mib 8)))))
      (match child ((COMPLETED c) c.result.value) ((FAILED f) f.accounting.attempt_ordinal)))))'''


@pytest.fixture
def world(tmp_path: Path, store_image):
    store, image = store_image
    repository = tmp_path / "repository"
    commit = _repository(repository)
    source = tmp_path / "parent-source"
    source.mkdir()
    (source / "controller.orc").write_text(PARENT.replace("REPO", repository.as_uri()).replace("IMAGE", image))
    typed = compile_typed_program(source / "controller.orc", entry_workflow="controller::run",
                                  source_roots=(source,), workspace_root=source, command_boundaries={})
    program = ClosedProgram.from_artifact(build_closed_program(typed, builder=Builder(typed)).artifact())
    [node] = [node for node in site_nodes(program).values() if node["class"] == "run_ref"]
    config = decode_run_ref_confined_static_config(b64decode(node["config"]))
    parent_run_root = tmp_path / "parent-workspace" / ".orchestrate" / "runs" / "parent-run"
    parent_run_root.mkdir(parents=True)
    return {"store": store, "commit": commit, "program": program, "config": config,
            "repository": repository,
            "inputs": {"seed": 1, "task": "t"}, "run_ref_root": tmp_path / "run-ref",
            "parent_run_root": parent_run_root, "parent_workspace": tmp_path / "parent-workspace",
            "visit": RunRefVisitKey(parent_run_id="parent-run", execution_frame_id="root",
                                    call_frame_id=None, step_id="root.site", visit_count=1)}


def _admit(world, *, request=None, host=HOST):
    config = world["config"]
    record = request if request is not None else confined_child_request(
        config, commit=world["commit"], inputs=world["inputs"])
    return admit_confined_child(config, record, commit=world["commit"], inputs=world["inputs"],
                                parent_program=world["program"], image_store=world["store"], host=host)


def _layout(world, *, ordinal=1, visit=None) -> ConfinedAttemptLayout:
    return confined_attempt_layout(run_ref_root=world["run_ref_root"], parent_run_root=world["parent_run_root"],
                                   visit=visit or world["visit"], attempt_ordinal=ordinal, config=world["config"])


def _provision(world, admission, layout=None):
    return provision_confined_child(admission, layout or _layout(world), run_ref_root=world["run_ref_root"],
                                    parent_run_root=world["parent_run_root"],
                                    parent_workspace=world["parent_workspace"])


def _run(world):
    admission = _admit(world)
    try:
        provisioned = _provision(world, admission)
        value = execute_confined_child(admission, provisioned, run_ref_root=world["run_ref_root"])
        return admission, provisioned, value
    finally:
        admission.close()


@pytest.mark.parametrize(("field", "value", "detail"), [
    ("bwrap", False, "bwrap"), ("systemd_run", False, "systemd_run"),
    ("ptrace_scope", 0, "yama_ptrace_scope"), ("ptrace_scope", None, "yama_ptrace_scope"),
    ("machine", "aarch64", "x86_64"),
])
def test_admission_refuses_a_missing_host_prerequisite(world, field, value, detail):
    with pytest.raises(RunRefRuntimeError) as caught:
        _admit(world, host=replace(HOST, **{field: value}))

    assert (caught.value.code, caught.value.detail) == (
        "run_ref_environment_unavailable", f"host_prerequisite_missing:{detail}")


def test_admission_maps_a_tampered_request_to_escape_rejected(world):
    request = confined_child_request(world["config"], commit=world["commit"], inputs=world["inputs"])
    request["source"]["resolved_commit_sha"] = "f" * 40

    with pytest.raises(RunRefRuntimeError) as caught:
        _admit(world, request=request)

    assert caught.value.code == "run_ref_environment_escape_rejected"


def test_admission_refuses_an_image_absent_from_the_store(world, tmp_path):
    world = {**world, "store": tmp_path / "empty-store"}

    with pytest.raises(RunRefRuntimeError) as caught:
        _admit(world)

    assert caught.value.code == "run_ref_environment_unavailable"


def test_admission_refuses_a_child_with_a_provider_site_until_its_transport_exists(tmp_path):
    from tests.test_workflow_lisp_run_ref_workflow_program import _built, _confined, _confined_site

    program = _built(_confined(tmp_path))
    _node, config = _confined_site(program)
    world = {"commit": "c" * 40, "inputs": {"seed": 1, "task": "t"}, "store": tmp_path / "store",
             "config": config, "program": program}

    with pytest.raises(RunRefRuntimeError) as caught:
        _admit(world)

    assert caught.value.code == "run_ref_provider_transport_unavailable"
    assert not world["store"].exists()


def test_admission_admits_a_child_whose_effects_are_commands(tmp_path, store_image):
    from tests.test_workflow_lisp_run_ref_workflow_program import DIGEST, _built, _confined, _confined_site

    store, image = store_image
    program = _built(_confined(tmp_path / "source", (
        "(let* ((verdict (provider-result providers.review :prompt prompts.base\n"
        "                      :inputs (task) :returns Verdict)))\n"
        "      (if verdict.ok (let* ((n (bump seed)) (box (fetch n))) box.n) 0))",
        "(let* ((n (bump seed)) (box (fetch n))) box.n)"),
        (":network :model-only", ":network :none"), (f"registry.example/project@sha256:{DIGEST}", image)))
    _node, config = _confined_site(program)
    world = {"commit": "c" * 40, "inputs": {"seed": 1, "task": "t"}, "store": store,
             "config": config, "program": program}

    admission = _admit(world)
    admission.close()

    assert admission.program.digest == config.program.child_program_digest


def test_each_activation_and_attempt_gets_its_own_clone_and_control_root(world):
    other_visit = replace(world["visit"], visit_count=2)
    layouts = [_layout(world), _layout(world, ordinal=2), _layout(world, visit=other_visit)]
    admission = _admit(world)
    try:
        clones = [_provision(world, admission, layout).layout.workspace for layout in layouts]
    finally:
        admission.close()

    assert (len({layout.workspace for layout in layouts}), len({layout.child_root for layout in layouts}),
            all((clone / "payload.txt").read_text() == "baseline\n" for clone in clones),
            all(layout.child_root.parent == world["parent_run_root"] / "run-ref-children" for layout in layouts)) == (
        3, 3, True, True)


def _overlaps(world, tmp_path):
    layout = _layout(world)
    return {
        "control-root-in-clone": (replace(layout, child_root=layout.workspace / "control"), {}),
        "clone-in-control-root": (replace(layout, workspace=layout.child_root / "clone"), {}),
        "parent-run-in-clone": (layout, {"parent_run_root": layout.workspace / "parent"}),
        "parent-workspace-in-clone": (layout, {"parent_workspace": layout.workspace / "checkout"}),
    }


@pytest.mark.parametrize("case", ["control-root-in-clone", "clone-in-control-root",
                                  "parent-run-in-clone", "parent-workspace-in-clone"])
def test_overlapping_clone_and_authority_roots_are_refused(world, tmp_path, case):
    layout, roots = _overlaps(world, tmp_path)[case]
    roots = {"parent_run_root": world["parent_run_root"], "parent_workspace": world["parent_workspace"], **roots}

    with pytest.raises(RunRefRuntimeError) as caught:
        refuse_overlapping_roots(layout, **roots)

    assert caught.value.code == "run_ref_environment_escape_rejected"


def test_a_run_ref_root_aliased_into_the_control_root_is_refused_before_cloning(world):
    layout = _layout(world)
    alias = world["parent_run_root"] / "run-ref-children" / layout.child_run_id
    alias.mkdir(parents=True)
    world["run_ref_root"].symlink_to(alias)
    admission = _admit(world)
    try:
        with pytest.raises(RunRefRuntimeError) as caught:
            _provision(world, admission, layout)
    finally:
        admission.close()

    assert (caught.value.code, list(alias.iterdir())) == ("run_ref_environment_escape_rejected", [])


def test_a_commit_absent_from_the_repository_is_refused_without_a_control_root(world):
    world = {**world, "commit": "b" * 40}
    admission = _admit(world)
    try:
        with pytest.raises(RunRefSourceRefusal) as caught:
            _provision(world, admission)
    finally:
        admission.close()

    assert (caught.value.code, os.path.lexists(_layout(world).child_root)) == ("trial_source_unresolvable", False)


def test_an_orphan_clone_without_its_control_root_is_refused_and_kept(world):
    """The control root (named by the child run id) exists before any clone: a bare clone is not ours."""
    layout = _layout(world)
    layout.workspace.mkdir(parents=True)
    (layout.workspace / "partial").write_text("not bound to this child\n")
    admission = _admit(world)
    try:
        with pytest.raises(RunRefRuntimeError) as caught:
            _provision(world, admission, layout)
    finally:
        admission.close()

    assert (caught.value.code, (layout.workspace / "partial").read_text(), os.path.lexists(layout.child_root)) == (
        "run_ref_evidence_invalid", "not bound to this child\n", False)


def test_an_interrupted_provisioning_is_discarded_through_its_control_root(world, monkeypatch):
    from orchestrator.workflow.run_ref import confinement

    layout = _layout(world)
    real = confinement.materialize_confined_source

    def crash_after_cloning(*args, **kwargs):
        real(*args, **kwargs)
        raise KeyboardInterrupt  # a crash between cloning and the recipe

    monkeypatch.setattr(confinement, "materialize_confined_source", crash_after_cloning)
    admission = _admit(world)
    try:
        with pytest.raises(KeyboardInterrupt):
            _provision(world, admission, layout)
    finally:
        admission.close()
    monkeypatch.setattr(confinement, "materialize_confined_source", real)

    _admission, provisioned, value = _run(world)

    assert (value, sorted(path.name for path in provisioned.layout.workspace.iterdir())) == (
        42, [".git", "payload.txt"])


@pytest.mark.parametrize("published", ["run.json", "run.lock"])
def test_a_torn_recipe_next_to_published_authority_refuses_and_keeps_the_clone(world, published):
    layout = _layout(world)
    layout.workspace.mkdir(parents=True)
    (layout.workspace / "kept").write_text("guest work\n")
    layout.child_root.mkdir(parents=True)
    (layout.child_root / "child-recipe.json").write_bytes(b'{"schema_version": "run_ref_conf')
    (layout.child_root / published).write_bytes(b"{}")
    admission = _admit(world)
    try:
        with pytest.raises(RunRefRuntimeError) as caught:
            _provision(world, admission, layout)
    finally:
        admission.close()

    assert (caught.value.code, (layout.workspace / "kept").read_text()) == ("run_ref_evidence_invalid", "guest work\n")


def test_provisioning_refuses_a_clone_beyond_the_profile_entry_bound(world, monkeypatch):
    from orchestrator.workflow.run_ref import confinement

    monkeypatch.setattr(confinement, "MAX_CHECKPOINT_ENTRIES", 0)
    admission = _admit(world)
    try:
        with pytest.raises(RunRefRuntimeError) as caught:
            _provision(world, admission)
    finally:
        admission.close()

    assert (caught.value.code, caught.value.detail) == (
        "run_ref_environment_unavailable", "clone_exceeds_entry_bound")


def test_provisioning_refuses_a_clone_beyond_the_profile_depth_bound(world):
    from orchestrator.workflow.run_ref.checkpoint import MAX_TREE_DEPTH

    repository = world["repository"]
    current = repository
    for index in range(MAX_TREE_DEPTH + 1):
        current = current / f"deep-{index}"
        current.mkdir()
    (current / "leaf.txt").write_text("depth bound\n")
    subprocess.run(["git", "-C", str(repository), "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repository), "commit", "--quiet", "-m", "deep tree"],
                   check=True, capture_output=True)
    world["commit"] = subprocess.run(["git", "-C", str(repository), "rev-parse", "HEAD"], check=True,
                                     capture_output=True, text=True).stdout.strip()
    admission = _admit(world)
    try:
        with pytest.raises(RunRefRuntimeError) as caught:
            _provision(world, admission)
    finally:
        admission.close()

    layout = _layout(world)
    assert (caught.value.code, caught.value.detail,
            os.path.lexists(layout.child_root / "child-recipe.json")) == (
        "run_ref_environment_unavailable", "clone_exceeds_depth_bound", False)


def test_image_paths_resolve_through_one_public_walk_beneath_the_image_root(store_image):
    from orchestrator.workflow.evaluated import interpreters

    sealed = image_store.open_sealed_image(*store_image)
    try:
        resolved = image_store.resolve_in_root(sealed.root_fd, "/bin/sh")
    finally:
        sealed.close()

    assert (resolved, interpreters.resolve_image_path is image_store.resolve_in_root) == ("/usr/bin/dash", True)


@pytest.mark.parametrize("recipe", [None, b'{"schema_version": "run_ref_conf'])
def test_a_control_root_without_a_complete_recipe_is_discarded_and_reprovisioned(world, recipe):
    layout = _layout(world)
    layout.workspace.mkdir(parents=True)
    layout.child_root.mkdir(parents=True)
    if recipe is not None:
        (layout.child_root / "child-recipe.json").write_bytes(recipe)

    _admission, provisioned, value = _run(world)

    assert (value, (provisioned.layout.child_root / "child-recipe.json").read_bytes()) == (
        42, provisioned.recipe_bytes)


# --- child authority outside the clone, run, resume and terminal witness -----------

def test_child_run_authority_lives_only_in_external_control_root(world):
    _admission, provisioned, _value = _run(world)
    clone, root = provisioned.layout.workspace, provisioned.layout.child_root

    in_clone = sorted(path.name for path in clone.rglob("*") if path.name in REJECTED_IN_CLONE)

    assert (in_clone, sorted(path.name for path in root.iterdir())) == (
        [], ["child-recipe.json", "closed_program.json", "image-inventory.json", "memo.jsonl", "run.json", "run.lock", "state.json"])


def test_external_control_root_memo_carries_the_terminal_value(world):
    _admission, provisioned, value = _run(world)

    _header, _program, memo = _captured_child_authority(provisioned.layout.child_root)

    assert (value, reduce_memo(memo, {}).terminal.data["value"]) == (42, 42)


def test_result_file_alone_is_not_child_authority(tmp_path):
    run_root = tmp_path / "control" / "forged"
    run_root.mkdir(parents=True)
    (run_root / "result.json").write_text('{"__result__": 42}', encoding="utf-8")

    with pytest.raises(OSError):
        _captured_child_authority(run_root)


def _witness(world, admission, provisioned, value):
    layout = provisioned.layout
    header = confined_child_header(program=admission.program, child_run_id=layout.child_run_id,
                                   child_root=layout.child_root, clone_root=layout.workspace,
                                   run_ref_root=world["run_ref_root"], inputs=admission.inputs)
    descriptor = world["config"].result_descriptor["envelope"]["fields"][0]["type"]
    return validate_confined_child_terminal(child_root=layout.child_root, clone_root=layout.workspace,
                                            expected_header=header, recipe_bytes=provisioned.recipe_bytes,
                                            value_descriptor=descriptor, direct_value=value,
                                            image_digest=admission.image.record["tree_digest"])


def test_terminal_witness_replays_the_committed_memo_from_the_control_root(world):
    admission, provisioned, value = _run(world)

    checked, header_path, digest = _witness(world, admission, provisioned, value)

    assert (checked, header_path, digest.startswith("sha256:")) == (
        42, provisioned.layout.child_root / "run.json", True)


def _tamper_memo_value(root: Path) -> None:
    memo = root / "memo.jsonl"
    record = json.loads(memo.read_bytes())
    record["value"] = 7
    memo.write_bytes(canonical_json_bytes(record) + b"\n")


@pytest.mark.parametrize(("tamper", "reason"), [
    ("memo-value", "replayed halt and direct result disagree"),
    ("recipe", "recipe differs"),
    ("direct-value", "replayed halt and direct result disagree"),
])
def test_terminal_witness_refuses_tampered_authority(world, tamper, reason):
    admission, provisioned, value = _run(world)
    root = provisioned.layout.child_root
    if tamper == "memo-value":
        _tamper_memo_value(root)
    elif tamper == "recipe":
        provisioned = replace(provisioned, recipe={**provisioned.recipe, "commit": "0" * 40})
    else:
        value = 43

    with pytest.raises(ValueError, match=reason):
        _witness(world, admission, provisioned, value)


def test_pure_child_resumes_in_its_control_root_without_a_new_clone(world):
    _admission, provisioned, _value = _run(world)
    clone_identity = os.stat(provisioned.layout.workspace).st_ino
    (provisioned.layout.child_root / "memo.jsonl").write_bytes(b"")  # crash before the terminal

    admission, resumed, value = _run(world)

    assert (value, os.stat(resumed.layout.workspace).st_ino, resumed.recipe,
            _witness(world, admission, resumed, value)[0]) == (42, clone_identity, provisioned.recipe, 42)


def test_resume_refuses_a_clone_that_differs_from_its_baseline(world):
    _admission, provisioned, _value = _run(world)
    (provisioned.layout.workspace / "payload.txt").write_text("edited\n")

    with pytest.raises(RunRefRuntimeError) as caught:
        _run(world)

    assert caught.value.code == "run_ref_environment_changed"


def test_resume_refuses_image_pins_that_drifted_since_admission(world):
    _admission, provisioned, _value = _run(world)
    recipe_path = provisioned.layout.child_root / "child-recipe.json"
    recipe = json.loads(recipe_path.read_bytes())
    recipe["admission"]["image"]["tree_digest"] = "sha256:" + "0" * 64
    recipe_path.write_bytes(canonical_json_bytes(recipe))

    with pytest.raises(RunRefRuntimeError) as caught:
        _run(world)

    assert caught.value.code == "run_ref_environment_changed"


def test_confined_revision_has_no_setup_and_accounting_charges_no_setup(world):
    _admission, provisioned, _value = _run(world)

    accounting = confined_child_accounting(provisioned.layout, attempt_ordinal=1,
                                           terminal_status="completed", elapsed_ms=5)

    assert (provisioned.source.repository_revision_id.authored_setup_identity,
            accounting["setup_ms"], accounting["compile_ms"]) == ("none", 0, 0)


def test_confinement_profile_is_not_a_registered_isolation_backend():
    with pytest.raises(ProviderIsolationBackendUnavailable):
        get_provider_isolation_backend("run_ref_confinement.v1")


def test_retained_image_inventory_reconstructs_live_file_and_directory_rows(tmp_path):
    layout, name = _oci_layout(tmp_path)
    store = tmp_path / 'store'
    image_store.import_oci_layout(store, name, layout)
    image = image_store.open_sealed_image(store, name)
    try:
        from orchestrator.workflow.evaluated.confined_dispatch import _image_row
        expected = {path: _image_row(image, path) for path in ('/bin/sh', '/usr/bin', '/etc/hostname')}
        payload = image_store.capture_inventory(image)
        admission = dict(image.record)
    finally:
        image.close()
    store.rename(tmp_path / 'withdrawn-store')
    inventory = image_store.validate_inventory(payload, admission)
    assert {path: inventory.implementation_row(path) for path in expected} == expected
    assert inventory.interpreter_pin('/bin/sh') == {
        'image': admission['tree_digest'], 'path': '/bin/sh', 'resolved': '/usr/bin/dash',
        'digest': 'sha256:' + hashlib.sha256(b'#!dash\n').hexdigest()}


@pytest.mark.parametrize('change', ['noncanonical', 'missing', 'target', 'order', 'parent', 'shape', 'admission'])
def test_retained_image_inventory_rejects_tamper(tmp_path, change):
    layout, name = _oci_layout(tmp_path)
    store = tmp_path / 'store'
    admission = image_store.import_oci_layout(store, name, layout)
    image = image_store.open_sealed_image(store, name)
    try:
        payload = image_store.capture_inventory(image)
    finally:
        image.close()
    rows = json.loads(payload)
    if change == 'noncanonical':
        payload += b'\n'
    elif change == 'admission':
        admission = {**admission, 'tree_digest': 'sha256:' + '0' * 64}
    else:
        if change == 'missing':
            rows.pop()
        elif change == 'target':
            next(row for row in rows if row[1] == 'symlink')[2] = '/foreign'
        elif change == 'order':
            rows.reverse()
        elif change == 'parent':
            rows[0][0] = 'missing/child'
        elif change == 'shape':
            next(row for row in rows if row[1] == 'file')[3] = True
        payload = json.dumps(rows, separators=(',', ':')).encode()
        # Shape/parent/order must fail even when a digest is internally self-consistent.
        if change in {'shape', 'parent', 'order'}:
            admission = {**admission, 'tree_digest': 'sha256:' + hashlib.sha256(payload).hexdigest()}
    with pytest.raises(image_store.ImageStoreError):
        image_store.validate_inventory(payload, admission)
