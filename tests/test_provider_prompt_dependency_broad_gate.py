from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER = REPO_ROOT / "scripts/provider_prompt_dependency_broad_gate.py"
BROAD_BASELINE = (
    REPO_ROOT
    / "tests/baselines/workflow_lisp/provider_prompt_dependencies_broad_known_failures.json"
)
BASELINE_HELPER_MIGRATION_INVARIANT_SHA256 = (
    "eba9b11a15ef5c42a10b05055a3835c342d9d71d6b7ab6662b6dcb75f3a71be4"
)
TASK10_OVERLAY_ELIGIBLE = [
    "tests/test_workflow_lisp_provider_prompt_dependencies_e2e.py",
    "tests/fixtures/workflow_lisp/provider_prompt_dependencies/mixed.orc",
    "tests/fixtures/workflow_lisp/provider_prompt_dependencies/procedure_loop.orc",
    "tests/test_workflow_lisp_provider_prompt_dependencies.py",
    "tests/test_provider_attempt_allocation.py",
    "tests/test_prompt_dependency_evidence.py",
    "tests/test_workflow_lisp_lexical_checkpoint_restore.py",
    "tests/test_workflow_lisp_lexical_checkpoint_default_resume.py",
]


def _load_helper():
    spec = importlib.util.spec_from_file_location("provider_prompt_dependency_broad_gate", HELPER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args], cwd=root, check=check, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )


def _write(path: Path, data: str = "data\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding="utf-8")
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "Test")
    _write(tmp_path / ".gitignore", ".orchestrate/tmp/\n")
    _write(tmp_path / "tracked.txt", "tracked\n")
    _git(tmp_path, "add", ".gitignore", "tracked.txt")
    _git(tmp_path, "commit", "-qm", "base")
    return tmp_path


@pytest.fixture
def replay_repo(tmp_path: Path) -> Path:
    clone = tmp_path / "replay"
    subprocess.run(
        ["git", "clone", "-q", "--no-checkout", str(REPO_ROOT), str(clone)], check=True
    )
    _git(clone, "checkout", "-q", "451765a2ebd374111d2cbeab0969cec4830717fb")
    _git(clone, "config", "user.email", "test@example.invalid")
    _git(clone, "config", "user.name", "Test")
    return clone


def _capture(module, repo: Path, **overrides):
    evidence = ".orchestrate/tmp/evidence/current"
    if "ignored_evidence_roots" in overrides and "output" not in overrides:
        roots = overrides["ignored_evidence_roots"]
        if len(roots) == 1:
            evidence = roots[0]
    values = {
        "repo_root": repo,
        "output": repo / evidence / "subject.json",
        "protected_paths": [],
        "allowed_untracked_paths": [],
        "task_subject_paths": [],
        "allowed_post_launch_updates": [],
        "generated_evidence_paths": [],
        "ignored_evidence_roots": [evidence],
        "generated_evidence_layout": "review-v1",
        "frozen_overlay_path": None,
    }
    values.update(overrides)
    return module.capture_subject(**values)


def _canonical(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _with_digest(payload: dict[str, object]) -> dict[str, object]:
    payload = dict(payload)
    payload["record_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    return payload


def _status(path: Path, *, nodeid: str, exit_code: int) -> None:
    path.write_bytes(
        _canonical(
            {
                "schema": "workflow_broad_isolated_status.v1",
                "row_index": 0,
                "nodeid": nodeid,
                "argv": [sys.executable, "-m", "pytest", "-q", nodeid],
                "exit_code": exit_code,
            }
        )
    )


def _junit(path: Path, *, nodeid: str, message: str | None = "assert 2 == 0") -> None:
    classname, name = nodeid.split("::", 1)
    junit_classname = classname.removesuffix(".py").replace("/", ".")
    failure = "" if message is None else f'<failure message="AssertionError">{message}</failure>'
    failures = 0 if message is None else 1
    path.write_text(
        f'<?xml version="1.0"?><testsuites tests="1" failures="{failures}" errors="0" skipped="0" time="0.1"><testsuite name="pytest" tests="1" failures="{failures}" errors="0" skipped="0" time="0.1"><testcase classname="{junit_classname}" name="{name}" time="0.1">{failure}</testcase></testsuite></testsuites>',
        encoding="utf-8",
    )


def _failure_junit(path: Path, *, nodeid: str, signature: str) -> None:
    exception, detail = signature.split(" | ", 1)
    case = ET.Element(
        "testcase",
        classname=nodeid.split("::", 1)[0].removesuffix(".py").replace("/", "."),
        name=nodeid.rsplit("::", 1)[1],
    )
    failure = ET.SubElement(case, "failure")
    if exception != "AssertionError":
        failure.set("message", f"{exception}: {detail}")
    else:
        source, compared = detail.rsplit(" | compared: ", 1)
        if " is contained in " in compared:
            left, right = compared.split(" is contained in ", 1)
            failure.set("message", f"assert {left} not in {right}\n{left} is contained in {right}")
        elif compared.endswith(" is truthy"):
            failure.set("message", f"assert {compared.removesuffix(' is truthy')}")
        else:
            failure.set("message", f"assert {compared}")
        failure.text = f">       {source}\nE       {failure.get('message').splitlines()[0]}"
    suite = ET.Element("testsuite", tests="1", failures="1", errors="0", skipped="0")
    suite.append(case)
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)


def _binding(path: Path, root: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _canonical_remediation_path(removed_rows: list[dict[str, object]]) -> str:
    digest = hashlib.sha256(_canonical(removed_rows)).hexdigest()
    return (
        "docs/plans/evidence/provider-prompt-dependencies/broad-remediations/"
        f"{digest}.json"
    )


def _full_baseline(gate, repo: Path) -> dict[str, object]:
    evidence_rel = ".orchestrate/tmp/full-baseline/current"
    subject = _capture(
        gate,
        repo,
        output=repo / evidence_rel / "subject.json",
        ignored_evidence_roots=[evidence_rel],
        generated_evidence_layout="broad-v1",
    )
    subject["head"] = "451765a2ebd374111d2cbeab0969cec4830717fb"
    subject = _with_digest({key: value for key, value in subject.items() if key != "record_sha256"})
    subject_path = repo / evidence_rel / "subject.json"
    subject_path.write_bytes(_canonical(subject))

    authority_paths = (
        "docs/plans/evidence/procedure-first-migration-waves/task8-baseline-replay/adjudication.json",
        "docs/plans/2026-07-13-procedure-migration-identity-compatibility-baseline-correction.json",
        "tests/workflow_lisp_procedure_identity.py",
    )
    for relative in authority_paths:
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((REPO_ROOT / relative).read_bytes())
    authority = json.loads((repo / authority_paths[0]).read_text(encoding="utf-8"))
    accepted = [row for row in authority["failures"] if row.get("category") == "established_unrelated"]

    collection_log = _write(
        repo / evidence_rel / "collection.log",
        "\n".join([*(row["nodeid"] for row in accepted), "", "6 tests collected in 0.01s", ""]),
    )
    collection_status = _with_digest(
        {
            "schema": "workflow_broad_command_status.v1",
            "phase": "collection",
            "argv": ["pytest", "--collect-only", "-q"],
            "exit_code": 0,
        }
    )
    collection_status_path = repo / evidence_rel / "collection.status.json"
    collection_status_path.write_bytes(_canonical(collection_status))

    broad_junit = repo / evidence_rel / "junit.xml"
    broad_suite = ET.Element("testsuite", tests="6", failures="6", errors="0", skipped="0")
    failure_rows = []
    for index, accepted_row in enumerate(accepted):
        stem = repo / evidence_rel / "isolated" / f"row-{index:02d}"
        stem.parent.mkdir(parents=True, exist_ok=True)
        raw_junit = stem.with_suffix(".xml")
        _failure_junit(
            raw_junit,
            nodeid=accepted_row["nodeid"],
            signature=accepted_row["normalized_failure_signature"],
        )
        canonical = gate.canonical_failure_from_junit(
            raw_junit, nodeid=accepted_row["nodeid"], repo_root=repo
        )
        assert canonical["normalized_failure_signature"] == accepted_row["normalized_failure_signature"]
        broad_case = ET.parse(raw_junit).getroot().find("testcase")
        assert broad_case is not None
        broad_suite.append(broad_case)
        raw_log = _write(stem.with_suffix(".log"), f"isolated row {index}\n")
        raw_status = stem.with_suffix(".status.json")
        junit_rel = raw_junit.relative_to(repo).as_posix()
        isolated_argv = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            accepted_row["nodeid"],
            f"--junitxml={junit_rel}",
        ]
        raw_status.write_bytes(
            _canonical(
                {
                    "schema": "workflow_broad_isolated_status.v1",
                    "row_index": index,
                    "nodeid": accepted_row["nodeid"],
                    "argv": isolated_argv,
                    "exit_code": 1,
                }
            )
        )
        projection = {
            "nodeid": accepted_row["nodeid"],
            "normalized_failure_signature": accepted_row["normalized_failure_signature"],
        }
        failure_rows.append(
            {
                "nodeid": accepted_row["nodeid"],
                "normalized_failure_signature": accepted_row["normalized_failure_signature"],
                "isolated_argv": isolated_argv,
                "isolated_exit": 1,
                "raw_log": _binding(raw_log, repo),
                "raw_junit": _binding(raw_junit, repo),
                "raw_status": _binding(raw_status, repo),
                "canonical_payload": canonical,
                "canonical_payload_sha256": hashlib.sha256(_canonical(canonical)).hexdigest(),
                "stable_signature_sha256": hashlib.sha256(_canonical(projection)).hexdigest(),
                "authority_row_sha256": hashlib.sha256(_canonical(accepted_row)).hexdigest(),
            }
        )
    ET.ElementTree(broad_suite).write(broad_junit, encoding="utf-8", xml_declaration=True)
    broad_log = _write(repo / evidence_rel / "broad.log", "6 failed in 0.01s\n")
    broad_status = _with_digest(
        {
            "schema": "workflow_broad_command_status.v1",
            "phase": "broad",
            "argv": [
                "pytest",
                "-q",
                "-n",
                "16",
                "--dist=worksteal",
                f"--junitxml={broad_junit.relative_to(repo).as_posix()}",
            ],
            "exit_code": 1,
        }
    )
    (repo / evidence_rel / "broad.status.json").write_bytes(_canonical(broad_status))
    baseline = _with_digest(
        {
            "schema": "workflow_broad_known_failure_baseline.v1",
            "implementation_base_commit": "451765a2ebd374111d2cbeab0969cec4830717fb",
            "captured_at": "2026-07-17T12:00:00Z",
            "subject": {
                **_binding(subject_path, repo),
                "record_sha256": subject["record_sha256"],
                "head": subject["head"],
                "index_tree": subject["index_tree"],
                "full_status": subject["full_status"],
                "inventory": subject["inventory"],
            },
            "environment": {"python": sys.version, "pytest": pytest.__version__, "platform": "test-platform"},
            "normalization": {
                "schema": "workflow_broad_failure_normalization.v1",
                "helper_sha256": hashlib.sha256(HELPER.read_bytes()).hexdigest(),
            },
            "authorities": {relative: _binding(repo / relative, repo) for relative in authority_paths},
            "collection": {"status": collection_status, "log": _binding(collection_log, repo), "collected": 6},
            "broad": {
                "status": broad_status,
                "log": _binding(broad_log, repo),
                "junit": _binding(broad_junit, repo),
                "totals": {
                    "tests": 6,
                    "failures": 6,
                    "errors": 0,
                    "skipped": 0,
                    "passed": 0,
                    "xfailed": 0,
                    "xpassed": 0,
                },
            },
            "failure_rows": failure_rows,
        }
    )
    gate.validate_baseline(baseline, repo_root=repo)
    return baseline


def _valid_remediation(gate, repo: Path) -> dict[str, object]:
    proof = _write(repo / "proof.log", "focused proof\n")
    _git(repo, "add", "proof.log")
    fixing_tree = _git(repo, "write-tree").stdout.decode().strip()
    fixing_reviews = {
        "specification": "PASS fixing-spec-review-123",
        "quality": "APPROVED fixing-quality-review-456",
    }
    message = (
        "fix established failure\n\n"
        f"Review-Tree: {fixing_tree}\n"
        f"Spec-Review: {fixing_reviews['specification']}\n"
        f"Quality-Review: {fixing_reviews['quality']}\n"
    )
    _git(repo, "commit", "-qm", message)
    fixing_commit = _git(repo, "rev-parse", "HEAD").stdout.decode().strip()
    removed_rows = [
        {
            "nodeid": "tests/test_x.py::test_x",
            "canonical_payload_sha256": "b" * 64,
            "stable_signature_sha256": "c" * 64,
            "baseline_row_sha256": "d" * 64,
        }
    ]
    record_reviews = {
        "specification": "PASS record-spec-review-789",
        "quality": "APPROVED record-quality-review-012",
    }
    record_path = _canonical_remediation_path(removed_rows)
    payload = _with_digest(
        {
            "schema": "workflow_broad_failure_remediation.v1",
            "captured_at": "2026-07-17T12:00:00Z",
            "baseline_record_sha256": "a" * 64,
            "record_path": record_path,
            "removed_rows": removed_rows,
            "fixing_commit": fixing_commit,
            "fixing_tree": fixing_tree,
            "focused_proofs": [_binding(proof, repo)],
            "reviews": {
                "fixing": fixing_reviews,
                "record": record_reviews,
            },
        }
    )
    record = repo / record_path
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_bytes(_canonical(payload))
    _git(repo, "add", record_path)
    record_tree = _git(repo, "write-tree").stdout.decode().strip()
    record_message = (
        "record established-failure remediation\n\n"
        f"Review-Tree: {record_tree}\n"
        f"Spec-Review: {record_reviews['specification']}\n"
        f"Quality-Review: {record_reviews['quality']}\n"
    )
    _git(repo, "commit", "-qm", record_message)
    gate.validate_remediation(payload, repo_root=repo, remediation_path=record)
    return payload


def _commit_with_review_layout(
    repo: Path, layout: str
) -> tuple[str, str, dict[str, str]]:
    proof = _write(repo / "review-layout-proof.log", "focused proof\n")
    _git(repo, "add", proof.relative_to(repo).as_posix())
    tree = _git(repo, "write-tree").stdout.decode().strip()
    reviews = {
        "specification": "PASS layout-spec-review-123",
        "quality": "APPROVED layout-quality-review-456",
    }
    trailers = {
        "tree": f"Review-Tree: {tree}",
        "tree_value": tree,
        "specification": f"Spec-Review: {reviews['specification']}",
        "specification_value": reviews["specification"],
        "quality": f"Quality-Review: {reviews['quality']}",
        "quality_value": reviews["quality"],
    }
    message = layout.format(**trailers)
    _git(repo, "commit", "-qm", message)
    commit = _git(repo, "rev-parse", "HEAD").stdout.decode().strip()
    return commit, tree, reviews


@pytest.mark.parametrize(
    "layout",
    [
        "reviewed change\n\n{tree}\n{specification}\n{quality}\n",
        (
            "reviewed change\n\n{tree}\n"
            "Review-Patch-SHA256: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
            "{specification}\nSigned-off-by: Test <test@example.invalid>\n{quality}\n"
        ),
    ],
    ids=["review-only", "interleaved-unrelated"],
)
def test_reviewed_commit_accepts_contiguous_terminal_git_trailers(
    repo: Path, layout: str
) -> None:
    gate = _load_helper()
    commit, tree, reviews = _commit_with_review_layout(repo, layout)

    gate._validate_reviewed_commit(
        repo_root=repo,
        commit=commit,
        tree=tree,
        reviews=reviews,
        label="fixture",
    )


@pytest.mark.parametrize(
    "layout",
    [
        "reviewed change\n\n{tree}\n\n{specification}\n\n{quality}\n",
        "reviewed change\n\n{tree}\n{specification}\n{quality}\n\npostscript\n",
        "reviewed change\n\n{tree}\n{specification}\n{specification}\n{quality}\n",
        "reviewed change\n\n{tree}\n{quality}\n{specification}\n",
        "reviewed change\n\n{tree}\nreview-tree: {tree_value}\n{specification}\n{quality}\n",
        "reviewed change\n\n{tree}\n{specification}\nqUaLiTy-ReViEw: APPROVED wrong-token\n{quality}\n",
    ],
    ids=[
        "blank-separated",
        "nonterminal",
        "duplicate",
        "reordered",
        "lowercase-duplicate",
        "mixed-case-unexpected-value",
    ],
)
def test_reviewed_commit_rejects_noncanonical_review_trailer_layouts(
    repo: Path, layout: str
) -> None:
    gate = _load_helper()
    commit, tree, reviews = _commit_with_review_layout(repo, layout)

    with pytest.raises(gate.GateError, match="review trailers"):
        gate._validate_reviewed_commit(
            repo_root=repo,
            commit=commit,
            tree=tree,
            reviews=reviews,
            label="fixture",
        )


def _run_gate_cli(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HELPER), *args],
        cwd=repo,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _capture_gate_subject(gate, repo: Path, root_rel: str) -> Path:
    root = repo / root_rel
    gate.capture_subject(
        repo_root=repo,
        output=root / "subject.json",
        protected_paths=[],
        allowed_untracked_paths=[],
        task_subject_paths=[],
        allowed_post_launch_updates=[],
        generated_evidence_paths=[],
        ignored_evidence_roots=[root_rel],
        generated_evidence_layout="broad-v1",
        frozen_overlay_path=None,
    )
    return root


