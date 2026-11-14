"""Measure one pinned task image and, for an agent image, check that it withholds the task's answers.

Plan D1 and Task 2b. For the image of <task> and <role> (`agent` or `verifier`) named in tasks.json:
1. pull it by digest with rootless Podman (up to three attempts), and record whether that worked, the
   compressed and unpacked size, the layers, the layers shared with images measured before (earlier
   lines of the result file) and the pull time;
2. for an agent image: create a container with no network, never start it, export its file system to a
   tar, and search the tar for the task package's solution/ and tests/ files (by path and by SHA-256)
   and for the benchmark's canary identifier, which is read from the package at run time and never
   written out;
3. delete the tar, the container and the image.
One JSON line is appended to the result file. It holds no absolute path and no user name.
Free space on / and /home is checked before each step; under 25 GB the run stops with exit code 3.

Usage (from the repository root; LH is the cache directory, by default ~/lh-cache):
  python -I experiments/long_horizon_tasks/image_check.py measure <task> <role> <scratch dir>
  python -I experiments/long_horizon_tasks/image_check.py totals
Needs: podman (rootless), taskset, ionice; the task packages unpacked at $LH/tasks41/<task>/x.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
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


class LowDisk(Exception):
    pass


# ---- pure parts -------------------------------------------------------------------------------


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


def totals(lines, task_order):
    """Disk needed under the three keeping strategies, and for the block in flight plus the next one."""
    measured = [line for line in lines if line.get("layers")]
    by_task = {}
    for line in measured:
        by_task.setdefault(line["task"], []).append(line)
    blocks = [union_bytes(by_task[t]) | {"task": t} for t in task_order if t in by_task]
    pairs = [union_bytes(by_task[a] + by_task[b]) | {"tasks": [a, b]}
             for a, b in zip(task_order, task_order[1:]) if a in by_task and b in by_task]
    return {"measured": len(measured),
            "all": union_bytes(measured),
            "agent_only": union_bytes([line for line in measured if line["role"] == "agent"]),
            "largest_block": max(blocks, key=lambda b: b["unpacked"], default=None),
            "largest_block_and_next": max(pairs, key=lambda b: b["unpacked"], default=None)}


def package_index(files):
    """Index a task package from (relative path, sha256) pairs."""
    index = {"answers": {}, "answer_names": set(), "env_sha": set(), "env_names": set()}
    for rel, sha in files:
        top, _, rest = rel.partition("/")
        name = rel.rsplit("/", 1)[-1]
        if top in ("solution", "tests") and rest:
            index["answers"][rel] = sha
            index["answer_names"].add(name)
        elif top == "environment":
            index["env_sha"].add(sha)
            index["env_names"].add(name)
    return index


def _answer_paths(path, index):
    parts = path.split("/")
    hits = [rel for rel in index["answers"] if path == rel or path.endswith("/" + rel)]
    if parts[0] in ("solution", "tests"):
        hits.append(parts[0] + "/")
    return hits


def classify(members, index):
    """Search an image's file listing; members are (path, sha256, holds_canary) for regular files."""
    answer_sha = {}
    for rel, sha in index["answers"].items():
        if sha != EMPTY_SHA and sha not in index["env_sha"]:
            answer_sha.setdefault(sha, []).append(rel)
    found = {"path_hits": [], "digest_hits": [], "name_matches": 0, "name_samples": [],
             "canary_env": [], "canary_other": [], "files": 0}
    for path, sha, canary in members:
        found["files"] += 1
        found["path_hits"] += [{"path": path, "matches": rel} for rel in _answer_paths(path, index)]
        if sha in answer_sha:
            found["digest_hits"].append({"path": path, "matches": answer_sha[sha]})
        name = path.rsplit("/", 1)[-1]
        if name in index["answer_names"]:
            found["name_matches"] += 1
            if len(found["name_samples"]) < SAMPLE:
                found["name_samples"].append(path)
        if canary:
            env = sha in index["env_sha"] or name in index["env_names"]
            found["canary_env" if env else "canary_other"].append(path)
    found["withheld"] = not found["path_hits"] and not found["digest_hits"]
    return found


def canary_id(texts):
    """The one canary identifier in a package's files (bytes), or None."""
    ids = {m.group(1) for text in texts for m in CANARY.finditer(text)}
    if len(ids) > 1:
        raise ValueError(f"{len(ids)} different canary identifiers in one package")
    return ids.pop() if ids else None


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


# ---- I/O --------------------------------------------------------------------------------------


def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def _free():
    return {m: shutil.disk_usage(m).free for m in MOUNTS}


def _check_room(need=0):
    free = _free()
    low = {m: f for m, f in free.items() if f - need < STOP_BYTES}
    if low:
        raise LowDisk(f"free space under 25 GB (needing {need} more bytes): {low}")
    return free


def _qualified(ref):
    first = ref.split("/", 1)[0]
    return ref if "." in first or ":" in first or first == "localhost" else "docker.io/" + ref


