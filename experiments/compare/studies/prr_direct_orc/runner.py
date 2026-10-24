"""PRR-P2 only: fixed natural-control check, then the bounded direct/ORC pilot."""
import argparse
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import tomllib

STUDY = "PRR-P2-20261024"
SLUG = "pure-result-replay-command-recovery"
E = Path("/home/ollie/sc-evidence/PRR-P2-20261024")
F = Path("/home/ollie/sc-evidence/freeze-prr-direct-orc-20261024")
WORK = Path("/home/ollie/sc-prr-direct-orc-work")
POOLS = Path("/home/ollie/sc-pools") / SLUG / STUDY
TASK = F / "task"
RUNTIME = Path("/home/ollie/sc-runtime-prr-direct-orc-20261024")
RUNTIME_COMMIT = "675966acf67f842ec67bf474dc8da460ed4b4d8f"
PREPARATION = Path("/home/ollie/sc-evidence/preparation")
AUTHORIZATION = PREPARATION / "PRR-P2-authorization-20261024.json"
AUTHORIZATION_SHA = "e6fd02a83b7cfc18ca16741b216247380129f08ec8e9777b5c043b5c2e54f312"
TOOL_PROOF = PREPARATION / "PRR-P2-toolchain/proof.json"
TOOL_PROOF_SHA = "963fab7d2f027b0428a6c3506d91e4c15503f2c989c9cc0699cef72d1d24650b"
CONTROL_PROOF = PREPARATION / "PRR-P2-control-admission/proof.json"
CONTROL_PROOF_SHA = "d653c0376c44f6b43d55d606c64f529249dd49f9ac9d139d2bee1b8b83d497f6"
COMPARE_BASE = "6b52682c6ee2584110d81002f2b25122f6197b87"
SOLUTION = "76427bdedbbac300bbd82d45db7fa6e24a770f84"
SOL_PATCH = Path("/home/ollie/sc-luna-sol-high-command-recovery-work/records/sol_high/run-1/calls/1/patch-cand-1.diff")
SOL_PATCH_SHA = "b6551ae2ac1438025c2a9538dce2c41e0dcb003e7cba0e57eff6f0a60cc0f135"
FAMILY = Path("/home/ollie/sc-evidence/LS11-20261023/combined-readout.json")
FAMILY_SHA = "cc8e98be793e4444636416fc9d37423c061aaa1290fd17cfc8fc37b39c85f6c3"
AUTHOR, JUDGE = "gpt-5.6-luna", "gpt-6.1-sol"
ARMS = ("direct", "implement_check_diagnose_repair")
AUTHOR_INPUTS = ("task", "intent", "repo", "context", "model")
RUBRIC = {"workflow": "score_functional.orc", "entry": "score_functional::score", "criteria": ["quality"], "reference": None}
EXCLUDE = ("docs/plans/evidence",)
PRICE_TABLE = {"currency": "USD", "tokens_per_unit": 1000000, "date": "2026-10-24",
    "source": "https://developers.openai.com/api/docs/models/gpt-5.6-luna ; https://developers.openai.com/api/docs/models/gpt-6.1-sol ; https://developers.openai.com/api/docs/pricing",
    "models": {AUTHOR: {"input": .20, "cache_read": .02, "cache_write": .25, "output": 1.20},
               JUDGE: {"input": 2., "cache_read": .10, "cache_write": 2.50, "output": 10.}}}


class StudyError(RuntimeError):
    pass


def require(condition, reason):
    if not condition:
        raise StudyError(reason)


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ref(path):
    return {"path": str(Path(path).resolve()), "sha256": sha(path)}


def write_new(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2); stream.write("\n")


def verify_refs(rows):
    for row in rows:
        require(sha(row["path"]) == row["sha256"], f"changed bound source: {row['path']}")


def api():
    """Fresh CLI processes use the frozen runtime, never mutable main's providers."""
    sys.path.insert(0, str(RUNTIME))
    modules = [importlib.import_module(name) for name in ("experiments.compare.prepare", "experiments.compare.pool",
        "experiments.compare.summarize", "experiments.compare.sandbox", "experiments.compare.repos",
        "experiments.orc_structural_search.metering", "experiments.orc_structural_search.pricing")]
    for module in modules:
        require(Path(module.__file__).resolve().is_relative_to(RUNTIME), "API imported outside the bound runtime")
    return modules