def _write_gate_capture(
    gate,
    repo: Path,
    root: Path,
    *,
    baseline_rows: list[dict[str, object]] | None = None,
    passing_indices: set[int] | None = None,
) -> None:
    authority = json.loads(
        (repo / "docs/plans/evidence/procedure-first-migration-waves/task8-baseline-replay/adjudication.json").read_text()
    )
    accepted = [row for row in authority["failures"] if row.get("category") == "established_unrelated"]
    passing = passing_indices or set()
    _write(
        root / "collection.log",
        "\n".join([*(row["nodeid"] for row in accepted), "", "6 tests collected in 0.01s", ""]),
    )
    gate.write_exit_status(
        root / "collection.status.json",
        phase="collection",
        argv=["pytest", "--collect-only", "-q"],
        exit_code=0,
    )
    broad_suite = ET.Element(
        "testsuite",
        tests="6",
        failures=str(6 - len(passing)),
        errors="0",
        skipped="0",
    )
    for index, accepted_row in enumerate(accepted):
        nodeid = accepted_row["nodeid"]
        if baseline_rows is not None:
            assert baseline_rows[index]["nodeid"] == nodeid
        stem = root / "isolated" / f"row-{index:02d}"
        stem.parent.mkdir(parents=True, exist_ok=True)
        junit = stem.with_suffix(".xml")
        if index in passing:
            _junit(junit, nodeid=nodeid, message=None)
        else:
            _failure_junit(
                junit,
                nodeid=nodeid,
                signature=accepted_row["normalized_failure_signature"],
            )
        case = ET.parse(junit).getroot().find(".//testcase")
        assert case is not None
        broad_suite.append(case)
        _write(stem.with_suffix(".log"), f"fresh row {index}\n")
        junit_rel = junit.relative_to(repo).as_posix()
        argv = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            nodeid,
            f"--junitxml={junit_rel}",
        ]
        stem.with_suffix(".status.json").write_bytes(
            _canonical(
                {
                    "schema": "workflow_broad_isolated_status.v1",
                    "row_index": index,
                    "nodeid": nodeid,
                    "argv": argv,
                    "exit_code": 0 if index in passing else 1,
                }
            )
        )
    broad_junit = root / "junit.xml"
    ET.ElementTree(broad_suite).write(broad_junit, encoding="utf-8", xml_declaration=True)
    summary_parts = []
    if 6 - len(passing):
        summary_parts.append(f"{6 - len(passing)} failed")
    if passing:
        summary_parts.append(f"{len(passing)} passed")
    _write(root / "broad.log", f"{', '.join(summary_parts)} in 0.01s\n")
    gate.write_exit_status(
        root / "broad.status.json",
        phase="broad",
        argv=[
            "pytest",
            "-q",
            "-n",
            "16",
            "--dist=worksteal",
            f"--junitxml={broad_junit.relative_to(repo).as_posix()}",
        ],
        exit_code=1 if len(passing) != 6 else 0,
    )


def _swap_one_broad_authority_failure_for_unrelated_case(repo: Path, root: Path) -> str:
    unrelated = "tests/test_unrelated.py::test_unrelated_failure"
    collection = root / "collection.log"
    lines = collection.read_text().splitlines()
    summary_index = next(index for index, line in enumerate(lines) if "tests collected" in line)
    lines.insert(summary_index - 1, unrelated)
    lines[summary_index + 1] = "7 tests collected in 0.01s"
    collection.write_text("\n".join(lines) + "\n")

    junit = root / "junit.xml"
    tree = ET.parse(junit)
    suite = tree.getroot()
    authority_case = suite.find("testcase")
    assert authority_case is not None
    for child in list(authority_case):
        if child.tag in ("failure", "error"):
            authority_case.remove(child)
    unrelated_case = ET.SubElement(
        suite,
        "testcase",
        classname="tests.test_unrelated",
        name="test_unrelated_failure",
    )
    ET.SubElement(unrelated_case, "failure", message="AssertionError").text = "assert False"
    suite.set("tests", "7")
    suite.set("failures", "6")
    tree.write(junit, encoding="utf-8", xml_declaration=True)
    _write(root / "broad.log", "6 failed, 1 passed in 0.01s\n")
    return unrelated


def _literal_baseline(gate, repo: Path) -> tuple[Path, dict[str, object]]:
    root = _capture_gate_subject(gate, repo, ".orchestrate/tmp/literal-baseline/current")
    _write_gate_capture(gate, repo, root)
    baseline_path = repo / ".orchestrate/tmp/literal-baseline/baseline.json"
    _run_gate_cli(
        repo,
        "build-baseline",
        "--authority",
        "docs/plans/evidence/procedure-first-migration-waves/task8-baseline-replay/adjudication.json",
        "--correction",
        "docs/plans/2026-07-13-procedure-migration-identity-compatibility-baseline-correction.json",
        "--normalizer",
        "tests/workflow_lisp_procedure_identity.py",
        "--subject-manifest",
        root.relative_to(repo).as_posix() + "/subject.json",
        "--capture-root",
        root.relative_to(repo).as_posix(),
        "--output",
        baseline_path.relative_to(repo).as_posix(),
    )
    return baseline_path, json.loads(baseline_path.read_text())


