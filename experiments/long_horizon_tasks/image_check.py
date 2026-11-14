"""Measure one pinned task image and, for an agent image, check that it withholds the task's answers.

Plan D1 and Task 2b. For the image of <task> and <role> (`agent` or `verifier`) named in tasks.json:
1. pull it by digest with rootless Podman (up to three attempts), and record whether that worked, the
   compressed and unpacked size, the layers, the layers shared with images measured before (earlier
   lines of the result file) and the pull time;
2. for an agent image, check withholding against the cached 4.1.0 package (its content digest is checked
   first). A container is created with no network and never started; its file system is exported to a
   tar and searched:
   - every member (file, hard link, symlink, directory) by path for the package's solution/ and tests/;
   - every regular file by SHA-256 against those files;
   - every regular file for the benchmark's canary identifier, which is read from the package at run time
     and never written out; a file holding it is a byte-identical environment copy, a name-only match
     ("needs a look") or other;
   - text files for near copies: lines of 25 or more characters that occur in solution/ or tests/ and in
     no environment/ file (only the lines' SHA-256 is recorded); system paths, language package
     directories and virtual environments (any directory holding a pyvenv.cfg) need NOISE_N matches;
   - archives and .git objects outside system paths, opened when small enough and searched the same way;
   then each layer of the image is walked, deleted files included, by path and SHA-256;
3. delete the tar and the container, and the image unless it was in the store before the pull.
One JSON line is appended to the result file (`recheck` replaces an agent line's withholding result). It
holds no absolute path and no user name. Free space on / and /home is checked before each step, the pull
included; under 25 GB the run stops with exit code 3.

Usage (from the repository root; LH is the cache directory, by default ~/lh-cache):
  python -I experiments/long_horizon_tasks/image_check.py measure <task> <role> <scratch dir>
  python -I experiments/long_horizon_tasks/image_check.py recheck <task> <scratch dir>   (withholding again)
  python -I experiments/long_horizon_tasks/image_check.py totals
Exit codes: 0 done; 1 pull failed; 2 bad arguments or package; 3 disk stop; 4 image left in place because a
container uses it; 5 a clean-up step failed.
Needs: podman (rootless), taskset, ionice; the task packages unpacked at $LH/tasks41/<task>/x; Harbor in
$LH/hvenv (for the package digest).
"""

import collections
import gzip
import hashlib
import io
import itertools
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
import zlib
from pathlib import Path

KIT = Path(__file__).resolve().parent
TASKS = KIT / "tasks.json"
RESULT = KIT / "image_measure.json"
STOP_BYTES = 25 * 10**9
MOUNTS = ("/", "/home")
CANARY = re.compile(rb"canary GUID ([0-9a-fA-F-]{36})")
EMPTY_SHA = hashlib.sha256(b"").hexdigest()
CHUNK = 1 << 20
NICE = ["taskset", "-c", "0-3", "ionice", "-c", "3", "nice", "-n", "10"]
SAMPLE = 10
MIN_LINE = 25
MAX_READ = 64 << 20  # files up to this size are read whole: line matching and archive opening
UNPACK_RATIO = 4  # unpacked over compressed size was 2.05 to 3.89 over the 32 images measured
NOISE_N = 10  # a system-path file with fewer near-copy lines is noise: the 16 images show at most 6 (RECORDINGS.md)
SYSTEM = re.compile(r"^(usr|bin|sbin|etc|lib|lib32|lib64|libx32|var/lib/dpkg|var/lib/apt)(/|$)")
LANG_DIRS = ("/site-packages/", "/dist-packages/", "/node_modules/", "/.cargo/registry/", "/.rustup/",
             "/go/pkg/mod/", "/gems/", "/.npm/", "/.cache/pip/", "/.local/share/uv/python/")
ARCHIVE = re.compile(r"\.(tar|tgz|txz|tbz2|tar\.(gz|xz|bz2|zst)|zip|whl|gz)$")
GIT_OBJECT = re.compile(r"(^|/)\.git/objects/[0-9a-f]{2}/[0-9a-f]{38}$")
GIT_PACK = re.compile(r"(^|/)\.git/objects/pack/[^/]+\.pack$")
ARCHIVE_ERRORS = (zipfile.BadZipFile, tarfile.TarError, OSError, zlib.error, EOFError, ValueError)


