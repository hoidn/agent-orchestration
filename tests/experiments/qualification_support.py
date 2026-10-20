"""Temporary qualification evidence; no provider calls and no committed study criteria."""

import hashlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return path


def ref(path):
    return {"file": str(path), "sha256": sha(path)}


def package_sha(task):
    lines = "".join(f"{sha(p)}  ./{p.relative_to(task).as_posix()}\n"
                    for p in sorted(task.rglob('*')) if p.is_file())
    return hashlib.sha256(lines.encode()).hexdigest()


def measure_free(root, *, template=None, tasks=()):
    value = json.loads(Path(template).read_text()) if template else {}
    value.update(purpose="measure-free", tasks=[str(t) for t in tasks])
    return write(root / "measure-free.json", value)


def qualified(root, *, runtime=None, tasks=None, judges=("gpt-6.1-sol",), providers=None):
    """Create two qualifying raw R55 samples and a calibrated blind anchor pool per task."""
    root.mkdir(parents=True, exist_ok=True)
    runtime = runtime or root / "runtime"
    if not (runtime / "experiments/compare/score.orc").exists():
        (runtime / "experiments/compare").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / "experiments/compare/score.orc", runtime / "experiments/compare/score.orc")
    bindings = runtime / "experiments/compare/score.providers.json"
    if not bindings.exists():
        write(bindings, {"providers.judge": "codex_unrestricted_workspace"})
    if tasks is None:
        task = root / "task"
        (task / "anchors").mkdir(parents=True)
        (task / "task.txt").write_text("Repair the task")
        (task / "base_commit").write_text("a" * 40)
        tasks = [task]
    family, measurements, pools = {}, {}, []
    for task in tasks:
        anchors = task / "anchors"
        anchors.mkdir(exist_ok=True)
        controls = {}
        for role in ("upstream", "stub"):
            anchor = anchors / f"{task.name}-{role}.diff"
            if not anchor.exists():
                alternatives = list(anchors.glob('*.diff'))
                selected = [p for p in alternatives if ('upstream' in p.stem) == (role == 'upstream')]
                if len(alternatives) == 2 and len(selected) == 1:
                    anchor = selected[0]
                else:
                    anchor.write_text(f"{role} patch")
            controls[role] = {"label": anchor.stem, "source": ref(anchor), "pooled_patch_sha256": sha(anchor)}
        digest, samples = package_sha(task), []
        for n in (1, 2):
            direct_dir = root / "private" / task.name / "direct_task" / f"run-{n}"
            review_dir = root / "private" / task.name / "review_once" / f"run-{n}"
            patch = direct_dir / "collected/final.diff"
            patch.parent.mkdir(parents=True)
            patch.write_text(f"patch {n}")
            common = {"task": str(task), "base": (task / "base_commit").read_text().strip(),
                      "compare_base": "b" * 40, "outcome": "completed", "calls": 1,
                      "scan": {"calls": 1, "hits": [], "verdict": None}}
            direct = write(direct_dir / "record.json", common | {
                "arm": "direct_task", "records": str(direct_dir), "patches": {"final": "collected/final.diff"}})
            inputs = write(direct_dir / "inputs.json", {"model": "gpt-6.1-sol", "effort": "high",
                                                       "task": (task / "task.txt").read_text()})
            review = write(review_dir / "record.json", common | {
                "arm": "review_once", "records": str(review_dir),
                "applied": {"path": str(patch), "sha256": sha(patch)},
                "review": {"variant": "REQUEST_CHANGES", "findings": ["one", "two"]}})
            samples.append({"direct_record": ref(direct), "direct_inputs": ref(inputs), "patch": ref(patch),
                            "review_record": ref(review)})
        source = write(root / "private" / task.name / "source.json", {"slug": task.name, "package_sha256": digest,
            "single_calls": [{"run": f"direct_task/run-{n}"} for n in (1, 2)]})
        family[task.name] = {"package_sha256": digest, "sources": [ref(source)], "samples": samples}
        measurements[task.name] = {"package_sha256": digest, "controls": controls}
    measurement = {"evaluator": {
        "score_workflow": ref(runtime / "experiments/compare/score.orc"),
        "judges": {name: {"effort": "high", "providers": ref((providers or {}).get(name, bindings))} for name in judges}},
        "tasks": measurements}
    calibration = write(root / "private/calibration/criterion.json", {
        "purpose": "calibration", "calibration_kind": "measure", "budget": {"call_cap": 20},
        "judges": list(judges), "calibration": {"margin": 2, "error_rate": 0}, "measurement": measurement})
    for task in tasks:
        pool = root / "private/calibration" / task.name
        clones = {role: {"arm": "anchor", "run": None, "labels": [measurements[task.name]["controls"][role]["label"]]}
                  for role in ("upstream", "stub")}
        mapping = write(pool / "records/mapping.json", {
            "task": str(task), "runtime": str(runtime), "criterion_sha256": sha(calibration), "runs": {},
            "judges": {name: {"dir": name, "providers": str((providers or {}).get(name, bindings))} for name in judges},
            "clones": clones, "batches": [["upstream", "stub"]]})
        for judge in judges:
            write(pool / 'records' / f'score-inputs-{judge}.json',
                  {'judge_model': judge, 'criterion_sha256': sha(calibration)})
        results = write(pool / "records/results.json", {
            "criterion_sha256": sha(calibration), "judges": list(judges), "excluded_judges": {},
            "clones": {cid: clone | {"ratings": {name: {key: 2 if cid == "upstream" else 0
                for key in ("root_cause", "scope", "generality", "layering")} for name in judges}}
                for cid, clone in clones.items()}})
        patches = {}
        for role in clones:
            path = pool / "records/patches" / f"{role}.diff"
            path.parent.mkdir(exist_ok=True)
            shutil.copyfile(Path(controls[role]["source"]["file"]) if len(tasks) == 1 else
                            Path(measurements[task.name]["controls"][role]["source"]["file"]), path)
            patches[role] = ref(path)
        pools.append({"task_id": task.name, "mapping": ref(mapping), "results": ref(results), "patches": patches})
    receipt = write(root / "private/qualification.json", {
        "schema": "orc-structural-qualification-v1",
        "family": {"kind": "review-blockers-r55", "rule": ref(REPO / "experiments/compare/criteria/calibration.json"),
                   "tasks": family}, "measure": {"criterion": ref(calibration), "pools": pools}})
    criterion = write(root / "criterion.json", {
        "purpose": "quality", "tasks": [str(t) for t in tasks], "judges": list(judges),
        "judge_bindings": {name: info["providers"]["file"]
                           for name, info in measurement["evaluator"]["judges"].items()},
        "calibration": {"margin": 2, "error_rate": 0}, "measurement": measurement, "qualification": ref(receipt)})
    return SimpleNamespace(criterion=criterion, receipt=receipt, calibration=calibration, runtime=runtime,
                           tasks=tasks, pools=pools, bindings=bindings, judges=list(judges))