def evaluator_gate(observations, criterion_sha, expected_hashes):
    require(len(observations) == 2 and set(expected_hashes) == {"baseline", "natural_partial"}
            and len(set(expected_hashes.values())) == 2, "two complete independent repetitions required")
    require({row.get("unit_key") for row in observations} == {"evaluator-1", "evaluator-2"}
        and all(row.get("pool") == str(POOLS / row["unit_key"]) for row in observations)
        and all(isinstance(row.get("native_session_id"), str) and row["native_session_id"] for row in observations)
        and len({row["native_session_id"] for row in observations}) == 2
        and all(isinstance(row.get("native_snapshot"), dict) for row in observations)
        and len({row["native_snapshot"].get("path") for row in observations}) == 2
        and len({row["native_snapshot"].get("sha256") for row in observations}) == 2,
        "two distinct declared pools and native sessions required")
    scores = []
    for observed in observations:
        mapping, results, hashes = observed["mapping"], observed["results"], observed["patch_hashes"]
        ids = set(mapping["clones"])
        require(len(ids) == 2 and ids == set(results["clones"]) == set(hashes)
            and len(mapping["batches"]) == 1 and len(mapping["batches"][0]) == 2
            and set(mapping["batches"][0]) == ids and not mapping.get("references")
            and set(hashes.values()) == set(expected_hashes.values()), "control clone/source denominator changed")
        require(mapping["criterion_sha256"] == results["criterion_sha256"] == criterion_sha
            and mapping["task"] == results["task"] == str(TASK) and mapping["rubric"] == RUBRIC
            and not mapping["runs"] and not results["runs"] and results["judges"] == [JUDGE]
            and not results["excluded_judges"] and results.get("calibration") is None,
            "evaluator identity, exclusion or generic calibration mismatch")
        by_source = {}
        for cid in ids:
            ratings = results["clones"][cid]["ratings"]
            require(set(ratings) == {JUDGE}, "one rating per declared judge and clone required")
            value = ratings[JUDGE]["quality"]
            require(type(value) is int and 0 <= value <= 8, "invalid functional rating")
            by_source[hashes[cid]] = value
        scores.append({name: by_source[digest] for name, digest in expected_hashes.items()})
    gaps = [row["natural_partial"] - row["baseline"] for row in scores]
    return {"passed": all(gap >= 1 for gap in gaps), "gaps": gaps, "scores": scores,
            "repetitions": 2, "margin": 1, "failed_repetitions": sum(gap < 1 for gap in gaps),
            "scope": "coarse absent-versus-partial discrimination only; no harness calibration verdict"}


def complete_finals(rows, expected_paths):
    return (set(rows) == set(expected_paths) and len(rows) == 4
        and all(sum(row["arm"] == arm for row in rows.values()) == 2 for arm in ARMS)
        and all(row["outcome"] == "completed" and not row.get("excluded")
                and row["calls"] in ((1,) if row["arm"] == "direct" else (1, 3)) for row in rows.values()))


def standard_cost(receipt, metadata):
    from experiments.orc_structural_search import pricing
    unavailable = {"value": "unavailable", "basis": "standard short-context list-price equivalent, not billed cost"}
    if (len(metadata) != receipt.get("provider_calls") or not metadata
            or any(not row.get("complete") or not row.get("request_inputs") or not row.get("context_windows")
                   or any(type(n) is not int or n < 0 or n > 272000 for n in row["request_inputs"])
                   or any(type(n) is not int or n <= 0 or n > 272000 for n in row["context_windows"]) for row in metadata)):
        return unavailable | {"reason": "per-request short-context coverage unavailable or exceeded"}
    for call in receipt.get("receipt_usage", []):
        if not isinstance(call.get("usage"), list):
            return unavailable | {"reason": "usage unavailable"}
        for usage in call["usage"]:
            tokens = usage.get("charge_tokens")
            if not isinstance(tokens, dict) or (tokens.get("cache_write", 0) and usage.get("cache_write_retention") != "default"):
                return unavailable | {"reason": "usage or nonzero cache-write retention unavailable"}
    return {"value": pricing.cost(receipt, PRICE_TABLE), "basis": unavailable["basis"]}


def bindings():
    verify_refs([{"path": str(path), "sha256": digest} for path, digest in (
        (AUTHORIZATION, AUTHORIZATION_SHA), (TOOL_PROOF, TOOL_PROOF_SHA),
        (CONTROL_PROOF, CONTROL_PROOF_SHA), (FAMILY, FAMILY_SHA), (SOL_PATCH, SOL_PATCH_SHA))])
    authorization = read(AUTHORIZATION)["approved"]
    require(authorization["judge"] == {"model": JUDGE, "effort": "high"}
        and authorization["authors"] == {"model": AUTHOR, "effort": "high"}
        and authorization["new_session_cap"] == 11 and authorization["historical_starts"] == 76
        and authorization["overall_cap"] == 87 and not any(authorization[key] for key in
        ("retries", "claude", "fable", "native_delegation")), "approved study scope differs")
    tools = read(TOOL_PROOF); verify_refs([*tools["package_files"], tools["node"]])
    prepare, pooling, summary, sandbox, repos, metering, pricing = api()
    require(repos.runtime_commit(RUNTIME) == RUNTIME_COMMIT, "derived runtime changed")
    family = read(FAMILY); result = family["tasks"][SLUG]
    require(len(result["runs"]) == len(result["clones"]) == 4 and not result["excluded_judges"], "LS11 denominator changed")
    values = {}
    origins = []
    for clone in result["clones"].values():
        value = clone["ratings"][JUDGE]["quality"]
        require(type(value) is int and 0 <= value <= 8, "LS11 rating invalid")
        values.setdefault(clone["arm"], []).append(value); origins.append(clone["run"])
    require(len(set(origins)) == 4 and set(values) == {"direct_task", "sol_high"}
        and all(len(rows) == 2 for rows in values.values())
        and sum(values["sol_high"]) / 2 >= 4 and sum(values["sol_high"]) > sum(values["direct_task"]), "LS11 qualification not reproduced")
    return tools


def environment(model, cap, declaration=None):
    env = dict(os.environ)
    env.update(COMPARE_SANDBOX=str(declaration or F / "dependencies.json"), COMPARE_MAX_CALLS=str(cap),
        COMPARE_CODEX_MODELS=model, ORC_ALLOWED_CODEX_MODELS=model, COMPARE_CLAUDE_MODELS="",
        ORC_ALLOWED_CLAUDE_MODELS="", PYTHONDONTWRITEBYTECODE="1", DISABLE_AUTOUPDATER="1")
    return env