class LowDisk(Exception):
    pass


class Stop(Exception):
    """A refusal with its exit code."""

    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


Entry = collections.namedtuple("Entry", "path kind size sha canary raw link")


# ---- sizes and disk ---------------------------------------------------------------------------


def layer_sizes(rootfs_layers, store_layers):
    """Per layer of an image (its RootFS diff digests, bottom first): sizes from the store's layers.json."""
    by_diff = {}
    for entry in store_layers:
        by_diff.setdefault(entry.get("diff-digest"), entry)
    out = []
    for diff in rootfs_layers:
        entry = by_diff.get(diff)
        if entry is None:
            raise ValueError(f"layer {diff} is not in the store's layers.json")
        out.append({"diff_digest": diff, "compressed": entry.get("compressed-size"), "unpacked": entry["diff-size"]})
    return out


def shared_with(layers, earlier_lines):
    """The layers of this image already present in images measured before, and their sizes."""
    seen = {layer["diff_digest"] for line in earlier_lines for layer in line.get("layers") or []}
    shared = [layer for layer in layers if layer["diff_digest"] in seen]
    return {"count": len(shared), "compressed": sum(layer["compressed"] or 0 for layer in shared),
            "unpacked": sum(layer["unpacked"] for layer in shared)}


def union_bytes(lines):
    """Store size of a set of images kept together: each distinct layer counted once."""
    layers = {layer["diff_digest"]: layer for line in lines for layer in line.get("layers") or []}
    return {"images": len(lines), "layers": len(layers),
            "compressed": sum(layer["compressed"] or 0 for layer in layers.values()),
            "unpacked": sum(layer["unpacked"] for layer in layers.values())}


def worst_blocks(by_task, k):
    """The k blocks (tasks) whose images together take the most room, over every choice of k tasks."""
    return max((union_bytes([x for t in combo for x in by_task[t]]) | {"tasks": list(combo)}
                for combo in itertools.combinations(sorted(by_task), k)), key=lambda b: b["unpacked"], default=None)


def totals(lines):
    """Disk needed when all images, only agent images, or k blocks at a time are kept.

    The plan orders blocks by a hash of a seed that is not frozen yet, and runs up to four attempts at
    once, so the worst case over any k tasks bounds every order."""
    measured = [line for line in lines if line.get("layers")]
    by_task = {}
    for line in measured:
        by_task.setdefault(line["task"], []).append(line)
    return {"measured": len(measured), "all": union_bytes(measured),
            "agent_only": union_bytes([line for line in measured if line["role"] == "agent"]),
            "worst_blocks": {k: worst_blocks(by_task, k) for k in (1, 2, 3, 4)}}


def pull_need(compressed, unpacked=None):
    """Free space a pull may take: the download plus the unpacked layers (estimated when not measured)."""
    return compressed + (unpacked if unpacked is not None else UNPACK_RATIO * compressed)


def removal(image_id, present_before, users):
    """Whether to delete the image after the check: never one that was there before, never under a container."""
    if image_id in present_before:
        return "keep", "in the store before the pull"
    if users:
        return "refuse", f"containers use the image: {sorted(users)}"
    return "remove", None


# ---- the package ------------------------------------------------------------------------------


def _is_text(raw):
    return b"\0" not in raw[:8192]


def distinctive_lines(answer_texts, env_texts, needle):
    """SHA-256 by line, for stripped lines of MIN_LINE or more that answers hold and the environment does not."""
    env = {line.strip() for raw in env_texts for line in raw.splitlines()}
    lines = {line.strip() for raw in answer_texts for line in raw.splitlines()}
    return {line: hashlib.sha256(line).hexdigest() for line in lines
            if len(line) >= MIN_LINE and line not in env and not (needle and needle in line)}


