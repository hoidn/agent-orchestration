"""Zero-spend leak audit of seed-set task packages (plan, "A candidate can reach the fix").

For each package it builds the candidate clone exactly as the harness does (`repos.build_candidate`: a
depth-one fetch of the base commit, the package's `seed/` committed onto it) and checks:

(a) `objects`: the clone holds no object introduced after the base commit. Its only refs, reflog entries and
    shallow roots name the base or the seeded commit; it has no remote, alternates or FETCH_HEAD; every
    object in its store is reachable from HEAD; every object HEAD has beyond the base commit's is the seeded
    commit, a tree, or a blob of a seed file; and none of the change's own commits is present.
(b) `lines`: no 20+ character line the change adds outside `tests/` that is new to the repository (absent
    from every file of the base tree) appears in any seed file.
(c) `scan_fires`: the harness scan (`scan.patterns` + `scan.find_hits`) reports a "solution hash" hit when
    `git show <change>` is planted in a candidate call's stdout; `scan_misses_content` records whether a
    planted copy of the change's diff without its hash produces any hit (the scan matches the hash, not the
    content).
(d) `network`: the candidate sandbox (`experiments/compare/sandbox.py`) does not pass `--unshare-net` to
    bwrap, so a candidate shares the host's network; the audit records the repository's remote host and
    whether the clone names the remote URL. It makes no network request.

A package failing (a) or (b) is rejected (`audit` returns the reasons). `python leak_audit.py --work W`
audits every package in `tasks.jsonl` and writes `leak_audit.json`. Depends on git and grep.
"""

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from experiments.compare import repos, scan, sandbox
from experiments.seed_set import build_tasks as b


def objects_reason(clone, base, seeded, seed_dir, commits):
    """(a): None, or what in the clone's git state leads past the base commit."""
    git = lambda *args: repos.git(clone, *args)  # noqa: E731
    known = {base, seeded}
    refs = {line.split()[1] for line in git("for-each-ref", "--format=%(refname) %(objectname)").splitlines()}
    reflog = set(git("reflog", "--all", "--format=%H").split())
    shallow = set((clone / ".git/shallow").read_text().split()) if (clone / ".git/shallow").exists() else set()
    extras = [name for name in ("FETCH_HEAD", "ORIG_HEAD", "packed-refs", "objects/info/alternates")
              if (clone / ".git" / name).exists()]
    if git("remote") or extras or not refs | reflog <= known or not shallow <= {base}:
        return f"refs, reflog, shallow or extras lead elsewhere: {sorted(refs | reflog | shallow - known)} {extras}"
    stored = set(git("cat-file", "--batch-all-objects", "--batch-check=%(objectname)").split())
    reachable = {line.split()[0] for line in git("rev-list", "--objects", "--all").splitlines()}
    if stored - reachable:
        return f"{len(stored - reachable)} unreachable objects"
    present = [c for c in commits if subprocess.run(["git", "-C", str(clone), "cat-file", "-e", c]).returncode == 0]
    if present:
        return f"the change's commit {present[0][:10]} is in the clone"
    base_objects = {line.split()[0] for line in git("rev-list", "--objects", base).splitlines()}
    seed_blobs = {git("hash-object", str(f)) for f in seed_dir.rglob("*") if f.is_file()}
    for line in git("rev-list", "--objects", seeded).splitlines():
        oid = line.split()[0]
        if oid in base_objects or oid == seeded:
            continue
        kind = git("cat-file", "-t", oid)
        if kind == "commit" or (kind == "blob" and oid not in seed_blobs):
            return f"{kind} {oid[:10]} beyond the base is not seed content"
    return None


