"""Tabulate the oracle check: per task label, the reference's passes and the untouched environment's passes.

Reads what oracle_check.sh writes: <jobs>/<agent>/<label>/<round>/ with meta.txt, samples and the harness's
<job>/<trial>/result.json (Harbor 0.25.0); agent is oracle (the reference), nop (untouched) or install (the CLI).
A label passes when every reference run earns reward 1 and no untouched run does.

Usage: python -I summarize.py <jobs> [--write <records.json>]
  prints one line per label: reference k of n, untouched k of n, install, wall time, load at start and end;
  --write also writes one JSON line per trial (outcomes, timings, load, images, digests, connections the egress
  sidecar refused, by address; no log text) and puts each task's counts, under the records file's stem, and its
  overlay digest into tasks.json.
"""

import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

TASKS = Path(__file__).resolve().parent / "tasks.json"
MODIFIED = "-uidfix"  # the labelled modified task of owner question 4 (oracle_check.sh)


def _seconds(phase):
    if not phase or not phase.get("finished_at"):
        return None
    start, end = (datetime.fromisoformat(phase[k]) for k in ("started_at", "finished_at"))
    return round((end - start).total_seconds())


def _floats(text):
    return [float(x) for x in text.split()] if text else None


def parse_meta(text):
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)


def _role(name):
    return ("verifier " if "__verifier__" in name else "agent ") + ("sidecar" if "sidecar" in name else "main")


def _named(rest, trial):
    """A sample line's container name and fields, and whether it is the trial's own (all are, without a trial)."""
    name, *fields = rest.split(" ")
    return name, dict(f.split("=", 1) for f in fields), not trial or name.startswith(trial.lower() + "__")


def _container(acc, rest, trial):
    name, values, own = _named(rest, trial)
    if not own:
        return
    box = acc["boxes"].setdefault(name, {"role": _role(name), "peak_bytes": None, "affinity": set()})
    if values.get("peak"):
        box["peak_bytes"] = max(box["peak_bytes"] or 0, int(values["peak"]))
    box["affinity"] |= set(filter(None, values.get("affinity", "").split("|")))


def _policy(acc, rest, trial):
    name, values, own = _named(rest, trial)
    seen = {"role": _role(name), "mode": values["mode"].replace("_", " "), "hosts": int(values["hosts"])}
    if own and seen not in acc["policies"]:
        acc["policies"].append(seen)


def _free_min(frees):
    return {"/": min(f[0] for f in frees), "/home": min(f[1] for f in frees)} if frees else None


_SAMPLE = {"load": lambda acc, rest, trial: acc["load"].append(float(rest)),
           "free": lambda acc, rest, trial: acc["free"].append([int(x) for x in rest.split()]),
           "container": _container, "policy": _policy}


def parse_samples(text, trial=None):
    """The highest 1-minute load, the lowest free space, per container its peak memory and affinities, and the
    network policies the sidecars reported (`network-policy show`), each once, in the order seen.

    The follower samples every container of the label; given the trial's name, only that trial's are kept."""
    acc = {"load": [], "free": [], "boxes": {}, "policies": []}
    for kind, _, rest in (line.partition(" ") for line in text.splitlines()):
        if kind in _SAMPLE:
            _SAMPLE[kind](acc, rest, trial)
    boxes = sorted(acc["boxes"].items(), key=lambda kv: (kv[1]["role"], kv[0]))
    return {"load_max": max(acc["load"], default=None), "free_min": _free_min(acc["free"]),
            "policies": acc["policies"], "containers": [b | {"affinity": sorted(b["affinity"])} for _, b in boxes]}


def parse_egress(texts):
    """Connections the egress sidecar refused ("bypass"), and their addresses: the log names no host."""
    dst, refused = {}, []
    for line in (x for text in texts for x in text.splitlines() if x.startswith("{")):
        event = json.loads(line)
        if event.get("dst"):
            dst[event.get("sid")] = event["dst"]
        elif event.get("msg") == "bypass":
            refused.append(event.get("sid"))
    return {"refused": len(refused), "addresses": sorted({dst.get(sid, "unknown") for sid in refused})}


