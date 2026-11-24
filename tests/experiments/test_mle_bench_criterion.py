"""The MLE-bench family's configuration as data (family plan docs/plans/2026-11-15-mle-bench-family-plan.md, Task 4).

`experiments/mle_bench_tasks/make_criterion.py` generates each tranche's `ladder.json` and `tasks.json` from the
ladder's reviewed `experiments/long_horizon_tasks/ladder.json` and this family's `criterion_fields.json`, the stage-two
tranche from a stage-one export by M9's rule, and each tranche's manifest through a private load of the reviewed
`manifest.py` with M4's four names replaced. These tests hold the generated files to the plan's figures, to the
ladder's unreplaced groups, and to what the reviewed launcher reads. No container, no network, no provider.
"""

import copy
import getpass
import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "experiments" / "mle_bench_tasks"
LADDER_KIT = ROOT / "experiments" / "long_horizon_tasks"
TABLE = ROOT / "orchestrator" / "providers" / "price_table.json"
MODEL = "claude-haiku-5-5"
STAGE_ONE = ("screen-cpu", "screen-gpu")
TRANCHE_NAMES = ("screen-cpu", "screen-cpu-2", "screen-gpu", "screen-gpu-2", "place-cpu", "place-gpu")
LINKS = ("harbor_patient.py", "passthrough.py", "relay-compose.yaml", "token_scan.py")
TYPE_NAMES = {"array", "object", "string", "sha256", "scalar", "number"}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mc = _load("mle_make_criterion_test", KIT / "make_criterion.py")
ladder = _load("mle_ladder_criterion_test", LADDER_KIT / "ladder.py")  # a private load: its names may be set here
ladder_manifest = _load("mle_ladder_manifest_test", LADDER_KIT / "manifest.py")
slot_record = _load("mle_slot_record_test", LADDER_KIT / "slot_record.py")


def _read(path):
    return json.loads(Path(path).read_text())


def _the_ladder():
    return _read(LADDER_KIT / "ladder.json")


def _criterion(tranche):
    return _read(KIT / "tranches" / tranche / "ladder.json")


def _tasks(tranche):
    return _read(KIT / "tranches" / tranche / "tasks.json")


def _names(criterion):
    return [t["name"] for t in criterion["tasks"]["list"]]


def _stand_ins(criterion, seed="a stand-in seed"):
    """The criterion with stand-ins for the pending fields the schedule reads, as a rehearsal gives them."""
    doc = copy.deepcopy(criterion)
    doc["tasks"]["qualified"] = _names(doc)
    doc["tasks"]["load_sensitive"] = []
    doc["schedule"]["order"]["seed"] = seed
    return doc


def _schedule(criterion):
    ladder.EFFORTS = tuple(criterion["attempt"]["efforts"])  # M4: the wrapper sets EFFORTS to the tranche's
    return ladder.schedule(_stand_ins(criterion))


def _drop(doc, path):
    *parents, last = path.split(".")
    for key in parents:
        doc = doc.get(key, {})
    doc.pop(last, None)


# ---- the generator's output is the committed output ---------------------------------------------------------