def _literal_outcome(
    gate,
    repo: Path,
    baseline_path: Path,
    baseline: dict[str, object],
    *,
    name: str,
    passing_indices: set[int],
) -> tuple[Path, dict[str, object]]:
    root = _capture_gate_subject(gate, repo, f".orchestrate/tmp/literal-outcome/{name}")
    _write_gate_capture(
        gate,
        repo,
        root,
        baseline_rows=baseline["failure_rows"],
        passing_indices=passing_indices,
    )
    outcome_path = root / "outcome.json"
    _run_gate_cli(
        repo,
        "build-outcome",
        "--baseline",
        baseline_path.relative_to(repo).as_posix(),
        "--subject-manifest",
        (root / "subject.json").relative_to(repo).as_posix(),
        "--capture-root",
        root.relative_to(repo).as_posix(),
        "--output",
        outcome_path.relative_to(repo).as_posix(),
    )
    return outcome_path, json.loads(outcome_path.read_text())


def _literal_remediation(
    gate,
    repo: Path,
    baseline: dict[str, object],
    *,
    removed_indices: set[int],
    directory: Path,
    commit_record: bool = True,
) -> tuple[Path, dict[str, object]]:
    suffix = "-".join(str(index) for index in sorted(removed_indices))
    proof = _write(repo / f"proof-{suffix}.log", "focused proof\n")
    _git(repo, "add", proof.relative_to(repo).as_posix())
    tree = _git(repo, "write-tree").stdout.decode().strip()
    fixing_reviews = {
        "specification": f"PASS fixing-spec-{suffix}",
        "quality": f"APPROVED fixing-quality-{suffix}",
    }
    message = (
        "fix established failures\n\n"
        f"Review-Tree: {tree}\n"
        f"Spec-Review: {fixing_reviews['specification']}\n"
        f"Quality-Review: {fixing_reviews['quality']}\n"
    )
    _git(repo, "commit", "-qm", message)
    commit = _git(repo, "rev-parse", "HEAD").stdout.decode().strip()
    removed_rows = []
    for index in sorted(removed_indices):
        row = baseline["failure_rows"][index]
        removed_rows.append(
            {
                "nodeid": row["nodeid"],
                "canonical_payload_sha256": row["canonical_payload_sha256"],
                "stable_signature_sha256": row["stable_signature_sha256"],
                "baseline_row_sha256": hashlib.sha256(_canonical(row)).hexdigest(),
            }
        )
    removed_rows.sort(key=lambda row: row["nodeid"])
    record_path = _canonical_remediation_path(removed_rows)
    record_reviews = {
        "specification": f"PASS record-spec-{suffix}",
        "quality": f"APPROVED record-quality-{suffix}",
    }
    remediation = _with_digest(
        {
            "schema": "workflow_broad_failure_remediation.v1",
            "captured_at": "2026-07-17T12:00:00Z",
            "baseline_record_sha256": baseline["record_sha256"],
            "record_path": record_path,
            "removed_rows": removed_rows,
            "fixing_commit": commit,
            "fixing_tree": tree,
            "focused_proofs": [_binding(proof, repo)],
            "reviews": {
                "fixing": fixing_reviews,
                "record": record_reviews,
            },
        }
    )
    path = repo / record_path
    assert directory.resolve() == path.parent.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical(remediation))
    if not commit_record:
        return path, remediation
    _git(repo, "add", record_path)
    record_tree = _git(repo, "write-tree").stdout.decode().strip()
    record_message = (
        "record established-failure remediation\n\n"
        f"Review-Tree: {record_tree}\n"
        f"Spec-Review: {record_reviews['specification']}\n"
        f"Quality-Review: {record_reviews['quality']}\n"
    )
    _git(repo, "commit", "-qm", record_message)
    gate.validate_remediation(remediation, repo_root=repo, remediation_path=path)
    return path, remediation


def test_subject_capture_is_closed_sorted_and_covers_regular_symlink_missing_and_full_status(repo: Path) -> None:
    gate = _load_helper()
    _write(repo / "protected.txt", "protected\n")
    _write(repo / "task.txt", "task\n")
    os.symlink("target", repo / "link.txt")
    subject = _capture(
        gate,
        repo,
        protected_paths=["protected.txt"],
        task_subject_paths=["missing.txt", "link.txt", "task.txt"],
    )
    assert set(subject) == gate.SUBJECT_KEYS
    assert subject["schema"] == "workflow_verification_subject.v1"
    assert subject["record_sha256"] == gate.record_digest(subject)
    assert subject["task_subject_paths"] == ["link.txt", "missing.txt", "task.txt"]
    rows = {row["path"]: row for row in subject["inventory"]}
    assert (rows["link.txt"]["type"], rows["link.txt"]["mode"]) == ("symlink", "0777")
    assert rows["missing.txt"]["type"] == "missing"
    assert rows["task.txt"]["status"] == "??"
    assert subject["full_status"] == sorted(subject["full_status"], key=lambda row: row["path"])
    gate.validate_subject(subject, repo_root=repo)
    missing_inventory = json.loads(json.dumps(subject))
    missing_inventory["inventory"].pop()
    missing_inventory = _with_digest(
        {key: value for key, value in missing_inventory.items() if key != "record_sha256"}
    )
    with pytest.raises(gate.GateError, match="inventory"):
        gate.validate_subject(missing_inventory, repo_root=repo)


@pytest.mark.parametrize("kind", ["duplicate", "overlap", "post_launch_not_subject"])
def test_subject_capture_rejects_invalid_authority_sets(repo: Path, kind: str) -> None:
    gate = _load_helper()
    _write(repo / "a", "a")
    kwargs = {"task_subject_paths": ["a"]}
    if kind == "duplicate":
        kwargs["task_subject_paths"] = ["a", "a"]
    elif kind == "overlap":
        kwargs["protected_paths"] = ["a"]
    else:
        kwargs["allowed_post_launch_updates"] = ["tracked.txt"]
    with pytest.raises(gate.GateError):
        _capture(gate, repo, **kwargs)


@pytest.mark.parametrize(
    ("source", "target"),
    [
        ("protected_paths", "allowed_untracked_paths"),
        ("protected_paths", "task_subject_paths"),
        ("allowed_untracked_paths", "protected_paths"),
        ("allowed_untracked_paths", "task_subject_paths"),
        ("task_subject_paths", "protected_paths"),
        ("task_subject_paths", "allowed_untracked_paths"),
    ],
)
def test_subject_validator_rejects_resealed_authority_overlap_in_both_directions(
    repo: Path, source: str, target: str
) -> None:
    gate = _load_helper()
    _write(repo / "candidate.txt", "candidate\n")
    subject = json.loads(json.dumps(_capture(gate, repo, **{source: ["candidate.txt"]})))
    subject[target] = ["candidate.txt"]
    subject = _with_digest(
        {key: value for key, value in subject.items() if key != "record_sha256"}
    )
    with pytest.raises(gate.GateError, match="overlap|disjoint"):
        gate.validate_subject(subject, repo_root=repo)


def test_subject_validator_rejects_resealed_post_launch_path_outside_task_subject(
    repo: Path,
) -> None:
    gate = _load_helper()
    subject = json.loads(json.dumps(_capture(gate, repo)))
    subject["allowed_post_launch_updates"] = ["tracked.txt"]
    subject = _with_digest(
        {key: value for key, value in subject.items() if key != "record_sha256"}
    )
    with pytest.raises(gate.GateError, match="post-launch|subset"):
        gate.validate_subject(subject, repo_root=repo)


def test_subject_validator_rejects_resealed_full_status_path_outside_authority_inventory(
    repo: Path,
) -> None:
    gate = _load_helper()
    _write(repo / "candidate.txt", "candidate\n")
    subject = json.loads(
        json.dumps(_capture(gate, repo, task_subject_paths=["candidate.txt"]))
    )
    subject["task_subject_paths"] = []
    subject["inventory"] = []
    subject = _with_digest(
        {key: value for key, value in subject.items() if key != "record_sha256"}
    )
    with pytest.raises(gate.GateError, match="full status|status.*inventory|authority"):
        gate.validate_subject(subject, repo_root=repo)


def test_subject_validator_does_not_require_clean_authority_row_in_full_status(
    repo: Path,
) -> None:
    gate = _load_helper()
    subject = _capture(gate, repo, protected_paths=["tracked.txt"])
    assert subject["full_status"] == []
    assert subject["inventory"][0]["status"] == "CLEAN"
    gate.validate_subject(subject, repo_root=repo)


def test_subject_validator_rejects_resealed_overlay_outside_subject_or_in_post_launch(
    repo: Path,
) -> None:
    gate = _load_helper()
    _write(repo / "owner.py", "before\n")
    _git(repo, "add", "owner.py")
    _git(repo, "commit", "-qm", "owner")
    _write(repo / "owner.py", "candidate\n")
    overlay_path = repo / ".orchestrate/tmp/authority-overlay/record.json"
    gate.capture_frozen_overlay(
        repo_root=repo, output=overlay_path, eligible_paths=["owner.py"]
    )
    subject = _capture(
        gate,
        repo,
        task_subject_paths=["owner.py"],
        frozen_overlay_path=overlay_path,
    )
    for tamper in ("outside_subject", "post_launch"):
        candidate = json.loads(json.dumps(subject))
        if tamper == "outside_subject":
            candidate["task_subject_paths"] = []
            candidate["protected_paths"] = ["owner.py"]
        else:
            candidate["allowed_post_launch_updates"] = ["owner.py"]
        candidate = _with_digest(
            {key: value for key, value in candidate.items() if key != "record_sha256"}
        )
        with pytest.raises(gate.GateError, match="overlay|subset|post-launch"):
            gate.validate_subject(candidate, repo_root=repo)


def test_subject_capture_rejects_undisclosed_dirty_staged_rename_non_file_and_invalid_utf8(repo: Path) -> None:
    gate = _load_helper()
    _write(repo / "undisclosed", "x")
    with pytest.raises(gate.GateError, match="undisclosed"):
        _capture(gate, repo)
    (repo / "undisclosed").unlink()
    _write(repo / "staged", "x")
    _git(repo, "add", "staged")
    with pytest.raises(gate.GateError, match="staged"):
        _capture(gate, repo)
    _git(repo, "reset", "-q")
    (repo / "staged").unlink()
    _git(repo, "mv", "tracked.txt", "renamed.txt")
    with pytest.raises(gate.GateError, match="rename|copy"):
        _capture(gate, repo, task_subject_paths=["tracked.txt", "renamed.txt"])
    _git(repo, "reset", "--hard", "-q")
    (repo / "dir").mkdir()
    with pytest.raises(gate.GateError, match="non-file"):
        _capture(gate, repo, task_subject_paths=["dir"])
    (repo / "dir").rmdir()
    bad = os.fsencode(repo) + b"/bad-\xff"
    fd = os.open(bad, os.O_CREAT | os.O_WRONLY, 0o644)
    os.close(fd)
    with pytest.raises(gate.GateError, match="UTF-8"):
        _capture(gate, repo)


@pytest.mark.parametrize(
    "tamper",
    ["status_type", "rename_status", "negative_bytes", "boolean_bytes"],
)
def test_subject_validator_rejects_resealed_nested_inventory_and_porcelain_status_tamper(
    repo: Path, tamper: str
) -> None:
    gate = _load_helper()
    _write(repo / "task.txt", "candidate\n")
    subject = json.loads(json.dumps(_capture(gate, repo, task_subject_paths=["task.txt"])))
    if tamper == "status_type":
        subject["full_status"][0]["status"] = 7
        subject["inventory"][0]["status"] = 7
    elif tamper == "rename_status":
        subject["full_status"][0]["status"] = "R "
        subject["inventory"][0]["status"] = "R "
    elif tamper == "negative_bytes":
        subject["inventory"][0]["bytes"] = -1
    else:
        subject["inventory"][0]["bytes"] = True
    subject = _with_digest(
        {key: value for key, value in subject.items() if key != "record_sha256"}
    )
    with pytest.raises(gate.GateError, match="status|inventory|bytes"):
        gate.validate_subject(subject, repo_root=repo)