def dependencies(tools):
    data = read(Path("/home/ollie/sc-evidence/LS8-20261023/sandbox-dependencies.json"))
    old = Path(data["codex"]).parent.parent
    data["readonly"] = {path: source for path, source in data["readonly"].items()
        if not Path(path).is_relative_to(old)}
    prefix = str(Path(tools["prefix"]).resolve()); entry = str(Path(tools["entry"]).resolve())
    data.update(codex=entry, claude=None)
    data["readonly"][prefix] = prefix
    node = Path(tools["node"]["path"])
    data["readonly"][str(node)] = str(node)
    data["path"] = [str(node.parent), *[path for path in data["path"] if path != str(node.parent)]]
    require(Path(entry).is_relative_to(prefix), "pinned CLI entry escapes the admitted installation")
    return data


def unit_from_pool(out, key, stage):
    mapping = read(out / "records/mapping.json"); item = mapping["judges"][JUDGE]
    home = out / "judges" / item["dir"]
    return {"key": key, "stage": stage, "kind": "judge", "pool": str(out), "model": JUDGE, "effort": "high", "cap": 1,
        "records": str(out / "records/judges" / JUDGE), "tree": str(home), "cwd": str(home),
        "state_root": str(home / "state"), "sandbox": item["sandbox"], "created_at": mapping["created_at"],
        "command_file": str(out / f"records/score-{JUDGE}.sh")}


def units():
    values = read(E / "prepared.json")["units"]
    return values + (read(E / "pilot-judge.json")["units"] if (E / "pilot-judge.json").exists() else [])


def dry_run(unit):
    command = Path(unit["command_file"]).read_text().strip() + " --dry-run"
    with (E / f"{unit['key']}.dry-run.log").open("x") as stream:
        result = subprocess.run(["bash", "-c", command], cwd=RUNTIME,
            env=environment(unit["model"], unit["cap"], unit["sandbox"]["declaration"]), stdout=stream, stderr=subprocess.STDOUT)
    require(result.returncode == 0, "public dry run failed")


def trust_author_project(record, sandbox):
    home = Path(sandbox.session_home(record)); config = home / ".codex/config.toml"
    cwd = Path(record["cwd"]).resolve()
    require(cwd.is_relative_to(Path(record["tree"]).resolve()) and config.is_file() and not config.is_symlink(),
        "author trust must name its own candidate and private configuration")
    require(not list((Path(record["records"]) / "calls").glob("*"))
        and not list((home / ".codex/sessions").rglob("*.jsonl")), "trust preparation requires an unstarted unit")
    original = config.read_text()
    require("projects" not in tomllib.loads(original), "fresh author configuration already contains project trust")
    config.write_text(original + f'\n[projects.{json.dumps(str(cwd))}]\ntrust_level = "trusted"\n')