def lines_reason(clone, pkg, seed_paths):
    """(b): None, or a line the change adds that is new to the repository and appears in a seed file."""
    upstream = next((pkg / "anchors").glob("*-upstream.diff")).read_text(errors="replace")
    added = b.added_lines(upstream)
    if not added:
        return None
    with tempfile.NamedTemporaryFile("w", suffix=".txt") as patterns:
        patterns.write("".join(line + "\n" for line in added))
        patterns.flush()
        found = subprocess.run(["grep", "-rFo", "--exclude-dir=.git", "-f", patterns.name, "."], cwd=clone,
                               capture_output=True, text=True).stdout.splitlines()
    in_base, in_seed = set(), set()
    for hit in found:
        path, _, text = hit[2:].partition(":")
        (in_seed if path in seed_paths else in_base).add(text)
    leaked = sorted(in_seed - in_base)
    return f"seed file holds a line the change adds: {leaked[0]!r}" if leaked else None


def audit(pkg, work, commits, repo=b.ROOT):
    """[(check, reason)] for checks (a) and (b) that fail on `pkg`'s candidate clone; [] when clean."""
    clone = work / f"audit-{pkg.name}"
    b.remove(clone)
    try:
        base = (pkg / "base_commit").read_text().strip()
        seeded = repos.build_candidate(repo, base, pkg / "seed", clone)
        seed_paths = {p.relative_to(pkg / "seed").as_posix() for p in (pkg / "seed").rglob("*") if p.is_file()}
        found = [("objects", objects_reason(clone, base, seeded, pkg / "seed", commits)),
                 ("lines", lines_reason(clone, pkg, seed_paths))]
        return [(check, reason) for check, reason in found if reason]
    finally:
        b.remove(clone)


def scan_check(commit, work, planted):
    """The harness scan's hit patterns for one candidate call whose stdout is `planted`."""
    records, tree, home = work / "records", work / "tree", work / "home"
    for path in (records / "calls/1", tree / "tmp", home):
        path.mkdir(parents=True, exist_ok=True)
    (records / "calls/1/stdout.txt").write_text(planted)
    (records / "calls/1/stderr.txt").write_text("")
    compiled = scan.patterns(main=b.ROOT, runtime=work / "runtime", solution=commit, home=home)
    return sorted({hit["pattern"] for hit in scan.find_hits(records, tree, 0, home, compiled)})


def network():
    """(d), read from the code and the local git config; no request is made."""
    source = Path(sandbox.__file__).read_text()
    remote = subprocess.run(["git", "-C", str(b.ROOT), "remote", "get-url", "origin"], capture_output=True,
                            text=True).stdout.strip()
    host = remote.split("@")[-1].split("://")[-1].split("/")[0].split(":")[0]
    return {"sandbox_unshares_network": "--unshare-net" in source, "remote_host": host, "url": remote}


def main(work):
    rows = [json.loads(line) for line in (b.HERE / "tasks.jsonl").read_text().splitlines()]
    work.mkdir(parents=True, exist_ok=True)
    net = network()
    remote = net.pop("url")
    result = {"network": net, "packages": {}}
    for row in rows:
        commits = row.get("commits") or [row["commit"]]
        for pid in filter(None, (row["id"], row.get("withheld_id"))):
            if not b.free_ok():
                raise SystemExit("stopped: under 20 GB free on / or /home")
            failed = audit(b.HERE / "tasks" / pid, work, commits)
            result["packages"][pid] = {"failed": failed}
            print(pid, failed or "clean", flush=True)
        with tempfile.TemporaryDirectory(dir=work) as box:
            shown = b.git("show", "--stat", row["commit"])
            diff = (b.HERE / "tasks" / row["id"] / "anchors").glob("*-upstream.diff")
            result["packages"][row["id"]] |= {
                "scan_fires": "solution hash" in scan_check(row["commit"], Path(box) / "a", shown),
                "scan_misses_content": scan_check(row["commit"], Path(box) / "b", next(diff).read_text()) == []}
    result["remote_named_in_a_clone"] = bool(remote) and any(
        subprocess.run(["git", "-C", str(b.ROOT), "grep", "-qF", remote, row["base_commit"]]).returncode == 0
        for row in rows)
    (b.HERE / "leak_audit.json").write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "packages"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work", type=Path, required=True)
    main(parser.parse_args().work.resolve())