def _verifier_files(trial):
    out = trial / "verifier" / "test-stdout.txt"
    ctrf = trial / "verifier" / "ctrf.json"
    summary = json.loads(ctrf.read_text())["results"]["summary"] if ctrf.exists() else None
    return ({"sha256": hashlib.sha256(out.read_bytes()).hexdigest(), "bytes": out.stat().st_size}
            if out.exists() else None,
            {k: summary[k] for k in ("tests", "passed", "failed", "skipped")} if summary else None)


def _outcome(round_dir):
    """The harness's trial result of one round: reward, rewards, error, phase seconds and verifier files."""
    results = sorted(round_dir.glob("*/*/result.json"))
    if len(results) > 1:
        raise ValueError(f"{round_dir}: {len(results)} trials, expected one")
    if not results:
        return {"trial": None, "reward": None, "rewards": None, "error": "no result.json", "verifier_output": None,
                "ctrf": None}
    result = json.loads(results[0].read_text())
    rewards = (result.get("verifier_result") or {}).get("rewards")
    output, ctrf = _verifier_files(results[0].parent)
    return {"trial": results[0].parent.name, "reward": (rewards or {}).get("reward"), "rewards": rewards,
            "error": (result.get("exception_info") or {}).get("exception_type"),
            "env_s": _seconds(result.get("environment_setup")), "agent_setup_s": _seconds(result.get("agent_setup")),
            "agent_s": _seconds(result.get("agent_execution")), "verify_s": _seconds(result.get("verifier")),
            "verifier_output": output, "ctrf": ctrf}


def trial_record(round_dir):
    """One trial of the oracle check, from its round directory."""
    round_dir = Path(round_dir)
    meta = parse_meta((round_dir / "meta.txt").read_text())
    samples = round_dir / "samples"
    record = {"label": meta["label"], "task": meta["label"].removesuffix(MODIFIED), "agent": meta["agent"],
              "round": int(meta["round"]), "rc": int(meta["rc"]) if "rc" in meta else None,
              "wall_s": int(meta["wall_s"]) if "wall_s" in meta else None,
              "load_start": _floats(meta.get("load_start")), "load_end": _floats(meta.get("load_end")),
              "gate": meta.get("gate"), "cpus": meta.get("cpus"), "overlay_sha256": meta.get("overlay_sha256"),
              "images": dict(x.split(":", 1) for x in meta.get("images", "").split()),
              "wall_bound_s": int(meta["wall_bound_s"]) if "wall_bound_s" in meta else None,
              "stop": meta.get("stop") or meta.get("disk_stop")}
    record |= {"env_s": None, "agent_setup_s": None, "agent_s": None, "verify_s": None} | _outcome(round_dir)
    own = f"egress-{(record['trial'] or '').lower()}__*"
    record["egress"] = parse_egress(p.read_text() for p in sorted(round_dir.glob(own)))
    return record | parse_samples(samples.read_text() if samples.exists() else "", record["trial"])


def verdict(r):
    """A graded run's outcome: "pass" (reward exactly 1), "fail" (reward exactly 0), or why it is no evidence.

    A run is evidence only without an error or a stop and with the verifier's tests run (its output kept and,
    where it wrote a CTRF report, at least one test in it); D1 counts reward 1 and reward 0 only."""
    if r.get("stop"):
        return "stopped: " + r["stop"]
    if r["error"]:
        return r["error"]
    if r["reward"] is None:
        return "no reward"
    if r["verifier_output"] is None or (r["ctrf"] is not None and r["ctrf"]["tests"] == 0):
        return "no tests ran"
    return {1: "pass", 0: "fail"}.get(r["reward"], f"reward {r['reward']}")