def pull(ref):
    """Pull by digest; three attempts of the pinned form, then the same without its tag."""
    pinned = _qualified(ref)
    untagged = pinned.split("@")[0].rsplit(":", 1)[0] + "@" + pinned.split("@")[1]
    errors = []
    for form in (pinned, untagged):
        for _ in range(3):
            start = time.monotonic()
            done = _run(NICE + ["podman", "pull", "-q", form])
            if done.returncode == 0:
                return {"ok": True, "form": "pinned" if form == pinned else "untagged",
                        "seconds": round(time.monotonic() - start), "image_id": done.stdout.split()[-1],
                        "attempts": len(errors) + 1, "errors": errors}
            errors.append(done.stderr.strip()[-500:])
            if "both a tag and digest" in done.stderr:
                break
    return {"ok": False, "attempts": len(errors), "errors": errors}


def inspect(image_id, ref):
    data = json.loads(_run(["podman", "image", "inspect", image_id], check=True).stdout)[0]
    graph = _run(["podman", "info", "--format", "{{.Store.GraphRoot}}"], check=True).stdout.strip()
    store = json.loads((Path(graph) / "overlay-layers" / "layers.json").read_text())
    digests = data.get("RepoDigests") or []
    layers = layer_sizes(data["RootFS"]["Layers"], store)
    return {"digest_matches": any(d.endswith("@" + ref.split("@")[1]) for d in digests), "unpacked": data["Size"],
            "compressed": sum(layer["compressed"] or 0 for layer in layers), "layers": layers}


def read_package(pkg):
    files, texts = [], []
    for path in sorted(p for p in pkg.rglob("*") if p.is_file() and not p.is_symlink()):
        raw = path.read_bytes()
        files.append((path.relative_to(pkg).as_posix(), hashlib.sha256(raw).hexdigest()))
        texts.append(raw)
    return package_index(files), canary_id(texts)


def tar_members(tar_path, needle):
    with tarfile.open(tar_path, "r:") as tar:
        for member in tar:
            if member.isreg():
                sha, hit = holds(tar.extractfile(member), needle)
                yield member.name.removeprefix("./").lstrip("/"), sha, hit


def withholding(image_id, task, scratch, pkg, unpacked):
    if not pkg.is_dir():
        index, needle, package = package_index([]), None, "not cached: path patterns only"
    else:
        (index, needle), package = read_package(pkg), "cached"
    name, tar_path = f"lh-wh-{task}", scratch / f"{task}.tar"
    _check_room(unpacked)
    _run(["podman", "create", "--pull", "never", "--network", "none", "--name", name, image_id, "true"], check=True)
    try:
        _run(NICE + ["podman", "export", "-o", str(tar_path), name], check=True)
        free = _check_room()
        found = classify(tar_members(tar_path, needle), index)
    finally:  # the tar and the container never outlive the check, whatever fails
        tar_path.unlink(missing_ok=True)
        _run(["podman", "rm", "-f", name])
    found["canary"] = "no identifier in package" if needle is None else (
        "not found" if not found["canary_env"] + found["canary_other"] else "found")
    return found | {"package": package, "free_during_export": free}


def measure(task, role, scratch):
    entry = next(t for t in json.loads(TASKS.read_text())["tasks"] if t["name"].endswith("/" + task))
    ref = entry["environment_image" if role == "agent" else "verifier_image"]
    line = {"task": task, "role": role, "ref": ref, "free_before": _check_room()}
    got = pull(ref)
    line["pull"] = got
    if got["ok"]:
        try:
            line |= inspect(got["image_id"], ref)
            line["shared"] = shared_with(line["layers"], _lines())
            line["free_pulled"] = _check_room()
            if role == "agent":
                pkg = Path(os.environ.get("LH", Path.home() / "lh-cache")) / "tasks41" / task / "x"
                line["withholding"] = withholding(got["image_id"], task, scratch, pkg, line["unpacked"])
        finally:  # the image never outlives its measurement, whatever fails
            _run(["podman", "rmi", "-f", got["image_id"]])
    else:
        dockerfile = "environment/Dockerfile" if role == "agent" else "tests/Dockerfile"
        line["fallback"] = f"local build from the package's {dockerfile} (not tried; a different configuration label)"
    line["free_after"] = _free()
    with RESULT.open("a") as out:
        out.write(json.dumps(line, sort_keys=True) + "\n")
    return line


def _lines():
    return [json.loads(x) for x in RESULT.read_text().splitlines() if x.strip()] if RESULT.exists() else []


def main(argv):
    if argv[:1] == ["totals"]:
        order = [t["name"].split("/")[-1] for t in json.loads(TASKS.read_text())["tasks"]]
        print(json.dumps(totals(_lines(), order) | {"free_now": _free()}, indent=1))
        return 0
    if len(argv) != 4 or argv[0] != "measure" or argv[2] not in ("agent", "verifier"):
        print(__doc__, file=sys.stderr)
        return 2
    try:
        line = measure(argv[1], argv[2], Path(argv[3]))
    except LowDisk as stop:
        print(f"stopped at {argv[1]} {argv[2]}: {stop}", file=sys.stderr)
        return 3
    wh = line.get("withholding") or {}
    print(json.dumps({"task": argv[1], "role": argv[2], "pulled": line["pull"]["ok"],
                      "unpacked": line.get("unpacked"), "withheld": wh.get("withheld"), "canary": wh.get("canary")}))
    return 0 if line["pull"]["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
