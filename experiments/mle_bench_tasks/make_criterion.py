"""Each tranche's configuration as data (family plan docs/plans/2026-11-15-mle-bench-family-plan.md, M4, M9, Task 4).

Usage (from the repository root):
  python -I experiments/mle_bench_tasks/make_criterion.py write
      writes tranches/screen-cpu/ and tranches/screen-gpu/ (ladder.json, tasks.json and the four links of M4), then
      the manifest of every tranche directory present, manifests/<tranche>.json, and prints each manifest's SHA-256.
      Refused (exit 2) for a tranche whose manifest is frozen.
  python -I experiments/mle_bench_tasks/make_criterion.py stage-two cpu|gpu --export FILE --probe-log FILE
      the stage-two tranche of the class from stage one's export (the launcher's `status --export`) and the live
      probe's request log, by M9's rule; prints the derivation as JSON and, when anything is funded, writes
      tranches/screen-<class>-2/ and its manifest. Refused (exit 2) for an export that cannot decide it.

Inputs, read only: the ladder's experiments/long_horizon_tasks/ladder.json (every field this file does not replace is
copied from it), criterion_fields.json (this family's fields; the only file to edit), family.json (the competitions),
the reviewed launcher ladder.py, loaded privately for its own functions (allowlist, overlay_digest, ORDER_HASH,
_set) and its own load of slot_record.py, and the reviewed manifest.py, loaded privately with M4's four names set.
Writes only under tranches/ and manifests/. Deterministic: the same inputs give the same bytes. No network, no
container, no provider.

What is replaced (replaced_paths): the fields of criterion_fields.json `set` and of the class's `set`; the fields
COMPUTED from family.json and the launcher (the competitions, their caps and overlay digests, the limits file, the
ceiling and starts, the pilot's fallback, the order's hash, the stops' counts, the graded-outcome map, the canary's
SHA-256, the stage group, the pending and filled records); and this family's own pending fields, null until
criterion_fields.json `filled` gives them for the tranche. The ladder's own pending and filled records are kept for
every field not replaced, so a value the ladder's live probe fills there reaches a tranche when it is regenerated.

tasks.json names each image by digest. Until tasks.packages is filled it holds placeholders that are pinned in form
but cannot be real: the registry placeholder.invalid (a reserved name that never resolves) and the all-zero digest,
for the images and for the package. The pending field keeps the tranche from freezing, and the launcher's task
check refuses any package against the all-zero digest.
"""

import argparse
import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent
ROOT = KIT.parents[1]
LADDER_KIT = ROOT / "experiments" / "long_horizon_tasks"
TRANCHES, MANIFESTS = KIT / "tranches", KIT / "manifests"
LINKS = ("harbor_patient.py", "passthrough.py", "relay-compose.yaml", "token_scan.py")  # what the launcher reads by KIT
LINK_TARGET = "../../../long_horizon_tasks/{}"  # from tranches/<tranche>/
ZERO = "0" * 64
PLACEHOLDER_HOST = "placeholder.invalid"
NOT_COVERED_HERE = {"manifests/": "the manifests: a tranche's own SHA-256 is its label, and the others' are no part of it",
                    "tranches/": "the tranches' directories: this tranche's files are covered through EXTERNAL, the "
                                 "others' are no part of its label"}
COMPUTED = ("tasks.list", "tasks.overlay_digests", "harness.host_side.limits_compose", "ceiling.total_usd",
            "ceiling.starts", "schedule.pilot.fallback", "schedule.order.hash", "stops.stops",
            "stops.pauses_for_a_ruling_or_an_input", "readout.graded_outcome.verifiers",
            "readout.contamination_scan.canary_sha256", "pending", "filled", "filled_rule", "stage")
PER_COMPETITION = ("tasks.list", "tasks.qualified", "tasks.load_sensitive", "tasks.overlay_digests", "tasks.extra_hosts",
                   "tasks.withholding", "tasks.packages", "readout.graded_outcome.verifiers",
                   "readout.contamination_scan.canary_exempt_tasks")
SMALL_TRANCHE_RULES = ("infrastructure failures", "cuts")  # stops' entries whose from_starts M9 sets per class
LEAST_COMPETITIONS = 2  # M9-R1: with one, the launcher's smoke and pilot are one slot, listed twice


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read(path):
    return json.loads(Path(path).read_text())