@pytest.mark.parametrize(
    "tamper",
    [
        "subject_negative_bytes",
        "subject_boolean_bytes",
        "generated_negative_bytes",
        "staged_path_type",
        "staged_rename_status",
        "staged_empty",
        "launch_inventory_extra",
        "reviewed_negative_bytes",
        "frozen_overlay_shape",
    ],
)
def test_review_validator_rejects_resealed_nested_binding_inventory_and_status_tamper(
    repo: Path, tamper: str
) -> None:
    gate = _load_helper()
    _write(repo / "plan.md", "before\n")
    subject = _capture(
        gate,
        repo,
        task_subject_paths=["plan.md"],
        allowed_post_launch_updates=["plan.md"],
    )
    _write(repo / "plan.md", "reviewed\n")
    _git(repo, "add", "plan.md")
    patch = hashlib.sha256(_git(repo, "diff", "--cached", "--binary").stdout).hexdigest()
    tree = _git(repo, "write-tree").stdout.decode().strip()
    review = gate.build_review_subject(
        repo_root=repo,
        subject=subject,
        subject_path=repo / ".orchestrate/tmp/evidence/current/subject.json",
        generated_evidence=repo / ".orchestrate/tmp/evidence/current/subject.json",
        review_patch_sha256=patch,
        review_tree=tree,
        output=repo / ".orchestrate/tmp/evidence/current/review-subject.json",
    )
    review = json.loads(json.dumps(review))
    if tamper == "subject_negative_bytes":
        review["subject"]["bytes"] = -1
    elif tamper == "subject_boolean_bytes":
        review["subject"]["bytes"] = True
    elif tamper == "generated_negative_bytes":
        review["generated_evidence"]["bytes"] = -1
    elif tamper == "staged_path_type":
        review["staged_status"][0]["path"] = 7
    elif tamper == "staged_rename_status":
        review["staged_status"][0]["status"] = "R "
    elif tamper == "staged_empty":
        review["staged_status"] = []
    elif tamper == "launch_inventory_extra":
        review["allowed_post_launch_updates"][0]["launch"]["extra"] = True
    elif tamper == "reviewed_negative_bytes":
        review["allowed_post_launch_updates"][0]["reviewed"]["bytes"] = -1
    else:
        review["frozen_overlay"] = {"extra": True}
    review = _with_digest(
        {key: value for key, value in review.items() if key != "record_sha256"}
    )
    with pytest.raises(gate.GateError, match="status|binding|inventory|bytes|path"):
        gate.validate_review_subject(review)


def test_ignored_roots_are_absent_ignored_scoped_and_layouts_bind_exit_files(repo: Path) -> None:
    gate = _load_helper()
    subject = _capture(gate, repo, generated_evidence_layout="broad-v1")
    suffixes = {Path(path).name for path in subject["generated_evidence_paths"]}
    assert {"collection.status.json", "broad.status.json", "collection.log", "junit.xml", "broad.log", "pane.log", "outcome.json", "review-subject.json"} <= suffixes
    with pytest.raises(gate.GateError):
        _capture(gate, repo, ignored_evidence_roots=["tmp/not-ignored"])
    occupied = repo / ".orchestrate/tmp/occupied"
    occupied.mkdir(parents=True)
    with pytest.raises(gate.GateError, match="absent"):
        _capture(gate, repo, ignored_evidence_roots=[".orchestrate/tmp/occupied"])


@pytest.mark.parametrize("target_kind", ["in_repo", "external"])
def test_generated_evidence_rejects_declared_symlink_before_loading(
    repo: Path, target_kind: str
) -> None:
    gate = _load_helper()
    subject = _capture(gate, repo, generated_evidence_layout="broad-v1")
    root = repo / ".orchestrate/tmp/evidence/current"
    record = _with_digest(
        {
            "schema": "workflow_test_generated_evidence.v1",
            "subject": {"record_sha256": subject["record_sha256"]},
        }
    )
    if target_kind == "in_repo":
        target = root / "outcome.json"
        target.write_bytes(_canonical(record))
        link_target = "outcome.json"
    else:
        target = repo.parent / f"{repo.name}-external-evidence.json"
        target.write_bytes(_canonical(record))
        link_target = target.as_posix()
    supplied = root / "review-subject.json"
    supplied.symlink_to(link_target)
    with pytest.raises(gate.GateError, match="regular|symlink|evidence"):
        gate.verify_subject(
            subject,
            repo_root=repo,
            phase="launch",
            generated_evidence=supplied,
        )


@pytest.mark.parametrize("leaf_kind", ["directory", "fifo"])
def test_generated_evidence_inventory_rejects_declared_non_regular_leaf(
    repo: Path, leaf_kind: str
) -> None:
    gate = _load_helper()
    subject = _capture(gate, repo, generated_evidence_layout="review-v1")
    leaf = repo / ".orchestrate/tmp/evidence/current/review-subject.json"
    if leaf_kind == "directory":
        leaf.mkdir()
    else:
        os.mkfifo(leaf)
    with pytest.raises(gate.GateError, match="regular|evidence|type"):
        gate.verify_subject(subject, repo_root=repo, phase="launch")


@pytest.mark.parametrize(
    "root_kind", ["ordinary", "in_repo_symlink", "external_symlink", "intermediate_symlink"]
)
def test_ignored_evidence_root_chain_requires_real_directories(
    repo: Path, root_kind: str
) -> None:
    gate = _load_helper()
    root_rel = (
        ".orchestrate/tmp/link-parent/current"
        if root_kind == "intermediate_symlink"
        else ".orchestrate/tmp/evidence/current"
    )
    subject = _capture(
        gate,
        repo,
        output=repo / root_rel / "subject.json",
        ignored_evidence_roots=[root_rel],
        generated_evidence_layout="review-v1",
    )
    root = repo / root_rel
    if root_kind == "ordinary":
        gate.verify_subject(subject, repo_root=repo, phase="launch")
        return
    subject_bytes = (root / "subject.json").read_bytes()
    if root_kind == "intermediate_symlink":
        target_parent = repo / ".orchestrate/tmp/redirected-parent"
        redirected_root = target_parent / "current"
        redirected_root.mkdir(parents=True)
        (redirected_root / "subject.json").write_bytes(subject_bytes)
        shutil.rmtree(root.parent)
        root.parent.symlink_to(target_parent, target_is_directory=True)
    else:
        target = (
            repo / ".orchestrate/tmp/redirected-root"
            if root_kind == "in_repo_symlink"
            else repo.parent / f"{repo.name}-external-root"
        )
        target.mkdir(parents=True)
        (target / "subject.json").write_bytes(subject_bytes)
        shutil.rmtree(root)
        root.symlink_to(target, target_is_directory=True)
    with pytest.raises(gate.GateError, match="root|directory|symlink|component"):
        gate.verify_subject(subject, repo_root=repo, phase="launch")


def test_launch_verification_allows_only_declared_generated_and_baseline_transitions(repo: Path) -> None:
    gate = _load_helper()
    _write(repo / "plan.md", "before\n")
    subject = _capture(
        gate,
        repo,
        task_subject_paths=["plan.md", "baseline.json"],
        allowed_post_launch_updates=["plan.md", "baseline.json"],
        generated_evidence_layout="broad-v1",
    )
    gate.verify_subject(subject, repo_root=repo, phase="launch")
    _write(repo / "plan.md", "after\n")
    with pytest.raises(gate.GateError):
        gate.verify_subject(subject, repo_root=repo, phase="launch")
    _write(repo / "plan.md", "before\n")
    baseline = _with_digest(
        {
            "schema": "workflow_broad_known_failure_baseline.v1",
            "subject": gate.subject_binding(subject, subject_path=repo / ".orchestrate/tmp/evidence/current/subject.json"),
            "implementation_base_commit": subject["head"],
            "normalization": {"schema": "workflow_broad_failure_normalization.v1", "helper_sha256": "0" * 64},
            "environment": {}, "collection": {}, "broad": {}, "failure_rows": [], "authorities": {},
        }
    )
    (repo / "baseline.json").write_bytes(_canonical(baseline))
    _write(repo / "plan.md", "after evidence\n")
    gate.verify_subject(subject, repo_root=repo, phase="launch", generated_evidence="baseline.json")
    (repo / "plan.md").unlink()
    with pytest.raises(gate.GateError, match="transition|inventory|type|status"):
        gate.verify_subject(subject, repo_root=repo, phase="launch", generated_evidence="baseline.json")
    os.symlink("tracked.txt", repo / "plan.md")
    with pytest.raises(gate.GateError, match="transition|inventory|type"):
        gate.verify_subject(subject, repo_root=repo, phase="launch", generated_evidence="baseline.json")
    (repo / "plan.md").unlink()
    _write(repo / "plan.md", "after evidence\n")
    _write(repo / ".orchestrate/tmp/evidence/current/extra", "x")
    with pytest.raises(gate.GateError, match="undeclared"):
        gate.verify_subject(subject, repo_root=repo, phase="launch", generated_evidence="baseline.json")


def test_exit_status_schema_is_closed_and_requires_exact_collect_zero_broad_one(tmp_path: Path) -> None:
    gate = _load_helper()
    collect = tmp_path / "collection.status.json"
    broad = tmp_path / "broad.status.json"
    gate.write_exit_status(collect, phase="collection", argv=["pytest", "--collect-only", "-q"], exit_code=0)
    gate.write_exit_status(broad, phase="broad", argv=["pytest", "-q"], exit_code=1)
    assert gate.load_exit_status(collect, expected_phase="collection", expected_exit=0)["exit_code"] == 0
    assert gate.load_exit_status(broad, expected_phase="broad", expected_exit=1)["exit_code"] == 1
    tampered = json.loads(broad.read_text())
    tampered["extra"] = True
    broad.write_bytes(_canonical(tampered))
    with pytest.raises(gate.GateError):
        gate.load_exit_status(broad, expected_phase="broad", expected_exit=1)


def test_artifact_binding_accepts_repo_relative_cli_paths(repo: Path) -> None:
    gate = _load_helper()
    artifact = gate._artifact(Path("tracked.txt"), repo)
    assert artifact["path"] == "tracked.txt"
    assert artifact["bytes"] == len(b"tracked\n")
    assert gate._authority_bindings([Path("tracked.txt")], repo) == {"tracked.txt": artifact}
    one_byte = _write(repo / "one-byte", "x")
    boolean_bytes = gate._artifact(one_byte, repo)
    boolean_bytes["bytes"] = True
    with pytest.raises(gate.GateError, match="bytes"):
        gate._validate_artifact_binding(boolean_bytes, repo_root=repo)