def package_index(files, needle=None):
    """Index a task package from (relative path, raw bytes) pairs."""
    index = {"answers": {}, "answer_names": set(), "env_sha": set(), "env_by_name": {}, "needle": needle}
    answer_texts, env_texts = [], []
    for rel, raw in files:
        top, _, rest = rel.partition("/")
        name, sha = rel.rsplit("/", 1)[-1], hashlib.sha256(raw).hexdigest()
        if top in ("solution", "tests") and rest:
            index["answers"][rel] = sha
            index["answer_names"].add(name)
            answer_texts += [raw] if _is_text(raw) else []
        elif top == "environment":
            index["env_sha"].add(sha)
            index["env_by_name"].setdefault(name, []).append(rel)
            env_texts += [raw] if _is_text(raw) else []
    index["answer_sha"] = {}
    for rel, sha in index["answers"].items():
        if sha != EMPTY_SHA and sha not in index["env_sha"]:
            index["answer_sha"].setdefault(sha, []).append(rel)
    index["lines"] = distinctive_lines(answer_texts, env_texts, needle)
    return index


def canary_id(texts):
    """The one canary identifier in a package's files (bytes), or None."""
    ids = {m.group(1) for text in texts for m in CANARY.finditer(text)}
    if len(ids) > 1:
        raise ValueError(f"{len(ids)} different canary identifiers in one package")
    return ids.pop() if ids else None


# ---- the search -------------------------------------------------------------------------------


def is_system(path, venvs=()):
    """A system path, a language package directory, or anything inside a virtual environment."""
    return (bool(SYSTEM.match(path)) or any(d in "/" + path for d in LANG_DIRS)
            or any(path.startswith(root + "/") for root in venvs))


def venv_roots(paths):
    """The virtual environments of an image: every directory that holds a `pyvenv.cfg`."""
    return {p.rsplit("/", 1)[0] for p in paths if p.endswith("/pyvenv.cfg")}


def closest_env(path, rels):
    """Of the environment files sharing a base name, the one whose path ends most like the image path."""
    parts = path.split("/")[::-1]

    def common(rel):
        return next((i for i, (a, b) in enumerate(zip(parts, rel.split("/")[:0:-1])) if a != b),
                    min(len(parts), rel.count("/")))
    return max(sorted(rels), key=common)


def canary_bucket(path, sha, index):
    """Where a file holding the canary comes from: a byte-identical environment copy, a name only, or neither."""
    if sha in index["env_sha"]:
        return "canary_env_sha", path
    rels = index["env_by_name"].get(path.rsplit("/", 1)[-1].split("!")[-1])
    if rels:
        return "canary_name_only", {"path": path, "env": closest_env(path, rels)}
    return "canary_other", path


def compare_texts(image, env, needle):
    """What a name-only canary file shares with the environment file of that name (non-empty lines)."""
    a, b = ({line.strip() for line in raw.splitlines() if line.strip()} for raw in (image, env))
    shared = a & b
    other = {line for line in shared if needle not in line}
    return {"image_size": len(image), "env_size": len(env), "identical": image == env,
            "shared_lines": len(shared), "shared_non_canary_lines": len(other), "canary_only_shared": not other,
            "image_only_lines": len(a - b), "env_only_lines": len(b - a)}


def near_verdict(path, count, venvs=()):
    return "needs a look" if not is_system(path, venvs) or count >= NOISE_N else "noise"


def near_copy(path, raw, index):
    """A text file's lines that only the package's answers hold, by SHA-256; None when there are none."""
    if not index["lines"] or not _is_text(raw):
        return None
    got = sorted({index["lines"][line] for line in (x.strip() for x in raw.splitlines()) if line in index["lines"]})
    return {"path": path, "count": len(got), "lines": got, "verdict": near_verdict(path, len(got), index.get("venvs", ()))} if got else None


def answer_paths(path, index):
    """Package solution/ or tests/ paths this path ends with, and a root solution/ or tests/ itself."""
    path = path.split("!")[-1].removeprefix("./").lstrip("/")
    hits = [rel for rel in index["answers"] if path == rel or path.endswith("/" + rel)]
    if path.split("/")[0] in ("solution", "tests"):
        hits.append(path.split("/")[0] + "/")
    return hits