ladder = _load("mle_ladder", LADDER_KIT / "ladder.py")  # the reviewed launcher; nothing in it is changed or set here
FIELDS = _read(KIT / "criterion_fields.json")
FAMILY = _read(KIT / "family.json")


class Refused(Exception):
    """The generator refuses: nothing is written. The message names the input at fault."""


# ---- stage one ----------------------------------------------------------------------------------------------

def own_pending(cls, fields=FIELDS):
    """This family's pending entries that apply to class `cls`, as they are written into a criterion."""
    return [{k: v for k, v in e.items() if k != "classes"} for e in fields["pending"] if cls in e.get("classes", [cls])]


def replaced_paths(cls, fields=FIELDS):
    """Every field of a class's criterion that is not the ladder's, outermost first: a field inside a replaced
    group is not listed again."""
    paths = {*fields["set"], *fields["classes"][cls]["set"], *COMPUTED, *(e["field"] for e in own_pending(cls, fields))}
    return sorted(p for p in paths if not any(p.startswith(q + ".") for q in paths))


def _under(field, paths):
    return any(field == p or field.startswith(p + ".") for p in paths)


def _limits(cls, pids):
    """The limits compose file's content (M4 item 3, M5): the process limit, the shared memory and, for a class with a
    GPU, the device entry the scout report ran through Harbor 0.25.0 on rootless Podman (D5)."""
    limits = FAMILY["classes"][cls]
    text = f'services:\n  main:\n    pids_limit: {pids}\n    shm_size: "{limits["shm_size"]}"\n'
    gpu = '    devices: ["nvidia.com/gpu=all"]\n    security_opt: ["label=disable"]\n'
    return text + (gpu if limits["gpu"] else "")


def _fallback(names, smoke, pilot):
    """The pilot's fallback: the other competitions in tasks.list order, the smoke's last."""
    return [n for n in names if n not in (smoke, pilot)] + ([smoke] if smoke != pilot else [])


def _stops(stops, from_starts):
    """The ladder's stops and pauses with M9's counts for small tranches; every other entry unchanged."""
    def one(entry):
        name = entry.get("stop", entry.get("pause", ""))
        return {**entry, "from_starts": from_starts} if name.startswith(SMALL_TRANCHE_RULES) else entry
    return {"stops": [one(e) for e in stops["stops"]],
            "pauses_for_a_ruling_or_an_input": [one(e) for e in stops["pauses_for_a_ruling_or_an_input"]]}


def _own(doc, tranche, entries, fields):
    """Set each of `entries`' fields: the value criterion_fields.json `filled` gives for the tranche, recorded in
    `filled` with its source, or null, recorded in `pending`. Any earlier record of those fields is dropped."""
    given, names = fields["filled"].get(tranche, {}), {e["field"] for e in entries}
    doc["pending"] = [e for e in doc["pending"] if e["field"] not in names]
    doc["filled"] = [e for e in doc["filled"] if e["field"] not in names]
    for entry in entries:
        fill = given.get(entry["field"])
        ladder._set(doc, entry["field"], copy.deepcopy(fill["value"]) if fill else None)
        (doc["filled"].append({**entry, "source": fill["source"]}) if fill else doc["pending"].append(entry))


def _stage(cls, fields):
    c, tranche = fields["classes"][cls], fields["classes"][cls]["tranche"]
    rule = {**fields["stage_two_rule"], "tranche": c["stage_two"], "extra_starts": c["extra_starts"],
            "live_probe_bound_usd": fields["live_probe_bound_usd"]}
    return {"tranche": tranche, "class": cls, "stage": 1, "ledger": fields["ledger"].format(tranche=tranche),
            "screen_ceiling_usd": fields["screen_ceiling_usd"], "class_ceiling_usd": c["ceiling_usd"],
            "attempts_per_competition": fields["attempts_per_competition"], "stage_two_rule": rule,
            "screen_classes": fields["screen_classes"]}


