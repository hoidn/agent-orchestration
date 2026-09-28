"""CF-1b Task 4: generic unions instantiated through specialization, end to end.

Contract: docs/design/workflow_lisp_parametric_type_system.md, "Proposed CF-1
First-Order Generic Unions"; transport obligations in
docs/design/workflow_lisp_composition_first.md sections 4, 9 and 10.

Hooks are command-backed probes (the supported deterministic route); every
probe appends its argv to a call log so tests can assert provider-free replay.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint, compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.test_workflow_lisp_generic_stdlib_composition import _execute_bundle
from tests.workflow_lisp_generic_union_runtime_sources import (
    HEADER,
    DECISION_LIB,
    TRIVIAL_ENTRY,
    CALLING_ENTRY,
    OUTCOME_PROBE,
    OUTCOME_LIB,
    LOOP_ENTRY,
    REVIEW_PROBE,
    REVISE_PROBE,
    IMPROVE_LIB,
    IMPROVE_ENTRY,
    RAW_REVIEW_PROBE,
    ADAPTER_REVIEW,
    CLASSIFY_LIB,
    TWO_INSTANCES_ENTRY,
)


def _write_sources(root: Path, sources: dict[str, str]) -> Path:
    for relative, text in sources.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root / "grt" / "entry.orc"


def _compile(root: Path, *, probes: dict[str, Path] | None = None, validate_shared: bool = True):
    return compile_stage3_entrypoint(
        root / "grt" / "entry.orc",
        source_roots=(root,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={
            name: ExternalToolBinding(name=name, stable_command=("python", path.as_posix()))
            for name, path in (probes or {}).items()
        },
        validate_shared=validate_shared,
        workspace_root=root,
        lowering_route=None,
    )


def test_uncalled_generic_with_applied_union_parameter_compiles(tmp_path: Path) -> None:
    """Addendum A: a generic template is not lowered before specialization."""

    _write_sources(tmp_path, {"grt/lib.orc": DECISION_LIB, "grt/entry.orc": TRIVIAL_ENTRY})

    result = _compile(tmp_path)

    assert "grt/entry::run" in result.validated_bundles_by_name


def test_generic_with_applied_union_parameter_lowers_after_specialization(tmp_path: Path) -> None:
    _write_sources(tmp_path, {"grt/lib.orc": DECISION_LIB, "grt/entry.orc": CALLING_ENTRY})

    result = _compile(tmp_path)

    assert "grt/entry::run" in result.validated_bundles_by_name


def _write_probe(root: Path, name: str, text: str) -> Path:
    probe = root / f"{name}.py"
    probe.write_text(text, encoding="utf-8")
    return probe


def _run(result, workflow: str, root: Path) -> dict[str, object]:
    bundle = result.validated_bundles_by_name[workflow]
    outcome = _execute_bundle(bundle, workflow_path=root / "grt" / "entry.orc", workspace=root, run_id="run")
    assert outcome["status"] == "completed", outcome.get("error")
    return dict(outcome["workflow_outputs"])


@pytest.mark.parametrize(
    ("limit", "expected"),
    [
        (2, {"return__variant": "OK", "return__value__title": "revise-seed", "return__value__score": 1}),
        (1, {"return__variant": "ERROR", "return__error": "exhausted"}),
    ],
    ids=["matched-ok", "exhausted"],
)
def test_imported_generic_result_is_matched_and_returned_from_a_caller_loop(
    tmp_path: Path, limit: int, expected: dict[str, object]
) -> None:
    probe = _write_probe(tmp_path, "probe_check", OUTCOME_PROBE)
    entry = LOOP_ENTRY.replace("PROBE_CHECK", probe.as_posix()).replace(":max limit", f":max {limit}")
    _write_sources(tmp_path, {"grt/lib.orc": OUTCOME_LIB, "grt/entry.orc": entry.replace("((limit Int))", "()")})

    result = _compile(tmp_path, probes={"probe_check": probe})

    assert _run(result, "grt/entry::run", tmp_path) == expected


def test_variant_payload_record_is_populated_from_a_bound_name(tmp_path: Path) -> None:
    """Addendum D (F1): `:value ok.value` lowers without rebuilding the record."""

    probe = _write_probe(tmp_path, "probe_check", OUTCOME_PROBE)
    entry = LOOP_ENTRY.replace("PROBE_CHECK", probe.as_posix()).replace(":max limit", ":max 2")
    entry = entry.replace("((limit Int))", "()").replace(
        "((OK ok) (done outcome))",
        "((OK ok) (done (variant Outcome[Candidate String] OK :value ok.value)))",
    )
    _write_sources(tmp_path, {"grt/lib.orc": OUTCOME_LIB, "grt/entry.orc": entry})

    result = _compile(tmp_path, probes={"probe_check": probe})

    assert _run(result, "grt/entry::run", tmp_path) == {
        "return__variant": "OK",
        "return__value__title": "revise-seed",
        "return__value__score": 1,
    }


def _write_improve_project(root: Path, *, seed: str, limit: int) -> dict[str, Path]:
    probes = {
        "probe_review": _write_probe(root, "probe_review", REVIEW_PROBE),
        "probe_revise": _write_probe(root, "probe_revise", REVISE_PROBE),
    }
    entry = (
        IMPROVE_ENTRY.replace("PROBE_REVIEW", probes["probe_review"].as_posix())
        .replace("PROBE_REVISE", probes["probe_revise"].as_posix())
        .replace('"SEED"', f'"{seed}"')
        .replace("LIMIT", str(limit))
    )
    _write_sources(root, {"grt/lib.orc": IMPROVE_LIB, "grt/entry.orc": entry})
    return probes


def _compile_improve(root: Path, *, seed: str, limit: int):
    return _compile(root, probes=_write_improve_project(root, seed=seed, limit=limit))


@pytest.mark.parametrize(
    ("seed", "expected"),
    [
        (
            "seed",
            {
                "return__variant": "APPROVED",
                "return__value__title": "revised-seed",
                "return__value__score": 1,
                "return__evidence__note": "ok-revised-seed",
            },
        ),
        (
            "blocked",
            {
                "return__variant": "BLOCKED",
                "return__value__title": "blocked",
                "return__value__score": 0,
                "return__reason__why": "refused-blocked",
            },
        ),
    ],
    ids=["approved-after-revision", "blocked"],
)
def test_generic_loop_returns_variants_carrying_its_record_state(
    tmp_path: Path, seed: str, expected: dict[str, object]
) -> None:
    result = _compile_improve(tmp_path, seed=seed, limit=3)

    assert _run(result, "grt/entry::run", tmp_path) == expected


def test_generic_loop_exhaustion_returns_its_latest_record_state(tmp_path: Path) -> None:
    result = _compile_improve(tmp_path, seed="seed", limit=1)

    assert _run(result, "grt/entry::run", tmp_path) == {
        "return__variant": "EXHAUSTED",
        "return__value__title": "revised-seed",
        "return__value__score": 1,
    }


@pytest.mark.parametrize(
    ("seed", "limit", "expected"),
    [
        ("seed", 3, ("revised-seed", "approved", "ok-revised-seed")),
        ("blocked", 3, ("blocked", "blocked", "refused-blocked")),
        ("seed", 1, ("revised-seed", "exhausted", "")),
    ],
    ids=["approved", "blocked", "exhausted"],
)
def test_downstream_consumer_matches_the_instantiated_result(
    tmp_path: Path, seed: str, limit: int, expected: tuple[str, str, str]
) -> None:
    result = _compile_improve(tmp_path, seed=seed, limit=limit)

    outputs = _run(result, "grt/entry::summarize", tmp_path)

    assert (outputs["return__title"], outputs["return__status"], outputs["return__note"]) == expected


def test_done_payload_of_the_exhausted_variant_is_not_replaced_by_state(tmp_path: Path) -> None:
    """Same-variant `done` keeps the loop result as the source (target 2.29 rule)."""

    source = tmp_path / "same_variant.orc"
    source.write_text(
        HEADER
        + """  (defrecord LoopState (message String))
  (defunion Outcome (COMPLETE (message String)))
  (defworkflow preserve-done ((finish Bool)) -> Outcome
    (loop/recur :max 1
      :state (record LoopState :message "state")
      :on-exhausted (variant Outcome COMPLETE :message state.message)
      (fn (state)
        (if finish (done (variant Outcome COMPLETE :message "done")) (continue state))))))
