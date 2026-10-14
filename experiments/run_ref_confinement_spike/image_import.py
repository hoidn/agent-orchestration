"""Throwaway F3 spike: import a digest-pinned OCI image into a sealed content-addressed rootfs.

Installation-time step (Ruling P5): anonymous registry v2 pull with the stdlib,
blob digest verification, layer extraction with whiteouts, canonical tree
manifest, read-only seal. Usage: python image_import.py <store> <repo> <tag|sha256:...>
"""
from __future__ import annotations

import hashlib, io, json, os, shutil, stat, sys, tarfile, urllib.request
from pathlib import Path

REGISTRY = "https://registry-1.docker.io"
ACCEPT = ", ".join((
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.docker.distribution.manifest.v2+json"))


def _token(repo: str) -> str:
    url = f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repo}:pull"
    return json.load(urllib.request.urlopen(url, timeout=30))["token"]


def _get(repo: str, token: str, kind: str, ref: str) -> bytes:
    req = urllib.request.Request(f"{REGISTRY}/v2/{repo}/{kind}/{ref}",
                                 headers={"Authorization": "Bearer " + token, "Accept": ACCEPT})
    return urllib.request.urlopen(req, timeout=120).read()


def _verified(data: bytes, digest: str) -> bytes:
    if "sha256:" + hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"blob digest mismatch for {digest}")
    return data


def resolve_platform_manifest(repo: str, ref: str) -> str:
    """Return the linux/amd64 manifest digest that pins `repo:ref`."""
    token = _token(repo)
    raw = _get(repo, token, "manifests", ref)
    doc = json.loads(raw)
    if "manifests" not in doc:
        return "sha256:" + hashlib.sha256(raw).hexdigest()
    [row] = [m for m in doc["manifests"]
             if m.get("platform", {}).get("os") == "linux" and m["platform"].get("architecture") == "amd64"]
    return row["digest"]


def _apply_layer(rootfs: Path, blob: bytes) -> None:
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as archive:
        members = []
        for member in archive.getmembers():
            parent, name = os.path.split(member.name.lstrip("./").rstrip("/"))
            if name == ".wh..wh..opq":
                target = rootfs / parent
                for child in target.iterdir() if target.is_dir() else ():
                    shutil.rmtree(child) if child.is_dir() and not child.is_symlink() else child.unlink()
                continue
            if name.startswith(".wh."):
                victim = rootfs / parent / name[4:]
                if victim.is_dir() and not victim.is_symlink():
                    shutil.rmtree(victim)
                elif victim.exists() or victim.is_symlink():
                    victim.unlink()
                continue
            if member.ischr() or member.isblk() or member.isfifo():
                continue  # devices come from bwrap --dev
            if member.isdir():
                member.mode |= 0o700
            members.append(member)
        archive.extractall(rootfs, members=members, filter="tar")
    for directory, dirs, _files in os.walk(rootfs):
        for name in dirs:
            path = os.path.join(directory, name)
            if not os.path.islink(path):
                os.chmod(path, os.lstat(path).st_mode | 0o700)


def tree_manifest(rootfs: Path) -> list[list]:
    rows = []
    for directory, dirs, files in os.walk(rootfs):
        dirs.sort()
        for name in sorted(dirs + files):
            path = Path(directory, name)
            rel = path.relative_to(rootfs).as_posix()
            info = os.lstat(path)
            mode = stat.S_IMODE(info.st_mode)
            if stat.S_ISLNK(info.st_mode):
                rows.append([rel, "symlink", os.readlink(path)])
            elif stat.S_ISDIR(info.st_mode):
                rows.append([rel, "dir", mode])
            elif stat.S_ISREG(info.st_mode):
                rows.append([rel, "file", mode, info.st_size,
                             hashlib.sha256(path.read_bytes()).hexdigest()])
            else:
                raise ValueError(f"unexpected file type in rootfs: {rel}")
    return rows


def tree_digest(rootfs: Path) -> str:
    data = json.dumps(tree_manifest(rootfs), separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(data).hexdigest()


def seal(rootfs: Path) -> None:
    for directory, dirs, files in os.walk(rootfs, topdown=False):
        for name in files + dirs:
            path = os.path.join(directory, name)
            if not os.path.islink(path):
                os.chmod(path, stat.S_IMODE(os.lstat(path).st_mode) & ~0o222)
    os.chmod(rootfs, 0o555)


def import_image(store: Path, repo: str, manifest_digest: str) -> dict:
    """Import `repo@manifest_digest` once; return the admission record."""
    final = store / "rootfs" / manifest_digest.replace(":", "-")
    record_path = store / "records" / (manifest_digest.replace(":", "-") + ".json")
    if record_path.exists():
        return json.loads(record_path.read_text())
    token = _token(repo)
    manifest = json.loads(_verified(_get(repo, token, "manifests", manifest_digest), manifest_digest))
    config = json.loads(_verified(_get(repo, token, "blobs", manifest["config"]["digest"]),
                                  manifest["config"]["digest"]))
    staging = store / "staging" / manifest_digest.replace(":", "-")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    for layer in manifest["layers"]:
        if not layer["mediaType"].endswith("gzip"):
            raise ValueError(f"unsupported layer media type {layer['mediaType']}")
        _apply_layer(staging, _verified(_get(repo, token, "blobs", layer["digest"]), layer["digest"]))
    for mountpoint in ("workspace", "result"):  # profile mount points on the sealed rootfs
        (staging / mountpoint).mkdir(exist_ok=True)
    final.parent.mkdir(parents=True, exist_ok=True)
    os.rename(staging, final)
    seal(final)
    digest = tree_digest(final)
    record = {"image": f"docker.io/{repo}@{manifest_digest}", "manifest_digest": manifest_digest,
              "config_digest": manifest["config"]["digest"], "platform": "linux/amd64",
              "tree_digest": digest, "rootfs": str(final),
              "env": config.get("config", {}).get("Env", [])}
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(json.dumps(record, indent=2))
    return record


def admit(record: dict) -> Path:
    """Refuse admission when the sealed tree no longer matches its recorded digest."""
    rootfs = Path(record["rootfs"])
    if tree_digest(rootfs) != record["tree_digest"]:
        raise RuntimeError("run_ref_environment_changed: sealed rootfs digest mismatch")
    return rootfs


if __name__ == "__main__":
    store, repo, ref = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    pinned = ref if ref.startswith("sha256:") else resolve_platform_manifest(repo, ref)
    print(json.dumps(import_image(store, repo, pinned), indent=2))
