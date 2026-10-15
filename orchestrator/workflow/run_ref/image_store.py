"""Sealed content-addressed image store for the `run_ref_confinement.v1` profile.

Installation time, never inside a workflow run: `import_oci_layout` imports one
digest-pinned image from an OCI image layout directory into
`<store>/rootfs/<digest-hex>` once per digest. Every blob is verified against
its digest, layers are applied with whiteouts, device and FIFO members are
skipped, setuid bits are cleared, the empty profile mount points are created,
the tree is sealed read-only and a canonical record pins its tree digest and
the image executables the spawner needs.

Admission: `open_sealed_image` opens the rootfs no-follow, rehashes it through
that retained directory descriptor, checks the mount points and executable
pins through it, and returns it; the launch binds the same descriptor
(`--ro-bind-fd`), so swapping the store path after the rehash changes nothing.
Every refusal is `run_ref_environment_unavailable`.

Dependencies: the local filesystem under `<store>` (trusted, owned by the
installing user) and, at import, an OCI layout directory. No network.
"""

from __future__ import annotations

from dataclasses import dataclass
import errno
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import posixpath
import shutil
import stat
import tarfile
from typing import Any

from orchestrator._common.io_atomic import durable_atomic_write

from .contracts import CONFINED_IMAGE_RE, canonical_json_bytes


RECORD_SCHEMA = "run_ref_image_record.v1"
PINS_SCHEMA = "run_ref_image_executable_pins.v1"
PLATFORM = {"os": "linux", "architecture": "amd64"}
MOUNT_POINTS = ("dev", "proc", "result", "run", "tmp", "workspace")
PINNED_EXECUTABLES = ("/bin/sh", "/usr/bin/env", "/usr/bin/setsid")
_LAYER_MODES = {
    "application/vnd.oci.image.layer.v1.tar+gzip": "r:gz",
    "application/vnd.docker.image.rootfs.diff.tar.gzip": "r:gz",
    "application/vnd.oci.image.layer.v1.tar": "r:",
}
_SYMLINK_HOPS = 40
_CHUNK = 1024 * 1024


class ImageStoreError(ValueError):
    """The image cannot be imported or admitted."""

    code = "run_ref_environment_unavailable"

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(f"{self.code}: {detail}")


@dataclass
class SealedImage:
    """An admitted rootfs: the retained descriptor and its canonical record."""

    root_fd: int
    record: dict[str, Any]

    def rehash(self) -> None:
        """Rehash through the retained descriptor (done again at every holder launch)."""
        if tree_digest(self.root_fd) != self.record["tree_digest"]:
            raise ImageStoreError("sealed rootfs digest differs from its record")

    def close(self) -> None:
        if self.root_fd >= 0:
            os.close(self.root_fd)
            self.root_fd = -1


def _digest_hex(image: str) -> str:
    if not isinstance(image, str) or CONFINED_IMAGE_RE.fullmatch(image) is None:
        raise ImageStoreError("image must be a repository pinned by a sha256 digest")
    return image.rsplit("@sha256:", 1)[1]


def _blob(layout: Path, digest: str) -> bytes:
    algorithm, _, hex_digest = digest.partition(":")
    if algorithm != "sha256" or len(hex_digest) != 64 or set(hex_digest) - set("0123456789abcdef"):
        raise ImageStoreError("layout blob digest is not sha256")
    try:
        payload = (layout / "blobs" / "sha256" / hex_digest).read_bytes()
    except OSError as exc:
        raise ImageStoreError(f"layout blob {digest} is missing") from exc
    if hashlib.sha256(payload).hexdigest() != hex_digest:
        raise ImageStoreError(f"layout blob {digest} does not match its digest")
    return payload


def _platform_manifest(layout: Path, digest: str) -> tuple[str, dict[str, Any]]:
    document = json.loads(_blob(layout, digest))
    if "manifests" not in document:
        return digest, document
    rows = [row for row in document["manifests"]
            if {key: row.get("platform", {}).get(key) for key in PLATFORM} == PLATFORM]
    if len(rows) != 1:
        raise ImageStoreError("image index has no single linux/amd64 manifest")
    manifest = json.loads(_blob(layout, rows[0]["digest"]))
    if "manifests" in manifest:
        raise ImageStoreError("nested image index is not supported")
    return rows[0]["digest"], manifest