def prepare(source_commit):
    tools = bindings(); prepare_api, pooling, summary, sandbox, repos, metering, pricing = api()
    require(all(not path.exists() for path in (E, F, WORK, POOLS)), "fresh PRR-P2 roots required")
    repo = Path(__file__).resolve().parents[4]
    prefix = "experiments/compare/studies/prr_direct_orc/"
    source_names = subprocess.check_output(["git", "-C", str(repo), "ls-tree", "-r", "--name-only", source_commit, "--", prefix], text=True).splitlines()
    require(source_names and any(name.endswith("/runner.py") for name in source_names), "reviewed study source snapshot missing")
    snapshots = {}
    for name in source_names:
        data = subprocess.check_output(["git", "-C", str(repo), "show", f"{source_commit}:{name}"])
        require(data == (repo / name).read_bytes(), "reviewed study source differs from current selected bytes")
        snapshots[name.removeprefix(prefix)] = data
    E.mkdir(); F.mkdir(); TASK.mkdir(); (F / "sources").mkdir(); (E / "contexts").mkdir()
    for name, data in snapshots.items():
        path = F / "sources" / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
    proof = read(CONTROL_PROOF)
    for name, identity in proof["files"].items():
        relative = f"experiments/compare/tasks/{SLUG}/{name}"
        data = subprocess.check_output(["git", "-C", str(repo), "show", f"{proof['source_commit']}:{relative}"])
        require(hashlib.sha256(data).hexdigest() == identity["after"], "corrected task identity differs")
        target = TASK / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
    require(len(list(path for path in TASK.rglob("*") if path.is_file())) == 6
        and (TASK / "task.txt").read_bytes() == (TASK / "intent.txt").read_bytes(), "six-file full task required")
    write_new(F / "dependencies.json", dependencies(tools))
    renderer = importlib.util.spec_from_file_location("prr_frozen_sources", F / "sources" / "sources.py")
    module = importlib.util.module_from_spec(renderer); renderer.loader.exec_module(module)
    rendered = module.render_sources(F / "rendered", sys.executable, F / "sources/trusted_check.py")
    base = (TASK / "base_commit").read_text().strip()
    reference = {"main": str(repos.main_checkout(RUNTIME)), "runtime": str(RUNTIME), "base": base, "compare_base": COMPARE_BASE}
    baseline = F / "baseline.diff"; baseline.write_bytes(b"")
    partial = F / "natural_partial.diff"
    kept, stripped = pooling.strip(SOL_PATCH.read_bytes()); partial.write_bytes(kept)
    controls = {"baseline": sha(baseline), "natural_partial": sha(partial)}
    criterion = {"purpose": "calibration", "calibration_kind": "measure", "anchors": {}, "judges": [JUDGE], "rubric": RUBRIC,
        "primary": [], "secondary": [], "price_table": PRICE_TABLE, "evaluator_check": {
            "sources": {"baseline": {"source": ref(baseline), "pooled": ref(baseline)},
                        "natural_partial": {"source": ref(SOL_PATCH), "pooled": ref(partial), "stripped": stripped}},
            "repetitions": 2, "margin": 1, "error_rate": 0},
        "authorization": ref(AUTHORIZATION), "runtime": {"path": str(RUNTIME), "commit": RUNTIME_COMMIT}}
    write_new(F / "evaluator-criterion.json", criterion)
    pilot = criterion | {"purpose": "quality", "arms": list(ARMS), "runs_per_arm": dict.fromkeys(ARMS, 2)}
    pilot.pop("calibration_kind"); pilot.pop("evaluator_check")
    write_new(F / "pilot-criterion.json", pilot)
    made = []
    for ordinal in (1, 2):
        out = POOLS / f"evaluator-{ordinal}"
        batches = pooling.diff_batches([baseline, partial], 1, 2, 2, ordinal)
        pooling.write_pool(TASK, F / "evaluator-criterion.json", out,
            [f"{JUDGE}={RUNTIME}/experiments/compare/providers/score_codex.json"], reference, {}, batches,
            review_exclude=EXCLUDE, environment=environment(JUDGE, 1))
        made.append(unit_from_pool(out, f"evaluator-{ordinal}", "evaluator"))
    for ordinal in (1, 2):
        for arm in ARMS:
            key = f"{arm}-{ordinal}"; context = E / "contexts" / f"{key}.json"
            spec = prepare_api.ArmSpec(Path(rendered["direct" if arm == "direct" else "orc"]), f"{arm}::run",
                Path(rendered["source_root"]), Path(rendered["providers"]), AUTHOR_INPUTS,
                command_boundaries=Path(rendered["commands"]))
            records = prepare_api.run_arm(TASK, arm, WORK, RUNTIME, spec=spec, sets=(f"context={context}", f"model={AUTHOR}"), environment=environment(AUTHOR, 1 if arm == "direct" else 3))
            record = read(records / "record.json")
            trust_author_project(record, sandbox)
            require(record["compare_base"] == COMPARE_BASE, "corrected seeded baseline changed")
            write_new(records / "initial-record.json", record)
            names = {"dev-check.json", *[arg for arg in read(TASK / "seed/dev-check.json")["argv"] if arg.startswith("tests/")]}
            tracked = repos.git(Path(record["candidates"][0]), "ls-tree", "-r", "--name-only", COMPARE_BASE).splitlines()
            names.update(name for name in tracked if Path(name).name == "conftest.py")
            names.update(("pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini", "conftest.py", "tests/conftest.py"))
            candidate = Path(record["candidates"][0])
            write_new(context, {"repo": str(candidate), "records": str(records), "diagnostics": str(E / "integrity" / key),
                "helper": ref(F / "sources/dev_check.py"), "protected": {name: sha(candidate / name) if (candidate / name).is_file() else None for name in sorted(names)}})
            made.append({key: record[key] for key in ("records", "tree", "cwd", "state_root", "sandbox", "created_at")} |
                {"key": key, "stage": "authors", "kind": "author", "arm": arm, "model": AUTHOR, "effort": "high",
                 "cap": 1 if arm == "direct" else 3, "command_file": str(records / "command.sh"), "context": str(context)})
    write_new(E / "prepared.json", {"source_commit": source_commit, "units": made, "controls": controls})
    for unit in made: dry_run(unit)
    write_new(E / "initial-inventory.json", inventory())
    print(json.dumps({"prepared_evaluators": 2, "prepared_authors": 4, "dry_runs": 6, "new_provider_calls": 0}))


def native_facts(path, *, live=False):
    """Read public header/usage/action metadata, excluding text, base instructions and reasoning."""
    facts = {"request_inputs": [], "context_windows": [], "models": [], "efforts": [], "complete": False, "forbidden": [],
             "pending_tail": live and Path(path).stat().st_size == 0}
    with Path(path).open() as stream:
        for line in stream:
            unfinished = not line.endswith("\n")
            if unfinished:
                require(live, "native transcript has an unfinished trailing record")
                facts["pending_tail"] = True
            try: row = json.loads(line)
            except json.JSONDecodeError:
                if live and unfinished: break
                raise
            payload = row.get("payload") or {}; kind = row.get("type")
            if kind == "session_meta":
                facts.update(id=payload.get("id"), cwd=payload.get("cwd"), parent=payload.get("parent_thread_id"))
                if isinstance(payload.get("source"), dict) and payload["source"].get("subagent"):
                    facts["parent"] = "subagent"
            elif kind == "turn_context":
                facts["models"].append(payload.get("model")); facts["efforts"].append(payload.get("effort"))
            elif kind == "event_msg" and payload.get("type") == "token_count":
                info = payload.get("info") or {}; usage = info.get("last_token_usage") or {}
                if "input_tokens" in usage: facts["request_inputs"].append(usage["input_tokens"])
                if "model_context_window" in info: facts["context_windows"].append(info["model_context_window"])
            elif kind == "event_msg" and payload.get("type") == "task_complete":
                facts["complete"] = not payload.get("error")
                if payload.get("error"): facts["forbidden"].append("native task ended with an external error")
            elif kind == "response_item" and payload.get("type") in ("function_call", "custom_tool_call"):
                if payload.get("name") in ("spawn_agent", "collaboration.spawn_agent"):
                    facts["forbidden"].append("native delegation")
    return facts