def stage_one(cls, fields=FIELDS, the_ladder=None):
    """(ladder.json, tasks.json) of class `cls`'s stage-one tranche, as dicts."""
    base = the_ladder or _read(LADDER_KIT / "ladder.json")
    doc, c = copy.deepcopy(base), fields["classes"][cls]
    for field, value in {**fields["set"], **c["set"]}.items():
        ladder._set(doc, field, copy.deepcopy(value))
    rows = [{"name": x["name"], "slug": x["slug"], "class": cls, "feasibility_rank": x["feasibility_rank"],
             "cap_usd": fields["cap_usd"]} for x in FAMILY["candidates"] if x["class"] == cls]
    names = [r["name"] for r in rows]
    doc["tasks"]["list"] = rows
    doc["tasks"]["overlay_digests"] = {n: ladder.overlay_digest(ladder.allowlist(doc, n)) for n in names}
    doc["harness"]["host_side"]["limits_compose"] = {"content": _limits(cls, doc["harness"]["pids_limit"])}
    doc["ceiling"]["total_usd"] = c["ceiling_usd"]
    doc["ceiling"]["starts"] = fields["attempts_per_competition"] * len(names) + c["extra_starts"]
    schedule = doc["schedule"]
    schedule["pilot"]["fallback"] = _fallback(names, schedule["smoke"]["task"], schedule["pilot"]["task"])
    schedule["order"]["hash"] = ladder.ORDER_HASH
    doc["stops"].update(_stops(doc["stops"], c["stops_from_starts"]))
    doc["readout"]["graded_outcome"]["verifiers"] = dict.fromkeys(names, "ctrf")
    canary = FAMILY["canary"].split()[-1]
    doc["readout"]["contamination_scan"]["canary_sha256"] = hashlib.sha256(canary.encode()).hexdigest()
    doc["stage"] = _stage(cls, fields)
    replaced = replaced_paths(cls, fields)
    doc["pending"] = [e for e in base["pending"] if not _under(e["field"], replaced)]
    doc["filled"] = [e for e in base["filled"] if not _under(e["field"], replaced)]
    doc["filled_rule"] = fields["filled_rule"]
    _own(doc, c["tranche"], own_pending(cls, fields), fields)
    _enough(doc)
    return doc, tasks_json(doc)


def _enough(doc):
    """Refused when the tranche has fewer than two competitions, or fewer than two qualified once that is filled
    (M9-R1): the launcher would schedule its smoke and its pilot as one slot, and every export would be refused."""
    qualified = doc["tasks"]["qualified"]
    for what, names in (("competitions", doc["tasks"]["list"]), ("qualified competitions", qualified)):
        if names is not None and len(names) < LEAST_COMPETITIONS:
            raise Refused(f"{doc['stage']['tranche']}: {len(names)} {what}; a tranche needs at least "
                          f"{LEAST_COMPETITIONS} (M9-R1)")


def _placeholder(name):
    return {"digest_4_1_0": "sha256:" + ZERO,
            "environment_image": f"{PLACEHOLDER_HOST}/mle-bench/{name}-agent@sha256:{ZERO}",
            "verifier_image": f"{PLACEHOLDER_HOST}/mle-bench/{name}-verifier@sha256:{ZERO}"}


def tasks_json(doc):
    """tasks.json of a criterion: per competition its package digest and two image references (tasks.packages, or
    placeholders while it is pending) and its withholding result (tasks.withholding, or null). Refused when
    tasks.packages is given but leaves a competition out: the tranche would freeze with a placeholder in it."""
    packages, withholding = doc["tasks"]["packages"], doc["tasks"]["withholding"] or {}
    missing = [t["name"] for t in doc["tasks"]["list"] if packages is not None and t["name"] not in packages]
    if missing:
        raise Refused(f"tasks.packages is filled but names no package for {', '.join(missing)}")
    packages = packages or {}
    return {"about": "Generated by make_criterion.py from the tranche's ladder.json; never edited by hand. The launcher "
                     "finds a competition by the last part of its name and compares its package's digest with "
                     "digest_4_1_0 and the package's two image references with environment_image and verifier_image, as "
                     "strings. digest_4_1_0 keeps the ladder's key name and holds the digest of the package wrap.py built "
                     "(family plan M4). While tasks.packages is pending the three values are placeholders: the registry "
                     f"{PLACEHOLDER_HOST}, which never resolves, and the all-zero digest, which no content has.",
            "tasks": [{"name": f"mle-bench/{t['name']}", "slug": t["slug"], "class": t["class"],
                       **(packages.get(t["name"]) or _placeholder(t["name"])), "withholding": withholding.get(t["name"])}
                      for t in doc["tasks"]["list"]]}


# ---- stage two (M9) -----------------------------------------------------------------------------------------

def probe_usd(path):
    """The live probe's priced usage, summed from its request log as the launcher's prior_usd sums it."""
    return sum(row.get("usd") or 0.0 for row in ladder._jsonl(path))