def _inside(root: Path, path: str) -> bool:
    real, base = os.path.realpath(path), os.path.realpath(root)
    return os.path.commonpath([real, base]) == base


def _whiteout(rootfs: Path, parent: str, name: str) -> None:
    directory = rootfs / parent
    if not _inside(rootfs, str(directory)):
        raise ImageStoreError("layer whiteout escapes the rootfs")
    if name == ".wh..wh..opq":
        for child in directory.iterdir() if directory.is_dir() else ():
            _remove(child)
        return
    victim_name = name[len(".wh."):]
    if victim_name in {"", ".", ".."}:
        raise ImageStoreError("layer whiteout names no entry")
    victim = directory / victim_name
    if os.path.lexists(victim):
        _remove(victim)


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def _require_image_hardlink(rootfs: Path, member: tarfile.TarInfo) -> None:
    """A hard link may only name a regular file this image already extracted.

    The "tar" extraction filter checks member names but not hard-link targets, so an
    absolute or `../` link name would otherwise link a host file into the rootfs.
    """
    link = member.linkname
    if link.startswith("/") or posixpath.normpath(link).split("/")[0] == "..":
        raise ImageStoreError(f"layer hard link leaves the rootfs: {member.name}")
    target = os.path.realpath(rootfs / link)
    if not _inside(rootfs, target) or not os.path.lexists(target) or not stat.S_ISREG(os.lstat(target).st_mode):
        raise ImageStoreError(f"layer hard link does not name an image file: {member.name}")


def _apply_layer(rootfs: Path, blob: bytes, media_type: str) -> None:
    mode = _LAYER_MODES.get(media_type)
    if mode is None:
        raise ImageStoreError(f"unsupported layer media type {media_type}")
    try:
        with tarfile.open(fileobj=io.BytesIO(blob), mode=mode) as archive:
            members = []
            for member in archive.getmembers():
                name = posixpath.normpath(member.name.lstrip("/"))
                if name == ".." or name.startswith("../"):
                    raise ImageStoreError("layer member escapes the rootfs")
                parent, leaf = posixpath.split(name)
                if leaf.startswith(".wh."):
                    _whiteout(rootfs, parent, leaf)
                elif not (member.ischr() or member.isblk() or member.isfifo()):
                    if member.isdir():
                        member.mode |= 0o700
                    members.append(member)
            for member in members:
                if member.islnk():
                    _require_image_hardlink(rootfs, member)
                # The "tar" filter refuses names and symlinks leaving the rootfs and clears
                # setuid/setgid/sticky and group/other write bits.
                archive.extract(member, rootfs, filter="tar")
    except (tarfile.TarError, gzip.BadGzipFile, OSError) as exc:
        raise ImageStoreError(f"layer cannot be applied: {exc}") from exc
    for directory, dirs, _files in os.walk(rootfs):
        for name in dirs:
            path = os.path.join(directory, name)
            if not os.path.islink(path):
                os.chmod(path, stat.S_IMODE(os.lstat(path).st_mode) | 0o700)


def _prepare_mount_points(rootfs: Path) -> None:
    for name in MOUNT_POINTS:
        path = rootfs / name
        if os.path.lexists(path):
            _remove(path)
        path.mkdir(mode=0o755)


def _set_writable(root: Path, writable: bool) -> None:
    """Seal a tree read-only, or reopen a stale one for removal."""
    for directory, dirs, files in os.walk(root):
        for name in dirs + files:
            path = os.path.join(directory, name)
            info = os.lstat(path)
            if stat.S_ISLNK(info.st_mode):
                continue
            mode = stat.S_IMODE(info.st_mode)
            if writable:
                os.chmod(path, mode | (0o700 if stat.S_ISDIR(info.st_mode) else 0o200))
            else:
                os.chmod(path, mode & ~0o222)
    os.chmod(root, 0o755 if writable else 0o555)


def _open_beneath(dir_fd: int, name: str, flags: int) -> int:
    return os.open(name, flags | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dir_fd)


def _file_digest(fd: int) -> str:
    digest = hashlib.sha256()
    while chunk := os.read(fd, _CHUNK):
        digest.update(chunk)
    return digest.hexdigest()