def native_paths(unit):
    metadata = read(Path(unit["records"]) / "record.json") if unit["kind"] == "author" else {
        "tree": unit["tree"], "records": unit["records"], "sandbox": unit["sandbox"]}
    home = Path(api()[3].session_home(metadata)); root = home / ".codex/sessions"
    require(not (home / ".codex").is_symlink() and not root.is_symlink()
        and root.resolve().is_relative_to(home), "native directory escapes the declared home")
    paths = list(root.rglob("rollout-*.jsonl"))
    require(all(not path.is_symlink() and path.resolve().is_relative_to(home) for path in paths), "native transcript symlink incident")
    return home, [path for path in paths if path.stat().st_mtime >= unit["created_at"]]


def inventory(*, strict=True, live=False):
    sandbox = api()[3]; by_unit = {}; natives = []; incidents = []
    for unit in units():
        metadata = read(Path(unit["records"]) / "record.json") if unit["kind"] == "author" else {
            "tree": unit["tree"], "records": unit["records"], "sandbox": unit["sandbox"]}
        home, paths = native_paths(unit)
        calls = list((Path(unit["records"]) / "calls").glob("*")); physical = sum((path / "prompt.txt").is_file() for path in calls)
        selected = []
        for path in paths:
            facts = native_facts(path, live=live); selected.append(facts); natives.append({"unit": unit["key"], "path": str(path), **facts})
            pending_header = live and facts["pending_tail"] and not facts.get("id")
            if (facts.get("parent") or (not pending_header and (not facts.get("cwd") or not Path(facts["cwd"]).is_relative_to(unit["tree"])))
                or any(model != unit["model"] for model in facts["models"])
                or any(effort != "high" for effort in facts["efforts"]) or facts["forbidden"]):
                incidents.append(unit["key"] + ": native ownership/model/delegation/external incident")
        if physical > unit["cap"] or len(selected) > physical or (not live and any(not (path / "prompt.txt").is_file() for path in calls)):
            incidents.append(unit["key"] + ": unrecorded root or extra/refused attempt")
        claude = list((home / ".claude/projects").rglob("*.jsonl"))
        if claude:
            incidents.append(unit["key"] + ": forbidden Claude session")
        by_unit[unit["key"]] = max(physical, len(selected)) + len(claude)
    count = sum(by_unit.values())
    if strict: require(count <= 11 and not incidents, "; ".join(incidents) or "eleven-new start cap exceeded")
    return {"calls_by_unit": by_unit, "new_starts": count, "historical_starts": 76, "overall_starts": 76 + count, "native": natives, "incidents": incidents}


def capture(unit, status):
    prepare_api, pooling, summary, sandbox, repos, metering, pricing = api(); errors = {}; values = {}
    records = Path(unit["records"]); home = Path(unit["sandbox"]["home"])
    def perform(name, function):
        try: values[name] = function()
        except (Exception, SystemExit) as error: errors[name] = str(error)
    if unit["kind"] == "author": perform("collect", lambda: prepare_api.collect(records))
    perform("native_scope", lambda: [str(path) for path in native_paths(unit)[1]])
    if "native_scope" not in errors:
        perform("scan", lambda: prepare_api.scan(records, SOLUTION, home=home) if unit["kind"] == "author"
                else pooling.scan_judge(Path(unit["pool"]), JUDGE, SOLUTION, home=home))
        perform("metering", lambda: metering.receipts(records, tree=Path(unit["tree"]), since=unit["created_at"], home=home))
    receipt = {"provider_calls": sum((path / "prompt.txt").is_file() for path in (records / "calls").glob("*")),
               **values.get("metering", {"consumption": "unavailable", "receipt_usage": "unavailable", "native_session_paths": []})}
    write_new(E / f"{unit['key']}.metering.json", receipt)
    perform("native_receipt", lambda: receipt_proof(unit))
    perform("terminal", lambda: prepare_api.finished_memo(Path(unit["state_root"]))[1][-1])
    if unit["kind"] == "judge": perform("verify_pool", lambda: pooling.verify_pool(Path(unit["pool"])))
    elapsed = values.get("collect", {}).get("wall_clock_sec", "unavailable")
    if unit["kind"] == "judge" and "terminal" in values:
        memo, rows = prepare_api.finished_memo(Path(unit["state_root"]))
        elapsed = memo.stat().st_mtime - min(row["time"] for row in rows if row["record"] == "started")
    value = {"unit": unit["key"], "exit_code": status, "errors": errors, "original_terminal": values.get("terminal"), "wall_clock_sec": elapsed,
             "collected_outcome": values.get("collect", {}).get("outcome"), "metering": ref(E / f"{unit['key']}.metering.json")}
    write_new(E / f"{unit['key']}.completion.json", value)
    return value