def archive_entries(path, raw, needle):
    """The members of an archive or a loose git object, as entries named `<archive>!<member>`."""
    if GIT_OBJECT.search(path):
        body = zlib.decompress(raw)
        return [_entry(f"{path}!blob", body.partition(b"\0")[2], needle)]
    if zipfile.is_zipfile(io.BytesIO(raw)):
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            return [_entry(f"{path}!{i.filename}", z.read(i), needle) for i in z.infolist() if not i.is_dir()]
    if re.search(r"\.gz$", path) and not re.search(r"\.tar\.gz$", path):
        return [_entry(f"{path}!{Path(path).stem}", gzip.decompress(raw), needle)]
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:*") as t:
        return [_entry(f"{path}!{m.name}", t.extractfile(m).read(), needle) for m in t if m.isreg()]


def _entry(path, raw, needle):
    return Entry(path, "file", len(raw), hashlib.sha256(raw).hexdigest(), bool(needle and needle in raw), raw, None)


def new_found():
    return {"path_hits": [], "digest_hits": [], "name_matches": 0, "name_samples": [],
            "name_match_dirs": collections.Counter(), "name_match_names": collections.Counter(),
            "canary_env_sha": [], "canary_name_only": [], "canary_other": [], "near_copies": [],
            "archives_opened": [], "not_opened": [], "git_dirs": [], "files": 0, "members": 0}


def _note_name(found, path, index):
    name = path.rsplit("/", 1)[-1]
    if name in index["answer_names"]:
        found["name_matches"] += 1
        found["name_match_dirs"]["/".join(path.split("/")[:2])] += 1
        found["name_match_names"][name] += 1
        if len(found["name_samples"]) < SAMPLE:
            found["name_samples"].append(path)


def _open_archive(found, entry, index, depth):
    venvs = index.get("venvs", ())
    if GIT_PACK.search(entry.path) and not is_system(entry.path, venvs):
        found["not_opened"].append({"path": entry.path, "size": entry.size, "why": "git pack"})
        return
    if is_system(entry.path, venvs) or not (ARCHIVE.search(entry.path) or GIT_OBJECT.search(entry.path)):
        return
    if depth:
        found["not_opened"].append({"path": entry.path, "size": entry.size, "why": "archive inside an archive"})
        return
    if entry.raw is None:
        found["not_opened"].append({"path": entry.path, "size": entry.size, "why": "larger than MAX_READ"})
        return
    try:
        members = archive_entries(entry.path, entry.raw, index["needle"])
    except ARCHIVE_ERRORS as err:  # an unreadable archive is reported, not fatal: the scan goes on
        found["not_opened"].append({"path": entry.path, "size": entry.size, "why": type(err).__name__})
        return
    found["archives_opened"].append({"path": entry.path, "members": len(members)})
    for member in members:
        judge(found, member, index, depth + 1)


def judge(found, entry, index, depth=0):
    """Apply every check to one member of an image (or of an archive inside it)."""
    found["members"] += 1
    found["path_hits"] += [{"path": entry.path, "kind": entry.kind, "matches": rel}
                           for rel in answer_paths(entry.path, index) + answer_paths(entry.link or "", index)]
    if entry.kind == "dir" and entry.path.rstrip("/").endswith(".git") and not is_system(entry.path, index.get("venvs", ())):
        found["git_dirs"].append(entry.path)
    if entry.kind != "file":
        return
    found["files"] += 1
    if entry.sha in index["answer_sha"]:
        found["digest_hits"].append({"path": entry.path, "matches": index["answer_sha"][entry.sha]})
    _note_name(found, entry.path, index)
    if entry.canary:
        bucket, item = canary_bucket(entry.path, entry.sha, index)
        found[bucket].append(item)
    if entry.raw is not None and entry.sha not in index["env_sha"]:
        near = near_copy(entry.path, entry.raw, index)
        found["near_copies"] += [near] if near else []
    _open_archive(found, entry, index, depth)