def _walk(dir_fd: int, prefix: str, rows: list[list[Any]]) -> None:
    with os.scandir(dir_fd) as entries:
        names = sorted(entry.name for entry in entries)
    subdirectories = []
    for name in names:
        relative = prefix + name
        info = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
        if stat.S_ISLNK(info.st_mode):
            rows.append([relative, "symlink", os.readlink(name, dir_fd=dir_fd)])
        elif stat.S_ISDIR(info.st_mode):
            rows.append([relative, "dir", stat.S_IMODE(info.st_mode)])
            subdirectories.append(name)
        elif stat.S_ISREG(info.st_mode):
            fd = _open_beneath(dir_fd, name, os.O_RDONLY | os.O_NONBLOCK)
            try:
                opened = os.fstat(fd)
                if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                    raise ImageStoreError(f"rootfs entry changed while hashing: {relative}")
                rows.append([relative, "file", stat.S_IMODE(opened.st_mode), opened.st_size, _file_digest(fd)])
            finally:
                os.close(fd)
        else:
            raise ImageStoreError(f"rootfs holds a special file: {relative}")
    for name in subdirectories:
        fd = _open_beneath(dir_fd, name, os.O_RDONLY | os.O_DIRECTORY)
        try:
            _walk(fd, prefix + name + "/", rows)
        finally:
            os.close(fd)


def tree_digest(root_fd: int) -> str:
    """Canonical digest of the tree beneath `root_fd`, never following a symlink."""
    rows: list[list[Any]] = []
    _walk(root_fd, "", rows)
    return "sha256:" + hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()


def resolve_in_root(root_fd: int, path: str) -> str:
    """Resolve absolute guest `path` as the guest would, by text, beneath the image root `root_fd`.

    No host symlink is followed; absolute link targets restart at the image root.
    Returns the absolute guest path; `OSError` when a component is absent or loops.
    """
    pending = [part for part in path.split("/") if part]
    resolved: list[str] = []
    hops = _SYMLINK_HOPS
    while pending:
        part = pending.pop(0)
        if part == ".":
            continue
        if part == "..":
            resolved = resolved[:-1]
            continue
        candidate = "/".join([*resolved, part])
        info = os.stat(candidate, dir_fd=root_fd, follow_symlinks=False)
        if not stat.S_ISLNK(info.st_mode):
            resolved.append(part)
            continue
        hops -= 1
        if hops < 0:
            raise OSError(errno.ELOOP, f"image path {path} has a symlink loop")
        target = os.readlink(candidate, dir_fd=root_fd)
        if target.startswith("/"):
            resolved = []
        pending = [item for item in target.split("/") if item] + pending
    return "/" + "/".join(resolved)


def executable_pins(root_fd: int) -> dict[str, Any]:
    """Pin each spawner executable to its resolved guest path and bytes."""
    pins = []
    for path in PINNED_EXECUTABLES:
        try:
            resolved = resolve_in_root(root_fd, path).lstrip("/")
            fd = _open_beneath(root_fd, resolved, os.O_RDONLY | os.O_NONBLOCK)
        except OSError as exc:
            raise ImageStoreError(f"image executable {path} is absent") from exc
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or not info.st_mode & 0o111:
                raise ImageStoreError(f"image executable {path} is not an executable file")
            pins.append({"path": path, "resolved": "/" + resolved, "mode": stat.S_IMODE(info.st_mode),
                         "size": info.st_size, "sha256": _file_digest(fd)})
        finally:
            os.close(fd)
    return {"schema_version": PINS_SCHEMA, "executables": pins}


def _paths(store: Path, image: str) -> tuple[Path, Path]:
    hex_digest = _digest_hex(image)
    return store / "records" / f"{hex_digest}.json", store / "rootfs" / hex_digest


def import_oci_layout(store: Path, image: str, layout: Path) -> dict[str, Any]:
    """Import `image` from an OCI layout once per digest; return its canonical record.

    An existing record is returned only after its tree is admitted again. Every
    refusal is an `ImageStoreError`.
    """
    store, layout = Path(store), Path(layout)
    record_path, rootfs = _paths(store, image)
    if record_path.is_file():
        open_sealed_image(store, image).close()
        return _read_record(record_path, image)
    try:
        return _import(store, image, layout, record_path, rootfs)
    except ImageStoreError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, RecursionError, OSError) as exc:
        raise ImageStoreError(f"image layout cannot be imported: {exc!r}") from exc