def _tree(root):
    """{relative path: ("link", target) or ("file", bytes)} of every entry under root."""
    out = {}
    for path in sorted(Path(root).rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            out[rel] = ("link", os.readlink(path))
        elif path.is_file():
            out[rel] = ("file", path.read_bytes())
    return out


def test_the_generator_reproduces_every_committed_tranche_directory_byte_for_byte(tmp_path):
    mc.write_stage_one(tmp_path)
    assert {t: _tree(tmp_path / t) for t in STAGE_ONE} == {t: _tree(KIT / "tranches" / t) for t in STAGE_ONE}


def test_every_committed_manifest_is_the_reviewed_manifest_module_s_write_under_m4_s_names(tmp_path):
    written = {}
    for tranche in STAGE_ONE:
        module = mc.manifest_module(tranche)
        module.MANIFEST = tmp_path / f"{tranche}.json"
        assert module.write(False) == 0
        written[tranche] = module.MANIFEST.read_bytes()
    assert written == {t: (KIT / "manifests" / f"{t}.json").read_bytes() for t in STAGE_ONE}


def test_the_committed_manifests_check_clean_under_m4_s_names():
    assert [mc.manifest_module(t).check() for t in STAGE_ONE] == [0, 0]


# ---- what the generator replaces, and what stays the ladder's -----------------------------------------------

REPLACED = (
    "criterion", "attempt.efforts", "harness.agent_timeout", "harness.rule", "harness.host_side.image_name",
    "harness.host_side.limits_compose", "tasks", "caps", "ceiling.source", "ceiling.total_usd", "ceiling.starts",
    "ceiling.launch_if", "ceiling.ends", "host.concurrency.pilot", "host.concurrency.rounds", "host.disk_plan",
    "host.disk_plan_rule", "schedule.source", "schedule.smoke.task", "schedule.smoke.effort",
    "schedule.smoke.fallback_rule", "schedule.pilot.task", "schedule.pilot.efforts", "schedule.pilot.together",
    "schedule.pilot.concurrency", "schedule.pilot.becomes", "schedule.pilot.fallback", "schedule.pilot.fallback_rule", "schedule.pilot.meters",
    "schedule.rounds", "schedule.blocks_per_round", "schedule.block", "schedule.order.seed", "schedule.order.hash",
    "schedule.skipped", "schedule.tail", "schedule.no_top_up", "stops.stops", "stops.pauses_for_a_ruling_or_an_input",
    "label.source", "label.is", "label.pooling", "readout.graded_outcome.verifiers", "readout.contamination_scan.terms",
    "readout.contamination_scan.canary_sha256", "readout.contamination_scan.canary_exempt_tasks",
    "readout.contamination_scan.canary_identifier", "readout.fall_bound.seed", "pending", "filled", "filled_rule",
    "stage")
UNCHANGED_GROUPS = ("price", "classification", "credential", "refusal", "usage_limits", "paid_usage", "settlement",
                    "allowance_guard", "network")


@pytest.mark.parametrize("tranche", STAGE_ONE)
def test_every_field_the_generator_does_not_replace_equals_the_ladder_s(tranche):
    ours, theirs = _criterion(tranche), _the_ladder()
    for path in REPLACED:
        _drop(ours, path)
        _drop(theirs, path)
    assert ours == theirs


@pytest.mark.parametrize("tranche", STAGE_ONE)
def test_the_groups_m4_names_as_copied_are_the_ladder_s_whole(tranche):
    ours, theirs = _criterion(tranche), _the_ladder()
    assert {g: ours[g] for g in UNCHANGED_GROUPS} == {g: theirs[g] for g in UNCHANGED_GROUPS}


@pytest.mark.parametrize("tranche", STAGE_ONE)
def test_the_generator_replaces_exactly_the_named_fields(tranche):
    assert sorted(mc.replaced_paths(_criterion(tranche)["stage"]["class"])) == sorted(REPLACED)


# ---- model, efforts, money, counts (M1, M9) -----------------------------------------------------------------

OTHER_MODEL = re.compile(r"(?i)\b(?:fable|opus|sonnet|haiku|gpt|gemini|luna|sol|astra|terra)\b"
                         r"|claude-(?!code\b)[\w.-]+")  # the ladder's own scan (test_long_horizon_ladder.py)


@pytest.mark.parametrize("tranche", STAGE_ONE)
def test_the_model_is_bound_and_no_other_model_string_occurs_in_any_file_of_the_tranche(tranche):
    files = [*(KIT / "tranches" / tranche).glob("*.json"), KIT / "manifests" / f"{tranche}.json"]
    texts = [path.read_text() for path in files]
    known = set(_read(TABLE)["models"]) - {MODEL}
    found = [m.group(0) for text in texts for m in OTHER_MODEL.finditer(text.replace(MODEL, ""))]
    criterion = _criterion(tranche)
    assert (criterion["attempt"]["model"], criterion["harness"]["model_argument"], found,
            sorted(m for m in known for text in texts if m in text)) == (MODEL, f"anthropic/{MODEL}", [], [])


@pytest.mark.parametrize("tranche", STAGE_ONE)
def test_the_screen_runs_m1_s_one_effort_within_the_ladder_s_three(tranche):
    criterion = _criterion(tranche)
    efforts = {criterion["schedule"]["smoke"]["effort"], *criterion["attempt"]["efforts"],
               *criterion["schedule"]["pilot"]["efforts"], *(s["effort"] for s in _schedule(criterion))}
    assert (efforts, efforts <= set(_the_ladder()["attempt"]["efforts"])) == ({"medium"}, True)


@pytest.mark.parametrize("tranche", STAGE_ONE)
def test_the_launcher_s_criterion_check_passes_under_the_tranche_s_efforts(tranche):
    criterion = _criterion(tranche)
    ladder.EFFORTS = tuple(criterion["attempt"]["efforts"])
    assert ladder._criterion_refusal(criterion) is None


M9 = {"screen-cpu": {"competitions": 3, "slots": 9, "repeated": [], "starts": 11, "cap": 8.0, "ceiling": 50.0,
                     "concurrency": {"smoke": 1, "pilot": 1, "rounds": 3}, "smoke": "leaf", "pilot": "birds"},
      "screen-gpu": {"competitions": 10, "slots": 30, "repeated": [], "starts": 34, "cap": 8.0, "ceiling": 150.0,
                     "concurrency": {"smoke": 1, "pilot": 1, "rounds": 1}, "smoke": "patent", "pilot": "tweet"}}


@pytest.mark.parametrize("tranche", STAGE_ONE)
def test_the_caps_ceilings_starts_slots_and_concurrency_are_m9_s(tranche):
    criterion = _criterion(tranche)
    slots = [ladder.slot_id(e) for e in _schedule(criterion)]
    concurrency = {k: criterion["host"]["concurrency"][k] for k in ("smoke", "pilot", "rounds")}
    assert {"competitions": len(criterion["tasks"]["list"]), "slots": len(slots),
            "repeated": sorted({s for s in slots if slots.count(s) > 1}),
            "starts": criterion["ceiling"]["starts"], "cap": {t["cap_usd"] for t in criterion["tasks"]["list"]}.pop(),
            "ceiling": criterion["ceiling"]["total_usd"], "concurrency": concurrency,
            "smoke": criterion["schedule"]["smoke"]["task"], "pilot": criterion["schedule"]["pilot"]["task"]} == M9[tranche]


def test_one_cap_serves_every_competition():
    assert {t["cap_usd"] for tr in STAGE_ONE for t in _criterion(tr)["tasks"]["list"]} == {8.0}


def test_the_screen_s_two_class_ceilings_sum_to_200_and_no_ceiling_is_above_200():
    ceilings = [_criterion(t)["ceiling"]["total_usd"] for t in STAGE_ONE]
    stated = {_criterion(t)["stage"]["screen_ceiling_usd"] for t in STAGE_ONE}
    assert (sum(ceilings), max(ceilings) <= 200, stated) == (200.0, True, {200.0})


def test_stage_one_completes_only_under_m9_s_mean_cost_per_attempt():
    """M9: stage one completes only if its attempts average under about USD 5.05 (CPU) or 4.85 (GPU)."""
    def bound(criterion):
        slots, rule = M9[criterion["stage"]["tranche"]]["slots"], criterion["stage"]["stage_two_rule"]
        last = criterion["tasks"]["list"][0]["cap_usd"] + criterion["ceiling"]["reservation"]["margin_usd"]
        return round((criterion["ceiling"]["total_usd"] - rule["live_probe_bound_usd"] - last) / (slots - 1), 2)
    assert [bound(_criterion(t)) for t in STAGE_ONE] == [5.07, 4.85]


@pytest.mark.parametrize("tranche", STAGE_ONE)
def test_the_free_disk_floor_is_the_ladder_s_20_gb(tranche):
    criterion = _criterion(tranche)
    disk = next(s for s in criterion["stops"]["stops"] if s["stop"] == "free disk")
    assert (criterion["host"]["disk_stop_free_gb"], disk["under_gb"], _the_ladder()["host"]["disk_stop_free_gb"]) == (
        20, 20, 20)


@pytest.mark.parametrize("tranche, from_starts", [("screen-cpu", 5), ("screen-gpu", 10)])
def test_the_stops_are_the_ladder_s_with_m9_s_counts_for_small_tranches(tranche, from_starts):
    ours, theirs = _criterion(tranche)["stops"], _the_ladder()["stops"]
    changed = [(a.get("stop") or a.get("pause"), a["from_starts"])
               for a, b in zip(ours["stops"] + ours["pauses_for_a_ruling_or_an_input"],
                               theirs["stops"] + theirs["pauses_for_a_ruling_or_an_input"]) if a != b]
    restored = [{**a, "from_starts": b["from_starts"]} if "from_starts" in a else a
                for a, b in zip(ours["stops"], theirs["stops"])]
    assert (changed, restored, len(ours["pauses_for_a_ruling_or_an_input"])) == (
        [("infrastructure failures other than cuts", from_starts), ("cuts", from_starts)], theirs["stops"],
        len(theirs["pauses_for_a_ruling_or_an_input"]))


@pytest.mark.parametrize("tranche", STAGE_ONE)
def test_each_competition_is_mapped_to_ctrf(tranche):
    criterion = _criterion(tranche)
    assert criterion["readout"]["graded_outcome"]["verifiers"] == dict.fromkeys(_names(criterion), "ctrf")


def _limits(tranche):
    return yaml.safe_load(_criterion(tranche)["harness"]["host_side"]["limits_compose"]["content"])["services"]["main"]


def test_a_gpu_tranche_s_limits_file_names_the_device_and_its_attempts_run_one_at_a_time():
    gpu = _limits("screen-gpu")
    assert ((gpu["devices"], gpu["security_opt"], gpu["shm_size"], gpu["pids_limit"]),
            {_criterion("screen-gpu")["host"]["concurrency"][k] for k in ("smoke", "pilot", "rounds")}) == (
        (["nvidia.com/gpu=all"], ["label=disable"], "8g", 4096), {1})


def test_a_cpu_tranche_s_limits_file_names_no_device_and_sets_shared_memory():
    assert _limits("screen-cpu") == {"pids_limit": 4096, "shm_size": "4g"}


@pytest.mark.parametrize("tranche", STAGE_ONE)
def test_the_schedule_is_the_smoke_the_pilot_then_three_rounds_of_one_slot_per_competition(tranche):
    criterion = _criterion(tranche)
    entries = _schedule(criterion)
    head = [(e["kind"], e["task"]) for e in entries[:2]]
    rounds = {(e["round"], e["task"]) for e in entries}
    assert (head, len({ladder.slot_id(e) for e in entries}), len(entries), rounds) == (
        [("smoke", M9[tranche]["smoke"]), ("pilot", M9[tranche]["pilot"])], M9[tranche]["slots"],
        M9[tranche]["slots"], {(r, t) for r in (1, 2, 3) for t in _names(criterion)})


@pytest.mark.parametrize("tranche, fallback", [("screen-cpu", ["textnorm-ru", "leaf"]),
                                                ("screen-gpu", ["essay2", "chaii", "jigsaw", "lmsys", "whale",
                                                                "petfinder", "kuzushiji", "cassava", "patent"])])
def test_the_pilot_falls_back_to_the_class_s_other_competitions_in_order_and_to_the_smoke_last(tranche, fallback):
    criterion = _criterion(tranche)
    pilot = criterion["schedule"]["pilot"]
    without = _stand_ins(criterion)
    without["tasks"]["qualified"] = [criterion["schedule"]["smoke"]["task"]]
    assert (pilot["fallback"], ladder.pilot_task(without)) == (fallback, criterion["schedule"]["smoke"]["task"])


def test_the_order_hash_is_the_launcher_s():
    assert {_criterion(t)["schedule"]["order"]["hash"] for t in STAGE_ONE} == {ladder.ORDER_HASH}


@pytest.mark.parametrize("tranche", STAGE_ONE)
def test_each_overlay_digest_is_the_launcher_s_digest_of_the_ladder_s_allowlist(tranche):
    criterion = _criterion(tranche)
    assert criterion["tasks"]["overlay_digests"] == {
        t: ladder.overlay_digest(ladder.allowlist(criterion, t)) for t in _names(criterion)} == dict.fromkeys(
        _names(criterion), next(iter(_the_ladder()["tasks"]["overlay_digests"].values())))


def test_the_canary_s_sha256_finds_the_family_s_canary_in_the_line_its_packages_carry(tmp_path):
    family = _read(KIT / "family.json")
    (tmp_path / "task.toml").write_text(f"# {family['canary']}\n[task]\n")
    found = {ladder.canary_term(tmp_path, _criterion(t)["readout"]["contamination_scan"]["canary_sha256"])
             for t in STAGE_ONE}
    assert found == {family["canary"].split()[-1]}


@pytest.mark.parametrize("tranche", STAGE_ONE)
def test_the_competitions_are_family_json_s_of_the_class_in_its_order(tranche):
    criterion = _criterion(tranche)
    family = _read(KIT / "family.json")["candidates"]
    cls = criterion["stage"]["class"]
    assert [(t["name"], t["slug"], t["feasibility_rank"]) for t in criterion["tasks"]["list"]] == [
        (c["name"], c["slug"], c["feasibility_rank"]) for c in family if c["class"] == cls]


# ---- pending and filled -------------------------------------------------------------------------------------

@pytest.mark.parametrize("tranche", STAGE_ONE)
def test_every_null_has_a_pending_entry_and_no_pending_entry_points_at_a_filled_field(tranche):
    criterion = _criterion(tranche)
    pending = [p["field"] for p in criterion["pending"]]
    untyped = [p["field"] for p in criterion["pending"] + criterion["filled"]
               if p.get("type") not in TYPE_NAMES or not p.get("filled_by")]
    filled_gaps = [g for g in ladder_manifest.freeze_gaps(criterion) if g.startswith("filled")]
    assert (sorted(ladder_manifest.nulls(criterion)), len(set(pending)), untyped, filled_gaps) == (
        sorted(pending), len(pending), [], [])


def test_the_pending_fields_are_the_ladder_s_live_probe_fields_and_this_family_s_own():
    common = {"usage_limits.vendor_headers_confirmed", "allowance_guard.utilisation_header", "tasks.qualified",
              "tasks.load_sensitive", "tasks.withholding", "tasks.packages", "schedule.order.seed",
              "readout.fall_bound.seed", "readout.contamination_scan.terms",
              "readout.contamination_scan.canary_exempt_tasks"}
    assert {t: {p["field"] for p in _criterion(t)["pending"]} for t in STAGE_ONE} == {
        "screen-cpu": common, "screen-gpu": common | {"tasks.weights"}}


def test_a_field_filled_in_the_ladder_s_copied_groups_is_filled_here_with_the_ladder_s_record():
    copied = [e for e in _the_ladder()["filled"] if e["field"].split(".")[0] in UNCHANGED_GROUPS + ("host",)
              and e["field"] != "host.disk_plan"]
    assert {t: [e for e in _criterion(t)["filled"] if e in copied] for t in STAGE_ONE} == dict.fromkeys(
        STAGE_ONE, copied)


def test_a_value_given_in_the_fields_file_fills_its_pending_field_and_names_its_source(tmp_path):
    fields = _read(KIT / "criterion_fields.json")
    fields["filled"] = {"screen-cpu": {"schedule.order.seed": {"value": "seed-1", "source": "ledger row X"}}}
    doc, _ = mc.stage_one("cpu", fields=fields)
    entry = next(e for e in doc["filled"] if e["field"] == "schedule.order.seed")
    assert (doc["schedule"]["order"]["seed"], entry["source"], entry["type"],
            "schedule.order.seed" in {p["field"] for p in doc["pending"]}) == ("seed-1", "ledger row X", "scalar", False)


# ---- images: placeholders that cannot launch ----------------------------------------------------------------

PINNED = re.compile(r"[^@\s]+@sha256:[0-9a-f]{64}")  # M4: <name>@sha256:<64 hexadecimal digits>


@pytest.mark.parametrize("tranche", STAGE_ONE)
def test_image_references_are_placeholders_of_the_pinned_form_that_no_real_image_can_have(tranche):
    entries = _tasks(tranche)["tasks"]
    refs = [e[k] for e in entries for k in ("environment_image", "verifier_image")]
    assert ([e["name"] for e in entries], all(PINNED.fullmatch(r) for r in refs),
            {r.split("/", 1)[0] for r in refs}, {r.rsplit(":", 1)[1] for r in refs},
            {e["digest_4_1_0"] for e in entries}) == (
        [f"mle-bench/{n}" for n in _names(_criterion(tranche))], True, {"placeholder.invalid"}, {"0" * 64},
        {"sha256:" + "0" * 64})


def _wrapped_ladder(tranche):
    """A private load of the launcher with the names of M4 that these checks read set to the tranche's."""
    module = _load(f"mle_ladder_wrapped_{tranche}", LADDER_KIT / "ladder.py")
    module.KIT, module.PACKAGES = KIT / "tranches" / tranche, "packages"
    module.EFFORTS = tuple(_criterion(tranche)["attempt"]["efforts"])
    return module


@pytest.mark.parametrize("tranche", STAGE_ONE)
def test_a_tranche_with_placeholder_images_is_refused_by_the_launcher_s_live_criterion_read(tranche, tmp_path):
    module = _wrapped_ladder(tranche)
    ctx = module.Ctx({"HOME": str(tmp_path), "LH": str(tmp_path / "mle-cache")})
    with pytest.raises(module.Refused, match="the criterion is not ready to freeze"):
        module.criterion(ctx)
    assert "pending: tasks.packages" in ladder_manifest.freeze_gaps(_criterion(tranche))


STANDIN_PYTHON = '''
import hashlib, sys, types
from pathlib import Path


def content_hash(path):
    outer = hashlib.sha256()
    for f in sorted(p for p in Path(path).rglob("*") if p.is_file()):
        outer.update(f"{f.relative_to(path).as_posix()}\\0{hashlib.sha256(f.read_bytes()).hexdigest()}\\n".encode())
    return outer.hexdigest(), []


packager = types.ModuleType("harbor.publisher.packager")
packager.Packager = type("Packager", (), {"compute_content_hash": staticmethod(content_hash)})
for name in ("harbor", "harbor.publisher"):
    sys.modules[name] = types.ModuleType(name)
sys.modules["harbor.publisher.packager"] = packager
code, args = sys.argv[sys.argv.index("-c") + 1], sys.argv[sys.argv.index("-c") + 2:]
sys.argv = ["-c", *args]
exec(compile(code, "<stand-in -c>", "exec"), {"__name__": "__main__"})
'''


def test_the_launcher_s_task_check_refuses_a_package_against_a_placeholder_even_when_it_names_the_placeholders(
        tmp_path):
    """The worst case: a package written with the placeholder references themselves. Its content hash cannot be the
    all-zero digest, so the reviewed task check refuses it (stand-in Packager with Harbor's construction)."""
    module = _wrapped_ladder("screen-cpu")
    lh = tmp_path / "mle-cache"
    (lh / "hvenv" / "bin").mkdir(parents=True)
    python = lh / "hvenv" / "bin" / "python"
    python.write_text(f"#!{sys.executable} -I\n{STANDIN_PYTHON}")
    python.chmod(0o700)
    record = _tasks("screen-cpu")["tasks"][0]
    x = lh / "packages" / "leaf" / "x"
    x.mkdir(parents=True)
    (x / "task.toml").write_text(f'[verifier.environment]\ndocker_image = "{record["verifier_image"]}"\n[agent]\n'
                                 f'[environment]\ndocker_image = "{record["environment_image"]}"\n')
    ctx = module.Ctx({"HOME": str(tmp_path), "LH": str(lh)})
    assert module.task_refusal(ctx, _criterion("screen-cpu"), "leaf") == (
        "leaf: the package's digest is not its 4.1.0 digest")


def _built(name):
    return {"digest_4_1_0": "sha256:" + "ab" * 32, "environment_image": f"localhost/mle-bench/{name}@sha256:" + "cd" * 32,
            "verifier_image": f"localhost/mle-bench/{name}-v@sha256:" + "ef" * 32}


def _fill_packages(names):
    fields = copy.deepcopy(mc.FIELDS)
    fields["filled"] = {"screen-cpu": {"tasks.packages": {"value": {n: _built(n) for n in names},
                                                          "source": "a stand-in build row"}}}
    return fields


def test_once_tasks_packages_is_filled_tasks_json_carries_its_strings_and_no_placeholder():
    names = _names(_criterion("screen-cpu"))
    doc, tasks = mc.stage_one("cpu", fields=_fill_packages(names))
    assert ([{k: e[k] for k in _built(n)} for e, n in zip(tasks["tasks"], names)],
            "tasks.packages" in {p["field"] for p in doc["pending"]}) == ([_built(n) for n in names], False)


def test_a_filled_tasks_packages_that_leaves_a_competition_out_is_refused():
    with pytest.raises(mc.Refused, match="birds"):
        mc.stage_one("cpu", fields=_fill_packages(["leaf", "textnorm-ru"]))


@pytest.mark.parametrize("tranche", STAGE_ONE)
def test_the_tasks_json_entries_carry_no_withholding_result_until_the_criterion_has_one(tranche):
    assert {e["withholding"] for e in _tasks(tranche)["tasks"]} == {None}


# ---- the tranche directory, its links, the state root -------------------------------------------------------

@pytest.mark.parametrize("tranche", STAGE_ONE)
def test_the_tranche_directory_holds_its_two_files_and_links_to_the_four_reviewed_files(tranche):
    directory = KIT / "tranches" / tranche
    links = {p.name: p.resolve() for p in directory.iterdir() if p.is_symlink()}
    files = sorted(p.name for p in directory.iterdir() if not p.is_symlink())
    relative = {os.readlink(directory / n).startswith("../") for n in links}
    assert (files, links, relative) == (["ladder.json", "tasks.json"], {n: LADDER_KIT / n for n in LINKS}, {True})


class _MleCtx(ladder.Ctx):
    """M4's subclass: it differs from the launcher's only in the state root."""

    def __init__(self, env, tranche):
        super().__init__(env)
        self.root = self.home / ".local" / "state" / "mle-bench" / tranche


def test_the_launcher_s_socket_check_passes_for_every_tranche_name_and_task_name_under_this_machine_s_home():
    home = os.path.expanduser("~")
    criteria = [_criterion(t) for t in STAGE_ONE]
    refusals = []
    for criterion in criteria:
        ladder.EFFORTS = tuple(criterion["attempt"]["efforts"])
        refusals += [ladder.socket_refusal(_MleCtx({"HOME": home}, name), _stand_ins(criterion))
                     for name in TRANCHE_NAMES]
    longest = max(len(n) for c in criteria for n in _names(c))
    assert (refusals, longest <= 12, set(TRANCHE_NAMES) == set(mc.FIELDS["tranches"]),
            max(map(len, TRANCHE_NAMES)) <= 12) == ([None] * 12, True, True, True)


# ---- the manifest (M4) --------------------------------------------------------------------------------------

def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _manifest(tranche):
    return _read(KIT / "manifests" / f"{tranche}.json")


@pytest.mark.parametrize("tranche", STAGE_ONE)
def test_the_manifest_lists_by_hash_every_kit_file_outside_manifests_tranches_prose_and_caches(tranche):
    kit = {p.relative_to(ROOT).as_posix(): _sha(p) for p in KIT.rglob("*")
           if p.is_file() and p.relative_to(KIT).parts[0] not in ("manifests", "tranches", "README.md", "results")
           and "__pycache__" not in p.parts}
    listed = {k: v for k, v in _manifest(tranche)["files"].items() if k.startswith("experiments/mle_bench_tasks/")
              and not k.startswith("experiments/mle_bench_tasks/tranches/")}
    assert (listed, "experiments/mle_bench_tasks/make_criterion.py" in listed) == (kit, True)


@pytest.mark.parametrize("tranche", STAGE_ONE)
def test_the_manifest_lists_this_tranche_s_files_with_links_hashed_through_to_their_content(tranche):
    prefix = f"experiments/mle_bench_tasks/tranches/{tranche}/"
    listed = {k[len(prefix):]: v for k, v in _manifest(tranche)["files"].items() if k.startswith(prefix)}
    others = [k for k in _manifest(tranche)["files"] if "/tranches/" in k and not k.startswith(prefix)]
    want = {n: _sha(KIT / "tranches" / tranche / n) for n in ("ladder.json", "tasks.json")}
    assert (listed, others) == (want | {n: _sha(LADDER_KIT / n) for n in LINKS}, [])


@pytest.mark.parametrize("tranche", STAGE_ONE)
def test_the_manifest_lists_every_path_the_ladder_s_own_manifest_lists_with_its_hash(tranche):
    theirs = ladder_manifest.files()
    assert {k: _manifest(tranche)["files"].get(k) for k in theirs} == theirs


def test_two_tranches_manifests_differ_and_name_the_not_covered_directories():
    cpu, gpu = (_manifest(t) for t in STAGE_ONE)
    assert (cpu != gpu, {"manifests/", "tranches/"} <= set(cpu["not_covered"]), cpu["frozen"]) == (True, True, False)


def test_a_change_to_a_kit_file_is_seen_by_the_manifest_check(tmp_path):
    module = mc.manifest_module("screen-cpu")
    recorded = _manifest("screen-cpu")
    recorded["files"]["experiments/mle_bench_tasks/family.json"] = "0" * 64
    module.MANIFEST = tmp_path / "m.json"
    module.MANIFEST.write_text(json.dumps(recorded))
    assert module.check() == 1


# ---- stage two (M9) -----------------------------------------------------------------------------------------

LABEL = "a" * 64
OBSERVATION_ROW, CUT_ROW = 5, 10


def _start(n, slot, reward=0, usd=3.0, row=OBSERVATION_ROW, cls="observation", label=LABEL):
    return {"slot": slot, "start": n, "label": label, "row": row, "class": cls, "stop_cause": None,
            "reward": reward if cls == "observation" else None, "excluded": None, "contamination": [], "usd": usd,
            "minutes": None, "tokens": dict.fromkeys(slot_record.TOKEN_KINDS), "api_retry": None, "graded": None,
            "egress_refused": {}, "relay_lookup_timeouts": {}, "artifact_absent": False}


def _export(tranche, medals=(), usd=3.0, cuts=(), end="schedule", criterion=None):
    """A constructed export of a tranche (stage one's committed criterion, or `criterion`) that ran its whole
    schedule: one observation per slot, reward 1 for the slots of `medals` ((round, task) pairs), each start at
    `usd`; a cut, then its rerun, on the slots of `cuts`. It loads through the reviewed slot_record.py."""
    criterion = criterion or _criterion(tranche)
    entries = _schedule(criterion)
    starts = []
    for e in entries:
        if (e["round"], e["task"]) in cuts:
            starts.append(_start(len(starts) + 1, ladder.slot_id(e), usd=usd, row=CUT_ROW, cls="cut"))
        starts.append(_start(len(starts) + 1, ladder.slot_id(e), int((e["round"], e["task"]) in medals), usd))
    doc = {"label": LABEL, "earlier_labels": [], "end": {"by": end, "cause": "a stop row" if end == "stop" else None},
           "slots": [{"slot": ladder.slot_id(e), "task": e["task"], "effort": e["effort"], "round": e["round"],
                      "pilot": e["kind"] == "pilot"} for e in entries], "starts": starts, "allowance": None, "open": []}
    slot_record.load(doc, criterion)
    return doc


def _derive(tranche, export, probe_usd=0.3):
    cls = _criterion(tranche)["stage"]["class"]
    return mc.derive_stage_two(cls, export, "e" * 64, probe_usd)


def test_stage_two_lists_the_competitions_with_no_medal_in_rank_order():
    export = _export("screen-gpu", medals={(2, "patent"), (1, "whale"), (3, "lmsys")}, usd=0.5)
    derivation, _, _ = _derive("screen-gpu", export)
    ranks = {t["name"]: t["feasibility_rank"] for t in _criterion("screen-gpu")["tasks"]["list"]}
    want = sorted(set(ranks) - {"patent", "whale", "lmsys"}, key=ranks.get)
    assert (derivation["no_medal"], want[:2]) == (want, ["tweet", "petfinder"])


def test_stage_two_s_ceiling_is_the_class_s_less_every_start_s_cost_cuts_included_and_the_live_probe_s():
    export = _export("screen-cpu", medals={(1, "leaf")}, usd=2.0, cuts={(2, "birds")})
    derivation, criterion, _ = _derive("screen-cpu", export, probe_usd=0.3)
    assert (derivation["committed_usd"], derivation["ceiling_usd"], criterion["ceiling"]["total_usd"]) == (
        20.3, 29.7, 29.7)


@pytest.mark.parametrize("usd, k", [(1.0, 2), (2.0, 2), (3.0, 0), (3.5, 0), (4.0, 0)])
def test_stage_two_s_size_is_the_largest_k_of_two_or_more_with_3k_less_1_mean_costs_and_9_45_within_its_ceiling(
        usd, k):
    """CPU, two competitions without a medal; ceiling 50 - 9 x usd - 0.3. At usd 2: 31.7 left, k=2 needs 5 x 2 +
    9.45 = 19.45. At usd 3: 22.7 left, k=2 needs 5 x 3 + 9.45 = 24.45; k=1 would fit (15.45) and is not funded
    (M9-R1). At usd 4: 13.7 left, k=1 would need 17.45."""
    export = _export("screen-cpu", medals={(1, "leaf")}, usd=usd)
    derivation, criterion, _ = _derive("screen-cpu", export)
    m, ceiling = derivation["mean_usd_per_start"], derivation["ceiling_usd"]
    fits = [j for j in range(len(derivation["no_medal"]) + 1)
            if j == 0 or (j >= 2 and (3 * j - 1) * m + 9.45 <= ceiling)]
    assert (derivation["k"], max(fits), derivation["funded"], derivation["not_funded"]) == (
        k, k, ["textnorm-ru", "birds"][:k], ["textnorm-ru", "birds"][k:])
    assert (criterion is None) == (k == 0)


def test_one_competition_without_a_medal_is_not_funded_as_a_stage_of_one():
    """M9-R1: k = 1 would fit; it is reported not funded, and there is no stage two."""
    export = _export("screen-cpu", medals={(1, "leaf"), (2, "textnorm-ru")}, usd=1.0)
    derivation, criterion, tasks = _derive("screen-cpu", export)
    assert (derivation["no_medal"], derivation["k"], derivation["funded"], derivation["not_funded"], criterion,
            tasks) == (["birds"], 0, [], ["birds"], None, None)


def test_a_stage_two_of_one_funded_competition_is_refused():
    derivation = {"export_label": LABEL, "export_sha256": "e" * 64, "funded": ["birds"], "ceiling_usd": 20.0}
    with pytest.raises(mc.Refused, match="M9-R1"):
        mc._stage_two(_criterion("screen-cpu"), derivation, "cpu", mc.FIELDS)


def test_a_stage_one_with_one_qualified_competition_is_refused():
    fields = copy.deepcopy(mc.FIELDS)
    fields["filled"] = {"screen-cpu": {"tasks.qualified": {"value": ["leaf"], "source": "a stand-in row"}}}
    with pytest.raises(mc.Refused, match="M9-R1"):
        mc.stage_one("cpu", fields=fields)


def test_a_stage_two_s_schedule_lists_each_slot_once_and_its_export_loads():
    """The smallest stage two the rule funds, two competitions: six slots, each once, and an export of its whole
    schedule loads through the reviewed slot_record.py (with one competition its smoke and pilot are one slot,
    which slot_record.py refuses)."""
    _, criterion, _ = _derive("screen-cpu", _export("screen-cpu", medals={(1, "leaf")}, usd=1.0))
    slots = [ladder.slot_id(e) for e in _schedule(criterion)]
    export = _export(None, criterion=_stand_ins(criterion))
    assert (slots[:2], sorted(slots), len(export["starts"])) == (
        ["r1-textnorm-ru-medium", "r1-birds-medium"],
        sorted(f"r{r}-{t}-medium" for r in (1, 2, 3) for t in ("textnorm-ru", "birds")), 6)


def test_a_gpu_stage_two_s_starts_cap_is_its_slots_and_four():
    export = _export("screen-gpu", medals={(1, n) for n in _names(_criterion("screen-gpu"))[2:]}, usd=0.5)
    derivation, criterion, _ = _derive("screen-gpu", export)
    assert (derivation["funded"], criterion["ceiling"]["starts"], criterion["host"]["concurrency"]["rounds"]) == (
        ["tweet", "patent"], 10, 1)


def test_an_export_with_a_medal_for_every_competition_gives_no_stage():
    export = _export("screen-cpu", medals={(1, n) for n in _names(_criterion("screen-cpu"))}, usd=1.0)
    derivation, criterion, tasks = _derive("screen-cpu", export)
    assert (derivation["no_medal"], derivation["k"], criterion, tasks) == ([], 0, None, None)


def _leaves(doc, path=""):
    if isinstance(doc, dict):
        out = {}
        for key, value in doc.items():
            out |= _leaves(value, f"{path}.{key}" if path else key)
        return out
    return {path: doc}


def test_stage_two_differs_from_stage_one_only_in_its_list_ceiling_starts_smoke_pilot_and_stage():
    """leaf has a medal: stage two is textnorm-ru (smoke) and birds (pilot, as in stage one, so its task is the
    same and only its fallback changes)."""
    export = _export("screen-cpu", medals={(1, "leaf")}, usd=1.0)
    _, criterion, _ = _derive("screen-cpu", export)
    one, two = _leaves(_criterion("screen-cpu")), _leaves(criterion)
    changed = sorted(p for p in one.keys() | two.keys() if one.get(p, KeyError) != two.get(p, KeyError))
    assert changed == sorted([
        "tasks.list", "tasks.overlay_digests.leaf", "readout.graded_outcome.verifiers.leaf", "ceiling.total_usd",
        "ceiling.starts", "schedule.smoke.task", "schedule.pilot.fallback", "stage.tranche",
        "stage.stage", "stage.ledger", "stage.derived_from.export_label", "stage.derived_from.export_sha256",
        "stage.derived_from.no_medal", "stage.derived_from.funded", "stage.derived_from.not_funded",
        "stage.derived_from.mean_usd_per_start", "stage.derived_from.committed_usd",
        "stage.derived_from.live_probe_usd", "stage.derived_from.k", "stage.derived_from.ceiling_usd"])


def test_stage_two_takes_its_own_seeds_even_when_stage_one_s_are_filled():
    one = _criterion("screen-cpu")
    for field, value in (("schedule.order.seed", "s1"), ("readout.fall_bound.seed", "s2")):
        ladder._set(one, field, value)
        entry = next(p for p in one["pending"] if p["field"] == field)
        one["pending"].remove(entry)
        one["filled"].append({**entry, "source": "a stand-in row"})
    _, two, _ = mc.derive_stage_two("cpu", _export("screen-cpu", usd=1.0), "e" * 64, 0.0, stage_one=one)
    assert ((two["schedule"]["order"]["seed"], two["readout"]["fall_bound"]["seed"]),
            {"schedule.order.seed", "readout.fall_bound.seed"} <= {p["field"] for p in two["pending"]},
            [e["field"] for e in two["filled"] if "seed" in e["field"]]) == ((None, None), True, [])


def test_stage_two_is_the_same_criterion_every_time():
    export = _export("screen-gpu", medals={(1, "patent")}, usd=0.5)
    assert _derive("screen-gpu", export) == _derive("screen-gpu", copy.deepcopy(export))


def test_stage_two_is_named_and_ledgered_as_m4_says_and_carries_its_derivation():
    _, criterion, _ = _derive("screen-cpu", _export("screen-cpu", usd=1.0))
    stage = criterion["stage"]
    assert (stage["tranche"], stage["stage"], stage["ledger"], stage["derived_from"]["export_sha256"]) == (
        "screen-cpu-2", 2, "docs/plans/2026-11-15-mle-bench-ledger-screen-cpu-2.md", "e" * 64)


@pytest.mark.parametrize("change", ["running", "open", "stop", "a medal under an earlier label"])
def test_an_export_that_cannot_decide_stage_two_is_refused_or_reads_only_the_current_label(change):
    export = _export("screen-cpu", usd=1.0)
    if change == "running":
        export["end"] = None
    elif change == "open":
        export["open"] = [{"slot": export["slots"][0]["slot"], "start": 99}]
    elif change == "stop":
        export["end"] = {"by": "stop", "cause": "a stop row"}
    else:
        export["earlier_labels"] = [{"label": "b" * 64, "ended_by": "a row"}]
        export["starts"][0] = _start(1, export["starts"][0]["slot"], reward=1, label="b" * 64)
        derivation, _, _ = _derive("screen-cpu", export)
        assert derivation["no_medal"] == ["leaf", "textnorm-ru", "birds"]
        return
    with pytest.raises(mc.Refused):
        _derive("screen-cpu", export)


def test_the_live_probe_s_usage_is_summed_as_the_launcher_sums_it(tmp_path):
    log = tmp_path / "requests.jsonl"
    log.write_text('{"usd": 0.1}\n{"usd": null}\n\n{"usd": 0.25}\n')
    assert mc.probe_usd(log) == pytest.approx(0.35)


def test_weights_json_is_a_placeholder_that_names_no_checkpoint_and_keeps_the_gpu_tranche_pending():
    weights = _read(KIT / "weights.json")
    assert (weights["checkpoints"], "tasks.weights" in {p["field"] for p in _criterion("screen-gpu")["pending"]},
            "weights" in _criterion("screen-cpu")["tasks"]) == (None, True, False)


# ---- no account detail --------------------------------------------------------------------------------------

def test_no_generated_or_input_file_names_this_account_or_a_home_path():
    paths = [KIT / "make_criterion.py", KIT / "criterion_fields.json", KIT / "weights.json",
             *(KIT / "manifests").glob("*.json"), *(p for t in STAGE_ONE for p in (KIT / "tranches" / t).glob("*.json"))]
    text = "\n".join(p.read_text() for p in paths)
    assert [w for w in (getpass.getuser(), os.path.expanduser("~"), "/tmp/") if w in text] == []