def canary_verdict(found, needle):
    if needle is None:
        return "no identifier in package"
    if found["canary_other"]:
        return "found outside environment files"
    if found["canary_name_only"]:
        return "needs a look"
    return "environment copies only" if found["canary_env_sha"] else "not found"


def classify(entries, index):
    """Search an image's members; returns the findings and their verdicts."""
    found = new_found()
    for entry in entries:
        judge(found, entry, index)
    found["withheld"] = not found["path_hits"] and not found["digest_hits"]
    found["canary_counts"] = {k: len(found["canary_" + k]) for k in ("env_sha", "name_only", "other")}
    found["canary"] = canary_verdict(found, index["needle"])
    look = [n for n in found["near_copies"] if n["verdict"] == "needs a look"]
    found["near_copy_look"] = [n["path"] for n in look]
    found["near_copy"] = "needs a look" if look or found["not_opened"] or found["git_dirs"] else "clean"
    for key in ("name_match_dirs", "name_match_names"):
        found[key] = found[key].most_common(5)
    return found


def holds(stream, needle):
    """SHA-256 of a stream and whether it holds needle (searched across chunk boundaries)."""
    digest, tail, hit = hashlib.sha256(), b"", False
    for chunk in iter(lambda: stream.read(CHUNK), b""):
        digest.update(chunk)
        if needle and not hit:
            window = tail + chunk
            hit = needle in window
            tail = window[max(0, len(window) - len(needle) + 1):]
    return digest.hexdigest(), hit


def _kind(member):
    return ("file" if member.isreg() else "hardlink" if member.islnk() else "symlink" if member.issym()
            else "dir" if member.isdir() else "other")


def tar_entries(tar_path, needle):
    """Every member of an exported tar; regular files are hashed, and read whole up to MAX_READ."""
    with tarfile.open(tar_path, "r:") as tar:
        for member in tar:
            path, kind = member.name.removeprefix("./").lstrip("/"), _kind(member)
            if kind != "file":
                yield Entry(path, kind, member.size, None, False, None, member.linkname or None)
            elif member.size <= MAX_READ:
                yield _entry(path, tar.extractfile(member).read(), needle)
            else:
                sha, hit = holds(tar.extractfile(member), needle)
                yield Entry(path, kind, member.size, sha, hit, None, None)


def layer_entries(dirs):
    """Every entry of the image's layer directories, deleted files and whiteouts included (path and hash)."""
    for i, top in enumerate(dirs):
        for root, dnames, fnames in os.walk(top):
            for name in dnames + fnames:
                full = os.path.join(root, name)
                rel, st = f"layer{i}/" + os.path.relpath(full, top), os.lstat(full)
                if name.startswith(".wh.") or (stat.S_ISCHR(st.st_mode) and st.st_rdev == 0):
                    yield Entry(rel.replace(".wh.", ""), "whiteout", 0, None, False, None, None)
                elif stat.S_ISREG(st.st_mode):
                    with open(full, "rb") as f:
                        sha, _ = holds(f, None)
                    yield Entry(rel, "file", st.st_size, sha, False, None, None)
                else:
                    yield Entry(rel, "dir" if stat.S_ISDIR(st.st_mode) else "other", 0, None, False, None, None)


def layer_verdict(entries, index):
    """Path and SHA-256 hits over the layers; paths are tested without their layer prefix."""
    found = new_found()
    whiteouts = 0
    for entry in entries:
        whiteouts += entry.kind == "whiteout"
        judge(found, entry._replace(path=entry.path.split("/", 1)[1] if "/" in entry.path else ""), index, depth=1)
    return {"members": found["members"], "files": found["files"], "whiteouts": whiteouts,
            "path_hits": found["path_hits"], "digest_hits": found["digest_hits"],
            "withheld": not found["path_hits"] and not found["digest_hits"]}


# ---- I/O --------------------------------------------------------------------------------------


def _run(cmd):
    """Run a command; a failure raises with Podman's own error text."""
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode:
        raise RuntimeError(f"{' '.join(cmd[:4])} ... failed ({done.returncode}): {done.stderr.strip()[-800:]}")
    return done.stdout


