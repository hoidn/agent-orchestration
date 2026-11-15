"""Build, once, the verifier image of the labelled variant vba-userform-port-uidfix, and record its identity.

Owner question 4; coordinator ruling of Task 2b fix round 1: the variant is the labelled reading of D1's one-line
verifier change, for use only if the owner does not widen the host's subordinate id range (`podman system
migrate`). The pinned verifier image carries its own /tests (the harness uploads none), so the change has to be
in an image. This script:
1. pulls the pinned verifier image by digest unless it is in the store, and checks its id against tasks.json;
2. builds FROM it by digest with one RUN, which refuses unless exactly one line of /tests/app_worker.py holds
   the bound and then changes that line (no network, no pull), and names the result IMAGE (the name the
   variant's task.toml uses) and KEEPER (a name no compose file references);
3. compares the two images file by file: each is exported from a created, never started container and streamed
   (kind, mode, owner, link target and SHA-256 per path; modification times aside). Exactly /tests/app_worker.py
   must differ; otherwise both names are deleted and nothing is recorded;
4. records under `variant` in the task's tasks.json entry: the ruling, the base image (ref, digest, id), the
   image id and both names, the recipe, the file's SHA-256 before and after, its diff, the differing paths and
   `podman image diff`.
The guard: podman-compose's teardown deletes images by the name their container used (`rmi --ignore --force
<name>`); with a second name that only untags, so the image and KEEPER survive. oracle_check.sh runs the
variant only on the recorded image id, restores IMAGE from KEEPER when a teardown removed it, and never builds
or deletes the variant. Delete the variant by hand (`podman rmi IMAGE KEEPER`, then the `variant` record).

Usage: python -I experiments/long_horizon_tasks/uidfix_variant.py      (LH: the cache, default ~/lh-cache)
Exit codes: 0 recorded; 1 a pull, build or export failed; 2 refused (a variant is recorded, or the base image's
id is not the recorded one); 3 disk stop; 5 the identity check failed.
"""

import difflib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

KIT = Path(__file__).resolve().parent
TASKS = KIT / "tasks.json"
TASK = "terminal-bench/vba-userform-port"
LABEL = "vba-userform-port-uidfix"
IMAGE = f"lh-oracle/{LABEL}:verifier"  # no localhost/ prefix: the teardown deletes local images by name
KEEPER = f"lh-keep/{LABEL}:verifier"
FILE = "tests/app_worker.py"
BOUND = "secrets.randbelow(1000000000)"
SED = r"s/secrets\.randbelow(1000000000)/secrets.randbelow(55000)/"  # oracle_check.sh's UIDFIX_SED
RULING = ("Coordinator ruling, Task 2b fix round 1: the labelled reading of D1's one-line verifier change (owner "
          "question 4), for use only if the owner does not run `podman system migrate`; the sub-id range is not "
          "widened.")
STOP_BYTES = 25 * 10**9
NICE = ["taskset", "-c", "0-3", "ionice", "-c", "3", "nice", "-n", "10"]


class Stop(Exception):
    """A refusal with its exit code."""

    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


def recipe(ref):
    """The Containerfile: the pinned image by digest and the one-line change, refused unless one line holds it."""
    return (f"FROM docker.io/{ref}\n"
            f"RUN test \"$(grep -cF '{BOUND}' /{FILE})\" = 1 && sed -i '{SED}' /{FILE}\n")


def tree(stream):
    """Per path of an exported file system: kind, mode, owner, link target and SHA-256; and FILE's text."""
    found, text = {}, None
    with tarfile.open(fileobj=stream, mode="r|") as tar:
        for member in tar:
            path = member.name.removeprefix("./")
            sha = None
            if member.isfile():
                raw = tar.extractfile(member).read()
                sha = hashlib.sha256(raw).hexdigest()
                text = raw.decode() if path == FILE else text
            found[path] = (member.type.decode(), member.mode, member.uid, member.gid, member.linkname, sha)
    return found, text


def differing(before, after):
    """The paths whose entry differs, or that only one tree holds."""
    return sorted(p for p in before.keys() | after.keys() if before.get(p) != after.get(p))


def diff_text(before, after):
    return "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), f"a/{FILE}", f"b/{FILE}",
                                        n=0))