def test_frozen_overlay_selects_exact_dirty_rows_and_detects_omission_clean_staged_and_drift(repo: Path) -> None:
    gate = _load_helper()
    _write(repo / "eligible-a", "a")
    _write(repo / "eligible-b", "b")
    _git(repo, "add", "eligible-a", "eligible-b")
    _git(repo, "commit", "-qm", "eligible")
    _write(repo / "eligible-a", "changed")
    output = repo / ".orchestrate/tmp/overlay/record.json"
    overlay = gate.capture_frozen_overlay(
        repo_root=repo,
        output=output,
        eligible_paths=["eligible-a", "eligible-b"],
    )
    assert overlay["selected_paths"] == ["eligible-a"]
    gate.validate_frozen_overlay(overlay, repo_root=repo, record_path=output)
    _write(repo / "eligible-a", "a")
    with pytest.raises(gate.GateError):
        gate.capture_frozen_overlay(
            repo_root=repo,
            output=repo / ".orchestrate/tmp/overlay-2/record.json",
            eligible_paths=["eligible-a", "eligible-b"],
        )
    _write(repo / "eligible-a", "drift")
    with pytest.raises(gate.GateError, match="drift|mismatch"):
        gate.validate_frozen_overlay(overlay, repo_root=repo, record_path=output)


def test_frozen_overlay_validator_rejects_resealed_omitted_dirty_and_selected_clean_rows_and_no_clobber(
    repo: Path,
) -> None:
    gate = _load_helper()
    for path in ("eligible-a", "eligible-b", "eligible-clean"):
        _write(repo / path, "before\n")
    _git(repo, "add", "eligible-a", "eligible-b", "eligible-clean")
    _git(repo, "commit", "-qm", "eligible")
    _write(repo / "eligible-a", "changed a\n")
    _write(repo / "eligible-b", "changed b\n")
    output = repo / ".orchestrate/tmp/overlay-matrix/record.json"
    overlay = gate.capture_frozen_overlay(
        repo_root=repo,
        output=output,
        eligible_paths=["eligible-a", "eligible-b", "eligible-clean"],
    )
    original = output.read_bytes()
    with pytest.raises(gate.GateError, match="absent|clobber|exist"):
        gate.capture_frozen_overlay(
            repo_root=repo,
            output=output,
            eligible_paths=["eligible-a", "eligible-b", "eligible-clean"],
        )
    assert output.read_bytes() == original

    omitted = json.loads(json.dumps(overlay))
    omitted["selected_paths"] = ["eligible-a"]
    omitted["inventory"] = [omitted["inventory"][0]]
    omitted = _with_digest({key: value for key, value in omitted.items() if key != "record_sha256"})
    with pytest.raises(gate.GateError, match="selection|dirty|omitted"):
        gate.validate_frozen_overlay(omitted, repo_root=repo, record_path=output)

    selected_clean = json.loads(json.dumps(overlay))
    selected_clean["selected_paths"].append("eligible-clean")
    selected_clean["selected_paths"].sort()
    status = {row["path"]: row["status"] for row in gate._status(repo)}
    selected_clean["inventory"].append(gate._inventory(repo, "eligible-clean", status))
    selected_clean["inventory"].sort(key=lambda row: row["path"])
    selected_clean = _with_digest(
        {key: value for key, value in selected_clean.items() if key != "record_sha256"}
    )
    with pytest.raises(gate.GateError, match="selection|dirty|clean"):
        gate.validate_frozen_overlay(selected_clean, repo_root=repo, record_path=output)

    digest_tamper = json.loads(json.dumps(overlay))
    digest_tamper["record_sha256"] = "0" * 64
    with pytest.raises(gate.GateError, match="digest"):
        gate.validate_frozen_overlay(digest_tamper, repo_root=repo, record_path=output)


def test_frozen_overlay_capture_rejects_staged_and_rename_rows(repo: Path) -> None:
    gate = _load_helper()
    _write(repo / "eligible", "before\n")
    _git(repo, "add", "eligible")
    _git(repo, "commit", "-qm", "eligible")
    _write(repo / "eligible", "staged\n")
    _git(repo, "add", "eligible")
    with pytest.raises(gate.GateError, match="staged"):
        gate.capture_frozen_overlay(
            repo_root=repo,
            output=repo / ".orchestrate/tmp/staged-overlay/record.json",
            eligible_paths=["eligible"],
        )
    _git(repo, "reset", "--hard", "-q")
    _git(repo, "mv", "eligible", "renamed")
    with pytest.raises(gate.GateError, match="rename|copy"):
        gate.capture_frozen_overlay(
            repo_root=repo,
            output=repo / ".orchestrate/tmp/rename-overlay/record.json",
            eligible_paths=["eligible", "renamed"],
        )


def test_frozen_overlay_is_enforced_in_launch_and_review_phases(repo: Path) -> None:
    gate = _load_helper()
    _write(repo / "owner.py", "before\n")
    _write(repo / "plan.md", "before\n")
    _git(repo, "add", "owner.py", "plan.md")
    _git(repo, "commit", "-qm", "owners")
    _write(repo / "owner.py", "frozen candidate\n")
    overlay_path = repo / ".orchestrate/tmp/phase-overlay/record.json"
    gate.capture_frozen_overlay(
        repo_root=repo, output=overlay_path, eligible_paths=["owner.py"]
    )
    subject = _capture(
        gate,
        repo,
        task_subject_paths=["owner.py", "plan.md"],
        allowed_post_launch_updates=["plan.md"],
        frozen_overlay_path=overlay_path,
    )
    gate.verify_subject(subject, repo_root=repo, phase="launch")
    _write(repo / "owner.py", "launch drift\n")
    with pytest.raises(gate.GateError, match="overlay|drift|mismatch"):
        gate.verify_subject(subject, repo_root=repo, phase="launch")
    _write(repo / "owner.py", "frozen candidate\n")
    _write(repo / "plan.md", "reviewed\n")
    _git(repo, "add", "plan.md")
    patch = hashlib.sha256(_git(repo, "diff", "--cached", "--binary").stdout).hexdigest()
    tree = _git(repo, "write-tree").stdout.decode().strip()
    review = gate.build_review_subject(
        repo_root=repo,
        subject=subject,
        subject_path=repo / ".orchestrate/tmp/evidence/current/subject.json",
        generated_evidence=repo / ".orchestrate/tmp/evidence/current/subject.json",
        review_patch_sha256=patch,
        review_tree=tree,
        output=repo / ".orchestrate/tmp/evidence/current/review-subject.json",
    )
    gate.verify_subject(subject, repo_root=repo, phase="review", review_subject=review)
    _write(repo / "owner.py", "review drift\n")
    with pytest.raises(gate.GateError, match="overlay|drift|mismatch"):
        gate.verify_subject(subject, repo_root=repo, phase="review", review_subject=review)
    _write(repo / "owner.py", "frozen candidate\n")
    _git(repo, "add", "owner.py")
    with pytest.raises(gate.GateError, match="overlay|staged|status"):
        gate.verify_subject(subject, repo_root=repo, phase="review", review_subject=review)


def test_task10_exact_eight_path_cli_derives_only_dirty_eligible_rows(repo: Path) -> None:
    for path in TASK10_OVERLAY_ELIGIBLE:
        _write(repo / path, "before\n")
    _git(repo, "add", *TASK10_OVERLAY_ELIGIBLE)
    _git(repo, "commit", "-qm", "task10 eligible")
    dirty = {TASK10_OVERLAY_ELIGIBLE[0], TASK10_OVERLAY_ELIGIBLE[3]}
    for path in dirty:
        _write(repo / path, "dirty\n")
    output = ".orchestrate/tmp/task10-exact-overlay/frozen-overlay.json"
    argv = [
        sys.executable,
        str(HELPER),
        "capture-frozen-overlay",
        "--output",
        output,
    ]
    for path in TASK10_OVERLAY_ELIGIBLE:
        argv.extend(["--eligible-path", path])
    completed = subprocess.run(argv, cwd=repo, text=True, capture_output=True)
    assert completed.returncode == 0, completed.stderr
    overlay = json.loads((repo / output).read_text())
    assert overlay["eligible_paths"] == sorted(TASK10_OVERLAY_ELIGIBLE)
    assert overlay["selected_paths"] == sorted(dirty)
    assert [row["path"] for row in overlay["inventory"]] == sorted(dirty)


def test_validate_frozen_overlay_cli_accepts_plan_literal(repo: Path) -> None:
    _write(repo / "tracked.txt", "dirty\n")
    overlay_path = repo / ".orchestrate/tmp/task10-validation/frozen-overlay.json"
    gate = _load_helper()
    gate.capture_frozen_overlay(
        repo_root=repo,
        output=overlay_path,
        eligible_paths=["tracked.txt"],
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(HELPER),
            "validate-frozen-overlay",
            "--overlay",
            overlay_path.relative_to(repo).as_posix(),
        ],
        cwd=repo,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_validate_frozen_overlay_rejects_current_index_tree_drift(repo: Path) -> None:
    _write(repo / "tracked.txt", "dirty\n")
    overlay_path = repo / ".orchestrate/tmp/task10-index-drift/frozen-overlay.json"
    gate = _load_helper()
    overlay = gate.capture_frozen_overlay(
        repo_root=repo,
        output=overlay_path,
        eligible_paths=["tracked.txt"],
    )
    gate.validate_frozen_overlay(overlay, repo_root=repo, record_path=overlay_path)

    _write(repo / "index-only.txt", "staged after capture\n")
    _git(repo, "add", "index-only.txt")
    with pytest.raises(gate.GateError, match="index|tree|staged"):
        gate.validate_frozen_overlay(overlay, repo_root=repo, record_path=overlay_path)


def test_post_edit_subject_binds_frozen_overlay_and_rejects_staging_or_post_launch_overlay(repo: Path) -> None:
    gate = _load_helper()
    _write(repo / "owner.py", "before")
    _git(repo, "add", "owner.py")
    _git(repo, "commit", "-qm", "owner")
    _write(repo / "owner.py", "candidate")
    overlay_path = repo / ".orchestrate/tmp/overlay/record.json"
    gate.capture_frozen_overlay(
        repo_root=repo, output=overlay_path, eligible_paths=["owner.py"]
    )
    subject = _capture(
        gate,
        repo,
        task_subject_paths=["owner.py"],
        frozen_overlay_path=overlay_path,
    )
    assert subject["frozen_overlay"]["selected_paths"] == ["owner.py"]
    gate.verify_subject(subject, repo_root=repo, phase="launch")
    _git(repo, "add", "owner.py")
    with pytest.raises(gate.GateError, match="frozen|staged"):
        gate.verify_subject(subject, repo_root=repo, phase="launch")
    _git(repo, "reset", "-q")
    with pytest.raises(gate.GateError):
        _capture(
            gate,
            repo,
            output=repo / ".orchestrate/tmp/other/current/subject.json",
            ignored_evidence_roots=[".orchestrate/tmp/other/current"],
            task_subject_paths=["owner.py"],
            allowed_post_launch_updates=["owner.py"],
            frozen_overlay_path=overlay_path,
        )