def freeze(stage):
    bindings(); require(stage in ("evaluator", "authors", "pilot-judge"), "unknown fixed stage")
    if stage != "evaluator": require_evaluator()
    selected = [unit for unit in units() if unit["stage"] == stage]
    require(selected and all(not list((Path(u["records"]) / "calls").glob("*")) for u in selected), "freeze requires untouched units")
    paths = [AUTHORIZATION, TOOL_PROOF, CONTROL_PROOF, FAMILY, SOL_PATCH, Path(__file__).resolve()]
    paths += [Path(row["path"]) for row in [*read(TOOL_PROOF)["package_files"], read(TOOL_PROOF)["node"]]]
    paths += [path for path in F.rglob("*") if path.is_file() and not path.name.endswith("-packet.json")]
    paths += [E / "prepared.json"] + list((E / "contexts").glob("*.json"))
    paths += [RUNTIME / "experiments/compare" / name for name in
        ("score_functional.orc", "providers/score_codex.json", "shim/claude", "shim/model-guard")]
    paths += [Path(read(F / "dependencies.json")["catalog"])]
    for unit in selected:
        metadata = read(Path(unit["records"]) / "record.json") if unit["kind"] == "author" else {
            "tree": unit["tree"], "records": unit["records"], "sandbox": unit["sandbox"]}
        home = Path(api()[3].session_home(metadata))
        paths += [Path(unit["sandbox"]["declaration"]), home / ".compare-unit.json", home / ".codex/config.toml", home / ".codex/public-models.json"]
        paths += [path for path in (home / ".codex/skills/tmux").rglob("*") if path.is_file()]
        if unit["kind"] == "author": paths += [Path(unit["records"]) / name for name in ("initial-record.json", "inputs.json", "command.sh", "sandbox.json")]
        else: paths += [path for path in (Path(unit["pool"]) / "records").rglob("*") if path.is_file()]
    if stage != "evaluator": paths += [E / "evaluator-admission.json"]
    write_new(F / f"{stage}-packet.json", {"study": STUDY, "stage": stage, "authorization": ref(AUTHORIZATION),
        "inventory": inventory(), "files": [ref(path) for path in sorted(set(paths))]})
    print(json.dumps({"packet": ref(F / f"{stage}-packet.json"), "provider_calls": 0}))


def execute(stage):
    bindings(); packet = F / f"{stage}-packet.json"; frozen = read(packet); verify_refs(frozen["files"])
    declaration = read(E / f"{stage}-declaration.json")
    require(declaration["packet"] == ref(packet) and declaration["authorization"] == ref(AUTHORIZATION)
        and declaration["new_cap"] == 11 and declaration["historical_starts"] == 76 and declaration["overall_cap"] == 87,
        "concrete reviewed stage declaration differs")
    verify_refs([declaration["independent_review"]])
    if stage != "evaluator": require_evaluator()
    selected = [unit for unit in units() if unit["stage"] == stage]
    if stage == "authors": selected.sort(key=lambda unit: (ARMS.index(unit["arm"]), unit["key"]))
    require(selected and all(not list((Path(u["records"]) / "calls").glob("*"))
        and not list(Path(u["state_root"]).glob("*/run.json")) and not (E / f"{u['key']}.launch.json").exists()
        for u in selected), "no retry, replacement or relaunch of started units")
    write_new(E / f"{stage}-before.json", {"inventory": inventory(), "packet": ref(packet)})
    active = []; width = 2 if stage in ("authors", "evaluator") else 1
    def stop(signum, frame): raise SystemExit(128 + signum)
    signal.signal(signal.SIGINT, stop); signal.signal(signal.SIGTERM, stop)
    try:
        for offset in range(0, len(selected), width):
            verify_refs(frozen["files"]); inventory(); active = []
            for unit in selected[offset:offset + width]:
                if unit["kind"] == "judge": api()[1].verify_pool(Path(unit["pool"]))
                write_new(E / f"{unit['key']}.launch.json", {"packet": ref(packet), "time": time.time(), "unit": unit})
                stream = (E / f"{unit['key']}.log").open("x")
                command = Path(unit["command_file"]).read_text().strip() + " --stream-output"
                process = subprocess.Popen(["bash", "-c", command], cwd=RUNTIME,
                    env=environment(unit["model"], unit["cap"], unit["sandbox"]["declaration"]), stdout=stream,
                    stderr=subprocess.STDOUT, start_new_session=True)
                active.append((process, stream, unit, time.monotonic()))
            audit_after = time.monotonic() + 10
            while any(process.poll() is None for process, _, _, _ in active):
                if time.monotonic() >= audit_after:
                    inventory(live=True); audit_after = time.monotonic() + 10
                for process, _, unit, start in active:
                    ceiling = 45120 if unit.get("arm") == ARMS[1] else 14460 if unit["kind"] == "author" else 3660
                    if process.poll() is None and time.monotonic() - start > ceiling:
                        raise StudyError("execution envelope exceeded; preserve and stop")
                time.sleep(1)
            errors = []
            for process, stream, unit, _ in active:
                stream.close(); outcome = capture(unit, process.returncode)
                if outcome["errors"]: errors.append(outcome["errors"])
            inventory(); require(not errors, f"capture incident: {errors}")
            require(not any((E / "integrity").rglob("*.json")) if (E / "integrity").exists() else True, "integrity incident stops further paid steps")
    except (Exception, SystemExit) as error:
        diagnostics = []
        for process, stream, unit, _ in active:
            try:
                if process.poll() is None: os.killpg(process.pid, signal.SIGTERM); process.wait(timeout=10)
            except (Exception, SystemExit):
                if process.poll() is None: os.killpg(process.pid, signal.SIGKILL); process.wait()
            stream.close()
            try:
                if not (E / f"{unit['key']}.completion.json").exists(): capture(unit, process.returncode)
            except (Exception, SystemExit) as failure: diagnostics.append({"unit": unit["key"], "error": str(failure)})
        write_new(E / f"{stage}-incident-{time.time_ns()}.json", {"original_error": str(error), "capture_errors": diagnostics, "retry": False})
        raise
    write_new(E / f"{stage}-completed.json", {"units": [u["key"] for u in selected], "inventory": inventory()})