def _import(store: Path, image: str, layout: Path, record_path: Path, rootfs: Path) -> dict[str, Any]:
    # ponytail: no import lock, blob/extraction size caps or tree fsync; installation-time,
    # single installer. Add them when imports run concurrently or from untrusted layouts.
    manifest_digest, manifest = _platform_manifest(layout, "sha256:" + _digest_hex(image))
    config = json.loads(_blob(layout, manifest["config"]["digest"]))
    if (config.get("os"), config.get("architecture")) != (PLATFORM["os"], PLATFORM["architecture"]):
        raise ImageStoreError("image config is not linux/amd64")
    for directory in ("records", "rootfs", "staging"):
        (store / directory).mkdir(mode=0o700, parents=True, exist_ok=True)
    staging = store / "staging" / rootfs.name
    for leftover in (staging, rootfs):
        if os.path.lexists(leftover):
            _set_writable(leftover, True)
            shutil.rmtree(leftover)
    staging.mkdir(mode=0o700)
    for layer in manifest["layers"]:
        _apply_layer(staging, _blob(layout, layer["digest"]), layer["mediaType"])
    _prepare_mount_points(staging)
    os.rename(staging, rootfs)
    _set_writable(rootfs, False)
    root_fd = os.open(rootfs, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        record = {
            "schema_version": RECORD_SCHEMA,
            "image": image,
            "manifest_digest": manifest_digest,
            "config_digest": manifest["config"]["digest"],
            "platform": "linux/amd64",
            "mount_points": ["/" + name for name in MOUNT_POINTS],
            "tree_digest": tree_digest(root_fd),
            "executable_pins": executable_pins(root_fd),
            "env": list(config.get("config", {}).get("Env", [])),
        }
    finally:
        os.close(root_fd)
    durable_atomic_write(record_path, canonical_json_bytes(record))
    return record


def _read_record(path: Path, image: str) -> dict[str, Any]:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            payload = b"".join(iter(lambda: os.read(fd, _CHUNK), b""))
        finally:
            os.close(fd)
        record = json.loads(payload)
    except (OSError, ValueError) as exc:
        raise ImageStoreError("image record is missing or unreadable") from exc
    if (not isinstance(record, dict) or canonical_json_bytes(record) != payload
            or record.get("schema_version") != RECORD_SCHEMA or record.get("image") != image):
        raise ImageStoreError("image record is not the canonical record of this image")
    return record


def _require_empty_mount_points(root_fd: int) -> None:
    for name in MOUNT_POINTS:
        try:
            fd = _open_beneath(root_fd, name, os.O_RDONLY | os.O_DIRECTORY)
        except OSError as exc:
            raise ImageStoreError(f"mount point /{name} is not a directory") from exc
        try:
            if os.listdir(fd):
                raise ImageStoreError(f"mount point /{name} is not empty")
        finally:
            os.close(fd)


def open_sealed_image(store: Path, image: str) -> SealedImage:
    """Admit `image`: rehash, mount points and pins all checked through one retained descriptor."""
    record_path, rootfs = _paths(Path(store), image)
    record = _read_record(record_path, image)
    try:
        root_fd = os.open(rootfs, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError as exc:
        raise ImageStoreError("sealed rootfs is missing") from exc
    sealed = SealedImage(root_fd, record)
    try:
        info = os.fstat(root_fd)
        if info.st_uid != os.geteuid() or info.st_mode & 0o222:
            raise ImageStoreError("sealed rootfs is not owned by the user or not read-only")
        sealed.rehash()
        _require_empty_mount_points(root_fd)
        if executable_pins(root_fd) != record["executable_pins"]:
            raise ImageStoreError("image executable pins differ from the record")
    except (ImageStoreError, OSError, KeyError, TypeError, RecursionError) as exc:
        sealed.close()
        if isinstance(exc, ImageStoreError):
            raise
        raise ImageStoreError(f"sealed rootfs cannot be read: {exc}") from exc
    return sealed


__all__ = [
    "ImageStoreError",
    "MOUNT_POINTS",
    "PINNED_EXECUTABLES",
    "SealedImage",
    "executable_pins",
    "import_oci_layout",
    "open_sealed_image",
    "resolve_in_root",
    "tree_digest",
]