def test_review_envelope_binds_staged_tree_patch_generated_evidence_and_allowed_plan_update(repo: Path) -> None:
    gate = _load_helper()
    _write(repo / "task.py", "candidate")
    _write(repo / "plan.md", "before")
    subject = _capture(
        gate,
        repo,
        task_subject_paths=["task.py", "plan.md"],
        allowed_post_launch_updates=["plan.md"],
    )
    _write(repo / "plan.md", "reviewed")
    _git(repo, "add", "task.py", "plan.md")
    patch = hashlib.sha256(_git(repo, "diff", "--cached", "--binary").stdout).hexdigest()
    tree = _git(repo, "write-tree").stdout.decode().strip()
    output = repo / ".orchestrate/tmp/evidence/current/review-subject.json"
    review = gate.build_review_subject(
        repo_root=repo,
        subject=subject,
        subject_path=repo / ".orchestrate/tmp/evidence/current/subject.json",
        generated_evidence=repo / ".orchestrate/tmp/evidence/current/subject.json",
        review_patch_sha256=patch,
        review_tree=tree,
        output=output,
    )
    assert set(review) == gate.REVIEW_SUBJECT_KEYS
    gate.verify_subject(subject, repo_root=repo, phase="review", review_subject=review)
    evidence_tamper = json.loads(json.dumps(review))
    evidence_tamper["generated_evidence"]["sha256"] = "0" * 64
    evidence_tamper = _with_digest(
        {key: value for key, value in evidence_tamper.items() if key != "record_sha256"}
    )
    with pytest.raises(gate.GateError, match="evidence|binding"):
        gate.verify_subject(subject, repo_root=repo, phase="review", review_subject=evidence_tamper)
    _write(repo / "plan.md", "drift")
    with pytest.raises(gate.GateError):
        gate.verify_subject(subject, repo_root=repo, phase="review", review_subject=review)


@pytest.mark.parametrize("extra_kind", ["untracked", "rename"])
def test_review_verification_rejects_post_envelope_undeclared_status_paths_but_allows_exact_mixed_transitions(
    repo: Path, extra_kind: str
) -> None:
    gate = _load_helper()
    _write(repo / "plan.md", "before\n")
    _git(repo, "add", "plan.md")
    _git(repo, "commit", "-qm", "tracked plan")
    _write(repo / "task.py", "candidate\n")
    subject = _capture(
        gate,
        repo,
        task_subject_paths=["plan.md", "task.py"],
        allowed_post_launch_updates=["plan.md"],
    )
    _write(repo / "plan.md", "allowed unstaged update\n")
    _git(repo, "add", "task.py")
    patch = hashlib.sha256(_git(repo, "diff", "--cached", "--binary").stdout).hexdigest()
    tree = _git(repo, "write-tree").stdout.decode().strip()
    review = gate.build_review_subject(
        repo_root=repo,
        subject=subject,
        subject_path=repo / ".orchestrate/tmp/evidence/current/subject.json",
        generated_evidence=repo / ".orchestrate/tmp/evidence/current/subject.json",
        review_patch_sha256=patch,
        review_tree=tree,
        output=repo / ".orchestrate/tmp/evidence/current/review-subject.json",
    )
    gate.verify_subject(subject, repo_root=repo, phase="review", review_subject=review)
    if extra_kind == "untracked":
        _write(repo / "undeclared-after-envelope.txt", "extra\n")
    else:
        _git(repo, "mv", "tracked.txt", "renamed-after-envelope.txt")
    with pytest.raises(gate.GateError, match="status|undeclared|rename|extra"):
        gate.verify_subject(subject, repo_root=repo, phase="review", review_subject=review)


def test_canonical_junit_payload_is_bounded_and_rejects_wrong_node_or_multiple_cases(tmp_path: Path) -> None:
    gate = _load_helper()
    nodeid = "tests/test_x.py::test_x"
    junit = tmp_path / "row.xml"
    _junit(junit, nodeid=nodeid, message="assert 2 == 0")
    text = junit.read_text().replace(
        "assert 2 == 0</failure>",
        "&gt;       assert result[&quot;exit_code&quot;] == 0\nE       assert 2 == 0</failure>",
    )
    junit.write_text(text)
    payload = gate.canonical_failure_from_junit(junit, nodeid=nodeid, repo_root=tmp_path)
    assert payload == {
        "schema": "workflow_broad_canonical_failure.v1",
        "nodeid": nodeid,
        "outcome": "failure",
        "exception_type": "AssertionError",
        "normalized_failure_signature": 'AssertionError | assert result["exit_code"] == 0 | compared: 2 == 0',
    }
    assert gate.normalize_failure_text("ERROR logger:file.py:123 semantic 99", repo_root=tmp_path) == "ERROR logger:file.py:$LINE semantic 99"
    multiline = tmp_path / "multiline.xml"
    multiline.write_text(
        '<?xml version="1.0"?><testsuite><testcase classname="tests.test_x" name="test_x">'
        '<failure message="assert False">&gt;       assert any(\n'
        '            step.kind == &quot;certified&quot; for step in steps\n'
        '        )\nE       assert False</failure></testcase></testsuite>',
        encoding="utf-8",
    )
    assert gate.canonical_failure_from_junit(multiline, nodeid=nodeid, repo_root=tmp_path)[
        "normalized_failure_signature"
    ] == 'AssertionError | assert any(step.kind == "certified" for step in steps) | compared: False is truthy'
    with pytest.raises(gate.GateError):
        gate.canonical_failure_from_junit(junit, nodeid="tests/test_y.py::test_y", repo_root=tmp_path)
    other_module = tmp_path / "other.xml"
    other_module.write_text(
        '<?xml version="1.0"?><testsuite><testcase classname="tests.other" name="test_x">'
        '<failure message="assert 2 == 0">&gt; assert 2 == 0\nE assert 2 == 0</failure>'
        '</testcase></testsuite>',
        encoding="utf-8",
    )
    with pytest.raises(gate.GateError, match="node ID"):
        gate.canonical_failure_from_junit(other_module, nodeid=nodeid, repo_root=tmp_path)
    text = junit.read_text().replace("</testsuite>", junit.read_text().split("<testcase", 1)[1].split("</testcase>", 1)[0].join(["<testcase", "</testcase></testsuite>"]), 1)
    junit.write_text(text)
    with pytest.raises(gate.GateError):
        gate.canonical_failure_from_junit(junit, nodeid=nodeid, repo_root=tmp_path)


def test_stable_failure_identity_ignores_fresh_raw_evidence_but_rejects_resealed_signature_change(
    repo: Path,
) -> None:
    gate = _load_helper()
    baseline = _full_baseline(gate, repo)
    fresh = json.loads(json.dumps(baseline["failure_rows"]))
    for index, row in enumerate(fresh):
        row["raw_log"] = {"path": f"fresh/row-{index}.log", "bytes": 999, "sha256": "f" * 64}
        row["raw_junit"] = {"path": f"fresh/row-{index}.xml", "bytes": 998, "sha256": "e" * 64}
        row["raw_status"] = {"path": f"fresh/row-{index}.json", "bytes": 997, "sha256": "d" * 64}
    assert gate._failure_identity_set(baseline["failure_rows"]) == gate._failure_identity_set(fresh)

    changed = json.loads(json.dumps(fresh))
    changed[0]["normalized_failure_signature"] += " changed"
    changed[0]["canonical_payload"]["normalized_failure_signature"] = changed[0]["normalized_failure_signature"]
    changed[0]["canonical_payload_sha256"] = hashlib.sha256(
        _canonical(changed[0]["canonical_payload"])
    ).hexdigest()
    changed[0]["stable_signature_sha256"] = hashlib.sha256(
        _canonical(
            {
                "nodeid": changed[0]["nodeid"],
                "normalized_failure_signature": changed[0]["normalized_failure_signature"],
            }
        )
    ).hexdigest()
    assert gate._failure_identity_set(baseline["failure_rows"]) != gate._failure_identity_set(changed)


def test_literal_outcome_cli_and_direct_api_accept_exact_and_reject_tamper_and_malformed_artifact(
    replay_repo: Path,
) -> None:
    gate = _load_helper()
    baseline_path, baseline = _literal_baseline(gate, replay_repo)
    outcome_path, outcome = _literal_outcome(
        gate,
        replay_repo,
        baseline_path,
        baseline,
        name="exact",
        passing_indices=set(),
    )
    _run_gate_cli(
        replay_repo,
        "validate-outcome",
        "--outcome",
        outcome_path.relative_to(replay_repo).as_posix(),
    )
    exact = _run_gate_cli(
        replay_repo,
        "compare",
        "--baseline",
        baseline_path.relative_to(replay_repo).as_posix(),
        "--outcome",
        outcome_path.relative_to(replay_repo).as_posix(),
        "--remediation-dir",
        ".orchestrate/tmp/literal-remediations/absent",
    )
    assert json.loads(exact.stdout) == {"accepted": True, "mode": "exact"}
    assert gate.compare_outcome(
        baseline, outcome, remediations=[], repo_root=replay_repo
    ) == {"accepted": True, "mode": "exact"}

    malformed_remediation = _with_digest(
        {"schema": "workflow_broad_failure_remediation.v1"}
    )
    malformed_path = replay_repo / ".orchestrate/tmp/malformed-remediation.json"
    malformed_path.parent.mkdir(parents=True, exist_ok=True)
    malformed_path.write_bytes(_canonical(malformed_remediation))
    with pytest.raises(gate.GateError):
        gate.compare_outcome(
            baseline,
            outcome,
            remediations=[(malformed_remediation, malformed_path)],
            repo_root=replay_repo,
        )

    unexpected_dir = replay_repo / ".orchestrate/tmp/literal-remediations/unexpected"
    _write(unexpected_dir / "README.txt", "not a remediation record\n")
    unexpected = _run_gate_cli(
        replay_repo,
        "compare",
        "--baseline",
        baseline_path.relative_to(replay_repo).as_posix(),
        "--outcome",
        outcome_path.relative_to(replay_repo).as_posix(),
        "--remediation-dir",
        unexpected_dir.relative_to(replay_repo).as_posix(),
        check=False,
    )
    assert unexpected.returncode == 2

    canonical_dir = replay_repo / "docs/plans/evidence/provider-prompt-dependencies/broad-remediations"
    uncommitted_path, uncommitted = _literal_remediation(
        gate,
        replay_repo,
        baseline,
        removed_indices={0},
        directory=canonical_dir,
        commit_record=False,
    )
    with pytest.raises(gate.GateError, match="addition commit|committed|immutable"):
        gate.compare_outcome(
            baseline,
            outcome,
            remediations=[(uncommitted, uncommitted_path)],
            repo_root=replay_repo,
        )
    exact_uncommitted = _run_gate_cli(
        replay_repo,
        "compare",
        "--baseline",
        baseline_path.relative_to(replay_repo).as_posix(),
        "--outcome",
        outcome_path.relative_to(replay_repo).as_posix(),
        "--remediation-dir",
        canonical_dir.relative_to(replay_repo).as_posix(),
        check=False,
    )
    assert exact_uncommitted.returncode == 2

    tampered = json.loads(json.dumps(outcome))
    tampered["broad"]["totals"]["passed"] -= 1
    tampered = _with_digest(
        {key: value for key, value in tampered.items() if key != "record_sha256"}
    )
    with pytest.raises(gate.GateError):
        gate.compare_outcome(baseline, tampered, remediations=[], repo_root=replay_repo)

    raw_log = replay_repo / outcome["failure_rows"][0]["raw_log"]["path"]
    original = raw_log.read_bytes()
    raw_log.write_bytes(original + b"tampered\n")
    malformed = _run_gate_cli(
        replay_repo,
        "validate-outcome",
        "--outcome",
        outcome_path.relative_to(replay_repo).as_posix(),
        check=False,
    )
    assert malformed.returncode == 2
    raw_log.write_bytes(original)