def _starts(export, one):
    """The export's starts joined to their slots by the reviewed slot_record.py; Refused when it cannot decide."""
    try:
        starts = ladder.slot_record.load(export, one)
    except ladder.slot_record.RecordError as exc:
        raise Refused(f"the export does not fit slot_record.py: {exc}") from None
    end = export["end"]
    if end is None or export["open"]:
        raise Refused("the export's tranche has not ended, or an attempt is open: stage two waits for its end")
    if end["by"] == "stop":
        raise Refused(f"the export's tranche ended in a stop ({end['cause']}): the line stops (family plan M9)")
    return starts


def _no_medal(one, starts, label):
    """M9's rule 1: stage one's qualified competitions with no medal among the current label's observations, in
    feasibility_rank order."""
    tasks = one["tasks"]
    medals = {s["task"] for s in starts if s["label"] == label and s["success"]}
    names = tasks["qualified"] if tasks["qualified"] is not None else [t["name"] for t in tasks["list"]]
    rank = {t["name"]: t["feasibility_rank"] for t in tasks["list"]}
    return sorted((n for n in names if n not in medals), key=rank.get)


def _money(one, starts, probe):
    """(m, committed, ceiling) of M9's rules 2 and 3: the mean cost of a counted start, what the launcher committed
    (every start that counts against the ceiling, of every label, and the probe) and the ceiling it leaves."""
    classes = one["classification"]["classes"]
    counted = [s["usd"] for s in starts if classes[s["class"]]["starts"]]
    if not counted:
        raise Refused("the export has no start that counts: stage two's mean cost per start is undefined")
    committed = round(sum(s["usd"] for s in starts if classes[s["class"]]["usd"]) + probe, 6)
    return round(sum(counted) / len(counted), 6), committed, round(one["stage"]["class_ceiling_usd"] - committed, 6)


def _size(one, starts, label, probe, fields):
    """M9's rules 1 to 3: the competitions with no medal, the ceiling left, and the first k of them it funds; k is
    at least two or zero (M9-R1)."""
    no_medal, (m, committed, ceiling) = _no_medal(one, starts, label), _money(one, starts, probe)
    last = one["caps"]["cap_usd"] + one["ceiling"]["reservation"]["margin_usd"] + fields["live_probe_bound_usd"]
    k = max((j for j in range(LEAST_COMPETITIONS, len(no_medal) + 1) if (3 * j - 1) * m + last <= ceiling),
            default=0)
    return {"no_medal": no_medal, "funded": no_medal[:k], "not_funded": no_medal[k:], "mean_usd_per_start": m,
            "committed_usd": committed, "live_probe_usd": probe, "k": k, "ceiling_usd": ceiling}


def _only(value, keep):
    if isinstance(value, dict):
        return {k: v for k, v in value.items() if k in keep}
    if isinstance(value, list):
        return [x for x in value if (x["name"] if isinstance(x, dict) else x) in keep]
    return value


def _stage_two(one, derivation, cls, fields):
    """Stage one's criterion with M9's fields of stage two: everything else is stage one's. Refused for fewer than
    two funded competitions (M9-R1)."""
    two, c, funded = copy.deepcopy(one), fields["classes"][cls], derivation["funded"]
    if len(funded) < LEAST_COMPETITIONS:
        raise Refused(f"{c['stage_two']}: {len(funded)} funded competitions; a tranche needs at least "
                      f"{LEAST_COMPETITIONS} (M9-R1)")
    for field in PER_COMPETITION:
        ladder._set(two, field, _only(ladder._at(two, field), set(funded)))
    two["ceiling"]["total_usd"] = derivation["ceiling_usd"]
    two["ceiling"]["starts"] = fields["attempts_per_competition"] * len(funded) + c["extra_starts"]
    smoke, pilot = funded[0], funded[1]
    two["schedule"]["smoke"]["task"], two["schedule"]["pilot"]["task"] = smoke, pilot
    two["schedule"]["pilot"]["fallback"] = _fallback([t["name"] for t in two["tasks"]["list"]], smoke, pilot)
    two["stage"] = {**one["stage"], "tranche": c["stage_two"], "stage": 2,
                    "ledger": fields["ledger"].format(tranche=c["stage_two"]), "derived_from": derivation}
    _own(two, c["stage_two"], [e for e in own_pending(cls, fields) if e["field"] in fields["per_tranche"]], fields)
    return two