def refresh(q):
    """Rehash edited referenced JSON files up to the study; changes remain subject to semantic validation."""
    receipt = json.loads(q.receipt.read_text())
    for task in receipt["family"]["tasks"].values():
        for source in task.get("sources", []):
            source.update(ref(Path(source["file"])))
        for sample in task.get("samples", []):
            for key, value in sample.items():
                if value is not None:
                    sample[key] = ref(Path(value["file"]))
    receipt["measure"]["criterion"] = ref(q.calibration)
    for pool in receipt["measure"]["pools"]:
        for key in ("mapping", "results"):
            pool[key] = ref(Path(pool[key]["file"]))
        mapping = json.loads(Path(pool['mapping']['file']).read_text())
        for judge in mapping['judges']:
            path = Path(pool['mapping']['file']).parent / f'score-inputs-{judge}.json'
            if path.exists():
                inputs = json.loads(path.read_text())
                inputs['criterion_sha256'] = mapping['criterion_sha256']
                write(path, inputs)
    write(q.receipt, receipt)
    study = json.loads(q.criterion.read_text())
    study["qualification"] = ref(q.receipt)
    write(q.criterion, study)


def module_criterion(root):
    template = REPO / 'experiments/orc_structural_search/criteria/three_arm.json'
    value = json.loads(template.read_text())
    value.update(models={'gpt-6.1-sol': ['high'], 'claude-opus-5-5': ['high']}, per_call_timeout_sec=5400,
                 arms={'I1': {'interface': 'I1', 'condition': 'topology-only', 'parent': 'orc'},
                       'I2': {'interface': 'I2', 'condition': 'topology-only', 'parent': 'orc'},
                       'I3': {'interface': 'I3', 'condition': 'topology-only', 'parent': 'python'},
                       'I1/module': {'interface': 'I1', 'condition': 'module', 'parent': 'orc'}})
    return write(root / 'module-criterion.json', value)
