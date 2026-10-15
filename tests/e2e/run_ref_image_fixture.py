"""OCI image layout fixture the run-ref image store imports (Task 6a e2e).

How it is produced: the Task 1 sealed rootfs (`run_ref_fixtures.IMAGE_RECORD`,
a Debian python image with `/bin/sh`, `/usr/bin/env`, `/usr/bin/setsid` and
`python3`) is packed into one uncompressed OCI layer with a config and an
image manifest in a fresh OCI layout directory; the image reference pins the
manifest digest. `orchestrator.workflow.run_ref.image_store.import_oci_layout`
then imports it into a store, the same path a real installation uses.

Caching: by default the layout and the store live under a pytest temporary
directory for the module (the store is made writable again at teardown so
pytest can remove it). Set `RUN_REF_E2E_IMAGE_STORE=<dir>` to keep the store
across sessions (opt-in); the import is skipped when the record is present.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tarfile
from pathlib import Path

import pytest

from orchestrator.workflow.run_ref.image_store import SealedImage, import_oci_layout, open_sealed_image
from tests.e2e.run_ref_fixtures import IMAGE_RECORD, skip_unless_user_manager

REPOSITORY = "example.invalid/run-ref-holder-fixture"


def _blob(layout: Path, payload: bytes) -> dict:
    digest = hashlib.sha256(payload).hexdigest()
    (layout / "blobs" / "sha256" / digest).write_bytes(payload)
    return {"digest": f"sha256:{digest}", "size": len(payload)}


def build_oci_layout(rootfs: Path, layout: Path) -> str:
    """Pack `rootfs` into a one-layer OCI layout; return the digest-pinned image reference."""
    (layout / "blobs" / "sha256").mkdir(parents=True)
    layer_path = layout / "layer.tar"
    with tarfile.open(layer_path, "w", format=tarfile.PAX_FORMAT) as archive:
        for name in sorted(os.listdir(rootfs)):
            archive.add(rootfs / name, arcname=name)
    layer = _blob(layout, layer_path.read_bytes())
    layer_path.unlink()
    config = _blob(layout, json.dumps({
        "architecture": "amd64", "os": "linux",
        "config": {"Env": ["PATH=/usr/local/bin:/usr/bin:/bin", "LANG=C.UTF-8"]},
        "rootfs": {"type": "layers", "diff_ids": [layer["digest"]]}}).encode())
    manifest = _blob(layout, json.dumps({
        "schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "config": {"mediaType": "application/vnd.oci.image.config.v1+json", **config},
        "layers": [{"mediaType": "application/vnd.oci.image.layer.v1.tar", **layer}]}).encode())
    (layout / "oci-layout").write_text('{"imageLayoutVersion": "1.0.0"}')
    (layout / "index.json").write_text(json.dumps({"schemaVersion": 2, "manifests": [
        {"mediaType": "application/vnd.oci.image.manifest.v1+json", **manifest}]}))
    return f"{REPOSITORY}@{manifest['digest']}"


def _writable(root: Path) -> None:
    for directory, dirs, _files in os.walk(root):
        for name in dirs:
            path = Path(directory, name)
            if not path.is_symlink():
                path.chmod(stat.S_IMODE(path.lstat().st_mode) | 0o700)
    root.chmod(0o700)


@pytest.fixture(scope="module")
def sealed_image(tmp_path_factory) -> SealedImage:
    skip_unless_user_manager()
    if not IMAGE_RECORD.exists():
        pytest.skip(f"Task 1 image record {IMAGE_RECORD} absent; import it as the feasibility README describes")
    source = Path(json.loads(IMAGE_RECORD.read_text())["rootfs"])
    work = tmp_path_factory.mktemp("run-ref-image")
    cached = os.getenv("RUN_REF_E2E_IMAGE_STORE")
    store = Path(cached) if cached else work / "store"
    image = build_oci_layout(source, work / "layout")
    import_oci_layout(store, image, work / "layout")
    sealed = open_sealed_image(store, image)
    yield sealed
    sealed.close()
    if not cached:
        _writable(store)
