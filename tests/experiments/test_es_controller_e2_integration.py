"""Provider-free public-entry integration for the ES Task-5 controller."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Mapping, cast

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))

from orchestrator.state import StateManager
from orchestrator.providers.registry import ProviderRegistry
from orchestrator.workflow.assets import WorkflowAssetResolver
from orchestrator.workflow.executable_ir import TrialStepConfig
from orchestrator.workflow.prompting import PromptComposer
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes, canonical_sha256
from orchestrator.workflow.run_ref.ledger import settled_result_binding_from_record
from orchestrator.workflow.run_ref.ledger import RunRefVisitKey
from orchestrator.workflow.trial.config import build_trial_runtime_request
from orchestrator.workflow.trial.contracts import (
    TrialCellKey,
    build_sealed_opaque_label_map,
)
from orchestrator.workflow.trial.sdk import TrialRunOptions, run_trial_entry
from orchestrator.workflow.trial import sdk as trial_sdk
from orchestrator.workflow.trial import evaluation as trial_evaluation
from orchestrator.workflow import executor as workflow_executor
from orchestrator.workflow.trial import checks as trial_checks
from orchestrator.workflow.trial.ledger import load_trial_event_ledger
from scripts.experiments.es import (
    attempts,
    controller,
    decision_lock,
    f1_evaluator,
    metering,
    reviews,
    synthesis,
)
from tests.experiments import test_es_attempts as attempt_fixtures


FAKE_CODEX = (
    REPOSITORY_ROOT / "tests/experiments/fixtures/es_task5/fake_codex.py"
)
LOCKED_CODEX_LAUNCHER_SHA256 = (
    "sha256:134063e133f0b4244fa3b251acf973d4f"
    "e4b4aeeacbdc135211bf480f59f1477"
)
ARMS = ("DIRECT", "DESIGN_QA", "PRODUCT_QA", "RICH")
TASK_TEXT = "provider-free integration task\n"
CHECK_TEXT = "provider-free integration checks\n"
FIXED_SALT = (b"es-task5-fixed-opaque-label-salt" * 2)[:32]


def test_task5_fake_codex_fixture_is_executable() -> None:
    assert FAKE_CODEX.is_file()
    assert FAKE_CODEX.stat().st_mode & 0o111


def test_task5_fake_codex_resolves_slot_from_prompt_allowlist_without_journal_fallback(
    tmp_path: Path,
) -> None:
    prompt = b"manifest-selected fixture treatment"
    output_path = (tmp_path / "result_bundle.json").resolve()
    capture_path = (tmp_path / "captured-prompts").resolve()
    manifest_path = (tmp_path / "provider-boundary.json").resolve()
    manifest_path.write_bytes(
        canonical_json_bytes(
            {
                "calls": [
                    {
                        "call_slot_id": "DIRECT.I",
                        "prompt_sha256s": [_sha(prompt)],
                        "cwd_selector": {
                            "kind": "exact",
                            "path": tmp_path.resolve().as_posix(),
                        },
                        "output_bundle_path": output_path.as_posix(),
                        "provider_attempt_site_key": "fixture-site",
                    }
                ],
                "journal_path": (tmp_path / "must-not-be-read.jsonl").as_posix(),
            }
        )
    )
    completed = subprocess.run(
        [
            FAKE_CODEX.as_posix(),
            "exec",
            "--json",
            "--dangerously-bypass-approvals-and-sandbox",
            "--skip-git-repo-check",
            "--model",
            "gpt-5.5",
            "--config",
            "model_reasoning_effort=high",
            "--",
            "-",
        ],
        cwd=tmp_path,
        env={
            **dict(os.environ),
            "ES_TASK5_FAKE_CAPTURE_DIR": capture_path.as_posix(),
            "ORC_ES_PROVIDER_BOUNDARY_MANIFEST_PATH": manifest_path.as_posix(),
            "ORCHESTRATOR_OUTPUT_BUNDLE_PATH": output_path.as_posix(),
            "ORCHESTRATOR_PROVIDER_ATTEMPT_SITE_KEY": "fixture-site",
        },
        input=prompt,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    [capture] = capture_path.glob("*.json")
    assert json.loads(capture.read_bytes())["slot"] == "DIRECT.I"


def test_resolved_fake_launcher_honors_explicit_control_and_fails_closed(
    tmp_path: Path,
) -> None:
    control_path = (tmp_path / "control.json").resolve()
    capture_path = (tmp_path / "captured-prompts").resolve()
    output_path = (tmp_path / "review_design_result_bundle.json").resolve()
    control_path.write_text('{"review_decision":"REVISE"}\n', encoding="utf-8")
    environment = {
        **dict(os.environ),
        "ES_TASK5_FAKE_CONTROL_PATH": control_path.as_posix(),
        "ES_TASK5_FAKE_CAPTURE_DIR": capture_path.as_posix(),
        "ORCHESTRATOR_OUTPUT_BUNDLE_PATH": output_path.as_posix(),
    }
    argv = [
        FAKE_CODEX.as_posix(),
        "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
        "--model",
        "gpt-5.5",
        "--config",
        "reasoning_effort=high",
    ]

    completed = subprocess.run(
        argv,
        cwd=tmp_path,
        env=environment,
        input=b"fixture review",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert completed.returncode == 0
    assert json.loads(output_path.read_text(encoding="utf-8")) == {
        "decision": "REVISE"
    }
    assert len(tuple(capture_path.glob("*.json"))) == 1

    output_path.unlink()
    control_path.write_text(
        '{"fail_provider_attempt_site_key":"site-key"}\n',
        encoding="utf-8",
    )
    site_failed = subprocess.run(
        argv,
        cwd=tmp_path,
        env={
            **environment,
            "ORCHESTRATOR_PROVIDER_ATTEMPT_SITE_KEY": "site-key",
        },
        input=b"fixture treatment",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert site_failed.returncode == 9
    assert not output_path.exists()

    control_path.unlink()
    missing = subprocess.run(
        argv,
        cwd=tmp_path,
        env=environment,
        input=b"fixture review",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert missing.returncode == 88

    control_path.write_text("not-json\n", encoding="utf-8")
    malformed = subprocess.run(
        argv,
        cwd=tmp_path,
        env=environment,
        input=b"fixture review",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert malformed.returncode == 88


def _stage_public_trial(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    workspace = (tmp_path / "workspace").resolve()
    source = REPOSITORY_ROOT / "workflows"
    shutil.copytree(
        source / "experiments/qa_placement_effectiveness",
        workspace / "workflows/experiments/qa_placement_effectiveness",
    )
    (workspace / "workflows/library/control").mkdir(parents=True)
    shutil.copy2(
        source / "library/control/direct_task.orc",
        workspace / "workflows/library/control/direct_task.orc",
    )
    state_dir = (tmp_path / "runs").resolve()
    state_dir.mkdir()
    run_ref_root = (tmp_path / "children").resolve()
    run_ref_root.mkdir()
    capture = (tmp_path / "captured-prompts").resolve()
    capture.mkdir()
    return workspace, state_dir, run_ref_root, capture


def _install_fake_codex(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_bin = (tmp_path / "bin").resolve()
    fake_bin.mkdir(exist_ok=True)
    launcher = fake_bin / "codex"
    locked_launcher_value = shutil.which("codex")
    assert locked_launcher_value is not None
    locked_launcher = Path(locked_launcher_value).resolve(strict=True)
    assert _sha(locked_launcher.read_bytes()) == LOCKED_CODEX_LAUNCHER_SHA256
    if not launcher.exists():
        launcher.symlink_to(locked_launcher)
    interpreter = fake_bin / "node"
    if not interpreter.exists():
        interpreter.symlink_to(FAKE_CODEX)
    control_path = (tmp_path / "fake-control.json").resolve()
    control_path.write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("ES_TASK5_FAKE_CONTROL_PATH", control_path.as_posix())
    monkeypatch.setenv(
        "ES_TASK5_FAKE_CAPTURE_DIR",
        (tmp_path / "captured-prompts").resolve().as_posix(),
    )


def test_provider_free_launcher_preserves_locked_codex_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_codex(tmp_path, monkeypatch)
    monkeypatch.setenv("PATH", (tmp_path / "bin").as_posix() + ":/usr/bin")

    chain = metering.resolve_executable_chain("codex")

    assert chain["launcher_sha256"] == LOCKED_CODEX_LAUNCHER_SHA256
    assert chain["version"] == "codex-cli 0.145.0"


def _set_fake_control(tmp_path: Path, value: dict[str, Any]) -> None:
    (tmp_path / "fake-control.json").write_bytes(
        canonical_json_bytes(value) + b"\n"
    )


def _trial_options(workspace: Path) -> TrialRunOptions:
    return TrialRunOptions(
        source_roots=(
            workspace / "workflows/experiments",
            workspace / "workflows/library",
        ),
        provider_externs_file=(
            workspace
            / "workflows/experiments/qa_placement_effectiveness/providers.json"
        ),
        prompt_externs_file=(
            workspace
            / "workflows/experiments/qa_placement_effectiveness/prompts.json"
        ),
        max_retries=0,
        retry_delay_ms=0,
    )


def _run_checked_in_trial(
    *,
    workspace: Path,
    state_dir: Path,
    run_ref_root: Path,
):
    return run_trial_entry(
        workflow_file=(
            workspace
            / "workflows/experiments/qa_placement_effectiveness/qa_placement_trial.orc"
        ),
        entry_workflow="compare",
        inputs={
            "task": TASK_TEXT,
            "check_contract": CHECK_TEXT,
            "model": "gpt-5.5",
            "effort": "high",
        },
        workspace=workspace,
        state_dir=state_dir,
        run_ref_root=run_ref_root,
        options=_trial_options(workspace),
    )


def _install_deterministic_check_seam(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actual = trial_checks.run_trial_checks

    def deterministic_checks(
        checks: object,
        *,
        cwd: Path,
        evidence_frozen_digest: str,
        max_output_bytes: int,
        **_ignored: object,
    ):
        return actual(
            checks,  # type: ignore[arg-type]
            cwd=cwd,
            evidence_frozen_digest=evidence_frozen_digest,
            max_output_bytes=max_output_bytes,
            runner=lambda argv, **_kwargs: subprocess.CompletedProcess(
                argv,
                0,
                stdout=b"provider-free checks passed\n",
                stderr=b"",
            ),
            monotonic_ns=lambda: 1_000_000_000,
        )

    monkeypatch.setattr(trial_checks, "run_trial_checks", deterministic_checks)


def _capture_records(capture: Path) -> tuple[dict[str, Any], ...]:
    return tuple(
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(capture.glob("*.json"))
    )


def _reset_public_trial_attempt(
    workspace: Path,
    state_dir: Path,
    run_ref_root: Path,
    capture: Path,
) -> None:
    for root in (state_dir, run_ref_root):
        shutil.rmtree(root)
        root.mkdir()
    for root in (workspace / ".orchestrate", workspace / "artifacts"):
        if root.exists():
            shutil.rmtree(root)
    for path in capture.glob("*.json"):
        path.unlink()


def test_checked_in_task4_trial_runs_through_public_entry_with_local_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, state_dir, run_ref_root, capture = _stage_public_trial(tmp_path)
    _install_fake_codex(tmp_path, monkeypatch)
    fake_bin = (tmp_path / "bin").resolve()
    monkeypatch.setenv("PATH", fake_bin.as_posix() + ":" + str(Path("/usr/bin")))
    monkeypatch.setenv("ES_TASK5_FAKE_CAPTURE_DIR", capture.as_posix())
    monkeypatch.setattr(
        StateManager,
        "_generate_run_id",
        lambda _self: "es-task5-public-entry-fixture",
    )
    monkeypatch.setattr(
        workflow_executor.os,
        "urandom",
        lambda count: (b"es-task5-fixed-opaque-label-salt" * 2)[:count],
    )

    result = _run_checked_in_trial(
        workspace=workspace,
        state_dir=state_dir,
        run_ref_root=run_ref_root,
    )

    records = _capture_records(capture)
    assert result.terminal_status == "completed"
    assert len(records) == 14
    assert sum("trial.evaluation_packet.v1" in row["prompt"] for row in records) == 4


def test_public_prompt_authority_is_invariant_across_fresh_parent_run_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, state_dir, run_ref_root, capture = _stage_public_trial(tmp_path)
    _install_fake_codex(tmp_path, monkeypatch)
    monkeypatch.setenv(
        "PATH",
        (tmp_path / "bin").resolve().as_posix() + ":/usr/bin",
    )
    monkeypatch.setattr(
        workflow_executor.os,
        "urandom",
        lambda count: (b"es-task5-fixed-opaque-label-salt" * 2)[:count],
    )
    _install_deterministic_check_seam(monkeypatch)
    observed: list[tuple[str, ...]] = []
    observed_sites: list[tuple[str, ...]] = []
    observed_product_review_sites: list[dict[str, str]] = []

    for run_id in ("es-task5-authority-first", "es-task5-authority-second"):
        monkeypatch.setattr(
            StateManager,
            "_generate_run_id",
            lambda _self, value=run_id: value,
        )
        result = _run_checked_in_trial(
            workspace=workspace,
            state_dir=state_dir,
            run_ref_root=run_ref_root,
        )
        records = _capture_records(capture)
        assert result.terminal_status == "completed"
        assert len(records) == 14
        observed.append(
            tuple(
                sorted(
                    "sha256:"
                    + hashlib.sha256(
                        str(row["prompt"]).encode("utf-8", "strict")
                    ).hexdigest()
                    for row in records
                )
            )
        )
        treatment_sites = tuple(
            sorted(
                row["provider_attempt_site_key"]
                for row in records
                if _packet_from_prompt(row["prompt"]) is None
            )
        )
        assert len(treatment_sites) == 10
        assert all(
            isinstance(value, str) and value.startswith("sha256:")
            for value in treatment_sites
        )
        assert all(
            row["provider_attempt_site_key"] is None
            for row in records
            if _packet_from_prompt(row["prompt"]) is not None
        )
        observed_sites.append(treatment_sites)
        arm_by_workspace = _prepared_workspace_by_arm(state_dir)
        product_review_sites = {
            arm_by_workspace[row["cwd"]]: row["provider_attempt_site_key"]
            for row in records
            if isinstance(row["output_bundle_path"], str)
            and "review_product" in row["output_bundle_path"]
        }
        assert set(product_review_sites) == {"PRODUCT_QA", "RICH"}
        assert len(set(product_review_sites.values())) == 2
        observed_product_review_sites.append(product_review_sites)
        _reset_public_trial_attempt(
            workspace,
            state_dir,
            run_ref_root,
            capture,
        )

    assert observed[0] == observed[1]
    assert observed_sites[0] == observed_sites[1]
    assert observed_product_review_sites[0] == observed_product_review_sites[1]


def test_fresh_random_label_salts_drift_only_scorer_prompt_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, state_dir, run_ref_root, capture = _stage_public_trial(tmp_path)
    _install_fake_codex(tmp_path, monkeypatch)
    monkeypatch.setenv(
        "PATH",
        (tmp_path / "bin").resolve().as_posix() + ":/usr/bin",
    )
    monkeypatch.setattr(
        StateManager,
        "_generate_run_id",
        lambda _self: "es-task5-salt-isolation",
    )
    _install_deterministic_check_seam(monkeypatch)
    treatment: list[tuple[str, ...]] = []
    scorer: list[tuple[str, ...]] = []

    for salt in (b"a" * 32, b"b" * 32):
        monkeypatch.setattr(
            workflow_executor.os,
            "urandom",
            lambda count, value=salt: value[:count],
        )
        result = _run_checked_in_trial(
            workspace=workspace,
            state_dir=state_dir,
            run_ref_root=run_ref_root,
        )
        records = _capture_records(capture)
        assert result.terminal_status == "completed"
        assert len(records) == 14
        partitioned = {
            is_scorer: tuple(
                sorted(
                    "sha256:"
                    + hashlib.sha256(
                        row["prompt"].encode("utf-8", "strict")
                    ).hexdigest()
                    for row in records
                    if ("trial.evaluation_packet.v1" in row["prompt"])
                    is is_scorer
                )
            )
            for is_scorer in (False, True)
        }
        treatment.append(partitioned[False])
        scorer.append(partitioned[True])
        _reset_public_trial_attempt(
            workspace,
            state_dir,
            run_ref_root,
            capture,
        )

    assert treatment[0] == treatment[1]
    assert scorer[0] != scorer[1]


def _sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _write_bound(
    workspace: Path,
    relative_path: str,
    raw: bytes,
) -> controller.BoundFile:
    path = workspace / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return controller.BoundFile(relative_path, _sha(raw))


def _existing_bound(
    workspace: Path,
    relative_path: str,
) -> controller.BoundFile:
    return controller.BoundFile(
        relative_path,
        _sha((workspace / relative_path).read_bytes()),
    )


def _frozen_trial_authority(
    workspace: Path,
    *,
    parent_run_id: str,
):
    module = workspace / "workflows/experiments/qa_placement_effectiveness"
    built = trial_sdk._compile_trial_entry(  # pyright: ignore[reportPrivateUsage]
        workflow_file=module / "qa_placement_trial.orc",
        entry_workflow="compare",
        workspace=workspace,
        options=_trial_options(workspace),
    )
    bundle = built.validated_bundle
    [trial_node] = [
        node
        for node in bundle.ir.nodes.values()
        if isinstance(node.execution_config, TrialStepConfig)
    ]
    step_config = trial_node.execution_config
    assert isinstance(step_config, TrialStepConfig)
    shared_inputs = {
        "task": TASK_TEXT,
        "check_contract": CHECK_TEXT,
        "model": "gpt-5.5",
        "effort": "high",
    }
    request = build_trial_runtime_request(
        step_config=step_config,
        visit=RunRefVisitKey(
            parent_run_id=parent_run_id,
            execution_frame_id="root",
            call_frame_id=None,
            step_id=trial_node.step_id,
            visit_count=1,
        ),
        resolved_inputs_by_arm={
            arm.arm_id: shared_inputs for arm in step_config.trial.arms
        },
    )
    sealed = build_sealed_opaque_label_map(
        cast(tuple[TrialCellKey, ...], request.cell_domain),
        salt=FIXED_SALT,
    )
    scorer, _prompt, _rubric = trial_evaluation._resolve_scorer(  # pyright: ignore[reportPrivateUsage]
        scorer_config=trial_evaluation.build_trial_scorer_config(request),
        provider_registry=ProviderRegistry(),
        prompt_composer=PromptComposer(
            workspace=workspace,
            asset_resolver=WorkflowAssetResolver(
                module / "qa_placement_trial.orc"
            ),
        ),
    )
    scorer_authority = {
        "evaluation_digest": request.evaluation_digest,
        "scorer_identity_digest": scorer["scorer_identity_digest"],
    }
    return (
        attempts.freeze_trial_artifact_authority(request, sealed),
        sealed,
        scorer_authority,
    )


def test_frozen_authority_reuses_public_sdk_compile_identity_for_e2(
    tmp_path: Path,
) -> None:
    workspace, _state_dir, _run_ref_root, _capture = _stage_public_trial(
        tmp_path
    )
    frozen, _sealed, _scorer = _frozen_trial_authority(
        workspace,
        parent_run_id="preallocated-frozen-parent",
    )
    runtime_build = trial_sdk._compile_trial_entry(  # pyright: ignore[reportPrivateUsage]
        workflow_file=(
            workspace
            / "workflows/experiments/qa_placement_effectiveness/qa_placement_trial.orc"
        ),
        entry_workflow="compare",
        workspace=workspace,
        options=_trial_options(workspace),
    )
    trial = attempt_fixtures._trial_fixture(
        tmp_path / "provider-free-ledger",
        built=runtime_build,
        common_inputs={
            "task": TASK_TEXT,
            "check_contract": CHECK_TEXT,
            "model": "gpt-5.5",
            "effort": "high",
        },
    )

    runtime_template = trial["request"].record
    runtime_visit = runtime_template.pop("visit")
    runtime_visit.pop("parent_run_id")
    assert frozen.record["request_template"] == runtime_template
    assert frozen.record["visit_template"] == runtime_visit

    attempt = attempt_fixtures._build_from_artifacts(
        trial,
        frozen_trial_artifact_authority=frozen.canonical_bytes,
    )
    assert attempt["status"] == "VALID"
    assert attempt["invalidity_code"] is None
    assert attempt["e2_authority"]["ledger_valid"] is True
    assert attempt["e2_authority"]["coherent_allocation"] is True


def test_frozen_scorer_authority_is_structural_and_rubric_tamper_evident(
    tmp_path: Path,
) -> None:
    workspace, _state_dir, _run_ref_root, _capture = _stage_public_trial(
        tmp_path
    )
    frozen, _sealed, scorer = _frozen_trial_authority(
        workspace,
        parent_run_id="preallocated-scorer-parent",
    )

    assert scorer["evaluation_digest"] == frozen.record["request_template"][
        "evaluation_digest"
    ]
    assert scorer["scorer_identity_digest"].startswith("sha256:")

    rubric = (
        workspace
        / "workflows/experiments/qa_placement_effectiveness/prompts/trial_rubric.md"
    )
    rubric.write_text(
        rubric.read_text(encoding="utf-8") + "\nprovider-free drift probe\n",
        encoding="utf-8",
    )
    drifted_frozen, _drifted_sealed, drifted_scorer = _frozen_trial_authority(
        workspace,
        parent_run_id="preallocated-scorer-parent",
    )

    assert drifted_frozen.record["request_template"]["evaluation_digest"] == (
        scorer["evaluation_digest"]
    )
    assert drifted_scorer["evaluation_digest"] == scorer["evaluation_digest"]
    assert drifted_scorer["scorer_identity_digest"] != scorer[
        "scorer_identity_digest"
    ]


def _packet_from_prompt(prompt: str) -> dict[str, Any] | None:
    for line in reversed(prompt.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and value.get("schema") == "trial.evaluation_packet.v1":
            return value
    return None


def _prepared_workspace_by_arm(
    state_dir: Path,
    *,
    run_id: str | None = None,
) -> dict[str, str]:
    ledger_root = state_dir if run_id is None else state_dir / run_id
    [ledger_path] = ledger_root.glob("*/**/trial-events.jsonl")
    ledger = load_trial_event_ledger(ledger_path)
    result: dict[str, str] = {}
    for row in ledger.rows:
        if row.kind != "cell_prepared":
            continue
        payload = row.payload
        cell_record = payload["cell"]
        cell = TrialCellKey(
            arm_id=cell_record["arm_id"],
            rep=cell_record["rep"],
        )
        settled = settled_result_binding_from_record(payload["settled_result"])
        result[cell.arm_id] = settled.workspace_path.as_posix()
    assert set(result) == set(ARMS)
    assert len(set(result.values())) == len(ARMS)
    return {workspace: arm for arm, workspace in result.items()}


def _cell_evidence_by_arm(
    state_dir: Path,
    *,
    run_id: str,
) -> dict[str, dict[str, Any]]:
    [ledger_path] = (state_dir / run_id).glob("*/**/trial-events.jsonl")
    ledger = load_trial_event_ledger(ledger_path)
    [frozen] = [row for row in ledger.rows if row.kind == "evidence_frozen"]
    rows = frozen.payload["cell_evidence"]
    assert isinstance(rows, list)
    result = {
        row["cell"]["arm_id"]: row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("cell"), dict)
    }
    assert set(result) == set(ARMS)
    return result


def _captured_call_slot(
    row: dict[str, Any],
    *,
    arm_by_label: dict[str, str],
    arm_by_workspace: dict[str, str],
) -> str:
    packet = _packet_from_prompt(row["prompt"])
    if packet is not None:
        return "EVAL.SCORER_" + arm_by_label[packet["evaluation_id"]]
    output_path = row["output_bundle_path"]
    assert isinstance(output_path, str)
    arm = arm_by_workspace[row["cwd"]]
    role = next(
        role_id
        for role_id, marker in (
            ("DREV", "revise_design"),
            ("DR", "review_design"),
            ("D", "produce_design"),
            ("PR", "review_product"),
            ("FIX", "fix_product"),
            ("I", "__result__result_bundle.json"),
        )
        if marker in output_path
    )
    return f"{arm}.{role}"


def _controller_package(
    *,
    tmp_path: Path,
    workspace: Path,
    state_dir: Path,
    run_ref_root: Path,
    evidence_root: Path,
    capture_records: tuple[dict[str, Any], ...],
    arm_by_workspace: dict[str, str],
    parent_run_id: str,
    attempt_history: tuple[controller.ControllerResult, ...] = (),
    prompt_variants_by_slot: Mapping[str, tuple[str, ...]] | None = None,
) -> tuple[Path, str]:
    frozen_authority, sealed, scorer_authority = _frozen_trial_authority(
        workspace,
        parent_run_id=parent_run_id,
    )
    arm_by_label = {
        binding.opaque_label: binding.cell.arm_id for binding in sealed.bindings
    }
    assert set(arm_by_workspace.values()) == set(ARMS)
    captures_by_slot = {
        _captured_call_slot(
            row,
            arm_by_label=arm_by_label,
            arm_by_workspace=arm_by_workspace,
        ): row
        for row in capture_records
    }
    prompts_by_slot = {
        slot: row["prompt"] for slot, row in captures_by_slot.items()
    }
    prompt_variants = (
        {} if prompt_variants_by_slot is None else prompt_variants_by_slot
    )
    assert set(prompt_variants).issubset(prompts_by_slot)
    selected_slots = {
        "DIRECT.I",
        "DESIGN_QA.D",
        "DESIGN_QA.DR",
        "DESIGN_QA.DREV",
        "DESIGN_QA.I",
        "PRODUCT_QA.I",
        "PRODUCT_QA.PR",
        "PRODUCT_QA.FIX",
        "RICH.D",
        "RICH.DR",
        "RICH.DREV",
        "RICH.I",
        "RICH.PR",
        "RICH.FIX",
        "EVAL.SCORER_DIRECT",
        "EVAL.SCORER_DESIGN_QA",
        "EVAL.SCORER_PRODUCT_QA",
        "EVAL.SCORER_RICH",
    }
    assert set(prompts_by_slot) == selected_slots

    fake_launcher = (tmp_path / "bin/codex").absolute()
    executable_chain = metering.resolve_executable_chain(
        fake_launcher.as_posix()
    )
    normalized_argv = [
        executable_chain["launcher_path"],
        "exec",
        "--json",
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
        "--model",
        "gpt-5.5",
        "--config",
        "model_reasoning_effort=high",
        "--",
        "-",
    ]
    all_slots = decision_lock._receipt_call_slots(  # pyright: ignore[reportPrivateUsage]
        decision_lock.derive_terminal_routes(),
        decision_lock.derive_evaluation_routes(),
    )
    prompt_manifest_record = {
        "schema_version": "es.prompt_manifest.v2",
        "calls": [
            {
                "call_slot_id": slot,
                "role_id": slot,
                "prompt_sha256s": sorted(
                    {
                        _sha(
                            prompts_by_slot.get(
                                slot,
                                "unselected provider-free fixture slot " + slot,
                            ).encode("utf-8", "strict")
                        ),
                        *(
                            _sha(value.encode("utf-8", "strict"))
                            for value in prompt_variants.get(slot, ())
                        ),
                    }
                ),
                "contract_sha256": _sha(
                    ("provider-free contract " + slot).encode("utf-8", "strict")
                ),
                "output_bundle_path": (
                    captures_by_slot[slot]["output_bundle_path"]
                    if slot in captures_by_slot
                    else None
                ),
                "provider_attempt_site_key": (
                    captures_by_slot[slot]["provider_attempt_site_key"]
                    if slot in captures_by_slot
                    else None
                ),
                "normalized_argv": normalized_argv,
            }
            for slot in all_slots
        ],
    }
    environment_record = {
        "schema_version": "es.environment_lock.v1",
        "provider_family": "codex-cli",
        "version": "codex-cli 0.145.0",
        "model": "gpt-5.5",
        "reasoning_effort": "high",
        "prompt_transport": "STDIN",
        "executable_chain": executable_chain,
        "evaluation_authority": {
            "schema_version": "es.evaluation_authority.v1",
            "hard_evaluator_identity_digest": _sha(b"hard-evaluator"),
            "hard_task_identity_digest": _sha(b"hard-task"),
            "hard_fixture_identity_digest": _sha(b"hard-fixture"),
            "scorer_evaluation_digest": scorer_authority[
                "evaluation_digest"
            ],
            "scorer_identity_digest": scorer_authority[
                "scorer_identity_digest"
            ],
        },
    }

    package_root = "experiments/task5-public-entry"
    workflow = _existing_bound(
        workspace,
        "workflows/experiments/qa_placement_effectiveness/qa_placement_trial.orc",
    )
    provider_externs = _existing_bound(
        workspace,
        "workflows/experiments/qa_placement_effectiveness/providers.json",
    )
    prompt_externs = _existing_bound(
        workspace,
        "workflows/experiments/qa_placement_effectiveness/prompts.json",
    )
    task = _write_bound(workspace, f"{package_root}/task.md", TASK_TEXT.encode())
    check_contract = _write_bound(
        workspace,
        f"{package_root}/checks.md",
        CHECK_TEXT.encode(),
    )
    source_projection = _write_bound(
        workspace,
        f"{package_root}/projection.json",
        (REPOSITORY_ROOT / "experiments/orc_effectiveness/f1_es/projection-manifest.json").read_bytes(),
    )
    task_profile = _write_bound(
        workspace,
        f"{package_root}/profile.json",
        (REPOSITORY_ROOT / "experiments/orc_effectiveness/f1_es/task-profile.json").read_bytes(),
    )
    task_seed = _write_bound(
        workspace,
        f"{package_root}/seed.json",
        (REPOSITORY_ROOT / "experiments/orc_effectiveness/f1_es/task-seed-manifest.json").read_bytes(),
    )
    evaluator = _write_bound(
        workspace,
        f"{package_root}/evaluator.json",
        (REPOSITORY_ROOT / "experiments/orc_effectiveness/f1_es/evaluator/fixture-manifest.json").read_bytes(),
    )
    environment = _write_bound(
        workspace,
        f"{package_root}/environment.json",
        canonical_json_bytes(environment_record),
    )
    prompt_manifest = _write_bound(
        workspace,
        f"{package_root}/prompt-manifest.json",
        canonical_json_bytes(prompt_manifest_record),
    )
    report_schema = _write_bound(
        workspace,
        f"{package_root}/report.schema.json",
        (REPOSITORY_ROOT / "experiments/orc_effectiveness/f1_es/report.schema.json").read_bytes(),
    )
    randomization_record = decision_lock.generate_randomization_manifest(
        _sha(b"provider-free-controller-randomization")
    )
    randomization = _write_bound(
        workspace,
        f"{package_root}/randomization.json",
        decision_lock.canonical_json_bytes(randomization_record),
    )
    bindings = {
        "arm_workflow_sha256": workflow.sha256,
        "environment_lock_sha256": environment.sha256,
        "evaluator_fixture_manifest_sha256": evaluator.sha256,
        "prompt_manifest_sha256": prompt_manifest.sha256,
        "randomization_manifest_sha256": decision_lock.decision_lock_digest(
            randomization_record
        ),
        "report_schema_sha256": report_schema.sha256,
        "source_projection_manifest_sha256": source_projection.sha256,
        "task_profile_sha256": task_profile.sha256,
        "task_seed_manifest_sha256": task_seed.sha256,
    }
    lock_record = decision_lock.build_decision_lock(
        bindings=bindings,
        randomization_manifest=randomization_record,
    )
    lock = _write_bound(
        workspace,
        f"{package_root}/decision-lock.json",
        decision_lock.canonical_json_bytes(lock_record),
    )
    call_authority = _write_bound(
        workspace,
        f"{package_root}/call-authority.json",
        canonical_json_bytes(
            {
                "schema_version": "es.frozen_call_authority.v1",
                "prompt_manifest": prompt_manifest_record,
                "environment_lock": environment_record,
            }
        ),
    )
    trial_artifact_authority = _write_bound(
        workspace,
        f"{package_root}/trial-artifact-authority.json",
        frozen_authority.canonical_bytes,
    )
    attempt_records = tuple(
        json.loads(result.attempt_record) for result in attempt_history
    )
    attempt_indexes = tuple(
        controller.AttemptIndexBinding(
            result.attempt_id,
            f"attempts/{result.attempt_id}/index.json",
            _sha(
                (
                    evidence_root
                    / f"attempts/{result.attempt_id}/index.json"
                ).read_bytes()
            ),
        )
        for result in attempt_history
    )
    package = controller.ControllerPackage(
        paths=controller.ControllerPaths(
            workspace=workspace,
            state_dir=state_dir,
            run_ref_root=run_ref_root,
            evidence_root=evidence_root,
        ),
        workflow=workflow,
        provider_externs=provider_externs,
        prompt_externs=prompt_externs,
        task=task,
        check_contract=check_contract,
        source_projection=source_projection,
        task_profile=task_profile,
        task_seed=task_seed,
        evaluator_fixture=evaluator,
        environment_lock=environment,
        prompt_manifest=prompt_manifest,
        report_schema=report_schema,
        randomization_manifest=randomization,
        decision_lock=lock,
        call_authority=call_authority,
        trial_artifact_authority=trial_artifact_authority,
        expected_bindings=tuple(sorted(bindings.items())),
        model="gpt-5.5",
        effort="high",
        consumed_attempt_ids=tuple(
            result.attempt_id for result in attempt_history
        ),
        consumed_attempt_call_counts=tuple(
            record["accounting"]["call_count"] for record in attempt_records
        ),
        invalid_attempt_count=sum(
            record["status"] == "INVALID" for record in attempt_records
        ),
        attempt_indexes=attempt_indexes,
    )
    raw_manifest = canonical_json_bytes(package.manifest_record) + b"\n"
    manifest_path = tmp_path / f"controller-package-{len(attempt_history)}.json"
    manifest_path.write_bytes(raw_manifest)
    return manifest_path, _sha(raw_manifest)


def _review_payload(
    request: controller.ReviewCallRequest,
    *,
    disagreement: bool,
) -> dict[str, Any]:
    labels = list(request.presentation_order)
    pairwise = []
    for index, (left, right) in enumerate(reviews.canonical_pair_order(labels)):
        outcome = (
            "B"
            if disagreement
            and request.call_slot_id.endswith("MAINTAINABILITY")
            and index == 0
            else "A"
        )
        pairwise.append(
            {
                "candidate_a_label": left,
                "candidate_b_label": right,
                "outcome": outcome,
                "rationale": "deterministic provider-free review",
                "citations": [
                    {"opaque_label": left, "citable_item_id": "task_spec"},
                    {"opaque_label": right, "citable_item_id": "task_spec"},
                ],
            }
        )
    if request.review_kind != reviews.INITIAL:
        schema = (
            "es-f1-adjudicator-review.v1"
            if request.review_kind == reviews.ADJUDICATOR
            else "es-f1-integrated-review.v1"
        )
        return {"schema_version": schema, "pairwise_results": pairwise}
    assert request.perspective_id is not None
    schema = (
        "es-f1-initial-scientific-application-semantics-review.v1"
        if request.perspective_id == reviews.SCIENTIFIC_APPLICATION_SEMANTICS
        else "es-f1-initial-api-persistence-migration-maintainability-review.v1"
    )
    return {
        "schema_version": schema,
        "candidates": [
            {
                "opaque_label": label,
                "dimensions": [
                    {
                        "dimension": dimension,
                        "assessment": "PASS",
                        "rationale": "deterministic provider-free review",
                        "citations": [
                            {
                                "opaque_label": label,
                                "citable_item_id": "task_spec",
                            }
                        ],
                    }
                    for dimension in reviews.PERSPECTIVE_DIMENSIONS[
                        request.perspective_id
                    ]
                ],
            }
            for label in labels
        ],
        "pairwise_results": pairwise,
    }


def _hard_replay_inputs(
    request: controller.HardEvidenceRequest,
    *,
    evaluation_authority: dict[str, Any],
) -> bytes:
    observations = [
        {
            "clause_id": clause_id,
            "satisfied": True,
            "evidence": [
                _sha(f"{request.arm_id}:{clause_id}".encode("utf-8", "strict"))
            ],
            "details": "provider-free controller integration observation",
        }
        for clause_id in f1_evaluator.HARD_CLAUSE_IDS
    ]
    return canonical_json_bytes(
        {
            "schema_version": "es.hard_evaluation_replay_inputs.v1",
            "candidate_claims": {
                "candidate_id": request.opaque_label,
                "nominated_architectures": {
                    "representative": "ffno",
                    "witness": "es_f1_witness",
                },
                "structural_fields": [
                    {"name": "width", "baseline": 4, "alternate": 8}
                ],
                "claims": [
                    {
                        "claim_id": "PUBLIC_CONSTRUCTION",
                        "evidence_path": "tests/control.json",
                    }
                ],
            },
            "evaluator_observations": observations,
            "proof_rows": [],
            "frozen_registry": ["ffno"],
            "trusted_product_freeze_digest": _sha(request.packet),
            "evaluator_identity_digest": evaluation_authority[
                "hard_evaluator_identity_digest"
            ],
            "task_identity_digest": evaluation_authority[
                "hard_task_identity_digest"
            ],
            "fixture_identity_digest": evaluation_authority[
                "hard_fixture_identity_digest"
            ],
            "frozen_proof_authority": [],
        }
    )


def _review_receipt(
    package: controller.ControllerPackage,
    request: controller.ReviewCallRequest,
    *,
    ordinal: int,
) -> tuple[bytes, bytes]:
    authority = json.loads(
        (
            package.paths.workspace / package.call_authority.relative_path
        ).read_text(encoding="utf-8")
    )
    static = next(
        row
        for row in authority["prompt_manifest"]["calls"]
        if row["call_slot_id"] == request.call_slot_id
    )
    session_id = f"{request.attempt_id}-review-session-{ordinal:02d}"
    provider_attempt_id = f"{request.attempt_id}-review-provider-{ordinal:02d}"
    raw_jsonl = b"".join(
        metering.canonical_json_bytes(row)
        for row in (
            {"type": "thread.started", "thread_id": session_id},
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 10,
                    "cached_input_tokens": 0,
                    "cache_write_input_tokens": 0,
                    "output_tokens": 5,
                    "reasoning_output_tokens": 0,
                },
            },
        )
    )
    usage = metering.parse_codex_jsonl(
        raw_jsonl,
        expected_session_id=session_id,
    )
    receipt = metering.build_usage_receipt(
        usage,
        study_id="F1-ES",
        block_id=request.attempt_id,
        role_id=static["role_id"],
        call_slot_id=request.call_slot_id,
        provider_attempt_id=provider_attempt_id,
        prompt_sha256=static["prompt_sha256s"][0],
        contract_sha256=static["contract_sha256"],
        raw_jsonl_path=(
            f"attempts/{request.attempt_id}/raw/review-{ordinal:02d}.jsonl"
        ),
        executable_chain=authority["environment_lock"]["executable_chain"],
        process={"pid": 10_000 + ordinal, "argv": static["normalized_argv"]},
        exit_status=0,
    )
    return canonical_json_bytes(receipt), raw_jsonl


def _controller_dependencies(
    *,
    package: controller.ControllerPackage,
    calls: list[str],
    disagreement: bool = False,
    failed_review_slot: str | None = None,
    interrupted_review_slot: str | None = None,
    missing_hard_arms: frozenset[str] = frozenset(),
    trial_run_id: str | None = None,
) -> controller.ControllerDependencies:
    environment = json.loads(
        (
            package.paths.workspace / package.environment_lock.relative_path
        ).read_text(encoding="utf-8")
    )

    def call_provider(
        request: controller.ReviewCallRequest,
    ) -> controller.ProviderCallResult:
        calls.append(request.call_slot_id)
        if request.call_slot_id == interrupted_review_slot:
            raise RuntimeError("provider-free review interruption")
        receipt, raw_jsonl = _review_receipt(
            package,
            request,
            ordinal=sum(slot.startswith("EVAL.") for slot in calls),
        )
        if request.call_slot_id == failed_review_slot:
            return controller.ProviderCallResult.failed(
                failure_code="PROVIDER_TYPED_OUTPUT_INVALID",
                receipt=receipt,
                raw_jsonl=raw_jsonl,
                elapsed_ms=1,
            )
        return controller.ProviderCallResult.succeeded(
            payload=canonical_json_bytes(
                _review_payload(request, disagreement=disagreement)
            ),
            receipt=receipt,
            raw_jsonl=raw_jsonl,
            elapsed_ms=1,
        )

    def collect_hard(
        request: controller.HardEvidenceRequest,
    ) -> controller.HardEvidenceInput:
        calls.append("HARD." + request.arm_id)
        if request.arm_id in missing_hard_arms:
            assert trial_run_id is not None
            evidence = _cell_evidence_by_arm(
                package.paths.state_dir,
                run_id=trial_run_id,
            )[request.arm_id]
            assert evidence["status"] == "failed"
            return controller.HardEvidenceInput.missing(
                canonical_json_bytes(
                    {
                        "schema_version": "es.trusted_product_freeze_absence.v1",
                        "reason": "TERMINAL_TREATMENT_FAILURE",
                        "cell": request.cell.record,
                        "terminal_row_digest": evidence["terminal_row_digest"],
                    }
                )
            )
        return controller.HardEvidenceInput.present(
            _hard_replay_inputs(
                request,
                evaluation_authority=environment["evaluation_authority"],
            )
        )

    return controller.default_controller_dependencies(
        call_provider=call_provider,
        collect_hard_evidence=collect_hard,
    )


def test_controller_public_entry_completes_agreement_and_one_adjudication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, state_dir, run_ref_root, capture = _stage_public_trial(tmp_path)
    _install_fake_codex(tmp_path, monkeypatch)
    monkeypatch.setenv("PATH", (tmp_path / "bin").as_posix() + ":/usr/bin")
    monkeypatch.setattr(
        workflow_executor.os,
        "urandom",
        lambda count: FIXED_SALT[:count],
    )
    _install_deterministic_check_seam(monkeypatch)
    monkeypatch.setattr(
        StateManager,
        "_generate_run_id",
        lambda _self: "es-task5-controller-discovery",
    )
    _set_fake_control(tmp_path, {"review_decision": "REVISE"})
    discovery = _run_checked_in_trial(
        workspace=workspace,
        state_dir=state_dir,
        run_ref_root=run_ref_root,
    )
    records = _capture_records(capture)
    assert discovery.terminal_status == "completed"
    assert len(records) == 18
    arm_by_workspace = _prepared_workspace_by_arm(state_dir)
    # Reuse the exact max-route authority frozen above.  The branch-dependent
    # runtime sites and scorer packets are intentionally not projected across
    # a different treatment route in this provider-free public-entry proof.
    _set_fake_control(tmp_path, {"review_decision": "REVISE"})

    for disagreement, expected_adjudicators in ((False, 0), (True, 1)):
        _reset_public_trial_attempt(
            workspace,
            state_dir,
            run_ref_root,
            capture,
        )
        evidence_root = (
            tmp_path / ("evidence-disagreement" if disagreement else "evidence-agreement")
        ).resolve()
        evidence_root.mkdir()
        run_id = "es-task5-controller-" + (
            "disagreement" if disagreement else "agreement"
        )
        manifest, digest = _controller_package(
            tmp_path=tmp_path,
            workspace=workspace,
            state_dir=state_dir,
            run_ref_root=run_ref_root,
            evidence_root=evidence_root,
            capture_records=records,
            arm_by_workspace=arm_by_workspace,
            parent_run_id=run_id,
        )
        loaded = controller.load_controller_package(
            manifest,
            expected_sha256=digest,
        )
        monkeypatch.setattr(
            StateManager,
            "_generate_run_id",
            lambda _self, value=run_id: value,
        )
        calls: list[str] = []

        result = controller.execute_attempt(
            loaded,
            _controller_dependencies(
                package=loaded,
                calls=calls,
                disagreement=disagreement,
            ),
        )

        assert result.attempt_id == "ES-ATTEMPT-01"
        assert result.trial_result is not None
        assert result.trial_result.terminal_status == "completed"
        assert result.next_attempt_id == "ES-ATTEMPT-02"
        assert calls.count("EVAL.ADJUDICATOR") == expected_adjudicators
        assert calls[-1] == "EVAL.INTEGRATED_REVIEW"
        assert all(calls.count("HARD." + arm) == 1 for arm in ARMS)
        assert (evidence_root / "attempts/ES-ATTEMPT-01/index.json").is_file()


def test_controller_public_entry_preserves_siblings_and_seals_terminal_review_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, state_dir, run_ref_root, capture = _stage_public_trial(tmp_path)
    _install_fake_codex(tmp_path, monkeypatch)
    monkeypatch.setenv("PATH", (tmp_path / "bin").as_posix() + ":/usr/bin")
    monkeypatch.setattr(
        workflow_executor.os,
        "urandom",
        lambda count: FIXED_SALT[:count],
    )
    _install_deterministic_check_seam(monkeypatch)
    monkeypatch.setattr(
        StateManager,
        "_generate_run_id",
        lambda _self: "es-task5-failure-discovery",
    )
    _set_fake_control(tmp_path, {"review_decision": "REVISE"})
    discovery = _run_checked_in_trial(
        workspace=workspace,
        state_dir=state_dir,
        run_ref_root=run_ref_root,
    )
    records = _capture_records(capture)
    arm_by_workspace = _prepared_workspace_by_arm(
        state_dir,
        run_id="es-task5-failure-discovery",
    )
    assert discovery.terminal_status == "completed"
    assert len(records) == 18

    for path in capture.glob("*.json"):
        path.unlink()
    design_implementation_site = next(
        row["provider_attempt_site_key"]
        for row in records
        if arm_by_workspace.get(row["cwd"]) == "DESIGN_QA"
        and "qa_placement_arms::implement-with-design/" in row["output_bundle_path"]
        and "__result__result_bundle.json" in row["output_bundle_path"]
    )
    assert isinstance(design_implementation_site, str)
    arm_failure_run_id = "es-task5-controller-arm-failure"
    failure_discovery_run_id = arm_failure_run_id
    monkeypatch.setattr(
        StateManager,
        "_generate_run_id",
        lambda _self: failure_discovery_run_id,
    )
    _set_fake_control(
        tmp_path,
        {
            "review_decision": "REVISE",
            "fail_provider_attempt_site_key": design_implementation_site,
        },
    )
    failure_discovery = _run_checked_in_trial(
        workspace=workspace,
        state_dir=state_dir,
        run_ref_root=run_ref_root,
    )
    failure_records = _capture_records(capture)
    [failure_ledger_path] = (state_dir / failure_discovery_run_id).glob(
        "*/**/trial-events.jsonl"
    )
    failure_ledger = load_trial_event_ledger(failure_ledger_path)
    failure_arm_by_workspace: dict[str, str] = {}
    for row in failure_ledger.rows:
        if row.kind != "cell_prepared":
            continue
        settled = settled_result_binding_from_record(row.payload["settled_result"])
        failure_arm_by_workspace[settled.workspace_path.as_posix()] = row.payload[
            "cell"
        ]["arm_id"]
    [failed_implementation_capture] = [
        row
        for row in failure_records
        if row["provider_attempt_site_key"] == design_implementation_site
        and "__result__result_bundle.json" in row["output_bundle_path"]
    ]
    failure_arm_by_workspace[failed_implementation_capture["cwd"]] = "DESIGN_QA"
    assert set(failure_arm_by_workspace.values()) == set(ARMS)
    assert len(failure_arm_by_workspace) == len(ARMS)
    assert failure_discovery.terminal_status == "completed"
    assert len(failure_records) == 18
    assert _cell_evidence_by_arm(
        state_dir,
        run_id=failure_discovery_run_id,
    )["DESIGN_QA"]["status"] == "failed"
    [frozen_failure_scorer_prompt] = [
        row["prompt"]
        for row in failure_records
        if "failure_evidence" in row["prompt"]
    ]

    _reset_public_trial_attempt(workspace, state_dir, run_ref_root, capture)
    assert not (state_dir / arm_failure_run_id).exists()
    assert not any(run_ref_root.iterdir())

    arm_failure_root = (tmp_path / "evidence-arm-failure").resolve()
    arm_failure_root.mkdir()
    _set_fake_control(
        tmp_path,
        {"review_decision": "REVISE", "fail_slot": "DESIGN_QA.I"},
    )
    manifest, digest = _controller_package(
        tmp_path=tmp_path,
        workspace=workspace,
        state_dir=state_dir,
        run_ref_root=run_ref_root,
        evidence_root=arm_failure_root,
        capture_records=failure_records,
        arm_by_workspace=failure_arm_by_workspace,
        parent_run_id=arm_failure_run_id,
    )
    package = controller.load_controller_package(manifest, expected_sha256=digest)
    monkeypatch.setattr(
        StateManager,
        "_generate_run_id",
        lambda _self: arm_failure_run_id,
    )
    arm_failure_calls: list[str] = []

    arm_failure = controller.execute_attempt(
        package,
        _controller_dependencies(
            package=package,
            calls=arm_failure_calls,
            missing_hard_arms=frozenset({"DESIGN_QA"}),
            trial_run_id=arm_failure_run_id,
        ),
    )

    arm_failure_index = json.loads(arm_failure.attempt_index)
    [observed_failure_scorer_prompt] = [
        row["prompt"]
        for row in _capture_records(capture)
        if "failure_evidence" in row["prompt"]
    ]
    assert _sha(observed_failure_scorer_prompt.encode("utf-8", "strict")) == _sha(
        frozen_failure_scorer_prompt.encode("utf-8", "strict")
    )
    settlements = {
        row["cell"]["arm_id"]: row["status"]
        for row in arm_failure_index["attempt_record"]["e2_authority"][
            "arm_settlements"
        ]
    }
    assert settlements == {
        "DIRECT": "completed",
        "DESIGN_QA": "failed",
        "PRODUCT_QA": "completed",
        "RICH": "completed",
    }
    failed_arm_settlement = next(
        row
        for row in arm_failure_index["attempt_record"]["e2_authority"][
            "arm_settlements"
        ]
        if row["cell"]["arm_id"] == "DESIGN_QA"
    )
    failed_hard = next(
        row
        for row in arm_failure_index["hard_evaluations"]
        if row["arm_id"] == "DESIGN_QA"
    )
    failed_allocation = next(
        row
        for row in arm_failure_index["call_allocations"]
        if row["call_slot_id"] == "DESIGN_QA.I"
    )
    failed_receipt = next(
        row
        for row in arm_failure_index["receipts"]
        if row["call_slot_id"] == "DESIGN_QA.I"
    )
    failed_binding = next(
        row
        for row in arm_failure_index["attempt_record"]["accounting"][
            "receipt_bindings"
        ]
        if row["call_slot_id"] == "DESIGN_QA.I"
    )
    assert failed_hard == {
        "schema_version": "es.hard_evaluation_evidence.v1",
        "arm_id": "DESIGN_QA",
        "trusted_product_freeze_status": "MISSING",
        "absence_authority": {
            "schema_version": "es.trusted_product_freeze_absence.v1",
            "reason": "TERMINAL_TREATMENT_FAILURE",
            "cell": {"arm_id": "DESIGN_QA", "rep": 1},
            "terminal_row_digest": failed_arm_settlement["terminal_row_digest"],
        },
    }
    assert failed_allocation["settlement"] == "RECEIPT_FROZEN"
    assert failed_receipt["record"]["exit_status"] == 9
    assert failed_allocation["receipt_sha256"] == failed_receipt["record_sha256"]
    assert failed_binding["receipt_sha256"] == failed_receipt["record_sha256"]
    assert arm_failure.trial_result is not None
    assert arm_failure.trial_result.terminal_status == "completed"
    assert arm_failure_calls[-1] == "EVAL.INTEGRATED_REVIEW"
    assert all(arm_failure_calls.count("HARD." + arm) == 1 for arm in ARMS)

    review_failure_root = (tmp_path / "evidence-review-failure").resolve()
    review_failure_root.mkdir()
    review_failure_run_id = "es-task5-controller-review-failure"
    _set_fake_control(tmp_path, {"review_decision": "REVISE"})
    manifest, digest = _controller_package(
        tmp_path=tmp_path,
        workspace=workspace,
        state_dir=state_dir,
        run_ref_root=run_ref_root,
        evidence_root=review_failure_root,
        capture_records=records,
        arm_by_workspace=arm_by_workspace,
        parent_run_id=review_failure_run_id,
    )
    package = controller.load_controller_package(manifest, expected_sha256=digest)
    monkeypatch.setattr(
        StateManager,
        "_generate_run_id",
        lambda _self: review_failure_run_id,
    )
    review_failure_calls: list[str] = []

    review_failure = controller.execute_attempt(
        package,
        _controller_dependencies(
            package=package,
            calls=review_failure_calls,
            failed_review_slot="EVAL.INTEGRATED_REVIEW",
        ),
    )

    review_failure_index = json.loads(review_failure.attempt_index)
    integrated = next(
        row
        for row in review_failure_index["attempt_record"]["accounting"][
            "review_settlements"
        ]
        if row["call_slot_id"] == "EVAL.INTEGRATED_REVIEW"
    )
    receipt = next(
        row
        for row in review_failure_index["attempt_record"]["accounting"][
            "receipt_bindings"
        ]
        if row["call_slot_id"] == "EVAL.INTEGRATED_REVIEW"
    )
    indexed_receipt = next(
        row
        for row in review_failure_index["receipts"]
        if row["call_slot_id"] == "EVAL.INTEGRATED_REVIEW"
    )
    allocation = next(
        row
        for row in review_failure_index["call_allocations"]
        if row["call_slot_id"] == "EVAL.INTEGRATED_REVIEW"
    )
    assert review_failure_index["attempt_record"]["status"] == "VALID"
    assert review_failure_index["attempt_record"]["interrupted"] is False
    assert integrated["status"] == "FAILED"
    assert integrated["receipt_sha256"] == receipt["receipt_sha256"]
    assert indexed_receipt["record_sha256"] == receipt["receipt_sha256"]
    assert allocation["receipt_sha256"] == receipt["receipt_sha256"]
    assert allocation["settlement"] == "RECEIPT_FROZEN"
    assert len(review_failure_index["integrated_payload"]["pairwise_results"]) == 6
    assert {
        row["outcome"]
        for row in review_failure_index["integrated_payload"]["pairwise_results"]
    } == {"INDETERMINATE"}
    assert review_failure_index["hard_primary_outcome"]["raw_outcome"] == (
        "INDETERMINATE"
    )
    assert review_failure_index["hard_primary_outcome"]["derived_outcome"] == (
        "INDETERMINATE"
    )
    assert review_failure_calls.count("EVAL.INTEGRATED_REVIEW") == 1
    assert review_failure_calls[-1] == "EVAL.INTEGRATED_REVIEW"


def test_controller_public_entry_never_resumes_and_regenerates_locked_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, state_dir, run_ref_root, capture = _stage_public_trial(tmp_path)
    _install_fake_codex(tmp_path, monkeypatch)
    monkeypatch.setenv("PATH", (tmp_path / "bin").as_posix() + ":/usr/bin")
    monkeypatch.setattr(
        workflow_executor.os,
        "urandom",
        lambda count: FIXED_SALT[:count],
    )
    _install_deterministic_check_seam(monkeypatch)
    discovery_run_id = "es-task5-lineage-discovery"
    monkeypatch.setattr(
        StateManager,
        "_generate_run_id",
        lambda _self: discovery_run_id,
    )
    _set_fake_control(tmp_path, {"review_decision": "REVISE"})
    discovery = _run_checked_in_trial(
        workspace=workspace,
        state_dir=state_dir,
        run_ref_root=run_ref_root,
    )
    records = _capture_records(capture)
    arm_by_workspace = _prepared_workspace_by_arm(
        state_dir,
        run_id=discovery_run_id,
    )
    assert discovery.terminal_status == "completed"
    assert len(records) == 18

    design_implementation_site = next(
        row["provider_attempt_site_key"]
        for row in records
        if arm_by_workspace.get(row["cwd"]) == "DESIGN_QA"
        and "qa_placement_arms::implement-with-design/" in row["output_bundle_path"]
        and "__result__result_bundle.json" in row["output_bundle_path"]
    )
    assert isinstance(design_implementation_site, str)
    for path in capture.glob("*.json"):
        path.unlink()
    failure_discovery_run_id = "es-task5-lineage-failure-discovery"
    monkeypatch.setattr(
        StateManager,
        "_generate_run_id",
        lambda _self: failure_discovery_run_id,
    )
    _set_fake_control(
        tmp_path,
        {
            "review_decision": "REVISE",
            "fail_provider_attempt_site_key": design_implementation_site,
        },
    )
    failure_discovery = _run_checked_in_trial(
        workspace=workspace,
        state_dir=state_dir,
        run_ref_root=run_ref_root,
    )
    failure_records = _capture_records(capture)
    [failure_ledger_path] = (state_dir / failure_discovery_run_id).glob(
        "*/**/trial-events.jsonl"
    )
    failure_ledger = load_trial_event_ledger(failure_ledger_path)
    labels_by_arm = {
        row["cell"]["arm_id"]: row["opaque_label"]
        for row in failure_ledger.rows[0].payload[
            "sealed_opaque_label_map"
        ]["bindings"]
    }
    failure_design_scorer_prompt = next(
        row["prompt"]
        for row in failure_records
        if (packet := _packet_from_prompt(row["prompt"])) is not None
        and packet["evaluation_id"] == labels_by_arm["DESIGN_QA"]
    )
    assert failure_discovery.terminal_status == "completed"
    assert len(failure_records) == 18
    assert _cell_evidence_by_arm(
        state_dir,
        run_id=failure_discovery_run_id,
    )["DESIGN_QA"]["status"] == "failed"
    _reset_public_trial_attempt(
        workspace,
        state_dir,
        run_ref_root,
        capture,
    )
    _set_fake_control(tmp_path, {"review_decision": "REVISE"})

    evidence_root = (tmp_path / "evidence-lineage").resolve()
    evidence_root.mkdir()
    run_ids = tuple(f"es-task5-lineage-{ordinal}" for ordinal in range(1, 5))
    history: list[controller.ControllerResult] = []

    manifest, digest = _controller_package(
        tmp_path=tmp_path,
        workspace=workspace,
        state_dir=state_dir,
        run_ref_root=run_ref_root,
        evidence_root=evidence_root,
        capture_records=records,
        arm_by_workspace=arm_by_workspace,
        parent_run_id=run_ids[0],
        prompt_variants_by_slot={
            "EVAL.SCORER_DESIGN_QA": (failure_design_scorer_prompt,),
        },
    )
    package = controller.load_controller_package(manifest, expected_sha256=digest)
    prompt_manifest = json.loads(
        (workspace / package.prompt_manifest.relative_path).read_bytes()
    )
    prompt_sets = {
        row["call_slot_id"]: row["prompt_sha256s"]
        for row in prompt_manifest["calls"]
    }
    assert len(prompt_sets["EVAL.SCORER_DESIGN_QA"]) == 2
    assert all(
        len(values) == 1
        for slot, values in prompt_sets.items()
        if slot != "EVAL.SCORER_DESIGN_QA"
    )
    monkeypatch.setattr(
        StateManager,
        "_generate_run_id",
        lambda _self: run_ids[0],
    )
    interrupted_calls: list[str] = []
    interrupted = controller.execute_attempt(
        package,
        _controller_dependencies(
            package=package,
            calls=interrupted_calls,
            interrupted_review_slot=(
                "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY"
            ),
        ),
    )
    history.append(interrupted)

    interrupted_index = json.loads(interrupted.attempt_index)
    interrupted_record = interrupted_index["attempt_record"]
    assert interrupted.attempt_id == "ES-ATTEMPT-01"
    assert interrupted.next_attempt_id == "ES-ATTEMPT-02"
    assert interrupted_record["status"] == "INVALID"
    assert interrupted_record["invalidity_code"] == "APPARATUS_ACCOUNTING_INCOMPLETE"
    assert interrupted_record["interrupted"] is True
    assert interrupted_record["resume_policy"] == "FORBIDDEN"
    assert interrupted_index["call_allocations"][-1]["call_slot_id"] == (
        "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY"
    )
    assert interrupted_index["call_allocations"][-1]["settlement"] == (
        "INTERRUPTED_IN_FLIGHT"
    )
    assert interrupted_index["call_allocations"][-1]["receipt_sha256"] is None
    assert all(
        row["call_slot_id"]
        != "EVAL.INITIAL_API_PERSISTENCE_MIGRATION_MAINTAINABILITY"
        for row in interrupted_index["receipts"]
    )
    first_root = evidence_root / "attempts/ES-ATTEMPT-01"
    frozen_first = {
        path.relative_to(first_root).as_posix(): path.read_bytes()
        for path in first_root.rglob("*")
        if path.is_file()
    }
    replay_calls: list[str] = []
    recovered = controller.execute_attempt(
        package,
        _controller_dependencies(package=package, calls=replay_calls),
    )
    assert replay_calls == []
    assert recovered.attempt_id == interrupted.attempt_id
    assert recovered.next_attempt_id == interrupted.next_attempt_id
    assert recovered.attempt_record == interrupted.attempt_record
    assert recovered.attempt_index == interrupted.attempt_index
    assert {
        path.relative_to(first_root).as_posix(): path.read_bytes()
        for path in first_root.rglob("*")
        if path.is_file()
    } == frozen_first

    for ordinal in range(1, 4):
        manifest, digest = _controller_package(
            tmp_path=tmp_path,
            workspace=workspace,
            state_dir=state_dir,
            run_ref_root=run_ref_root,
            evidence_root=evidence_root,
            capture_records=records,
            arm_by_workspace=arm_by_workspace,
            parent_run_id=run_ids[ordinal],
            attempt_history=tuple(history),
            prompt_variants_by_slot={
                "EVAL.SCORER_DESIGN_QA": (failure_design_scorer_prompt,),
            },
        )
        package = controller.load_controller_package(
            manifest,
            expected_sha256=digest,
        )
        monkeypatch.setattr(
            StateManager,
            "_generate_run_id",
            lambda _self, value=run_ids[ordinal]: value,
        )
        calls: list[str] = []
        if ordinal == 1:
            _set_fake_control(
                tmp_path,
                {
                    "review_decision": "REVISE",
                    "fail_provider_attempt_site_key": (
                        design_implementation_site
                    ),
                },
            )
        else:
            _set_fake_control(tmp_path, {"review_decision": "REVISE"})
        result = controller.execute_attempt(
            package,
            _controller_dependencies(
                package=package,
                calls=calls,
                disagreement=ordinal == 2,
                failed_review_slot=(
                    "EVAL.INTEGRATED_REVIEW" if ordinal == 2 else None
                ),
                missing_hard_arms=(
                    frozenset({"DESIGN_QA"})
                    if ordinal == 1
                    else frozenset()
                ),
                trial_run_id=run_ids[ordinal],
            ),
        )
        history.append(result)
        assert result.attempt_id == f"ES-ATTEMPT-0{ordinal + 1}"
        if ordinal == 2:
            assert calls.count("EVAL.ADJUDICATOR") == 1

    arm_failure_index = json.loads(history[1].attempt_index)
    arm_failure_record = arm_failure_index["attempt_record"]
    arm_failure_settlements = {
        row["cell"]["arm_id"]: row
        for row in arm_failure_record["e2_authority"]["arm_settlements"]
    }
    failed_hard = next(
        row
        for row in arm_failure_index["hard_evaluations"]
        if row["arm_id"] == "DESIGN_QA"
    )
    failed_allocation = next(
        row
        for row in arm_failure_index["call_allocations"]
        if row["call_slot_id"] == "DESIGN_QA.I"
    )
    failed_receipt = next(
        row
        for row in arm_failure_index["receipts"]
        if row["call_slot_id"] == "DESIGN_QA.I"
    )
    assert arm_failure_record["status"] == "VALID"
    assert arm_failure_record["interrupted"] is False
    assert {
        arm: row["status"] for arm, row in arm_failure_settlements.items()
    } == {
        "DIRECT": "completed",
        "DESIGN_QA": "failed",
        "PRODUCT_QA": "completed",
        "RICH": "completed",
    }
    assert failed_hard["absence_authority"] == {
        "schema_version": "es.trusted_product_freeze_absence.v1",
        "reason": "TERMINAL_TREATMENT_FAILURE",
        "cell": {"arm_id": "DESIGN_QA", "rep": 1},
        "terminal_row_digest": arm_failure_settlements["DESIGN_QA"][
            "terminal_row_digest"
        ],
    }
    assert failed_allocation["settlement"] == "RECEIPT_FROZEN"
    assert failed_receipt["record"]["exit_status"] == 9
    assert failed_allocation["receipt_sha256"] == failed_receipt["record_sha256"]

    terminal = history[-1]
    failed_review_index = json.loads(history[-2].attempt_index)
    failed_review_record = failed_review_index["attempt_record"]
    failed_review = next(
        row
        for row in failed_review_index["reviews"]
        if row["call_slot_id"] == "EVAL.INTEGRATED_REVIEW"
    )
    failed_review_allocation = next(
        row
        for row in failed_review_index["call_allocations"]
        if row["call_slot_id"] == "EVAL.INTEGRATED_REVIEW"
    )
    failed_review_receipt = next(
        row
        for row in failed_review_index["receipts"]
        if row["call_slot_id"] == "EVAL.INTEGRATED_REVIEW"
    )
    assert failed_review_record["status"] == "VALID"
    assert failed_review_record["interrupted"] is False
    assert failed_review_record["accounting"]["terminal_authority_complete"] is True
    assert failed_review["status"] == "FAILED"
    assert failed_review["record"]["schema_version"] == "es_evaluator_call_failure.v1"
    assert failed_review_allocation["settlement"] == "RECEIPT_FROZEN"
    assert failed_review_allocation["receipt_sha256"] == failed_review_receipt[
        "record_sha256"
    ]
    assert len(failed_review_index["integrated_payload"]["pairwise_results"]) == 6
    assert {
        row["outcome"]
        for row in failed_review_index["integrated_payload"]["pairwise_results"]
    } == {"INDETERMINATE"}
    assert failed_review_index["hard_primary_outcome"]["raw_outcome"] == (
        "INDETERMINATE"
    )
    assert failed_review_index["hard_primary_outcome"]["derived_outcome"] == (
        "INDETERMINATE"
    )

    assert terminal.attempt_id == "ES-ATTEMPT-04"
    assert terminal.stopped is True
    assert terminal.next_attempt_id is None
    assert terminal.report is not None
    assert {
        path.relative_to(first_root).as_posix(): path.read_bytes()
        for path in first_root.rglob("*")
        if path.is_file()
    } == frozen_first

    lock = json.loads(
        (workspace / package.decision_lock.relative_path).read_bytes()
    )
    schedule = json.loads(
        (workspace / package.randomization_manifest.relative_path).read_bytes()
    )
    bindings = dict(package.expected_bindings)
    indexes = [
        json.loads(
            (evidence_root / f"attempts/{result.attempt_id}/index.json").read_bytes()
        )
        for result in history
    ]
    validated = [
        synthesis.validate_attempt_evidence_index(
            index,
            expected_index_sha256=index["index_sha256"],
            decision_lock=lock,
            randomization_manifest=schedule,
            expected_bindings=bindings,
        )
        for index in indexes
    ]
    regenerated = synthesis.synthesize_report(
        indexed_attempts=validated,
        expected_index_digests=[index["index_sha256"] for index in indexes],
        decision_lock=lock,
        randomization_manifest=schedule,
        expected_bindings=bindings,
    )
    assert synthesis.canonical_report_bytes(regenerated) == terminal.report + b"\n"