def derive_stage_two(cls, export, export_sha256, probe, stage_one=None, fields=FIELDS):
    """(derivation, ladder.json, tasks.json) of class `cls`'s stage-two tranche, from stage one's criterion (the
    committed one unless given), its export (a dict in slot_record.py's layout) with the SHA-256 of its file, and
    the live probe's usage; the last two are None when nothing is funded. Refused when the export cannot decide."""
    one = stage_one or _read(TRANCHES / fields["classes"][cls]["tranche"] / "ladder.json")
    derivation = {"export_label": export["label"], "export_sha256": export_sha256,
                  **_size(one, _starts(export, one), export["label"], probe, fields)}
    if not derivation["funded"]:
        return derivation, None, None
    two = _stage_two(one, derivation, cls, fields)
    return derivation, two, tasks_json(two)


# ---- files --------------------------------------------------------------------------------------------------

def _dump(doc):
    return json.dumps(doc, indent=1, ensure_ascii=False) + "\n"


def write_tranche(directory, doc, tasks):
    """The tranche's directory: ladder.json, tasks.json and the four links of M4 into the reviewed kit."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ladder.json").write_text(_dump(doc))
    (directory / "tasks.json").write_text(_dump(tasks))
    for name in LINKS:
        link = directory / name
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(LINK_TARGET.format(name))


def write_stage_one(root=TRANCHES):
    for cls in ("cpu", "gpu"):
        write_tranche(Path(root) / FIELDS["classes"][cls]["tranche"], *stage_one(cls))


def manifest_module(tranche):
    """A private load of the reviewed manifest.py with M4's four names set for the tranche: KIT this family's kit,
    MANIFEST manifests/<tranche>.json, NOT_COVERED the ladder's and manifests/ and tranches/, EXTERNAL every path the
    ladder's own manifest lists (from the unmodified module) and every file of the tranche's directory."""
    module = _load(f"mle_manifest_{tranche}", LADDER_KIT / "manifest.py")
    theirs = _load("mle_manifest_ladder", LADDER_KIT / "manifest.py").files()
    own = sorted(p.relative_to(ROOT).as_posix() for p in (TRANCHES / tranche).iterdir())
    module.KIT, module.MANIFEST = KIT, MANIFESTS / f"{tranche}.json"
    module.NOT_COVERED = {**module.NOT_COVERED, **NOT_COVERED_HERE}
    module.EXTERNAL = (*sorted(theirs), *own)
    return module


def _frozen(tranche):
    path = MANIFESTS / f"{tranche}.json"
    return path.is_file() and _read(path)["frozen"]


def write_manifest(tranche):
    MANIFESTS.mkdir(exist_ok=True)
    if manifest_module(tranche).write(False) != 0:
        raise Refused(f"{tranche}: the manifest was not written")


def write_all():
    """`write`: the stage-one tranches, then the manifest of every tranche directory present."""
    frozen = [t for t in (FIELDS["classes"][c]["tranche"] for c in ("cpu", "gpu")) if _frozen(t)]
    if frozen:
        raise Refused(f"a frozen manifest: {', '.join(frozen)} is not rewritten")
    write_stage_one()
    for directory in sorted(p for p in TRANCHES.iterdir() if p.is_dir()):
        write_manifest(directory.name)


def stage_two(cls, export_path, probe_log):
    """`stage-two`: the derivation, and when anything is funded the tranche's directory and its manifest."""
    tranche = FIELDS["classes"][cls]["stage_two"]
    if _frozen(tranche):
        raise Refused(f"a frozen manifest: {tranche} is not rewritten")
    raw = Path(export_path).read_bytes()
    export = ladder.slot_record.read(Path(export_path))
    derivation, doc, tasks = derive_stage_two(cls, export, hashlib.sha256(raw).hexdigest(), probe_usd(probe_log))
    print(json.dumps({"tranche": tranche, **derivation}, indent=1))
    if doc is not None:
        write_tranche(TRANCHES / tranche, doc, tasks)
        write_manifest(tranche)


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("write")
    two = sub.add_parser("stage-two")
    two.add_argument("cls", choices=sorted(FIELDS["classes"]))
    two.add_argument("--export", required=True, type=Path)
    two.add_argument("--probe-log", required=True, type=Path)
    args = p.parse_args(argv)
    try:
        write_all() if args.command == "write" else stage_two(args.cls, args.export, args.probe_log)
    except Refused as exc:
        print(f"make_criterion.py: refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