def _errors(runs):
    """Every run that is no evidence, and an install that failed."""
    graded = [f"{r['agent']} {r['round']}: {verdict(r)}" for r in runs
              if r["agent"] != "install" and verdict(r) not in ("pass", "fail")]
    return graded + [f"install {r['round']}: {r['error']}" for r in runs if r["agent"] == "install" and r["error"]]


def _of(runs, agent):
    return [r for r in runs if r["agent"] == agent]


def _install(runs):
    installs = _of(runs, "install")
    return (installs[0]["error"] or "ok") if installs else None


def _label_counts(label, runs):
    ref, nop = _of(runs, "oracle"), _of(runs, "nop")
    ref_v, nop_v = [verdict(r) for r in ref], [verdict(r) for r in nop]
    qualifies = set(ref_v) == {"pass"} and set(nop_v) == {"fail"}  # both halves present, every run evidence
    return {"label": label, "task": runs[0]["task"], "reference": [ref_v.count("pass"), len(ref)],
            "untouched": [nop_v.count("pass"), len(nop)], "install": _install(runs), "errors": _errors(runs),
            "passes": qualifies, "wall_s": {a: [r["wall_s"] for r in _of(runs, a)] for a in ("oracle", "nop")},
            "load": [[r["load_start"], r["load_end"]] for r in ref + nop]}


def counts(records):
    """Per label: reference passes of runs, untouched passes (reward 1) of runs, install outcome, every run that
    is no evidence, whether the label qualifies (every reference run passes, every untouched run earns exactly 0,
    none is missing), wall times and loads."""
    by_label = defaultdict(list)
    for r in records:
        by_label[r["label"]].append(r)
    return {label: _label_counts(label, runs) for label, runs in sorted(by_label.items())}


def _load(pair):
    start, end = pair
    return f"{start[0] if start else '?'}-{end[0] if end else '?'}"


def table(by_label):
    lines = ["label | reference | untouched | install | wall s (oracle; nop) | load 1-min start-end | errors | verdict"]
    for c in by_label.values():
        walls = "; ".join(",".join(str(w) for w in c["wall_s"].get(a, [])) for a in ("oracle", "nop"))
        lines.append(" | ".join([c["label"], "reference {} of {}".format(*c["reference"]),
                                 "untouched {} of {}".format(*c["untouched"]), str(c["install"]), walls,
                                 " ".join(_load(p) for p in c["load"]), "; ".join(c["errors"]) or "-",
                                 "qualifies" if c["passes"] else "does not qualify"]))
    return lines


def fill_tasks(tasks, records, key):
    """Put each task's counts (under key) and its one overlay digest into the tasks.json data."""
    by_label = counts(records)
    keep = ("label", "reference", "untouched", "install", "errors", "passes")
    for entry in tasks["tasks"]:
        task = entry["name"].rsplit("/", 1)[-1]
        mine = [r for r in records if r["task"] == task]
        if not mine:
            continue
        digests = {r["overlay_sha256"] for r in mine}
        if len(digests) != 1:
            raise ValueError(f"{task}: overlay digests {sorted(map(str, digests))}, expected one")
        entry["overlay_digest"] = digests.pop()
        entry["oracle_evidence"] = (entry.get("oracle_evidence") or {}) | {
            key: [{k: c[k] for k in keep} for c in by_label.values() if c["task"] == task]}
    return tasks


def main(argv):
    jobs, write = Path(argv[0]), (Path(argv[2]) if argv[1:2] == ["--write"] else None)
    records = sorted((trial_record(meta.parent) for meta in jobs.glob("*/*/*/meta.txt")),
                     key=lambda r: (r["label"], r["agent"], r["round"]))
    print("\n".join(table(counts(records))))
    if write:
        write.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in records))
        TASKS.write_text(json.dumps(fill_tasks(json.loads(TASKS.read_text()), records, write.stem), indent=1) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:])