def _cleanup(cmd, problems):
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode:
        problems.append(f"{' '.join(cmd[:3])} failed ({done.returncode}): {done.stderr.strip()[-300:]}")


def _free():
    return {m: shutil.disk_usage(m).free for m in MOUNTS}


def _check_room(need=0):
    free = _free()
    low = {m: f for m, f in free.items() if f - need < STOP_BYTES}
    if low:
        raise LowDisk(f"free space under 25 GB (needing {need} more bytes): {low}")
    return free


def scratch_dir(path):
    """The scratch directory for export tars: created with mode 700, refused if others can enter it."""
    path = Path(path)
    if not path.exists():
        path.mkdir(mode=0o700)
    if path.stat().st_mode & 0o077:
        raise Stop(f"scratch directory {path} is group- or world-accessible", 2)
    return path


def _qualified(ref):
    first = ref.split("/", 1)[0]
    return ref if "." in first or ":" in first or first == "localhost" else "docker.io/" + ref


def registry_compressed(ref):
    """The image's compressed size from its manifest on Docker Hub (anonymous; before any pull)."""
    repo, digest = ref.split("@")[0].rsplit(":", 1)[0], ref.split("@")[1]
    if not _qualified(ref).startswith("docker.io/"):
        raise Stop(f"no size lookup for a registry other than docker.io: {ref}", 2)
    auth = f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repo}:pull"
    with urllib.request.urlopen(auth, timeout=60) as r:
        token = json.load(r)["token"]
    req = urllib.request.Request(f"https://registry-1.docker.io/v2/{repo}/manifests/{digest}", headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        manifest = json.load(r)
    return sum(layer["size"] for layer in manifest["layers"]) + manifest["config"]["size"]


def pull(ref):
    """Pull by digest; three attempts of the pinned form, then the same without its tag."""
    pinned = _qualified(ref)
    untagged = pinned.split("@")[0].rsplit(":", 1)[0] + "@" + pinned.split("@")[1]
    errors = []
    for form in (pinned, untagged):
        for _ in range(3):
            start = time.monotonic()
            done = subprocess.run(NICE + ["podman", "pull", "-q", form], capture_output=True, text=True)
            if done.returncode == 0:
                return {"ok": True, "form": "pinned" if form == pinned else "untagged",
                        "seconds": round(time.monotonic() - start), "image_id": done.stdout.split()[-1],
                        "attempts": len(errors) + 1, "errors": errors}
            errors.append(done.stderr.strip()[-500:])
            if "both a tag and digest" in done.stderr:
                break
    return {"ok": False, "attempts": len(errors), "errors": errors}


def _image_ids():
    return set(_run(["podman", "images", "-a", "-q", "--no-trunc"]).replace("sha256:", "").split())


def release(image_id, present_before, problems):
    """Delete the image if this run brought it; never with -f, never one a container uses."""
    users = set(_run(["podman", "ps", "-a", "-q", "--filter", f"ancestor={image_id}"]).split())
    action, why = removal(image_id, present_before, users)
    if action == "remove":
        _cleanup(["podman", "rmi", image_id], problems)
    elif action == "refuse":
        problems.append(f"image {image_id[:12]} left in place: {why}")
    return {"action": action, "why": why}


def inspect(image_id, ref):
    data = json.loads(_run(["podman", "image", "inspect", image_id]))[0]
    graph = _run(["podman", "info", "--format", "{{.Store.GraphRoot}}"]).strip()
    store = json.loads((Path(graph) / "overlay-layers" / "layers.json").read_text())
    digests = data.get("RepoDigests") or []
    layers = layer_sizes(data["RootFS"]["Layers"], store)
    return {"digest_matches": any(d.endswith("@" + ref.split("@")[1]) for d in digests), "unpacked": data["Size"],
            "compressed": sum(layer["compressed"] or 0 for layer in layers), "layers": layers}


def read_package(task):
    """The task's cached package, after checking its content digest against tasks.json; missing is an error."""
    lh = Path(os.environ.get("LH", Path.home() / "lh-cache"))
    pkg = lh / "tasks41" / task / "x"
    if not pkg.is_dir():
        raise Stop(f"no cached package for {task} (expected $LH/tasks41/{task}/x)", 2)
    want = _task_entry(task)["digest_4_1_0"]
    got = "sha256:" + _run([str(lh / "hvenv" / "bin" / "python"), "-I", "-c",
                            "import sys; from pathlib import Path; from harbor.publisher.packager import Packager; "
                            "print(Packager.compute_content_hash(Path(sys.argv[1]))[0])", str(pkg)]).strip()
    if got != want:
        raise Stop(f"cached package of {task} is {got}, not the 4.1.0 package {want}", 2)
    files = [(p.relative_to(pkg).as_posix(), p.read_bytes())
             for p in sorted(pkg.rglob("*")) if p.is_file() and not p.is_symlink()]
    needle = canary_id([raw for _, raw in files])
    return pkg, package_index(files, needle), got


def describe_name_only(tar_path, pkg, items, needle):
    """Add to each name-only canary file how it differs from its environment namesake."""
    wanted = {item["path"]: item for item in items}
    with tarfile.open(tar_path, "r:") as tar:
        for member in tar:
            item = wanted.get(member.name.removeprefix("./").lstrip("/"))
            if item and member.isreg():
                item |= compare_texts(tar.extractfile(member).read(), (pkg / item["env"]).read_bytes(), needle)


def layer_check(image_id, task):
    """Walk the image's layer directories in Podman's user namespace (they are owned by mapped ids)."""
    data = json.loads(_run(["podman", "image", "inspect", "--format", "{{json .GraphDriver.Data}}", image_id]))
    dirs = [d for d in data.get("LowerDir", "").split(":") if d] + [data["UpperDir"]]
    out = _run(NICE + ["podman", "unshare", sys.executable, "-I", str(Path(__file__).resolve()), "layers", task]
               + dirs)
    return json.loads(out)


def withholding(image_id, task, scratch, unpacked):
    pkg, index, digest = read_package(task)
    name, tar_path, problems = f"lh-wh-{task}", scratch / f"{task}.tar", []
    _check_room(unpacked)
    _run(["podman", "create", "--pull", "never", "--network", "none", "--name", name, image_id, "true"])
    try:
        _run(NICE + ["podman", "export", "-o", str(tar_path), name])
        free = _check_room()
        with tarfile.open(tar_path, "r:") as tar:
            index["venvs"] = venv_roots(m.name.removeprefix("./").lstrip("/") for m in tar)
        found = classify(tar_entries(tar_path, index["needle"]), index)
        found["venvs"] = sorted(index["venvs"])
        describe_name_only(tar_path, pkg, found["canary_name_only"], index["needle"])
    finally:  # the tar and the container never outlive the check, whatever fails
        tar_path.unlink(missing_ok=True)
        _cleanup(["podman", "rm", name], problems)
    found["layers"] = layer_check(image_id, task)
    return found | {"package_digest": digest, "free_during_export": free, "cleanup_problems": problems}


def _task_entry(task):
    for entry in json.loads(TASKS.read_text())["tasks"]:
        if entry["name"].endswith("/" + task):
            return entry
    raise Stop(f"unknown task {task!r}: not in tasks.json", 2)


def measure(task, role, scratch):
    ref = _task_entry(task)["environment_image" if role == "agent" else "verifier_image"]
    line = {"task": task, "role": role, "ref": ref}
    line["free_before"] = _check_room(pull_need(registry_compressed(ref)))
    present = _image_ids()
    got = pull(ref)
    line["pull"] = got
    problems = []
    if got["ok"]:
        try:
            line |= inspect(got["image_id"], ref)
            line["shared"] = shared_with(line["layers"], _lines())
            line["free_pulled"] = _check_room()
            if role == "agent":
                line["withholding"] = withholding(got["image_id"], task, scratch, line["unpacked"])
        finally:  # the image never outlives its measurement, unless it was there before or is in use
            line["release"] = release(got["image_id"], present, problems)
    else:
        dockerfile = "environment/Dockerfile" if role == "agent" else "tests/Dockerfile"
        line["fallback"] = f"local build from the package's {dockerfile} (not tried; a different configuration label)"
    line["free_after"], line["cleanup_problems"] = _free(), problems
    with RESULT.open("a") as out:
        out.write(json.dumps(line, sort_keys=True) + "\n")
    return line


def _summary(old):
    return {k: old.get(k) for k in ("pass", "free_during_export", "withheld", "canary_counts", "near_copy")}


def recheck(task, scratch):
    """Pull an agent image again and replace the withholding result of its line in place."""
    lines = _lines()
    line = next((x for x in lines if x["task"] == task and x["role"] == "agent"), None)
    if line is None:
        raise Stop(f"no measured agent line for {task}", 2)
    _check_room(pull_need(line["compressed"], line["unpacked"]))
    present = _image_ids()
    got = pull(line["ref"])
    if not got["ok"]:
        raise Stop(f"re-pull of {task} failed: {got['errors'][-1:]}", 1)
    problems = []
    try:
        found = withholding(got["image_id"], task, scratch, line["unpacked"])
    finally:  # the image never outlives its check, unless it was there before or is in use
        released = release(got["image_id"], present, problems)
    old = line["withholding"]
    found["earlier_passes"] = old.get("earlier_passes", []) + [_summary(old | {"pass": old.get("pass", 1)})]
    line["withholding"] = found | {"pass": old.get("pass", 1) + 1, "pull_seconds": got["seconds"],
                                   "release": released}
    line["withholding"]["cleanup_problems"] += problems
    RESULT.write_text("".join(json.dumps(x, sort_keys=True) + "\n" for x in lines))
    return line


def _lines():
    return [json.loads(x) for x in RESULT.read_text().splitlines() if x.strip()] if RESULT.exists() else []


def _exit_code(line, problems):
    if any("left in place" in p for p in problems):
        return 4
    if problems:
        return 5
    return 0 if line["pull"]["ok"] else 1


def _cmd_measure(argv):
    if len(argv) != 3 or argv[1] not in ("agent", "verifier"):
        raise Stop(__doc__, 2)
    line = measure(argv[0], argv[1], scratch_dir(argv[2]))
    wh = line.get("withholding") or {}
    problems = line["cleanup_problems"] + wh.get("cleanup_problems", [])
    print(json.dumps({"task": argv[0], "role": argv[1], "pulled": line["pull"]["ok"], "unpacked": line.get("unpacked"),
                      "withheld": wh.get("withheld"), "canary": wh.get("canary"), "near_copy": wh.get("near_copy"),
                      "problems": problems}))
    return _exit_code(line, problems)


def _cmd_recheck(argv):
    if len(argv) != 2:
        raise Stop(__doc__, 2)
    line = recheck(argv[0], scratch_dir(argv[1]))
    wh = line["withholding"]
    print(json.dumps({"task": argv[0], "withheld": wh["withheld"], "layers_withheld": wh["layers"]["withheld"],
                      "canary": wh["canary"], "near_copy": wh["near_copy"], "look": wh["near_copy_look"],
                      "problems": wh["cleanup_problems"]} | wh["canary_counts"]))
    return _exit_code(line, wh["cleanup_problems"])


def _cmd_layers(argv):
    _, index, _ = read_package(argv[0])
    print(json.dumps(layer_verdict(layer_entries(argv[1:]), index)))
    return 0


def _cmd_totals(argv):
    print(json.dumps(totals(_lines()) | {"free_now": _free()}, indent=1))
    return 0


def main(argv):
    commands = {"measure": _cmd_measure, "recheck": _cmd_recheck, "layers": _cmd_layers, "totals": _cmd_totals}
    if not argv or argv[0] not in commands:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        return commands[argv[0]](argv[1:])
    except LowDisk as stop:
        print(f"stopped: {stop}", file=sys.stderr)
        return 3
    except Stop as stop:
        print(stop, file=sys.stderr)
        return stop.code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