def receipt_proof(unit):
    receipt = read(E / f"{unit['key']}.metering.json")
    physical = sorted(path.name for path in (Path(unit["records"]) / "calls").glob("*") if (path / "prompt.txt").is_file())
    rows = receipt.get("receipt_usage"); paths = receipt.get("native_session_paths")
    require(isinstance(rows, list) and isinstance(paths, list) and receipt["provider_calls"] == len(physical) == len(rows) == len(paths)
        and sorted(row["call_id"] for row in rows) == physical and len(set(paths)) == len(paths), "exact per-call native receipt coverage required")
    facts = [native_facts(path) for path in paths]
    require(all(row.get("id") and row["complete"] and row["models"] and row["efforts"]
        and all(model == unit["model"] for model in row["models"]) and all(effort == "high" for effort in row["efforts"])
        and not row.get("parent") and not row["forbidden"] for row in facts), "native effort/model/completion differs")
    hashes = {"sha256:" + sha(path) for path in paths}
    require(all(row["provider"] == "codex" and row["status"] == "complete" and isinstance(row["usage"], list) and row["usage"]
        and all(usage["model"] == unit["model"] and usage["provenance"].get("model_source") == "turn_context.model"
            and usage["provenance"].get("complete_native_transcript") is True
            and usage["provenance"].get("session_sha256") in hashes for usage in row["usage"]) for row in rows), "usage lineage is incomplete")
    return receipt, facts


def evaluation_observations():
    pooling, summary = api()[1:3]; selected = [unit for unit in units() if unit["stage"] == "evaluator"]
    require([unit["key"] for unit in selected] == ["evaluator-1", "evaluator-2"], "two original evaluator units required")
    observations = []
    for unit in selected:
        outcome = read(E / f"{unit['key']}.completion.json")
        require(not outcome["errors"] and outcome["exit_code"] == 0 and outcome["original_terminal"]["outcome"] == "completed", "evaluator did not complete")
        receipt, facts = receipt_proof(unit); require(len(facts) == 1, "one evaluator native root required")
        out = Path(unit["pool"]); pooling.verify_pool(out)
        result = summary.summarize(out, F / "evaluator-criterion.json"); mapping = read(out / "records/mapping.json")
        observations.append({"unit_key": unit["key"], "pool": str(out), "native_session_id": facts[0]["id"],
            "native_snapshot": ref(receipt["native_session_paths"][0]), "mapping": mapping, "results": result,
            "patch_hashes": {cid: sha(out / "records/patches" / f"{cid}.diff") for cid in mapping["clones"]}})
    return observations


def require_evaluator():
    admission = read(E / "evaluator-admission.json")
    require(admission["evaluator_criterion"] == ref(F / "evaluator-criterion.json")
        and admission["pilot_criterion"] == ref(F / "pilot-criterion.json"), "evaluator admission belongs to other criteria")
    gate = evaluator_gate(evaluation_observations(), sha(F / "evaluator-criterion.json"), read(E / "prepared.json")["controls"])
    require(gate["passed"] and admission["gate"] == gate, "evaluator gate failed or changed; no pilot allowance")
    return gate


def close_evaluator():
    bindings(); inventory()
    try:
        observations = evaluation_observations()
        gate = evaluator_gate(observations, sha(F / "evaluator-criterion.json"), read(E / "prepared.json")["controls"])
    except (Exception, SystemExit) as error:
        write_new(E / "evaluator-failed.json", {"passed": False, "reason": str(error), "pilot_allowed": False,
            "all_attempts": costs_and_outcomes()}); raise
    value = {"evaluator_criterion": ref(F / "evaluator-criterion.json"), "pilot_criterion": ref(F / "pilot-criterion.json"),
        "observations": observations, "gate": gate, "harness_calibration": None, "all_attempts": costs_and_outcomes()}
    write_new(E / ("evaluator-admission.json" if gate["passed"] else "evaluator-failed.json"), value)
    print(json.dumps({"evaluator_passed": gate["passed"], "gaps": gate["gaps"]}))


def _pilot_pool():
    bindings(); require_evaluator(); prepare_api, pooling, summary, sandbox, repos, metering, pricing = api()
    selected = [unit for unit in units() if unit["stage"] == "authors"]; rows = {}; views = {}
    spec = importlib.util.spec_from_file_location("prr_frozen_check", F / "sources/trusted_check.py")
    trusted_check = importlib.util.module_from_spec(spec); spec.loader.exec_module(trusted_check)
    for unit in selected:
        completion = read(E / f"{unit['key']}.completion.json")
        require(not completion["errors"] and completion["exit_code"] == 0
            and completion["original_terminal"]["outcome"] == "completed", "failed or incomplete final capture")
        trusted_check.verify(read(unit["context"]), "final-capture")
        receipt_proof(unit); path = str(Path(unit["records"]).resolve()); record = read(Path(path) / "record.json")
        row, _ = pooling.pool_runs({path: record}); rows.update(row); views[path] = record
        if record.get("patches", {}).get("final"):
            last = sorted((Path(path) / "calls").glob("*"), key=lambda p: int(p.name))[-1] / "patch-cand-1.diff"
            require(sha(Path(path) / record["patches"]["final"]) == sha(last), "final differs from the original raw last snapshot")
    expected = {str(Path(unit["records"]).resolve()) for unit in selected}
    if not complete_finals(rows, expected) or any("final" not in view.get("patches", {}) for view in views.values()):
        write_new(E / "pilot-incomplete.json", {"rows": rows, "units": selected, "inventory": inventory(), "quality_comparison": "unavailable", "all_attempts": costs_and_outcomes()})
        return
    usable = {arm: [(path, record) for path, record in views.items() if record["arm"] == arm] for arm in ARMS}
    out = POOLS / "pilot"
    pooling.write_pool(TASK, F / "pilot-criterion.json", out, [f"{JUDGE}={RUNTIME}/experiments/compare/providers/score_codex.json"],
        next(iter(views.values())), rows, pooling.compose(usable), review_exclude=EXCLUDE, environment=environment(JUDGE, 1))
    require(len(read(out / "records/mapping.json")["clones"]) == 4, "all four final clones required")
    unit = unit_from_pool(out, "pilot-judge", "pilot-judge")
    write_new(E / "pilot-judge.json", {"units": [unit]}); dry_run(unit)