""",
        encoding="utf-8",
    )
    lowered = compile_stage3_module(source, validate_shared=True, workspace_root=tmp_path).lowered_workflows[0]
    result_step = next(step for step in lowered.authored_mapping["steps"] if step["name"].endswith("__result"))

    ref = result_step["match"]["cases"]["COMPLETE"]["outputs"]["return__message"]["from"]["ref"]
    assert ref.endswith(".artifacts.result__message")


@pytest.mark.parametrize(
    ("seed", "expected"),
    [("seed", ("revised-seed", "approved", "ok-revised-seed")), ("blocked", ("blocked", "blocked", "refused-blocked"))],
    ids=["approved", "blocked"],
)
def test_caller_adapter_converts_a_concrete_result_into_the_applied_union(
    tmp_path: Path, seed: str, expected: tuple[str, str, str]
) -> None:
    """Addendum E (F2): a match that builds a union with variant fields validates."""

    probes = {
        "probe_review": _write_probe(tmp_path, "probe_review", RAW_REVIEW_PROBE),
        "probe_revise": _write_probe(tmp_path, "probe_revise", REVISE_PROBE),
    }
    hook_start = IMPROVE_ENTRY.index("  (defproc review-candidate")
    hook_end = IMPROVE_ENTRY.index("  (defproc revise-candidate")
    entry = IMPROVE_ENTRY[:hook_start] + ADAPTER_REVIEW + IMPROVE_ENTRY[hook_end:]
    entry = (
        entry.replace("PROBE_REVIEW", probes["probe_review"].as_posix())
        .replace("PROBE_REVISE", probes["probe_revise"].as_posix())
        .replace('"SEED"', f'"{seed}"')
        .replace("LIMIT", "3")
    )
    _write_sources(tmp_path, {"grt/lib.orc": IMPROVE_LIB, "grt/entry.orc": entry})

    outputs = _run(_compile(tmp_path, probes=probes), "grt/entry::summarize", tmp_path)

    assert (outputs["return__title"], outputs["return__status"], outputs["return__note"]) == expected


class _PostCommitInterruption(BaseException):
    pass


def _public_run_files(root: Path, probes: dict[str, Path]) -> dict[str, Path]:
    files = {
        "source": root / "grt" / "entry.orc",
        "source_root": root,
        "providers": root / "providers.json",
        "prompts": root / "prompts.json",
        "commands": root / "commands.json",
    }
    files["providers"].write_text("{}", encoding="utf-8")
    files["prompts"].write_text("{}", encoding="utf-8")
    files["commands"].write_text(
        json.dumps(
            {
                name: {"kind": "external_tool", "stable_command": ["python", path.as_posix()]}
                for name, path in probes.items()
            }
        ),
        encoding="utf-8",
    )
    return files


def _public_run(files: dict[str, Path]):
    from unittest.mock import patch
    import sys

    from orchestrator.cli.commands.run import run_workflow
    from tests.test_workflow_lisp_rich_loop_values_e2e import _run_args, _run_argv

    args = _run_args(files)
    args.command_boundaries_file = str(files["commands"])
    argv = [*_run_argv(files), "--command-boundaries-file", str(files["commands"])]
    with patch.object(sys, "argv", argv):
        return run_workflow(args)


def _log(probe: Path) -> list[str]:
    log = probe.with_suffix(".log")
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


APPROVED_OUTPUTS = {
    "return__variant": "APPROVED",
    "return__value__title": "revised-seed",
    "return__value__score": 1,
    "return__evidence__note": "ok-revised-seed",
}


def test_public_run_returns_the_instantiated_union(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    probes = _write_improve_project(tmp_path, seed="seed", limit=3)
    monkeypatch.chdir(tmp_path)

    result = _public_run(_public_run_files(tmp_path, probes))

    assert result.exit_code == 0
    assert dict(result.workflow_outputs) == APPROVED_OUTPUTS
    assert (_log(probes["probe_review"]), _log(probes["probe_revise"])) == (["seed", "revised-seed"], ["revised-seed"])


def test_resume_after_a_committed_iteration_keeps_state_without_replaying_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import patch

    from orchestrator.cli.commands.resume import resume_workflow
    from orchestrator.workflow.executor import WorkflowExecutor

    probes = _write_improve_project(tmp_path, seed="seed", limit=3)
    files = _public_run_files(tmp_path, probes)
    original_hook = WorkflowExecutor._emit_lexical_checkpoint_shadow_after_repeat_until_commit

    def interrupt_after_first_commit(self, step, progress):
        original_hook(self, step, progress)
        if progress.get("last_condition_result") is False:
            raise _PostCommitInterruption

    monkeypatch.chdir(tmp_path)
    with patch.object(
        WorkflowExecutor, "_emit_lexical_checkpoint_shadow_after_repeat_until_commit", interrupt_after_first_commit
    ):
        with pytest.raises(_PostCommitInterruption):
            _public_run(files)
    assert (_log(probes["probe_review"]), _log(probes["probe_revise"])) == (["seed"], ["revised-seed"])

    run_id = next((tmp_path / ".orchestrate" / "runs").iterdir()).name
    assert resume_workflow(run_id=run_id, retry_delay_ms=0) == 0

    state = json.loads((tmp_path / ".orchestrate" / "runs" / run_id / "state.json").read_text(encoding="utf-8"))
    assert (state["status"], state["workflow_outputs"]) == ("completed", APPROVED_OUTPUTS)
    assert (_log(probes["probe_review"]), _log(probes["probe_revise"])) == (["seed", "revised-seed"], ["revised-seed"])


def _union_descriptors(bundle) -> dict[str, set[str]]:
    from orchestrator.workflow.executable_ir import workflow_executable_ir_to_json

    shapes: dict[str, set[str]] = {}

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if node.get("kind") == "union" and "variants" in node:
                shapes.setdefault(node["name"], set()).add(json.dumps(node, sort_keys=True))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(workflow_executable_ir_to_json(bundle.ir))
    return shapes


def test_two_instantiations_get_distinct_concrete_descriptors(tmp_path: Path) -> None:
    """Addendum G: one IR carries each instantiation under its own concrete name."""

    probe = _write_probe(tmp_path, "probe_review", REVIEW_PROBE)
    entry = TWO_INSTANCES_ENTRY.replace("PROBE_REVIEW", probe.as_posix())
    _write_sources(tmp_path, {"grt/lib.orc": CLASSIFY_LIB, "grt/entry.orc": entry})
    result = _compile(tmp_path, probes={"probe_review": probe})

    shapes = _union_descriptors(result.validated_bundles_by_name["grt/entry::run"])

    assert sorted(shapes) == [
        "grt/lib::Improvement[Candidate Feedback Blocker]",
        "grt/lib::Improvement[Draft Feedback Blocker]",
    ]
    assert all(len(variants) == 1 for variants in shapes.values())
    assert _run(result, "grt/entry::run", tmp_path) == {"return__first": "revised-a", "return__second": "refused-blocked"}