def _run(cmd, code=1):
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode:
        raise Stop(f"{' '.join(cmd[:4])} ... failed ({done.returncode}): {done.stderr.strip()[-800:]}", code)
    return done.stdout.strip()


def _room(need=0):
    free = {m: shutil.disk_usage(m).free for m in ("/", "/home")}
    low = {m: f for m, f in free.items() if f - need < STOP_BYTES}
    if low:
        raise Stop(f"free space under 25 GB (needing {need} more bytes): {low}", 3)


def _image_id(name):
    done = subprocess.run(["podman", "image", "inspect", "-f", "{{.Id}}", name], capture_output=True, text=True)
    return done.stdout.strip() if done.returncode == 0 else None


def base_image(entry):
    """The pinned verifier image in the store (pulled by digest when absent), checked against its recorded id."""
    ref, recorded = entry["verifier_image"], entry["images"]["verifier"]
    if _image_id(ref) is None:
        _room(recorded["compressed"] + recorded["unpacked"])
        _run(NICE + ["podman", "pull", "-q", f"docker.io/{ref}"])
    if _image_id(ref) != recorded["image_id"]:
        raise Stop(f"{ref}: image id {_image_id(ref)}, recorded {recorded['image_id']}", 2)
    return recorded["image_id"]


def build(ref):
    with tempfile.TemporaryDirectory() as ctx:
        Path(ctx, "Containerfile").write_text(recipe(ref))
        _run(NICE + ["podman", "build", "-q", "--pull=never", "--network", "none", "-t", IMAGE, ctx])
    image_id = _image_id(IMAGE)
    _run(["podman", "tag", image_id, KEEPER])
    return image_id


def export_tree(image_id):
    """The image's file system, streamed from a created (never started) container with no network."""
    name = f"lh-variant-{image_id[:12]}-{os.getpid()}"
    _run(["podman", "create", "--pull", "never", "--network", "none", "--name", name, image_id, "true"])
    try:
        export = subprocess.Popen(NICE + ["podman", "export", name], stdout=subprocess.PIPE)
        found = tree(export.stdout)
        if export.wait():
            raise Stop(f"podman export {name} failed ({export.returncode})", 1)
        return found
    finally:
        _run(["podman", "rm", name])


def identity(entry, base_id, image_id):
    """The variant's record, or a refusal (exit 5) when anything but FILE differs from the pinned image."""
    (before, old), (after, new) = export_tree(base_id), export_tree(image_id)
    paths = differing(before, after)
    if paths != [FILE] or old is None or new is None:
        raise Stop(f"the variant differs from the pinned image in {paths[:20]} (expected only {FILE})", 5)
    return {"label": LABEL, "ruling": RULING, "base_ref": entry["verifier_image"],
            "base_digest": entry["images"]["verifier"]["digest"], "base_image_id": base_id, "image": IMAGE,
            "keeper": KEEPER, "image_id": image_id, "recipe": recipe(entry["verifier_image"]), "file": FILE,
            "sha256_before": before[FILE][5], "sha256_after": after[FILE][5], "diff": diff_text(old, new),
            "differing_paths": paths,
            "image_diff": _run(["podman", "image", "diff", base_id, image_id]).splitlines()}


def main():
    data = json.loads(TASKS.read_text())
    entry = next(e for e in data["tasks"] if e["name"] == TASK)
    if entry.get("variant") or _image_id(IMAGE) or _image_id(KEEPER):
        raise Stop(f"a variant is already recorded or built ({IMAGE}); it is built once", 2)
    _room()
    base_id = base_image(entry)
    image_id = build(entry["verifier_image"])
    try:
        entry["variant"] = identity(entry, base_id, image_id)
    except Stop:
        subprocess.run(["podman", "rmi", IMAGE, KEEPER], capture_output=True)
        raise
    TASKS.write_text(json.dumps(data, indent=1) + "\n")
    print(json.dumps({k: entry["variant"][k] for k in ("image", "keeper", "image_id", "sha256_before",
                                                         "sha256_after", "differing_paths")}, indent=1))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Stop as stop:
        print(f"uidfix_variant: {stop}", file=sys.stderr)
        sys.exit(stop.code)