def pilot_pool():
    try:
        _pilot_pool()
    except (Exception, SystemExit) as error:
        write_new(E / "pilot-incomplete.json", {"complete": False, "reason": str(error),
            "quality_comparison": "unavailable", "all_attempts": costs_and_outcomes()})
        print(json.dumps({"complete": False, "quality_comparison": "unavailable", "reason": str(error)}))


def costs_and_outcomes():
    values = []
    for unit in units():
        path = E / f"{unit['key']}.completion.json"
        value = {"unit": unit["key"], "stage": unit["stage"], "arm": unit.get("arm"), "cost": {"value": "unavailable"}, "wall_clock_sec": "unavailable"}
        try:
            if not path.exists():
                idle = not (E / f"{unit['key']}.launch.json").exists() and not list((Path(unit["records"]) / "calls").glob("*")) and not native_paths(unit)[1]
                value.update(outcome="not_started" if idle else "incomplete")
                if idle: value.update(cost={"value": 0., "basis": "no provider start"}, wall_clock_sec=0.)
            else:
                receipt = read(E / f"{unit['key']}.metering.json"); paths = receipt.get("native_session_paths")
                facts = [native_facts(path) for path in paths] if isinstance(paths, list) else []
                value.update(original_completion=read(path), receipt=ref(E / f"{unit['key']}.metering.json"),
                    cost=standard_cost(receipt, facts), wall_clock_sec=read(path).get("wall_clock_sec", "unavailable"))
        except (Exception, SystemExit) as error: value["unavailable_diagnostic"] = str(error)
        values.append(value)
    return values


def consumption_totals(attempts):
    groups = {arm: [row for row in attempts if row.get("arm") == arm] for arm in ARMS}
    groups["evaluation_overhead"] = [row for row in attempts if row["stage"] != "authors"]
    groups["total_study"] = attempts
    result = {}
    for name, rows in groups.items():
        costs = [row["cost"]["value"] for row in rows]; times = [row["wall_clock_sec"] for row in rows]
        result[name] = {"standard_usd": sum(costs) if all(type(value) in (int, float) for value in costs) else "unavailable",
            "summed_run_wall_clock_sec": sum(times) if all(type(value) in (int, float) for value in times) else "unavailable"}
    return result


def close_pilot():
    bindings()
    attempts = costs_and_outcomes()
    try:
        require_evaluator(); current = inventory(); judges = [unit for unit in units() if unit["stage"] == "pilot-judge"]
        require(not (E / "pilot-incomplete.json").exists() and len(judges) == 1, "four usable finals and a prepared final judge are unavailable")
        unit = judges[0]; receipt_proof(unit)
        outcome = read(E / "pilot-judge.completion.json")
        require(not outcome["errors"] and outcome["exit_code"] == 0 and outcome["original_terminal"]["outcome"] == "completed", "final judge incomplete")
        pooling, summary = api()[1:3]; pooling.verify_pool(POOLS / "pilot")
        result = summary.summarize(POOLS / "pilot", F / "pilot-criterion.json")
        require(len(result["runs"]) == len(result["clones"]) == 4 and not result["excluded_judges"], "four final canonical joins required")
        scores = {arm: [row["value"] for row in result["runs"] if row["arm"] == arm] for arm in ARMS}
        require(all(len(rows) == 2 and all(type(value) is int and 0 <= value <= 8 for value in rows) for rows in scores.values()), "complete integer arm ratings required")
        means = {arm: sum(rows) / 2 for arm, rows in scores.items()}
        write_new(E / "pilot-readout.json", {"complete": True, "canonical": result, "scores": scores, "means": means,
            "orc_minus_direct": means[ARMS[1]] - means[ARMS[0]], "inventory": current, "all_attempts": attempts, "consumption": consumption_totals(attempts),
            "deployed_generation_stages": ["authors"], "evaluation_overhead_stages": ["evaluator", "pilot-judge"],
            "limits": ["Descriptive two-per-arm contrast; unequal compute, prompts and staged context.", "Standard token-equivalent cost, not billed cost.", "No C1/V2 or campaign authority."]})
    except (Exception, SystemExit) as error:
        write_new(E / "pilot-readout.json", {"complete": False, "comparison": "unavailable", "reason": str(error),
            "all_attempts": attempts, "consumption": consumption_totals(attempts)}); return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "freeze", "run", "close-evaluator", "pool", "close"))
    parser.add_argument("--source-commit"); parser.add_argument("--stage", choices=("evaluator", "authors", "pilot-judge"))
    args = parser.parse_args()
    if args.phase == "prepare":
        require(args.source_commit, "exact reviewed source commit required"); prepare(args.source_commit)
    elif args.phase == "freeze": require(args.stage, "fixed stage required"); freeze(args.stage)
    elif args.phase == "run": require(args.stage, "fixed stage required"); execute(args.stage)
    elif args.phase == "close-evaluator": close_evaluator()
    elif args.phase == "pool": pilot_pool()
    else: close_pilot()


if __name__ == "__main__":
    main()