def test_literal_compare_cli_and_direct_api_accept_reviewed_subset_and_zero_exit_and_reject_remediation(
    replay_repo: Path,
) -> None:
    gate = _load_helper()
    baseline_path, baseline = _literal_baseline(gate, replay_repo)
    subset_path, subset = _literal_outcome(
        gate,
        replay_repo,
        baseline_path,
        baseline,
        name="subset",
        passing_indices={0},
    )
    subset_dir = replay_repo / "docs/plans/evidence/provider-prompt-dependencies/broad-remediations"
    _, remediation = _literal_remediation(
        gate,
        replay_repo,
        baseline,
        removed_indices={0},
        directory=subset_dir,
    )
    subset_result = _run_gate_cli(
        replay_repo,
        "compare",
        "--baseline",
        baseline_path.relative_to(replay_repo).as_posix(),
        "--outcome",
        subset_path.relative_to(replay_repo).as_posix(),
        "--remediation-dir",
        subset_dir.relative_to(replay_repo).as_posix(),
    )
    assert json.loads(subset_result.stdout) == {"accepted": True, "mode": "reviewed_subset"}
    assert gate.compare_outcome(
        baseline,
        subset,
        remediations=[(remediation, Path(remediation["record_path"]))],
        repo_root=replay_repo,
    ) == {"accepted": True, "mode": "reviewed_subset"}

    uncommitted_path, uncommitted = _literal_remediation(
        gate,
        replay_repo,
        baseline,
        removed_indices={1},
        directory=subset_dir,
        commit_record=False,
    )
    with pytest.raises(gate.GateError, match="addition commit|committed|immutable"):
        gate.compare_outcome(
            baseline,
            subset,
            remediations=[
                (remediation, Path(remediation["record_path"])),
                (uncommitted, uncommitted_path),
            ],
            repo_root=replay_repo,
        )
    subset_uncommitted = _run_gate_cli(
        replay_repo,
        "compare",
        "--baseline",
        baseline_path.relative_to(replay_repo).as_posix(),
        "--outcome",
        subset_path.relative_to(replay_repo).as_posix(),
        "--remediation-dir",
        subset_dir.relative_to(replay_repo).as_posix(),
        check=False,
    )
    assert subset_uncommitted.returncode == 2
    uncommitted_path.unlink()

    invalid_dir = replay_repo / ".orchestrate/tmp/literal-remediations/invalid"
    invalid = json.loads(json.dumps(remediation))
    invalid["baseline_record_sha256"] = "0" * 64
    invalid = _with_digest(
        {key: value for key, value in invalid.items() if key != "record_sha256"}
    )
    invalid_dir.mkdir(parents=True)
    (invalid_dir / "invalid.json").write_bytes(_canonical(invalid))
    rejected = _run_gate_cli(
        replay_repo,
        "compare",
        "--baseline",
        baseline_path.relative_to(replay_repo).as_posix(),
        "--outcome",
        subset_path.relative_to(replay_repo).as_posix(),
        "--remediation-dir",
        invalid_dir.relative_to(replay_repo).as_posix(),
        check=False,
    )
    assert rejected.returncode == 2

    zero_path, zero = _literal_outcome(
        gate,
        replay_repo,
        baseline_path,
        baseline,
        name="zero",
        passing_indices=set(range(6)),
    )
    zero_dir = subset_dir
    _, zero_remediation = _literal_remediation(
        gate,
        replay_repo,
        baseline,
        removed_indices=set(range(1, 6)),
        directory=zero_dir,
    )
    zero_result = _run_gate_cli(
        replay_repo,
        "compare",
        "--baseline",
        baseline_path.relative_to(replay_repo).as_posix(),
        "--outcome",
        zero_path.relative_to(replay_repo).as_posix(),
        "--remediation-dir",
        zero_dir.relative_to(replay_repo).as_posix(),
    )
    assert json.loads(zero_result.stdout) == {"accepted": True, "mode": "reviewed_subset"}
    assert zero["broad"]["status"]["exit_code"] == 0
    assert gate.compare_outcome(
        baseline,
        zero,
        remediations=[
            (remediation, Path(remediation["record_path"])),
            (zero_remediation, Path(zero_remediation["record_path"])),
        ],
        repo_root=replay_repo,
    ) == {"accepted": True, "mode": "reviewed_subset"}


@pytest.mark.parametrize(
    "tamper",
    ["environment", "timestamp", "collection_argv", "broad_argv", "isolated_argv"],
)
def test_full_baseline_validator_rejects_independently_resealed_contract_tamper(
    repo: Path, tamper: str
) -> None:
    gate = _load_helper()
    baseline = json.loads(json.dumps(_full_baseline(gate, repo)))
    if tamper == "environment":
        baseline["environment"]["extra"] = "forbidden"
    elif tamper == "timestamp":
        baseline["captured_at"] = "2026-07-17T12:00:00-07:00"
    elif tamper == "collection_argv":
        baseline["collection"]["status"]["argv"].append("tests")
        baseline["collection"]["status"] = _with_digest(
            {key: value for key, value in baseline["collection"]["status"].items() if key != "record_sha256"}
        )
    elif tamper == "broad_argv":
        baseline["broad"]["status"]["argv"][4] = "--dist=load"
        baseline["broad"]["status"] = _with_digest(
            {key: value for key, value in baseline["broad"]["status"].items() if key != "record_sha256"}
        )
    else:
        baseline["failure_rows"][0]["isolated_argv"].append("--unexpected")
    baseline = _with_digest(
        {key: value for key, value in baseline.items() if key != "record_sha256"}
    )
    with pytest.raises(gate.GateError):
        gate.validate_baseline(baseline, repo_root=repo)


def test_reviewed_baseline_helper_migration_changes_only_helper_and_record_digests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gate = _load_helper()
    baseline = json.loads(BROAD_BASELINE.read_text(encoding="utf-8"))
    invariant = {key: value for key, value in baseline.items() if key != "record_sha256"}
    invariant["normalization"] = dict(invariant["normalization"])
    invariant["normalization"]["helper_sha256"] = "__HELPER_SHA256__"

    assert hashlib.sha256(_canonical(invariant)).hexdigest() == (
        BASELINE_HELPER_MIGRATION_INVARIANT_SHA256
    )
    assert baseline["normalization"]["helper_sha256"] == hashlib.sha256(
        HELPER.read_bytes()
    ).hexdigest()
    captured_interpreter = baseline["failure_rows"][0]["isolated_argv"][0]
    with monkeypatch.context() as context:
        context.setattr(gate.sys, "executable", captured_interpreter)
        gate.validate_baseline(baseline, repo_root=REPO_ROOT)


def test_baseline_builder_rejects_same_count_authority_failure_swap(
    replay_repo: Path,
) -> None:
    gate = _load_helper()
    root = _capture_gate_subject(
        gate, replay_repo, ".orchestrate/tmp/same-count-builder/current"
    )
    _write_gate_capture(gate, replay_repo, root)
    _swap_one_broad_authority_failure_for_unrelated_case(replay_repo, root)
    with pytest.raises(gate.GateError, match="broad|authority|failure"):
        gate.build_baseline(
            repo_root=replay_repo,
            authority_path=replay_repo
            / "docs/plans/evidence/procedure-first-migration-waves/task8-baseline-replay/adjudication.json",
            correction_path=replay_repo
            / "docs/plans/2026-07-13-procedure-migration-identity-compatibility-baseline-correction.json",
            normalizer_path=replay_repo / "tests/workflow_lisp_procedure_identity.py",
            subject_path=root / "subject.json",
            capture_root=root,
            output=replay_repo / ".orchestrate/tmp/same-count-builder/baseline.json",
        )


def test_baseline_validator_rejects_resealed_same_count_authority_failure_swap(
    repo: Path,
) -> None:
    gate = _load_helper()
    baseline = json.loads(json.dumps(_full_baseline(gate, repo)))
    root = repo / ".orchestrate/tmp/full-baseline/current"
    _swap_one_broad_authority_failure_for_unrelated_case(repo, root)
    baseline["collection"]["log"] = _binding(root / "collection.log", repo)
    baseline["collection"]["collected"] = 7
    baseline["broad"]["log"] = _binding(root / "broad.log", repo)
    baseline["broad"]["junit"] = _binding(root / "junit.xml", repo)
    baseline["broad"]["totals"] = gate._authoritative_broad_totals(
        root / "collection.log", root / "broad.log", root / "junit.xml"
    )
    baseline = _with_digest(
        {key: value for key, value in baseline.items() if key != "record_sha256"}
    )
    with pytest.raises(gate.GateError, match="broad|authority|failure"):
        gate.validate_baseline(baseline, repo_root=repo)


def test_standalone_baseline_validator_rejects_resealed_missing_evidence_domains() -> None:
    gate = _load_helper()
    rows = []
    for index in range(6):
        payload = {
            "schema": "workflow_broad_canonical_failure.v1",
            "nodeid": f"tests/test_{index}.py::test_{index}",
            "outcome": "failure",
            "exception_type": "AssertionError",
            "normalized_failure_signature": f"AssertionError | assert {index} == 9 | compared: {index} == 9",
        }
        rows.append(
            {
                "nodeid": payload["nodeid"],
                "canonical_payload": payload,
                "canonical_payload_sha256": hashlib.sha256(_canonical(payload)).hexdigest(),
                "isolated_exit": 1,
            }
        )
    incomplete = _with_digest(
        {
            "schema": "workflow_broad_known_failure_baseline.v1",
            "implementation_base_commit": "451765a2ebd374111d2cbeab0969cec4830717fb",
            "failure_rows": rows,
        }
    )
    with pytest.raises(gate.GateError, match="closed|keys|domain"):
        gate.validate_baseline(incomplete, repo_root=REPO_ROOT)


@pytest.mark.parametrize(
    ("schema", "validator"),
    [
        ("workflow_broad_outcome.v1", "validate_outcome"),
        ("workflow_broad_failure_remediation.v1", "validate_remediation"),
    ],
)
def test_outcome_and_remediation_validators_reject_resealed_missing_domains(schema: str, validator: str) -> None:
    gate = _load_helper()
    kwargs = {"repo_root": REPO_ROOT}
    if validator == "validate_remediation":
        kwargs["remediation_path"] = REPO_ROOT / "missing-remediation.json"
    incomplete = _with_digest({"schema": schema})
    with pytest.raises(gate.GateError, match="closed|keys|domain"):
        getattr(gate, validator)(incomplete, **kwargs)
    extra = _with_digest({"schema": schema, "extra": "forbidden"})
    with pytest.raises(gate.GateError, match="closed|keys|domain"):
        getattr(gate, validator)(extra, **kwargs)


@pytest.mark.parametrize(
    "tamper",
    [
        "empty_nodeid",
        "bad_removed_digest",
        "missing_commit",
        "wrong_tree",
        "blank_review_id",
        "wrong_review_prefix",
        "commit_without_trailers",
        "proof_path",
        "proof_digest",
        "proof_missing_blob",
    ],
)
def test_remediation_validator_rejects_resealed_identity_git_binding_and_review_trailer_tamper(
    repo: Path, tamper: str
) -> None:
    gate = _load_helper()
    remediation = json.loads(json.dumps(_valid_remediation(gate, repo)))
    if tamper == "empty_nodeid":
        remediation["removed_rows"][0]["nodeid"] = ""
    elif tamper == "bad_removed_digest":
        remediation["removed_rows"][0]["canonical_payload_sha256"] = "not-a-digest"
    elif tamper == "missing_commit":
        remediation["fixing_commit"] = "0" * 40
    elif tamper == "wrong_tree":
        remediation["fixing_tree"] = remediation["fixing_commit"]
    elif tamper == "blank_review_id":
        remediation["reviews"]["fixing"]["specification"] = "PASS "
    elif tamper == "wrong_review_prefix":
        remediation["reviews"]["fixing"]["quality"] = "PASS quality-review-456"
    elif tamper == "proof_path":
        remediation["focused_proofs"][0]["path"] = "../proof.log"
    elif tamper == "proof_digest":
        remediation["focused_proofs"][0]["sha256"] = "0" * 64
    elif tamper == "proof_missing_blob":
        remediation["focused_proofs"][0]["path"] = "missing-proof.log"
    else:
        remediation["fixing_commit"] = _git(repo, "rev-parse", "HEAD~2").stdout.decode().strip()
        remediation["fixing_tree"] = _git(repo, "rev-parse", "HEAD~2^{tree}").stdout.decode().strip()
    remediation = _with_digest(
        {key: value for key, value in remediation.items() if key != "record_sha256"}
    )
    remediation_path = repo / remediation["record_path"]
    remediation_path.write_bytes(_canonical(remediation))
    with pytest.raises(gate.GateError, match="node|digest|commit|tree|review|trailer|bytes|path|proof|blob|artifact"):
        gate.validate_remediation(
            remediation, repo_root=repo, remediation_path=remediation_path
        )


def test_remediation_focused_proof_is_read_from_fixing_commit_not_worktree(repo: Path) -> None:
    gate = _load_helper()
    remediation = _valid_remediation(gate, repo)
    (repo / remediation["focused_proofs"][0]["path"]).unlink()
    gate.validate_remediation(
        remediation,
        repo_root=repo,
        remediation_path=repo / remediation["record_path"],
    )


@pytest.mark.parametrize(
    ("command", "arguments"),
    [
        ("capture-subject", ["--output", "root/subject.json"]),
        (
            "verify-subject",
            [
                "--manifest",
                "root/subject.json",
                "--phase",
                "review",
                "--generated-evidence",
                "root/outcome.json",
                "--review-subject",
                "root/review-subject.json",
            ],
        ),
        (
            "capture-frozen-overlay",
            ["--output", "root/frozen-overlay.json", "--eligible-path", "tests/test_one.py"],
        ),
        ("validate-frozen-overlay", ["--overlay", "root/frozen-overlay.json"]),
        (
            "build-review-subject",
            [
                "--subject-manifest",
                "root/subject.json",
                "--generated-evidence",
                "root/outcome.json",
                "--review-patch-sha256",
                "a" * 64,
                "--review-tree",
                "b" * 40,
                "--output",
                "root/review-subject.json",
            ],
        ),
        (
            "write-command-status",
            ["--output", "root/status.json", "--phase", "broad", "--exit-code", "1", "--arg", "pytest"],
        ),
        (
            "build-baseline",
            [
                "--authority",
                "authority.json",
                "--correction",
                "correction.json",
                "--normalizer",
                "normalizer.py",
                "--subject-manifest",
                "root/subject.json",
                "--capture-root",
                "root",
                "--output",
                "baseline.json",
            ],
        ),
        ("validate-baseline", ["--baseline", "baseline.json"]),
        (
            "build-outcome",
            [
                "--baseline",
                "baseline.json",
                "--subject-manifest",
                "root/subject.json",
                "--capture-root",
                "root",
                "--output",
                "root/outcome.json",
            ],
        ),
        ("validate-outcome", ["--outcome", "root/outcome.json"]),
        (
            "compare",
            [
                "--baseline",
                "baseline.json",
                "--outcome",
                "root/outcome.json",
                "--remediation-dir",
                "remediations",
            ],
        ),
    ],
)
def test_plan_prescribed_helper_cli_literals_parse(
    command: str, arguments: list[str]
) -> None:
    gate = _load_helper()
    parsed = gate._cli().parse_args([command, *arguments])
    assert parsed.command == command


def test_cli_help_lists_only_evidence_operations_and_never_pytest_execution() -> None:
    completed = subprocess.run([sys.executable, str(HELPER), "--help"], check=True, text=True, capture_output=True)
    assert all(name in completed.stdout for name in ("capture-subject", "verify-subject", "capture-frozen-overlay", "validate-frozen-overlay", "build-review-subject", "write-command-status", "build-baseline", "build-outcome", "validate-baseline", "validate-outcome", "validate-remediation", "compare"))
    assert "run-pytest" not in completed.stdout
    compare_help = subprocess.run(
        [sys.executable, str(HELPER), "compare", "--help"], check=True, text=True, capture_output=True
    )
    assert "--remediation-dir" in compare_help.stdout


@pytest.mark.parametrize(
    ("summary", "expected"),
    [
        (
            "2 failed, 3 passed, 1 skipped in 0.10s\n",
            {
                "tests": 6,
                "failures": 2,
                "errors": 0,
                "skipped": 1,
                "passed": 3,
                "xfailed": 0,
                "xpassed": 0,
            },
        ),
        (
            "1 failed, 2 passed, 3 skipped, 4 xfailed, 5 xpassed in 0.10s\n",
            {
                "tests": 15,
                "failures": 1,
                "errors": 0,
                "skipped": 3,
                "passed": 2,
                "xfailed": 4,
                "xpassed": 5,
            },
        ),
    ],
)
def test_pytest_summary_totals_reconcile_explicit_zero_and_nonzero_xfail_xpass(
    tmp_path: Path, summary: str, expected: dict[str, int]
) -> None:
    gate = _load_helper()
    log = _write(tmp_path / "broad.log", summary)
    assert gate._pytest_summary_totals(log) == expected
    statuses = (
        ["failure"] * expected["failures"]
        + ["error"] * expected["errors"]
        + ["skipped"] * expected["skipped"]
        + ["xfailed"] * expected["xfailed"]
        + ["passed"] * (expected["passed"] + expected["xpassed"])
    )
    nodeids = [f"tests/test_totals.py::test_{index}" for index in range(len(statuses))]
    collection = _write(
        tmp_path / "collection.log",
        "\n".join([*nodeids, "", f"{len(nodeids)} tests collected in 0.01s", ""]),
    )
    suite = ET.Element(
        "testsuite",
        tests=str(len(statuses)),
        failures=str(expected["failures"]),
        errors=str(expected["errors"]),
        skipped=str(expected["skipped"] + expected["xfailed"]),
    )
    for index, status in enumerate(statuses):
        case = ET.SubElement(
            suite, "testcase", classname="tests.test_totals", name=f"test_{index}"
        )
        if status == "xfailed":
            ET.SubElement(case, "skipped", type="pytest.xfail", message="expected")
        elif status != "passed":
            ET.SubElement(case, status, message=status)
    junit = tmp_path / "junit.xml"
    ET.ElementTree(suite).write(junit, encoding="utf-8", xml_declaration=True)
    assert gate._authoritative_broad_totals(collection, log, junit) == expected

    mismatched = _write(tmp_path / "mismatched.log", summary.replace("failed", "passed", 1))
    with pytest.raises(gate.GateError, match="reconcile"):
        gate._authoritative_broad_totals(collection, mismatched, junit)


@pytest.mark.parametrize(
    ("summary", "normalized"),
    [
        (
            "6 failed, 5762 passed, 17 skipped, 33 warnings in 64.79s\n",
            "6 failed, 5762 passed, 17 skipped, 33 warnings in $TIME\n",
        ),
        (
            "6 failed, 5762 passed, 17 skipped, 33 warnings in 64.79s (0:01:04)\n",
            "6 failed, 5762 passed, 17 skipped, 33 warnings in $TIME\n",
        ),
        (
            "6 failed, 5762 passed, 17 skipped, 33 warnings in 64.79s (100:59:59)\r\n",
            "6 failed, 5762 passed, 17 skipped, 33 warnings in $TIME\r\n",
        ),
    ],
)
def test_pytest_elapsed_summary_accepts_seconds_and_optional_wall_clock_duration(
    tmp_path: Path, summary: str, normalized: str
) -> None:
    gate = _load_helper()
    log = _write(tmp_path / "broad.log", summary)

    assert gate._pytest_summary_totals(log) == {
        "tests": 5785,
        "failures": 6,
        "errors": 0,
        "skipped": 17,
        "passed": 5762,
        "xfailed": 0,
        "xpassed": 0,
    }
    assert gate.normalize_failure_text(summary, repo_root=tmp_path) == normalized


@pytest.mark.parametrize(
    "suffix",
    [
        " (0:1:04)",
        " (0:01:4)",
        " (0:60:00)",
        " (0:00:60)",
        " (0:99:99)",
        " (0:01:04) trailing",
        " (0:01:04) ",
        " ",
        " trailing",
    ],
)
def test_pytest_elapsed_summary_rejects_malformed_or_trailing_duration_text(
    tmp_path: Path, suffix: str
) -> None:
    gate = _load_helper()
    summary = f"6 failed, 5762 passed, 17 skipped in 64.79s{suffix}\n"
    log = _write(tmp_path / "broad.log", summary)

    with pytest.raises(gate.GateError, match="cannot derive pytest broad summary totals"):
        gate._pytest_summary_totals(log)
    assert gate.normalize_failure_text(summary, repo_root=tmp_path) == summary


@pytest.mark.parametrize("tamper", ["unknown", "missing", "duplicate_pass", "duplicate_skip"])
def test_complete_collection_junit_inventory_rejects_unknown_missing_and_duplicate_nodes(
    tmp_path: Path, tamper: str
) -> None:
    gate = _load_helper()
    nodeids = [
        "tests/test_inventory.py::test_pass",
        "tests/test_inventory.py::test_skip",
    ]
    collection = _write(
        tmp_path / "collection.log", "\n".join([*nodeids, "", "2 tests collected in 0.01s", ""])
    )
    suite = ET.Element("testsuite", tests="2", failures="0", errors="0", skipped="1")
    passing = ET.SubElement(
        suite, "testcase", classname="tests.test_inventory", name="test_pass"
    )
    skipped = ET.SubElement(
        suite, "testcase", classname="tests.test_inventory", name="test_skip"
    )
    ET.SubElement(skipped, "skipped", type="pytest.skip", message="reason")
    if tamper == "unknown":
        passing.set("name", "test_unknown")
    elif tamper == "missing":
        suite.remove(passing)
    elif tamper == "duplicate_pass":
        suite.append(ET.fromstring(ET.tostring(passing)))
    else:
        suite.append(ET.fromstring(ET.tostring(skipped)))
    junit = tmp_path / "junit.xml"
    ET.ElementTree(suite).write(junit, encoding="utf-8", xml_declaration=True)
    with pytest.raises(gate.GateError, match="inventory|unknown|missing|duplicate"):
        gate._reconcile_collection_junit_inventory(collection, junit)


def test_collection_junit_inventory_preserves_colons_inside_parameter_ids(tmp_path: Path) -> None:
    gate = _load_helper()
    nodeid = "tests/test_inventory.py::test_param[HelperEvidence::test_case]"
    collection = _write(
        tmp_path / "collection.log", f"{nodeid}\n\n1 test collected in 0.01s\n"
    )
    suite = ET.Element("testsuite", tests="1", failures="0", errors="0", skipped="0")
    ET.SubElement(
        suite,
        "testcase",
        classname="tests.test_inventory",
        name="test_param[HelperEvidence::test_case]",
    )
    junit = tmp_path / "junit.xml"
    ET.ElementTree(suite).write(junit, encoding="utf-8", xml_declaration=True)
    assert gate._reconcile_collection_junit_inventory(collection, junit) == {
        nodeid: "passed"
    }
