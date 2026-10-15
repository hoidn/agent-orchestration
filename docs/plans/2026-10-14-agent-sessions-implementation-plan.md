# Agent Sessions Implementation Plan A: Admission And Transport

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Use `superpowers:test-driven-development` for every behavior change and `tmux` for broad pytest runs.

**Goal:** admit the `agent` constructor and opaque `Agent` type at a new evaluated target 2.38 (frontend, typecheck, effect origins, escape checks, closed-program shape, target registration, frontend §8.8 exception) and build the native-session transport both adapters need (Claude `session_support` + stream-json accumulator, Codex position evidence, native-store adapters, session request plumbing in the evaluated provider path, deterministic fake CLIs), without any runtime allocation or turn coordination.

**Architecture:** `agent` is a new `CORE_EFFECT` form that elaborates to `AgentExpr`, types as the prelude primitive `Agent` (installed only at targets >= 2.38) and emits `uses-provider` for its extern; `provider-result` accepts an `Agent`-typed first operand and becomes an `agent_turn` perform whose closed node carries the statically checked provider `origins`. Escape checks join the existing `Provider`/`Prompt` refusal sites and `_NONTRANSPORTABLE_PRIMITIVES`. Transport adds one metadata mode (`claude_stream_json_stdout`) with its own accumulator module, a `native_store.py` adapter module lifted from `scripts/experiments/native_session_cli_evidence.py`, and a `session_request`/`observation_handle` pass-through in `orchestrator/workflow/evaluated/providers.py`. Plan B (`2026-10-14-agent-sessions-implementation-plan-b.md`) owns the runtime, C8, observation, consumer and qualification; the interface contract between the two plans is the section "Interface contract with Plan B" below.

**Tech Stack:** Python 3.12, pytest (`-n 16 --dist=worksteal` for broad runs, in tmux), Workflow Lisp frontend/closed-program compiler, `orchestrator/providers` executor and session transport.

**Spec:** `docs/design/workflow_lisp_agent_sessions.md` (authoritative, amended 2026-10-14). Deferred owners: `docs/design/workflow_lisp_evaluated_execution.md` §§6–9, `docs/design/workflow_lisp_frontend_specification.md` §8.8, `docs/design/workflow_lisp_runtime_closures_boundary.md` §§9–9.1, `specs/{providers,io,state,cli,versioning,observability}.md`. Owner decisions D1–D8 are recorded in the design's Metadata, Architecture and Open Questions sections and in `docs/plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md#pq-1-sequential-native-session-turns`.

**Split decision:** the first slice is 23 tasks; the brief's ~20-task rule applies, so Plan A (8 tasks: admission + transport, compile- and transport-testable with no evaluated runtime change beyond keyword pass-through, plus the owner's D8a Claude mini-probe) and Plan B (15 tasks) are separate files. Plan A is complete on its own: every program at 2.38 compiles to a checked closed program, every transport primitive is tested through `ProviderExecutor` with fake CLIs, and nothing in Plan A can start an agent turn.

## Global Constraints

- Target: `agent`/`Agent`/`agent_turn` are admitted only at evaluated target `"2.38"`; `2.35`, `2.36`, `2.37` contracts are unchanged (D4). The 2.37 gate `PARALLEL_MAP_MIN_TARGET_DSL_VERSION` stays independent.
- Memo profile stays `evaluated_execution.v1`, schema `3.0`, representation `table/1` (`specs/state.md` "Authority and run root"); Plan A adds no memo record.
- No provider-name dispatch: capability comes from `ProviderTemplate.session_support.metadata_mode` and the structural adapter registry; do not extend `node["provider"].startswith("omp")` at `orchestrator/workflow/evaluated/effect_inputs.py:120`.
- Native sessions live in the provider default home (`~/.codex`, `~/.claude`); no per-run `CODEX_HOME`/`CLAUDE_CONFIG_DIR`, no credential provisioning (D7). The adapters read `CODEX_HOME`/`CLAUDE_CONFIG_DIR` only when the orchestrator's own environment already sets them (tests do), else the default home.
- Modules stay <= 500 lines, cyclomatic complexity <= 12 per function. Current counts of modules this plan touches: `expressions.py` 7127, `check.py` 5051, `pure_expr.py` 2679, `typecheck_effects.py` 1463, `types.py` 904, `session_transport.py` 626, `sites.py` 554, `closed/effects.py` 468, `registry.py` 457, `providers.py` 334. Rule: a module already over 500 receives at most one dispatch line per edit site and all new code goes to a new module (`agent_forms.py`, `typecheck_agents.py`, `closed/agent_effects.py`, `closed_program/check_agents.py`, `closed_program/node_walk.py`, `session_transport_claude.py`, `agent_value.py`); a module under 500 that a task would push over is split in that task. Every task that touches one of these modules ends with `wc -l` on it and records the count in its commit message body.
- Diagnostic codes introduced by Plan A (all registered in `orchestrator/workflow_lisp/diagnostics.py` and catalogued in the drafting guide section Plan B Task 16 writes): `agent_target_dsl_unsupported`, `agent_provider_invalid`, `agent_keyword_invalid`, `agent_model_type_invalid`, `agent_effort_type_invalid`, `agent_policy_operand_not_inline_lowerable`, `agent_turn_policy_override_forbidden`, `agent_turn_option_unsupported`, `agent_transport_forbidden`, `parallel_agent_boundary`, `let_proc_capture_agent_forbidden`, `agent_origin_mismatch` (closed-program check rule). No others.
- Tests assert types, effect summaries, closed-node shapes, diagnostics, accumulator metadata and native-store facts; never literal prompt text.
- Commits: `git add <new paths>` then `git commit -m "<conventional message>" -- <paths>`; no assistant attribution lines, no `Co-Authored-By` trailers, never `--no-verify`. The checkout carries other sessions' uncommitted edits: never `git add .`/`-A`, never stash or reset.
- Narrow pytest selectors first; after adding or renaming a test module run `pytest --collect-only <module>`; broad runs `pytest -q -n 16 --dist=worksteal` in tmux at the end of the plan.
- No real provider is invoked anywhere in Plan A except Task 6a (the owner's D8a mini-probe: at most three `haiku` calls, opt-in, run manually in tmux).

## Review Focus

1. `agent` written in a module whose `:target-dsl` is `2.37` or lower: the author expects a clear target diagnostic (`agent_target_dsl_unsupported`), not an unknown-head error. Test pinned in Task 2.
2. An `Agent` handed to a provider as `:inputs (designer)`, a prompt `:value` fill or a command argv/input: must refuse at compile with `agent_transport_forbidden`, never render JSON of the handle. Test pinned in Task 3.
3. A Claude `stream-json` run that dies before its `result` event: `finalize(require_terminal=True)` must return an error, not a session with `session_id` only. Test pinned in Task 4.
4. Two native files answering one locator (a copied rollout): `locate` must report ambiguity (`None` plus `ambiguous=True`), so Plan B refuses `agent_session_unavailable` instead of appending to the wrong file. Test pinned in Task 5.
5. The evaluated provider path with `session_request=None` must produce byte-identical `prepare_invocation` kwargs and `execute` calls as today, so ordinary 2.35–2.37 provider effects are unchanged. Test pinned in Task 7.

---

## Interface contract with Plan B

Plan B consumes exactly these names; a change here is a Plan B change.

| Produced by | Name and signature |
| --- | --- |
| Task 1 | `orchestrator.contracts.closed_program.targets.AGENT_SESSIONS_MIN_TARGET_DSL_VERSION = "2.38"`; `target_dsl_supports_agent_sessions(target: str) -> bool`; both re-exported from `orchestrator.workflow_lisp.syntax` |
| Task 2 | Frontend `AgentExpr(provider, model, effort, span, form_path, expansion_stack)` in `expressions.py` (elaborated by `workflow_lisp/agent_forms.py`); prelude primitive `Agent` at >= 2.38; `typecheck_agents.typecheck_agent_expr`; `typecheck_agents.agent_origins(expr, context) -> frozenset[str]` (extern names); `typecheck_agents.require_no_agent(type_ref, *, where, span, form_path, expansion_stack)` raising `agent_transport_forbidden` |
| Task 3 | Closed nodes: `{"k":"perform","class":"agent","result":{"kind":"primitive","name":"Agent"},"repeat":"rerun","provider":<provider_id>,"policy":{"model"?,"effort"?},"site":...}` and `{"k":"perform","class":"agent_turn","result":<desc>,"repeat":"rerun","agent":<value node>,"origins":[<provider_id>...] (sorted, unique, non-empty),"prompt","inputs","dependencies","policy":{"timeout_sec"?},"contract","site"}`. `_effect_value_children`: `agent` -> `list(policy.values())`; `agent_turn` -> `[node["agent"], *input rows[2], *fill values, *required, *optional, *policy values]`. Runtime `Agent` value shape accepted by `coerce_pure_value` (via `orchestrator/workflow/agent_value.py::coerce_agent_value`): `{"run_id": str, "identity": str, "provider": str, "policy": {str: str}, "config_digest": str}` (`config_digest` is the pinned-configuration digest defined in Plan B Task 9). `closed_program/node_walk.py` owns `_ast_nodes`, `_bound_nodes`, `_value_nodes`, `_arm_root_values`, `_effect_value_children`, `_value_children` (re-exported from `sites.py`) |
| Task 4 | `ProviderSessionMetadataMode.CLAUDE_STREAM_JSON_STDOUT = "claude_stream_json_stdout"`; `orchestrator.providers.session_transport_claude.ClaudeStreamJsonAccumulator`; `create_session_transport_accumulator` returns it for that mode; `claude_unrestricted_workspace.session_support` (fresh/resume) |
| Task 5 | `orchestrator.providers.native_store` (completion rules: Codex `task_complete`; Claude either a `StructuredOutput` `toolEndsTurn` user row with its attachment, as the live probe observed, or an assistant `stop_reason == "end_turn"` row, a hypothesis Task 6a confirms or falsifies before Plan B): `NativePosition(turn_id: str, end_line: int)`, `NativeHead(locator, path, position: NativePosition | None, open_turn: bool)`, `NativeTurn(position: NativePosition, user_line: int)`, `NativeLocate(path: Path | None, ambiguous: bool)`, `NativeStoreAdapter` protocol (`metadata_mode`, `locate(locator) -> NativeLocate`, `head(path) -> NativeHead`, `completed_turn(path, *, after: NativePosition | None, prompt_marker: str) -> NativeTurn | None`), `native_store_adapter(metadata_mode) -> NativeStoreAdapter | None`; `CodexExecJsonlAccumulator.finalize` metadata gains `"turns_completed": int` |
| Task 6 | `tests/agent_session_shims.py`: `FAKE_CODEX`, `FAKE_CLAUDE`, `install_agent_shims(bin_dir, monkeypatch, *, codex_home, claude_home, plan) -> None`, `shim_requests(root) -> list[dict]`; plan modes `success`, `interrupted` (store written, no completion, exit 137), `overlap`, `lose-locator`, `invalid-result`, `timeout` (sleep before any store write), `nonzero` (store written, no completion, exit 9), `nonzero-before-append` (exit 9 before touching the store), `complete-then-hang` (store, result and stdout complete, then sleep 30 s), `linger` (completes, then forks a child that sleeps 30 s so a process outlives the CLI); each step may carry `files: {path: text}` written before the result |
| Task 6a | `scripts/experiments/native_session_cli_probe.py --command-form {schema,plain}`; private receipt `claude-plain-form.json` with `completion_marker ∈ {end_turn, tool_ends_turn, NOT_OBSERVED}` |
| Task 7 | `evaluated.providers.launch_provider(node, resolved, identity, *, executor, attempt_files, workspace_files, result_path, stream_output=False, launch_cwd=None, logical_workspace_root=None, session_request=None, observation_handle=None, control=None) -> ProviderExecutionResult` (`control: ProviderExecutionControl | None` is forwarded to `executor.execute`; the executor binds the child pgid through `control.bind(process, pgid)`); `_prepare_provider_invocation(node, resolved, result_path, executor, *, session_request=None)`; `provider_delivery_name_for_template(template: ProviderTemplate) -> str` |

---

### Task 1: Register target 2.38 and the agent-sessions gate

**Files:**
- Modify: `orchestrator/contracts/closed_program/targets.py:3-36,45-50`
- Modify: `orchestrator/workflow_lisp/syntax.py:21-30` (re-exports)
- Modify: `orchestrator/workflow/run_ref/config.py:28`
- Modify: `tests/test_workflow_lisp_target_233.py:71`, `tests/test_workflow_lisp_target_234.py:91-96,119`, `tests/test_workflow_lisp_w3_target.py:42-43`, `tests/test_workflow_lisp_target_evaluated_execution.py:34-35`, `tests/test_executor_retirement_cutoff.py:135`, `tests/test_workflow_lisp_lsp_compile_driver.py:4497`
- Create: `tests/test_workflow_lisp_target_238.py`
- Modify (spec amendment, versioning): `specs/versioning.md:10-11` (support prose), `:1028` (per-version additions list, add the `v2.38` entry after `v2.36`; no `v2.37` back-fill), `:1137-1193` (summary table: add the 2.38 row after 2.36; no 2.37 row), `specs/dsl.md:25`, `specs/cli.md:10,228-229`, `specs/io.md:10,327-328`, `specs/state.md:278-279,300`, `specs/index.md:51`

**Interfaces:**
- Produces: `AGENT_SESSIONS_MIN_TARGET_DSL_VERSION`, `target_dsl_supports_agent_sessions`, `"2.38" in SUPPORTED_TARGET_DSL_VERSIONS`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_workflow_lisp_target_238.py
"""Target 2.38 is registered as an additive evaluated target that gates agent sessions."""
from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow import run_ref
from orchestrator.workflow.run_ref import config as run_ref_config
from orchestrator.workflow_lisp import syntax
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from tests.test_workflow_lisp_target_233 import _compile_minimal_module

TARGET = "2.38"


@pytest.mark.parametrize("registry", [
    pytest.param(syntax.SUPPORTED_TARGET_DSL_VERSIONS, id="frontend"),
    pytest.param(run_ref_config._SUPPORTED_TARGET_DSL_VERSIONS, id="run-ref-config"),
])
def test_target_238_is_registered(registry) -> None:
    assert TARGET in registry


def test_agent_sessions_gate_opens_at_238_and_keeps_earlier_gates() -> None:
    assert syntax.AGENT_SESSIONS_MIN_TARGET_DSL_VERSION == TARGET
    assert [syntax.target_dsl_supports_agent_sessions(t) for t in ("2.36", "2.37", "2.38")] == [False, False, True]
    assert syntax.target_dsl_supports_parallel_map("2.38") is True
    assert syntax.target_dsl_uses_evaluated_execution("2.38") is True
    assert syntax.PARALLEL_MAP_MIN_TARGET_DSL_VERSION == "2.37"


def test_module_targeting_238_compiles_with_no_new_forms(tmp_path: Path) -> None:
    assert _compile_minimal_module(tmp_path, TARGET).typed_program.target == TARGET


def test_module_targeting_239_is_rejected_as_unsupported(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_minimal_module(tmp_path, "2.39")
    assert excinfo.value.diagnostics[0].code == "target_dsl_unsupported"
```

Also edit the existing probes: in `tests/test_workflow_lisp_target_233.py:71` rename `test_module_targeting_238_is_rejected_as_unsupported` to `..._239_...` and compile `"2.39"`; in `tests/test_workflow_lisp_target_234.py:119` change `_write_program(tmp_path, "2.38")` to `"2.39"` and rename the test; add `GATES_FROM_AGENT_SESSIONS = {"AGENT_SESSIONS_MIN_TARGET_DSL_VERSION": syntax.target_dsl_supports_agent_sessions}` beside `GATES_FROM_PARALLEL_MAP` (`:91-96`) and include it in the union asserted by `test_every_min_target_gate_has_a_predicate_here` (`:133-136`); add `"2.38"` to the parametrized lists at `tests/test_executor_retirement_cutoff.py:135` and `tests/test_workflow_lisp_lsp_compile_driver.py:4497`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_workflow_lisp_target_238.py tests/test_workflow_lisp_target_234.py::test_every_min_target_gate_has_a_predicate_here -q`
Expected: FAIL — `AttributeError: module 'orchestrator.workflow_lisp.syntax' has no attribute 'AGENT_SESSIONS_MIN_TARGET_DSL_VERSION'` and `assert '2.38' in frozenset(...)` failures.

- [ ] **Step 3: Implement the registration**

```python
# orchestrator/contracts/closed_program/targets.py (additions)
AGENT_SESSIONS_MIN_TARGET_DSL_VERSION = "2.38"
SUPPORTED_TARGET_DSL_VERSIONS = frozenset({..., "2.37", "2.38"})


def target_dsl_supports_agent_sessions(target_dsl_version: str) -> bool:
    """Return whether a registered target admits `agent`, `Agent` and agent turns."""
    return target_dsl_version in SUPPORTED_TARGET_DSL_VERSIONS and tuple(
        map(int, target_dsl_version.split("."))
    ) >= (2, 38)
```

`orchestrator/workflow_lisp/syntax.py:21-30`: import and re-export `AGENT_SESSIONS_MIN_TARGET_DSL_VERSION` and `target_dsl_supports_agent_sessions` in the same `from orchestrator.contracts.closed_program.targets import (...)` block. `orchestrator/workflow/run_ref/config.py:28`: append `"2.38"` to `_SUPPORTED_TARGET_DSL_VERSIONS`.

- [ ] **Step 4: Amend versioning and the per-spec target mentions (design-spec-drafting: each edit names its section)**

- `specs/versioning.md:10-11`: "admits evaluated entries/profiles at 2.35/2.36, the registered bounded 2.37 surface and the registered bounded 2.38 agent-sessions surface with their existing limits".
- `specs/versioning.md` per-version additions list (after the `v2.36` bullet at `:1028`; the absent `v2.37` bullet is owned by the Phase 5 plan and is not back-filled here): add `- `v2.38`: Workflow Lisp agent sessions: `agent`/`Agent` and sequential native-session turns through `provider-result` on an agent, memo commit per turn, two session adapters (Claude, Codex); qualification pending under [PQ-1a](../docs/plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md#pq-1-sequential-native-session-turns)`.
- `specs/versioning.md` "Version Gating Summary" table (after the 2.36 row at `:1193`; no 2.37 row is added, same ownership note): row `| 2.38 | Workflow Lisp agent sessions: `agent` constructor, opaque `Agent`, `provider-result` on an agent as a coordinator `agent_turn` effect | Registered and additive; 2.35/2.36/2.37 unchanged. Admission of allocation/turn runtime, recovery and C8 guards is owned by [`docs/plans/2026-10-14-agent-sessions-implementation-plan-b.md`](../docs/plans/2026-10-14-agent-sessions-implementation-plan-b.md); state schema `3.0`, profile `evaluated_execution.v1` unchanged (additive `effect_class` values and class-specific `proof`). |`
- `specs/dsl.md:25`, `specs/cli.md:10,228-229`, `specs/io.md:10,327-328`, `specs/state.md:278-279,300`, `specs/index.md:51`: where each says "bounded 2.37" add "and registered bounded 2.38 (agent sessions; see versioning)". Do not claim the runtime is implemented.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_workflow_lisp_target_238.py tests/test_workflow_lisp_target_233.py tests/test_workflow_lisp_target_234.py tests/test_workflow_lisp_w3_target.py tests/test_workflow_lisp_target_evaluated_execution.py tests/test_executor_retirement_cutoff.py -q -k "238 or 239 or registered or gate or explain"`
Expected: PASS; then `pytest --collect-only tests/test_workflow_lisp_target_238.py -q` lists 5 items.

- [ ] **Step 6: Commit**

```bash
git add tests/test_workflow_lisp_target_238.py
git commit -m "feat: register evaluated target 2.38 with the agent-sessions gate" -- orchestrator/contracts/closed_program/targets.py orchestrator/workflow_lisp/syntax.py orchestrator/workflow/run_ref/config.py tests/test_workflow_lisp_target_238.py tests/test_workflow_lisp_target_233.py tests/test_workflow_lisp_target_234.py tests/test_workflow_lisp_w3_target.py tests/test_workflow_lisp_target_evaluated_execution.py tests/test_executor_retirement_cutoff.py tests/test_workflow_lisp_lsp_compile_driver.py specs/versioning.md specs/dsl.md specs/cli.md specs/io.md specs/state.md specs/index.md
```

---

### Task 2: `agent` constructor, opaque `Agent` type and provider origins

**Files:**
- Modify: `orchestrator/workflow_lisp/form_registry.py:86` (add spec after `provider-result` at `:510-520`)
- Modify: `orchestrator/workflow_lisp/expressions.py:856` (add the `AgentExpr` dataclass before `ProviderResultExpr`; 12 lines), `:1844` (one route-table line `"agent": _elaborate_agent` importing from `agent_forms`)
- Create: `orchestrator/workflow_lisp/agent_forms.py` (`_elaborate_agent`; `expressions.py` is 7127 lines and receives no function body)
- Modify: `orchestrator/workflow_lisp/type_env.py:145-160` (`prelude_type_names_for_target` adds `"Agent"` at >= 2.38; `PRELUDE_PRIMITIVE_TYPE_NAMES` unchanged so older targets never see it)
- Create: `orchestrator/workflow_lisp/typecheck_agents.py`
- Modify: `orchestrator/workflow_lisp/typecheck_dispatch.py:1206` (dispatch `AgentExpr`), `orchestrator/workflow_lisp/expression_traversal.py:293` (traverse `AgentExpr.provider/model/effort`), `orchestrator/workflow_lisp/procedure_specialization.py:577,651` (the two `isinstance(node, (…, RequestInputExpr, …))` tuples gain `AgentExpr`, so specialization rewrites and effect scans see allocations), `orchestrator/workflow_lisp/closed/command_templates.py:86` (the tuple `ex.CommandResultExpr, ex.ProviderResultExpr, ex.RequestInputExpr, ex.CallExpr` gains `ex.AgentExpr`)
- Modify: `orchestrator/workflow_lisp/diagnostics.py:209` region (register the twelve codes listed in Global Constraints)
- Create: `tests/test_workflow_lisp_agent_constructor.py`

**Interfaces:**
- Consumes: Task 1 gate.
- Produces: `AgentExpr`, `typecheck_agent_expr(expr, *, context, recurse, typed_factory)`, `agent_origins(expr, context) -> frozenset[str]`, `record_agent_origin(context, name, origins)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_workflow_lisp_agent_constructor.py
"""`agent` types as the opaque `Agent` primitive at 2.38 and carries provider origins."""
from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow_lisp.build import FrontendBuildRequest, build_frontend
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.effects import UsesProviderEffect, render_effect_set
from orchestrator.workflow_lisp.type_env import PrimitiveTypeRef

MODULE = '''(workflow-lisp (:language "0.1") (:target-dsl "{target}")
  (defmodule main) (export run)
  (defrecord Note (text String))
  (defworkflow run ((task String) (planner String)) -> Note
    (let* ((designer (agent providers.claude :model planner :effort "high"))
           (same designer))
      (provider-result providers.codex :prompt prompts.base :inputs (task) :returns Note))))'''


def _build(root: Path, source: str):
    (root / "main.orc").write_text(source, encoding="utf-8")
    (root / "prompt.md").write_text("ASSET\n", encoding="utf-8")
    (root / "providers.json").write_text('{"providers.claude": "claude_unrestricted_workspace", "providers.codex": "codex"}')
    (root / "prompts.json").write_text('{"prompts.base": {"asset_file": "prompt.md"}}')
    return build_frontend(FrontendBuildRequest(source_path=root / "main.orc", source_roots=(root,), workspace_root=root,
        provider_externs_path=root / "providers.json", prompt_externs_path=root / "prompts.json"))


TEAM = MODULE.replace("(defrecord Note (text String))", "(defrecord Note (text String)) (defrecord Team (lead Agent) (label String))") \
    .replace("(same designer))", '(same designer) (team (Team :lead {lead} :label "d")))')


def test_agent_binding_types_as_opaque_agent_and_uses_its_provider(tmp_path: Path) -> None:
    built = _build(tmp_path, MODULE.format(target="2.38"))
    workflow = built.typed_program.workflows["main::run"]
    subjects = {e.subject for e in workflow.effect_summary.direct_effects if isinstance(e, UsesProviderEffect)}
    assert subjects == {("providers", "claude"), ("providers", "codex")}


def test_alias_is_an_agent_and_a_string_is_not(tmp_path: Path) -> None:
    """The record field typed `Agent` accepts the alias (type `Agent`) and refuses a `String` with the ordinary field diagnostic."""
    _build(tmp_path, TEAM.format(target="2.38", lead="same"))
    with pytest.raises(LispFrontendCompileError) as agent_as_string:
        _build(tmp_path, TEAM.format(target="2.38", lead="task"))
    with pytest.raises(LispFrontendCompileError) as control:
        _build(tmp_path, TEAM.format(target="2.38", lead="task").replace("(lead Agent)", "(lead Int)"))
    assert agent_as_string.value.diagnostics[0].code == control.value.diagnostics[0].code   # same field-type mismatch code as Int vs String


@pytest.mark.parametrize("target", ["2.36", "2.37"])
def test_agent_below_238_refuses_with_target_diagnostic(tmp_path: Path, target: str) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build(tmp_path, MODULE.format(target=target))
    assert excinfo.value.diagnostics[0].code == "agent_target_dsl_unsupported"


@pytest.mark.parametrize("operand, code", [
    ("task", "agent_provider_invalid"),
    ("prompts.base", "agent_provider_invalid"),
])
def test_agent_requires_a_provider_extern(tmp_path: Path, operand: str, code: str) -> None:
    source = MODULE.format(target="2.38").replace("(agent providers.claude", f"(agent {operand}")
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build(tmp_path, source)
    assert excinfo.value.diagnostics[0].code == code


def test_agent_rejects_timeout_and_unknown_keywords(tmp_path: Path) -> None:
    source = MODULE.format(target="2.38").replace(':effort "high"', ':effort "high" :timeout-sec 60')
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build(tmp_path, source)
    assert excinfo.value.diagnostics[0].code == "agent_keyword_invalid"


def test_agent_type_name_is_absent_below_238(tmp_path: Path) -> None:
    source = MODULE.format(target="2.37").replace("(agent providers.claude :model planner :effort \"high\")", '"x"') \
        .replace("(defrecord Note (text String))", "(defrecord Note (text String) (who Agent))")
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build(tmp_path, source)
    assert excinfo.value.diagnostics[0].code == "type_unknown"   # type_env.py:1467


def test_agent_inside_a_pure_definition_is_refused_like_any_effect(tmp_path: Path) -> None:
    pure = MODULE.format(target="2.38").replace("(defworkflow run", '(defun helper ((p Provider)) -> Agent (agent p))\n  (defworkflow run')
    control = pure.replace("(agent p)", '(provider-result p :prompt prompts.base :inputs () :returns Note)').replace("-> Agent", "-> Note")
    with pytest.raises(LispFrontendCompileError) as agent_in_defun, pytest.raises(LispFrontendCompileError) as effect_in_defun:
        _build(tmp_path, pure)
        _build(tmp_path, control)
    assert agent_in_defun.value.diagnostics[0].code == effect_in_defun.value.diagnostics[0].code
```

The pure-definition test uses two separate `with pytest.raises` blocks in the implementation (one per build); the sketch above compresses them. `MODULE`'s `run` is `main::run` in the typed program (see `tests/test_workflow_lisp_closed_program_frontend.py:125` for the accessor).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_workflow_lisp_agent_constructor.py -q`
Expected: FAIL — unknown head `agent` (`macro_head_unknown` or similar), not `agent_target_dsl_unsupported`.

- [ ] **Step 3: Implement the form, expression and typing**

```python
# orchestrator/workflow_lisp/form_registry.py — new entry after "provider-result"
    _spec(
        "agent",
        kind=FormKind.CORE_EFFECT,
        owner_module="expressions",
        introduced_in="workflow_lisp_agent_sessions",
        remove_by=None,
        macro_bindable=False,
        admitted_top_level=False,
        elaboration_route="agent",
        feature_tags=("agent_sessions",),
        rationale="Run-local agent allocation elaborates through one fixed compiler path.",
        min_target_dsl_version="2.38",
    ),
```

```python
# orchestrator/workflow_lisp/expressions.py (dataclass only; the elaborator lives in agent_forms.py)
@dataclass(frozen=True)
class AgentExpr:
    """One run-local agent allocation over a statically resolved provider extern."""

    provider: "ExprNode"
    span: SourceSpan
    form_path: tuple[str, ...]
    expansion_stack: ExpansionStack = ()
    model: "ExprNode | None" = field(default=None, metadata={"json_omit_if_none": True})
    effort: "ExprNode | None" = field(default=None, metadata={"json_omit_if_none": True})
```

```python
# orchestrator/workflow_lisp/agent_forms.py
"""Elaboration of the target-gated `agent` constructor."""
from __future__ import annotations

from .expressions import AgentExpr, SyntaxKeyword, _elaborate, _keyword_sections, _raise_error
from .syntax import target_dsl_supports_agent_sessions


def _elaborate_agent(datum, *, form_path, bound_names, procedure_names, session_state) -> AgentExpr:
    if not target_dsl_supports_agent_sessions(session_state.target_dsl_version or ""):
        _raise_error("`agent` requires target DSL 2.38", code="agent_target_dsl_unsupported",
                     span=datum.span, form_path=form_path, expansion_stack=datum.expansion_stack)
    if len(datum.items) < 2:
        _raise_error("`agent` requires a provider extern", code="agent_provider_invalid",
                     span=datum.span, form_path=form_path, expansion_stack=datum.expansion_stack)
    provider = _elaborate(datum.items[1], form_path=form_path, bound_names=bound_names,
                          procedure_names=procedure_names, session_state=session_state)
    sections = _keyword_sections(datum.items[2:], form_path=form_path, label="`agent`")
    invalid = next((name for name in sections if name not in {":model", ":effort"}), None)
    if invalid is not None:
        keyword_node = next(item for item in datum.items[2::2]
                            if isinstance(item, SyntaxKeyword) and item.value == invalid)
        _raise_error(f"`agent` does not accept keyword `{invalid}`", code="agent_keyword_invalid",
                     span=keyword_node.span, form_path=form_path, expansion_stack=keyword_node.expansion_stack)
    policy = {name: _elaborate(sections[name], form_path=form_path, bound_names=bound_names,
                               procedure_names=procedure_names, session_state=session_state)
              for name in (":model", ":effort") if name in sections}
    return AgentExpr(provider=provider, span=datum.span, form_path=form_path,
                     expansion_stack=datum.expansion_stack, model=policy.get(":model"), effort=policy.get(":effort"))
```

Add `"agent": _elaborate_agent` to the route table at `expressions.py:1844` with a local import (`from .agent_forms import _elaborate_agent`) to avoid an import cycle.

```python
# orchestrator/workflow_lisp/typecheck_agents.py
"""Typing of `agent` allocations and conservative provider-origin propagation."""
from __future__ import annotations

from .effects import UsesProviderEffect, effect_summary_from_direct, merge_effect_summaries
from .expressions import AgentExpr, FieldAccessExpr, LiteralExpr, NameExpr
from .type_env import PrimitiveTypeRef
from .typecheck_effects import _extern_operand_name, raise_error, typecheck_expected_extern_operand

AGENT_TYPE = PrimitiveTypeRef(name="Agent")


def typecheck_agent_expr(expr: AgentExpr, *, context, recurse, typed_factory):
    from .workflows import ProviderExtern

    typed_provider = typecheck_expected_extern_operand(expr.provider, expected_primitive="Provider",
                                                       context=context, recurse=recurse, typed_factory=typed_factory)
    name = _extern_operand_name(expr.provider)
    binding = None if name is None or context.extern_environment is None \
        else context.extern_environment.bindings_by_name.get(name)
    if typed_provider.type_ref != PrimitiveTypeRef(name="Provider") or not isinstance(binding, ProviderExtern):
        raise_error("`agent` requires a compiler-known provider extern", code="agent_provider_invalid",
                    span=expr.provider.span, form_path=expr.provider.form_path,
                    expansion_stack=expr.provider.expansion_stack)
    summaries = []
    for field_name, policy_expr in (("model", expr.model), ("effort", expr.effort)):
        if policy_expr is None:
            continue
        typed_policy = recurse(policy_expr)
        if typed_policy.type_ref != PrimitiveTypeRef(name="String"):
            raise_error(f"`agent :{field_name}` must have type `String`", code=f"agent_{field_name}_type_invalid",
                        span=policy_expr.span, form_path=policy_expr.form_path, expansion_stack=policy_expr.expansion_stack)
        if not isinstance(policy_expr, (LiteralExpr, NameExpr, FieldAccessExpr)) or typed_policy.effect_summary.direct_effects \
                or typed_policy.effect_summary.transitive_effects:
            raise_error(f"`agent :{field_name}` must use an inline-lowerable String operand",
                        code="agent_policy_operand_not_inline_lowerable", span=policy_expr.span,
                        form_path=policy_expr.form_path, expansion_stack=policy_expr.expansion_stack)
        summaries.append(typed_policy.effect_summary)
    return typed_factory(expr=expr, type_ref=AGENT_TYPE, effect=merge_effect_summaries(
        *summaries, effect_summary_from_direct(direct_effects=(UsesProviderEffect(subject=tuple(name.split("."))),))))


def record_agent_origin(context, name: str, value_expr, typed_value) -> None:
    """Remember the exact origin set of a `let*`-bound Agent when it is statically visible."""
    if typed_value.type_ref != AGENT_TYPE:
        return
    if isinstance(value_expr, AgentExpr):
        origins = frozenset({_extern_operand_name(value_expr.provider)})
    elif isinstance(value_expr, NameExpr) and value_expr.name in context.agent_origins:
        origins = context.agent_origins[value_expr.name]
    else:
        origins = all_provider_externs(context)
    context.agent_origins[name] = origins


def agent_origins(expr, context) -> frozenset[str]:
    """Origins of an Agent-typed operand: exact when bound by a visible `let*`, else every extern."""
    if isinstance(expr, NameExpr) and expr.name in context.agent_origins:
        return context.agent_origins[expr.name]
    return all_provider_externs(context)


def all_provider_externs(context) -> frozenset[str]:
    from .workflows import ProviderExtern

    if context.extern_environment is None:
        return frozenset()
    return frozenset(name for name, binding in context.extern_environment.bindings_by_name.items()
                     if isinstance(binding, ProviderExtern))
```

Wire it: add `agent_origins: dict[str, frozenset[str]] = field(default_factory=dict)` to the typecheck context dataclass that `typecheck_dispatch.py` passes as `context` (the class whose instances carry `value_env`, `type_env` and `extern_environment`; it is constructed once per definition body, so the dict is per body); call `record_agent_origin(context, binding.name, binding.value, typed_binding)` in the `let*` binding loop; dispatch `if type(expr) is AgentExpr: return typecheck_agent_expr(...)` next to `ProviderResultExpr` at `:1206`. `type_env.prelude_type_names_for_target`: `if target_dsl_supports_agent_sessions(target_dsl_version): names = names | frozenset({"Agent"})`, with `Agent` resolving to `PrimitiveTypeRef(name="Agent")` like the other prelude primitives. `expression_traversal.py:293`: yield `expr.provider`, `expr.model`, `expr.effort` for `AgentExpr`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_workflow_lisp_agent_constructor.py tests/test_workflow_lisp_target_238.py -q`
Expected: PASS (7 + 5 items).

- [ ] **Step 5: Commit**

```bash
git add orchestrator/workflow_lisp/agent_forms.py orchestrator/workflow_lisp/typecheck_agents.py tests/test_workflow_lisp_agent_constructor.py
git commit -m "feat: admit the agent constructor and opaque Agent type at target 2.38" -- orchestrator/workflow_lisp/form_registry.py orchestrator/workflow_lisp/agent_forms.py orchestrator/workflow_lisp/expressions.py orchestrator/workflow_lisp/type_env.py orchestrator/workflow_lisp/typecheck_agents.py orchestrator/workflow_lisp/typecheck_dispatch.py orchestrator/workflow_lisp/expression_traversal.py orchestrator/workflow_lisp/procedure_specialization.py orchestrator/workflow_lisp/closed/command_templates.py orchestrator/workflow_lisp/diagnostics.py tests/test_workflow_lisp_agent_constructor.py
```

---

### Task 3: `provider-result` on an `Agent`, escape checks, closed `agent`/`agent_turn` nodes and the §8.8 exception

**Files:**
- Modify: `orchestrator/workflow_lisp/typecheck_effects.py:945-998` (branch on `typed_provider.type_ref == PrimitiveTypeRef("Agent")`; delegate to `typecheck_agents.check_agent_turn_options`)
- Modify: `orchestrator/workflow_lisp/typecheck_agents.py` (add `check_agent_turn_options`)
- Modify (escape checks, add `"Agent"` to each `{"Json","Provider","Prompt"}` / `{"Provider","Prompt"}` set, one token each): `orchestrator/workflow_lisp/contracts.py:1430,1840`, `orchestrator/workflow_lisp/workflows.py:601`, `orchestrator/workflow_lisp/loop_state.py:1152`, `orchestrator/workflow_lisp/loops.py:130`, `orchestrator/workflow_lisp/typecheck_resource_view.py:50`, `orchestrator/workflow/type_descriptor.py:14-20` (`_NONTRANSPORTABLE_PRIMITIVES` and `COMPILER_PRIMITIVE_TYPE_NAMES` gain `"Agent"`), `orchestrator/workflow_lisp/parallel_map.py` (one call to `typecheck_agents.check_parallel_body(expr, context, value_env)` raising `parallel_agent_boundary`), `orchestrator/workflow_lisp/typecheck_run_ref.py:706` (`_require_transportable` already refuses via `is_transportable_result_type`; add a test), `orchestrator/workflow_lisp/procedure_refs.py` capture admission (refuse Agent captures with `let_proc_capture_agent_forbidden`), `orchestrator/workflow_lisp/typecheck_effects.py` provider `:inputs` loop (`:1150-1160`) and `typecheck_commands.py` argv/`:inputs` operands (one `require_no_agent` call each), `orchestrator/workflow_lisp/prompts.py` fill typing (one `require_no_agent` call)
- Modify: `orchestrator/workflow/pure_expr.py:2313` (one line in `_coerce_value`: `if name == "Agent": return coerce_agent_value(value, context)`), `:1675-1690` (`print` and `=`/`!=` refuse an `Agent` operand with `pure_expr_operand_type_mismatch`: one `_reject_agent(arg_types, operator)` call)
- Create: `orchestrator/workflow/agent_value.py` (`AGENT_VALUE_KEYS`, `coerce_agent_value(value, context) -> dict`, `_reject_agent(arg_types, operator)`)
- Create: `orchestrator/contracts/closed_program/node_walk.py` (move `_ast_nodes`, `_bound_nodes`, `_value_nodes`, `_arm_root_values`, `_effect_value_children`, `_value_children` out of `sites.py:198-293,535-554`; `sites.py` re-imports them so every existing `from ...sites import _effect_value_children` keeps working; `sites.py` 554 → about 440)
- Create: `orchestrator/contracts/closed_program/check_agents.py` (`check_agent_node(checker, node, env, ...)`, `check_agent_turn_node(checker, ...)`, `check_agent_configuration(checker, node, scope, owner)`; `check.py` gains three dispatch lines)
- Create: `orchestrator/workflow_lisp/closed/agent_effects.py` (`_translate_agent`, `_translate_agent_turn`; `closed/effects.py` 468 gains two dispatch lines and the `_provider_effect_core` extraction, staying under 500)
- Modify: `orchestrator/workflow_lisp/wcc/elaborate.py:6490-6530` (agent-turn `WccPerform`), `:6538` (an `AgentExpr` branch beside `RequestInputExpr` building the `agent` perform), `:5693,7526` (effect-kind classification branches gain `AgentExpr`), tuples `:2214,2877,4594,7006` (each `isinstance(..., (…, RequestInputExpr, …))` tuple gains `AgentExpr`)
- Modify: `orchestrator/workflow_lisp/closed/effects.py:109-138` (two dispatch lines), `:247-375` (extract `_provider_effect_core`)
- Modify: `orchestrator/contracts/closed_program/check.py:111-115` (perform keys `agent`, `origins`), `:567-601` (`_effect_children` delegates to `node_walk._effect_value_children` for the two classes), `:891-927` and `:4397-4546` (one dispatch line each into `check_agents`), `:3150-3157,3333-3356` (`_bound` returns a third flag; `agent_origins` threaded like `provider_origins`)
- Modify: `orchestrator/contracts/closed_program/sites.py` (imports from `node_walk`; no new logic)
- Modify: `tests/workflow_lisp_closed_program_corpus.py` only if a corpus entry changes (none in this task)
- Create: `tests/test_workflow_lisp_agent_turn_admission.py`, `tests/fixtures/workflow_lisp/agent_sessions/{carriage.orc,escape_*.orc}` as written by the test module itself (inline sources; no fixture files needed)
- Modify (spec amendment, frontend §8.8): `docs/design/workflow_lisp_frontend_specification.md:1467-1471`

**Interfaces:**
- Consumes: Task 2 `AgentExpr`, `agent_origins`.
- Produces: closed node shapes and operand order in the interface table; `check.py` validation; `coerce_pure_value` acceptance of the runtime `Agent` value.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_workflow_lisp_agent_turn_admission.py
"""Compile-only proofs: carriage, escape and provider-origin analysis for agent turns at 2.38."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.contracts.closed_program.sites import _effect_value_children
from orchestrator.workflow.pure_expr import PureExprEvaluationError, coerce_pure_value
from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.effects import UsesProviderEffect

HEADER = '(workflow-lisp (:language "0.1") (:target-dsl "2.38") (defmodule main) (export run)\n' \
         '(defrecord Note (text String)) (defrecord Team (lead Agent) (label String))\n' \
         '(defprompt ask (:fills (task :text)) -> Note "Task: {task}")\n'
TWO_AGENTS = HEADER + '''(defproc turn ((who Agent) (task String)) -> Note
    (provider-result who :prompt (ask :task task) :timeout-sec 60))
  (defworkflow run ((task String) (pick Bool)) -> Note
    (let* ((designer (agent providers.claude :model "m1" :effort "high"))
           (reviewer (agent providers.codex :model "m2" :effort "high"))
           (team (Team :lead designer :label "d"))
           (chosen (if pick designer reviewer))
           (a1 (provider-result designer :prompt (ask :task task)))
           (b1 (provider-result reviewer :prompt (ask :task a1.text)))
           (a2 (turn team.lead a1.text))
           (c (provider-result chosen :prompt (ask :task b1.text))))
      c)))'''


def _request(root: Path, source: str) -> FrontendBuildRequest:
    (root / "main.orc").write_text(source, encoding="utf-8")
    (root / "providers.json").write_text(json.dumps({"providers.claude": "claude_unrestricted_workspace", "providers.codex": "codex"}))
    return FrontendBuildRequest(source_path=root / "main.orc", source_roots=(root,), workspace_root=root,
                                provider_externs_path=root / "providers.json")


def _performs(tree):
    from orchestrator.contracts.closed_program.sites import _ast_nodes
    bodies = [tree["body"], *(d["body"] for d in tree["definitions"].values())]
    return [n for body in bodies for n in _ast_nodes(body) if n.get("k") == "perform"]


def test_two_agents_compile_to_allocations_and_origin_bound_turns(tmp_path: Path) -> None:
    bundle = build_closed_program_bundle(_request(tmp_path, TWO_AGENTS))
    performs = _performs(bundle.program.tree)
    allocations = [n for n in performs if n["class"] == "agent"]
    turns = [n for n in performs if n["class"] == "agent_turn"]
    assert [n["provider"] for n in allocations] == ["claude_unrestricted_workspace", "codex"]
    assert all(n["result"] == {"kind": "primitive", "name": "Agent"} and n["repeat"] == "rerun" for n in allocations)
    assert len(turns) == 4
    by_origin = sorted(tuple(n["origins"]) for n in turns)
    # a1 exact, b1 exact, helper turn and branch-selected turn conservative (both externs)
    assert by_origin == [("claude_unrestricted_workspace",), ("claude_unrestricted_workspace", "codex"),
                         ("claude_unrestricted_workspace", "codex"), ("codex",)]
    for turn in turns:
        children = _effect_value_children(dict(turn))
        assert children[0] is turn["agent"]
        assert "provider" not in turn and set(turn["policy"]) <= {"timeout_sec"}
    assert bundle.sites == 7


def test_helper_turn_carries_uses_provider_for_every_possible_origin(tmp_path: Path) -> None:
    from orchestrator.workflow_lisp.build import build_frontend
    built = build_frontend(_request(tmp_path, TWO_AGENTS))
    helper = built.typed_program.procedures["turn"]
    subjects = {e.subject for e in helper.effect_summary.direct_effects if isinstance(e, UsesProviderEffect)}
    assert subjects == {("providers", "claude"), ("providers", "codex")}


@pytest.mark.parametrize("tail, code", [
    ('(provider-result designer :prompt (ask :task task) :model "x")', "agent_turn_policy_override_forbidden"),
    ('(provider-result designer :prompt (ask :task task) :effort "x")', "agent_turn_policy_override_forbidden"),
    ('(provider-result designer :prompt (ask :task task) :capture-context :portable)', "agent_turn_option_unsupported"),
    ('(provider-result designer :prompt (ask :task task) :session-artifact s)', "agent_turn_option_unsupported"),
    ('(provider-result designer :prompt (ask :task task) :delivery :phased)', "agent_turn_option_unsupported"),
])
def test_agent_turn_rejects_overrides_and_unbounded_options(tmp_path: Path, tail: str, code: str) -> None:
    source = HEADER + f'(defworkflow run ((task String)) -> Note (let* ((designer (agent providers.claude))) {tail})))'
    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_closed_program_bundle(_request(tmp_path, source))
    assert excinfo.value.diagnostics[0].code == code


D = '(defworkflow run ((task String)) -> Note (let* ((d (agent providers.claude))) '


@pytest.mark.parametrize("source, code", [
    # provider data: :inputs, prompt :value fill, nested record carrying an Agent
    (HEADER + D + '(provider-result providers.codex :prompt (ask :task task) :inputs (d) :returns Note)))', "agent_transport_forbidden"),
    (HEADER + '(defprompt who (:fills (lead :value Team)) -> Note "x {lead}") ' + D + '(provider-result providers.codex :prompt (who :lead (Team :lead d :label "l")))))', "agent_transport_forbidden"),
    # command data: argv and typed inputs
    (HEADER + D + '(command-result tool :argv ("python" "t.py" d) :returns String) (Note :text "x")))', "agent_transport_forbidden"),
    (HEADER + D + '(command-result tool :argv ("python" "t.py") :inputs ((who d)) :returns String) (Note :text "x")))', "agent_transport_forbidden"),
    # workflow signature: parameter, return, nested record return, call signature of a child workflow
    (HEADER + '(defworkflow run ((who Agent)) -> Note (provider-result who :prompt (ask :task "t")))', "workflow_boundary_type_invalid"),
    (HEADER + '(defworkflow run ((task String)) -> Agent (agent providers.claude))', "workflow_boundary_type_invalid"),
    (HEADER + '(defworkflow run ((task String)) -> Team (Team :lead (agent providers.claude) :label "l"))', "workflow_boundary_type_invalid"),
    (HEADER + '(defworkflow child ((who Agent)) -> Note (provider-result who :prompt (ask :task "t"))) ' + D + '(call child :who d)))', "workflow_boundary_type_invalid"),
    # run-ref input and result
    (HEADER + D + '(run-ref :program (:path "child.orc") :inputs ((who d)) :returns Note)))', "workflow_boundary_type_invalid"),
    (HEADER + D + '(run-ref :program (:path "child.orc") :inputs ((t task)) :returns Team)))', "workflow_boundary_type_invalid"),
    # loop state
    (HEADER + D + '(loop/recur :max 2 (loop-state (who Agent d)) (done (Note :text "x")))))', "loop_state_runtime_transport_forbidden"),
    # parallel worker: free Agent used in the body, Agent constructed in the body, Agent in the result
    (HEADER + '(defworkflow run ((items List[String])) -> List[Note] (let* ((d (agent providers.claude))) '
              '(par-map (item items) :max 2 :workspace "." (provider-result d :prompt (ask :task item)))))', "parallel_agent_boundary"),
    (HEADER + '(defworkflow run ((items List[String])) -> List[Note] (par-map (item items) :max 2 :workspace "." '
              '(let* ((w (agent providers.claude))) (provider-result w :prompt (ask :task item)))))', "parallel_agent_boundary"),
    (HEADER + '(defworkflow run ((items List[String])) -> List[Team] (par-map (item items) :max 2 :workspace "." (Team :lead (agent providers.claude) :label item)))', "parallel_agent_boundary"),
    # closure capture
    (HEADER + D + '(let-proc ((f ((t String)) -> Note (provider-result d :prompt (ask :task t)))) (call f task))))', "let_proc_capture_agent_forbidden"),
    # pure handling: equality, print
    (HEADER + D + '(if (= d d) (Note :text "a") (Note :text "b"))))', "pure_expr_operand_type_mismatch"),
    (HEADER + D + '(let* ((p (print d))) (Note :text "a"))))', "pure_expr_operand_type_mismatch"),
])
def test_agent_cannot_escape_its_run_local_positions(tmp_path: Path, source: str, code: str) -> None:
    (tmp_path / "t.py").write_text("")
    (tmp_path / "commands.json").write_text(json.dumps({"tool": {"stable_command": ["python", "t.py"], "closure": ["t.py"]}}))
    (tmp_path / "child.orc").write_text(HEADER.replace("(export run)", "(export run)") + '(defworkflow run ((who String) (t String)) -> Note (Note :text t)))')
    request = _request(tmp_path, source)
    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_closed_program_bundle(request.__class__(**{**request.__dict__, "command_boundaries_path": tmp_path / "commands.json"}))
    assert excinfo.value.diagnostics[0].code == code


def test_runtime_agent_value_shape_is_exact() -> None:
    desc = {"kind": "primitive", "name": "Agent"}
    good = {"run_id": "r", "identity": "workflow:main::run / designer", "provider": "codex", "policy": {"model": "m"},
            "config_digest": "sha256:" + "0" * 64}
    assert coerce_pure_value(good, desc) == good
    for bad in ({"run_id": "r"}, "agent:x", {**good, "extra": 1}, {**good, "policy": {"model": 1}}, {**good, "config_digest": "x"}):
        with pytest.raises(PureExprEvaluationError):
            coerce_pure_value(bad, desc)
```

Codes are the real ones: `workflow_boundary_type_invalid` (`contracts.py:1432`, `workflows.py:3027`, `typecheck_run_ref.py:715`), `loop_state_runtime_transport_forbidden` (`loop_state.py:1037`), `pure_expr_operand_type_mismatch` (`pure_expr.py:1695`); `agent_transport_forbidden`, `parallel_agent_boundary` and `let_proc_capture_agent_forbidden` are introduced by this task. The `run-ref` rows use a `child.orc` the test writes; run-ref `:returns Team` fails at `_require_transportable` because `is_transportable_result_type` sees the `Agent` field through `_NONTRANSPORTABLE_PRIMITIVES`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_workflow_lisp_agent_turn_admission.py -q`
Expected: FAIL — `provider_result_provider_invalid` for the first test (Agent operand not accepted) and `pure_expr_operand_type_mismatch` for the value-shape test.

- [ ] **Step 3: Implement typing of agent turns**

In `typecheck_effects.py:945-998`, after `typed_provider` is computed:

```python
    if typed_provider.type_ref == PrimitiveTypeRef(name="Agent"):
        from .typecheck_agents import check_agent_turn_options, agent_origins
        check_agent_turn_options(expr, context=context)
        origins = agent_origins(expr.provider, context)
        provider_extern_name = None
        provider_binding = None
    else:
        ...existing extern checks unchanged...
```

and at the effect summary (`:1166-1169`) emit one `UsesProviderEffect(subject=tuple(name.split(".")))` per origin for agent turns. `check_agent_turn_options`:

```python
def check_agent_turn_options(expr, *, context) -> None:
    for field_name, value in (("model", expr.model), ("effort", expr.effort)):
        if value is not None:
            raise_error(f"an agent turn cannot override `:{field_name}`; change the `agent` constructor",
                        code="agent_turn_policy_override_forbidden", span=value.span,
                        form_path=value.form_path, expansion_stack=value.expansion_stack)
    unsupported = [name for name, value in (("session-artifact", expr.session_artifact),
        ("context", expr.context_expr), ("capture-context", expr.capture_context),
        ("materialization-attempts", expr.materialization_attempts)) if value is not None]
    if expr.delivery is not None and getattr(expr.delivery, "value", None) == "phased":
        unsupported.append("delivery :phased")
    if unsupported:
        raise_error(f"agent turns do not accept `:{unsupported[0]}`", code="agent_turn_option_unsupported",
                    span=expr.span, form_path=expr.form_path, expansion_stack=expr.expansion_stack)
```

Record origins on the typed expression so WCC can carry them: set `typed_factory(..., metadata={"agent_origins": tuple(sorted(origins))})` if the factory supports metadata; otherwise return a `replace(expr, agent_origins=...)` by adding an optional `agent_origins: tuple[str, ...] | None = None` field to `ProviderResultExpr` (json-omitted when None). Choose the second; it is explicit and survives specialization.

Escape checks: add `"Agent"` to each set listed in Files. `typecheck_agents.require_no_agent(type_ref, *, where, span, form_path, expansion_stack)` walks the type (records, unions, optional, list, map) and raises `agent_transport_forbidden` with `where` naming the position; it is called for every provider `:inputs` operand and prompt fill (`typecheck_effects.py:1150-1160`, `prompts.py` fill typing) and every command argv/`:inputs` operand (`typecheck_commands.py`). `typecheck_agents.check_parallel_body(expr, context, value_env)` raises `parallel_agent_boundary` when the item type, the workspace type or the result type contains `Agent` (`require_no_agent` walk), when any free `NameExpr` of the body resolves to `Agent` in `value_env`, or when the body contains an `AgentExpr` or a `ProviderResultExpr` whose first operand types as `Agent` (walk with `expression_traversal`). `procedure_refs.py`: an `Agent`-typed capture raises `let_proc_capture_agent_forbidden`.

```python
# orchestrator/workflow/agent_value.py
"""Runtime shape of the opaque `Agent` reference descriptor (frontend §8.8 versioned exception)."""
from __future__ import annotations

import re

AGENT_VALUE_KEYS = frozenset({"run_id", "identity", "provider", "policy", "config_digest"})
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


def coerce_agent_value(value, context: str) -> dict:
    from orchestrator.workflow.pure_expr import _raise
    ok = (isinstance(value, dict) and set(value) == AGENT_VALUE_KEYS
          and all(isinstance(value[k], str) and value[k] for k in ("run_id", "identity", "provider"))
          and isinstance(value["policy"], dict)
          and all(isinstance(k, str) and isinstance(v, str) for k, v in value["policy"].items())
          and isinstance(value["config_digest"], str) and _DIGEST.fullmatch(value["config_digest"]))
    if not ok:
        _raise("pure_expr_operand_type_mismatch", f"{context} must be an Agent reference descriptor")
    return {**value, "policy": dict(value["policy"])}


def _reject_agent(arg_types, operator: str) -> None:
    from orchestrator.workflow.pure_expr import _raise
    if any(isinstance(t, dict) and t.get("kind") == "primitive" and t.get("name") == "Agent" for t in arg_types):
        _raise("pure_expr_operand_type_mismatch", f"operator `{operator}` cannot take an Agent operand")
```

`pure_expr._coerce_value` primitive branch gains one line before the generic string fallback: `if name == "Agent": return coerce_agent_value(value, context)`; the `print` and `=`/`!=` type rules (`pure_expr.py:1675-1690`) call `_reject_agent(arg_types, operator)` first.

- [ ] **Step 4: Implement WCC and closed translation**

`wcc/elaborate.py`: for `AgentExpr` build `WccPerform(perform_kind="agent", target_name=_require_name_expr(expr.provider), prompt_name=None, positional_args=(), keyword_args=tuple((k, _elaborate_atomic_value(v, ...)) for k, v in (("model", expr.model), ("effort", expr.effort)) if v is not None), returns_type_name="Agent", operation_payload=None)` with `role="perform:agent"`. For a `ProviderResultExpr` whose `agent_origins` is not None build `perform_kind="agent_turn"`, `target_name="agent"`, `positional_args=(agent_value, *inputs)` where `agent_value = _elaborate_atomic_value(expr.provider, ...)`, and `operation_payload["agent_origins"] = expr.agent_origins`.

`closed/effects.py`:

```python
def translate_perform(builder, perform, d, env):
    if perform.perform_kind == "provider_result":
        return _translate_provider_result(builder, perform, d, env)
    if perform.perform_kind == "agent":
        return _translate_agent(builder, perform, d, env)
    if perform.perform_kind == "agent_turn":
        return _translate_agent_turn(builder, perform, d, env)
    ...


def _translate_agent(builder, perform, d, env):
    owner_config = builder.configuration_for(d.source_program, d.owner)
    row = owner_config["providers"].get(perform.target_name)
    if not isinstance(row, Mapping) or not isinstance(row.get("provider_id"), str):
        raise ValueError(f"provider extern {perform.target_name!r} is missing from its owner")
    node = {"k": "perform", "class": "agent", "result": {"kind": "primitive", "name": "Agent"}, "repeat": "rerun",
            "provider": row["provider_id"],
            "policy": {name: builder.value(value, d, env) for name, value in perform.keyword_args}}
    node.update(builder.provenance(perform.metadata))
    return node


def _translate_agent_turn(builder, perform, d, env):
    owner_config = builder.configuration_for(d.source_program, d.owner)
    origins = sorted({owner_config["providers"][name]["provider_id"] for name in perform.operation_payload["agent_origins"]})
    agent_value, *inputs = perform.positional_args
    core = _provider_effect_core(builder, perform, d, env, inputs)   # prompt, inputs, dependencies, policy, contract
    if set(core["policy"]) - {"timeout_sec"}:
        raise ValueError("agent turn policy must contain only timeout_sec")
    node = {"k": "perform", "class": "agent_turn", "result": builder.desc(perform.metadata.type_ref, d),
            "repeat": "rerun", "agent": builder.value(agent_value, d, env), "origins": origins, **core}
    node.update(builder.provenance(perform.metadata))
    builder.retain_generated_result_contract(node, perform, d)
    return node
```

`_provider_effect_core` is the existing body of `_translate_provider_result` from `prompt_application = ...` through `contract` (no `provider` key), parameterized by the positional inputs; `_translate_provider_result` calls it too.

`node_walk._effect_value_children` (moved from `sites.py`, re-exported there):

```python
    if kind == "agent":
        return [v for v in (node.get("policy") or {}).values() if isinstance(v, dict)]
    if kind == "agent_turn":
        children = [node["agent"], *(row[2] for row in node.get("inputs", []))]
        ...same fills/dependencies/policy extension as provider...
```

`check.py`: `_VALUE_KEYS["perform"]` gains `"agent"`, `"origins"`; `_effect_children` delegates to `node_walk._effect_value_children` for the two classes; `_check_effect_configurations` and `_check_effect_node` each gain one line `if effect_class in {"agent", "agent_turn"}: return check_agents.<fn>(self, ...)`. In `check_agents.py`: configuration — class `agent` checks `provider` like the provider branch, class `agent_turn` checks each origin is a configured `provider_id` and the prompt source like the provider branch; node — `agent` node keys exactly `{k,class,result,repeat,site,@,provider,policy}`, result must equal the Agent primitive, policy keys ⊆ `{model, effort}` inline String values; `agent_turn` keys exactly the provider set minus `provider` plus `{agent, origins}`, `origins` a non-empty sorted unique list of strings, `agent` value typed `{"kind":"primitive","name":"Agent"}`, policy keys ⊆ `{timeout_sec}`; when the `agent` value is `{"k":"name","n":X}` and `X` is in `agent_origins` (a frozenset of names bound by `let` to `agent` performs, tracked beside `provider_origins` at `:3150-3157`), require that perform's `provider` ∈ `origins` (`agent_origin_mismatch`). `_bound` returns `(result, kind == "provider", kind == "agent")`; thread the third element as `agent_origins` the same way `provider_origins` is threaded.

- [ ] **Step 5: Amend frontend §8.8 (design-spec-drafting: section named)**

`docs/design/workflow_lisp_frontend_specification.md` §8.8, paragraph at `:1467-1471`: after "Runtime state must not carry type parameters, procedure values, provider refs, prompt refs, or closure environments." add: "Versioned exception (target 2.38, [Agent Sessions](workflow_lisp_agent_sessions.md#authoring-and-composition)): runtime state may carry a runtime-owned `Agent` reference descriptor `{run_id, identity, provider, policy}` whose provider origins are fixed by checked source (the closed `agent_turn` node's `origins`). It admits no other provider ref, prompt ref, executable value or closure environment; `Agent` is non-transportable at every workflow, run-ref, provider, command, loop-state, parallel and closure-capture boundary."

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_workflow_lisp_agent_turn_admission.py tests/test_workflow_lisp_agent_constructor.py tests/test_workflow_lisp_closed_program_corpus.py tests/test_workflow_lisp_closed_program_check.py tests/test_workflow_lisp_closed_program_sites.py -q`
Expected: PASS; corpus counts unchanged (no 2.38 corpus entry yet). Then `wc -l orchestrator/workflow_lisp/closed/effects.py orchestrator/workflow_lisp/closed/agent_effects.py orchestrator/contracts/closed_program/sites.py orchestrator/contracts/closed_program/node_walk.py orchestrator/contracts/closed_program/check_agents.py orchestrator/workflow_lisp/typecheck_agents.py orchestrator/workflow/agent_value.py` — expected about 470, 120, 440, 120, 150, 180, 40; `check.py`, `expressions.py`, `pure_expr.py` and `typecheck_effects.py` grow by their dispatch lines only (<= 6 lines each, verified with `git diff --stat`).

- [ ] **Step 7: Commit**

```bash
git add tests/test_workflow_lisp_agent_turn_admission.py orchestrator/workflow/agent_value.py orchestrator/contracts/closed_program/node_walk.py orchestrator/contracts/closed_program/check_agents.py orchestrator/workflow_lisp/closed/agent_effects.py
git commit -m "feat: compile provider-result on an Agent into origin-bound agent_turn effects" -- orchestrator/workflow/agent_value.py orchestrator/contracts/closed_program/node_walk.py orchestrator/contracts/closed_program/check_agents.py orchestrator/workflow_lisp/closed/agent_effects.py orchestrator/workflow_lisp/typecheck_commands.py orchestrator/workflow_lisp/prompts.py orchestrator/workflow_lisp/typecheck_effects.py orchestrator/workflow_lisp/typecheck_agents.py orchestrator/workflow_lisp/expressions.py orchestrator/workflow_lisp/contracts.py orchestrator/workflow_lisp/workflows.py orchestrator/workflow_lisp/loop_state.py orchestrator/workflow_lisp/loops.py orchestrator/workflow_lisp/typecheck_resource_view.py orchestrator/workflow_lisp/parallel_map.py orchestrator/workflow_lisp/procedure_refs.py orchestrator/workflow/type_descriptor.py orchestrator/workflow/pure_expr.py orchestrator/workflow_lisp/wcc/elaborate.py orchestrator/workflow_lisp/closed/effects.py orchestrator/contracts/closed_program/check.py orchestrator/contracts/closed_program/sites.py docs/design/workflow_lisp_frontend_specification.md tests/test_workflow_lisp_agent_turn_admission.py
```

---

### Task 4: Claude session transport (metadata mode, accumulator, template)

**Files:**
- Modify: `orchestrator/providers/types.py:191-195` (`ProviderSessionMetadataMode.CLAUDE_STREAM_JSON_STDOUT = "claude_stream_json_stdout"`), `:541-545` (allowed `command_metadata_mode` set, if it enumerates modes)
- Create: `orchestrator/providers/session_transport_claude.py`
- Modify: `orchestrator/providers/session_transport.py:584-607` (`create_session_transport_accumulator` returns the Claude accumulator for the new mode; one `if` only)
- Modify: `orchestrator/providers/registry.py:194-214` (`claude_unrestricted_workspace` gains `session_support`)
- Create: `tests/test_provider_session_transport_claude.py`
- Modify (spec amendment): `specs/providers.md:32-36` (metadata modes list names `claude_stream_json_stdout`), `:256-260` (`claude_unrestricted_workspace` row gains its `session_support`), `:1027-1041` quick-reference row

**Interfaces:**
- Produces: `ClaudeStreamJsonAccumulator(*, assistant_text_callback=None)` implementing `SessionTransportAccumulator`; `finalize` metadata `{"session_id", "normalized_stdout", "event_count", "result_subtype": str | None, "is_error": bool}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_provider_session_transport_claude.py
"""`claude -p --output-format stream-json` is a structural session codec with a terminal result event."""
from __future__ import annotations

import json

import pytest

from orchestrator.providers.registry import ProviderRegistry
from orchestrator.providers.session_transport import create_session_transport_accumulator
from orchestrator.providers.types import ProviderSessionMetadataMode, ProviderSessionMode, ProviderSessionRequest

SID = "1930ae6b-5267-4eec-b1e1-b430dad86844"


def _events(*rows: dict) -> bytes:
    return b"".join(json.dumps(row).encode() + b"\n" for row in rows)


def _init(sid=SID):
    return {"type": "system", "subtype": "init", "session_id": sid, "model": "haiku"}


def _assistant(text, sid=SID):
    return {"type": "assistant", "session_id": sid, "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}


def _result(sid=SID, is_error=False):
    return {"type": "result", "subtype": "error" if is_error else "success", "is_error": is_error,
            "session_id": sid, "result": "done", "duration_ms": 5}


def test_mode_is_registered_and_selected_structurally() -> None:
    mode = ProviderSessionMetadataMode.CLAUDE_STREAM_JSON_STDOUT.value
    assert mode == "claude_stream_json_stdout"
    acc = create_session_transport_accumulator(mode)
    assert acc is not None and acc.event_count == 0


def test_finalize_binds_session_id_assistant_text_and_terminal() -> None:
    texts = []
    acc = create_session_transport_accumulator("claude_stream_json_stdout", assistant_text_callback=texts.append)
    acc.feed(_events(_init(), _assistant("hello "), _assistant("world")))
    snapshot = acc.snapshot()
    assert (snapshot.status, snapshot.session_ids, snapshot.terminal_seen) == ("unique", (SID,), False)
    acc.feed(_events(_result()))
    metadata, error = acc.finalize(expected_session_id=None, require_terminal=True)
    assert error is None
    assert metadata["session_id"] == SID and metadata["event_count"] == 4
    assert metadata["normalized_stdout"] == "hello world" and texts == ["hello ", "world"]
    assert (metadata["result_subtype"], metadata["is_error"]) == ("success", False)


def test_missing_result_event_is_an_error_not_a_session() -> None:
    acc = create_session_transport_accumulator("claude_stream_json_stdout")
    acc.feed(_events(_init(), _assistant("partial")))
    metadata, error = acc.finalize(expected_session_id=None, require_terminal=True)
    assert metadata is None and error["type"] == "provider_session_transport_error"
    assert "terminal" in error["message"]


def test_resume_must_match_requested_session_and_rejects_mixed_ids() -> None:
    acc = create_session_transport_accumulator("claude_stream_json_stdout")
    acc.feed(_events(_init(), _result()))
    _metadata, error = acc.finalize(expected_session_id="other", require_terminal=True)
    assert error is not None and error["context"]["observed_session_id"] == SID
    mixed = create_session_transport_accumulator("claude_stream_json_stdout")
    mixed.feed(_events(_init(), _init("22222222-2222-4222-8222-222222222222"), _result()))
    assert mixed.snapshot().status == "ambiguous"


def test_non_json_line_invalidates_without_raising() -> None:
    acc = create_session_transport_accumulator("claude_stream_json_stdout")
    acc.feed(b"not json\n")
    assert acc.snapshot().status == "invalid"


def test_claude_unrestricted_workspace_declares_session_support_without_changing_its_command() -> None:
    template = ProviderRegistry().get("claude_unrestricted_workspace")
    assert template.command == ["claude", "-p", "--model", "${model}", "--effort", "${effort}", "--permission-mode", "bypassPermissions"]
    support = template.session_support
    assert support.metadata_mode == "claude_stream_json_stdout" and support.turn_boundary_resume is False
    assert support.fresh_command[:4] == ["claude", "-p", "--output-format", "stream-json"] and "--verbose" in support.fresh_command
    assert support.resume_command.count("${SESSION_ID}") == 1 and "--resume" in support.resume_command
    assert "${PROMPT}" not in support.fresh_command + support.resume_command
    assert template.validate() == []
    assert ProviderRegistry().get("claude").session_support is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_provider_session_transport_claude.py -q`
Expected: FAIL — `AttributeError: CLAUDE_STREAM_JSON_STDOUT`.

- [ ] **Step 3: Implement the accumulator and template**

```python
# orchestrator/providers/session_transport_claude.py
"""Incremental codec for `claude -p --output-format stream-json --verbose` stdout."""
from __future__ import annotations

import copy
import json
import threading
from typing import Any, Callable, Mapping

from .session_transport import SessionIdentitySnapshot, _TRANSPORT_ERROR_TYPE, _freeze_snapshot_error

_TERMINAL_TYPE = "result"


class ClaudeStreamJsonAccumulator:
    """Bind one `session_id`, the assistant text and the terminal `result` event without altering stdout."""

    def __init__(self, *, assistant_text_callback: Callable[[str], None] | None = None) -> None:
        self._callback = assistant_text_callback
        self._buffer = bytearray()
        self._session_ids: set[str] = set()
        self._text_parts: list[str] = []
        self._terminal: dict[str, Any] | None = None
        self._event_count = 0
        self._line_number = 0
        self._invalid: dict[str, Any] | None = None
        self._finalized = False
        self._lock = threading.RLock()

    @property
    def event_count(self) -> int:
        with self._lock:
            return self._event_count

    @property
    def normalized_stdout(self) -> str:
        with self._lock:
            return "".join(self._text_parts)

    def feed(self, chunk: bytes) -> None:
        if not isinstance(chunk, bytes):
            raise TypeError("session transport chunks must be bytes")
        emitted: list[str] = []
        with self._lock:
            if self._finalized:
                raise RuntimeError("session transport accumulator is finalized")
            if self._invalid is not None or not chunk:
                return
            self._buffer.extend(chunk)
            while self._invalid is None and (offset := self._buffer.find(b"\n")) >= 0:
                line = bytes(self._buffer[:offset]); del self._buffer[: offset + 1]
                text = self._consume(line)
                if text is not None:
                    emitted.append(text)
        for text in emitted:
            if self._callback is not None:
                self._callback(text)

    def _consume(self, raw: bytes) -> str | None:
        if not raw.strip():
            return None
        self._line_number += 1
        try:
            event = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            self._invalid = self._error(f"stream-json line {self._line_number} is not JSON", {"error": str(exc)})
            return None
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            self._invalid = self._error(f"stream-json line {self._line_number} is not an event", {})
            return None
        self._event_count += 1
        sid = event.get("session_id")
        if isinstance(sid, str) and sid:
            self._session_ids.add(sid)
        if event["type"] == _TERMINAL_TYPE:
            self._terminal = event
            return None
        if event["type"] == "assistant":
            content = (event.get("message") or {}).get("content")
            text = "".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text") \
                if isinstance(content, list) else ""
            if text:
                self._text_parts.append(text)
                return text
        return None

    def snapshot(self) -> SessionIdentitySnapshot:
        with self._lock:
            ids = tuple(sorted(self._session_ids))
            if self._invalid is not None:
                return SessionIdentitySnapshot("invalid", ids, self._terminal is not None, _freeze_snapshot_error(self._invalid))
            if len(ids) > 1:
                return SessionIdentitySnapshot("ambiguous", ids, self._terminal is not None,
                                               _freeze_snapshot_error(self._error("stream-json exposed conflicting session ids", {"session_ids": list(ids)})))
            return SessionIdentitySnapshot("unique" if ids else "missing", ids, self._terminal is not None, None)

    def finalize(self, *, expected_session_id: str | None, require_terminal: bool):
        with self._lock:
            if not self._finalized:
                self._finalized = True
                tail = bytes(self._buffer); self._buffer.clear()
                if self._invalid is None and tail.strip():
                    text = self._consume(tail)
                    if text is not None and self._callback is not None:
                        self._callback(text)
        snapshot = self.snapshot()
        if snapshot.status in {"invalid", "ambiguous"}:
            return None, copy.deepcopy(dict(snapshot.error))
        if require_terminal and self._terminal is None:
            return None, self._error("Session transport is missing a terminal result event", {"events": self.event_count})
        if snapshot.status == "missing":
            return None, self._error("Session transport did not expose a session_id", {"events": self.event_count})
        session_id = snapshot.session_ids[0]
        if expected_session_id is not None and session_id != expected_session_id:
            return None, self._error("Session transport did not match the requested session_id",
                                     {"expected_session_id": expected_session_id, "observed_session_id": session_id})
        terminal = self._terminal or {}
        return {"session_id": session_id, "normalized_stdout": self.normalized_stdout, "event_count": self.event_count,
                "result_subtype": terminal.get("subtype"), "is_error": bool(terminal.get("is_error", False))}, None

    @staticmethod
    def _error(message: str, context: Mapping[str, Any]) -> dict[str, Any]:
        return {"type": _TRANSPORT_ERROR_TYPE, "message": message, "context": dict(context)}
```

`session_transport.create_session_transport_accumulator`: add before the OMP branch

```python
    if metadata_mode == ProviderSessionMetadataMode.CLAUDE_STREAM_JSON_STDOUT.value:
        from .session_transport_claude import ClaudeStreamJsonAccumulator
        return ClaudeStreamJsonAccumulator(assistant_text_callback=assistant_text_callback)
```

`registry.py` `claude_unrestricted_workspace`: add

```python
                session_support=ProviderSessionSupport(
                    metadata_mode=ProviderSessionMetadataMode.CLAUDE_STREAM_JSON_STDOUT.value,
                    fresh_command=["claude", "-p", "--output-format", "stream-json", "--verbose",
                                   "--model", "${model}", "--effort", "${effort}", "--permission-mode", "bypassPermissions"],
                    resume_command=["claude", "-p", "--resume", "${SESSION_ID}", "--output-format", "stream-json", "--verbose",
                                    "--model", "${model}", "--effort", "${effort}", "--permission-mode", "bypassPermissions"],
                    turn_boundary_resume=False,
                ),
```

(stdin input mode is unchanged; `claude -p` with no positional prompt reads stdin.)

- [ ] **Step 4: Amend `specs/providers.md` (sections named)**

"Provider templates" bullet at `:32-36`: `metadata_mode` ∈ `codex_exec_jsonl_stdout`, `omp_json_stdout`, `claude_stream_json_stdout` (the last binds `session_id` from the `system/init` and later events, assistant text from `assistant` events and completion from the terminal `result` event; it has no resume-boundary observation, so `turn_boundary_resume` stays `false`). Built-in template paragraph at `:256-260`: `claude_unrestricted_workspace` additionally declares `session_support` with the fresh/resume commands above; ordinary calls keep `command`. Quick-reference table `:1027-1041`: add a `claude_unrestricted_workspace` row with input mode `stdin` and the note "session-capable (`claude_stream_json_stdout`); used by agent sessions at 2.38".

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_provider_session_transport_claude.py tests/test_provider_registry.py tests/test_provider_templates.py -q` (use the registry/template test modules that exist under `ls tests | grep -i provider_`; at minimum run `pytest tests -q -k "registry and provider" -x`).
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/providers/session_transport_claude.py tests/test_provider_session_transport_claude.py
git commit -m "feat: add the Claude stream-json session codec and claude_unrestricted_workspace session_support" -- orchestrator/providers/types.py orchestrator/providers/session_transport.py orchestrator/providers/session_transport_claude.py orchestrator/providers/registry.py specs/providers.md tests/test_provider_session_transport_claude.py
```

---

### Task 5: Native-store adapters and Codex position evidence

**Files:**
- Create: `orchestrator/providers/native_store.py` (lift `_read_jsonl`, `_identity`, `_codex_session`, `_codex_events`, the Codex lifecycle walk, and the Claude lineage/uniqueness/padding checks `_claude_tool_result`, `_claude_descendants`, `_claude_structured_result`, `_claude_resume_padding` from `scripts/experiments/native_session_cli_evidence.py:59-130,131-258,259-495` verbatim, adapted only from nonce matching to prompt-marker matching; the experiment script is left untouched)
- Modify: `orchestrator/providers/session_transport.py:322-460` (`CodexExecJsonlAccumulator` counts `turn.completed` events into `finalize` metadata `turns_completed`)
- Create: `tests/test_provider_native_store.py`
- Modify (spec amendment): `specs/providers.md` new subsection "Native session stores (target 2.38 agent sessions)" after the session-support bullets at `:63`

**Interfaces:**
- Produces: the `native_store` API in the interface table. Semantics: `head(path)` returns the last completed turn's position and whether a turn is open; `completed_turn(path, after=P, prompt_marker=m)` returns the position of the unique completed turn whose user message follows `P` (or is the first turn when `P is None`) and contains `m`, else `None`. Claude completion rule: a turn is complete when its lineage (every row descends from the submitted user row through `_claude_descendants`, same `sessionId`/`promptId`, no sidechain) ends in exactly one final: either a `StructuredOutput` `toolEndsTurn` user row with its matching attachment (`_claude_structured_result`, observed live) or an assistant row with `stop_reason == "end_turn"` (hypothesis for the plain `stream-json` command form; Task 6a confirms or falsifies it before Plan B starts). More than one final, unsupported ancestry or an unrecognized trailing row make the turn incomplete (`None`), never a guess; the only tolerated trailing row is `_claude_resume_padding`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_provider_native_store.py
"""Native-store adapters read position and completion evidence; they never write."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.providers.native_store import NativePosition, native_store_adapter

CODEX_SID = "01a13777-79ec-7511-8b2b-42a6111e33cf"
CLAUDE_SID = "1930ae6b-5267-4eec-b1e1-b430dad86844"


def _jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _codex_rows(turns: list[tuple[str, str, bool]]):
    rows = [{"type": "session_meta", "payload": {"id": CODEX_SID}}]
    for turn_id, marker, complete in turns:
        rows.append({"type": "event_msg", "payload": {"type": "task_started", "turn_id": turn_id}})
        rows.append({"type": "event_msg", "payload": {"type": "item_completed", "turn_id": turn_id, "thread_id": CODEX_SID,
                     "item": {"id": f"u-{turn_id}", "type": "UserMessage", "content": [{"text_elements": [marker]}]}}})
        if complete:
            rows.append({"type": "event_msg", "payload": {"type": "item_completed", "turn_id": turn_id, "thread_id": CODEX_SID,
                         "item": {"id": f"a-{turn_id}", "type": "AgentMessage", "phase": "final_answer", "content": [{"type": "Text", "text": "{}"}]}}})
            rows.append({"type": "event_msg", "payload": {"type": "task_complete", "turn_id": turn_id, "last_agent_message": "{}"}})
    return rows


def _claude_rows(turns: list[tuple[str, str, bool]]):
    rows, parent = [], None
    for prompt_id, marker, complete in turns:
        user_id = f"user-{prompt_id}"
        rows.append({"type": "user", "uuid": user_id, "parentUuid": parent, "sessionId": CLAUDE_SID, "promptId": prompt_id,
                     "isSidechain": False, "message": {"role": "user", "content": marker}})
        if complete:
            final_id = f"assistant-{prompt_id}"
            rows.append({"type": "assistant", "uuid": final_id, "parentUuid": user_id, "sessionId": CLAUDE_SID, "promptId": prompt_id,
                         "isSidechain": False, "message": {"role": "assistant", "stop_reason": "end_turn", "content": [{"type": "text", "text": "ok"}]}})
            parent = final_id
    return rows


@pytest.mark.parametrize("mode, sid, rows_for, home_env, relpath", [
    ("codex_exec_jsonl_stdout", CODEX_SID, _codex_rows, "CODEX_HOME", f"sessions/2026/10/14/rollout-2026-10-14T00-00-00-{CODEX_SID}.jsonl"),
    ("claude_stream_json_stdout", CLAUDE_SID, _claude_rows, "CLAUDE_CONFIG_DIR", f"projects/-tmp-ws/{CLAUDE_SID}.jsonl"),
])
def test_head_and_completed_turn_follow_the_store(tmp_path, monkeypatch, mode, sid, rows_for, home_env, relpath) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv(home_env, str(home))
    adapter = native_store_adapter(mode)
    assert adapter.metadata_mode == mode
    assert adapter.locate(sid).path is None  # nothing yet
    path = home / relpath
    _jsonl(path, rows_for([("t1", "attempt-1/result.json", True)]))
    located = adapter.locate(sid)
    assert (located.path, located.ambiguous) == (path, False)
    head = adapter.head(path)
    assert head.locator == sid and head.open_turn is False and head.position.turn_id == "t1"
    first = adapter.completed_turn(path, after=None, prompt_marker="attempt-1/result.json")
    assert first is not None and first.position == head.position
    _jsonl(path, rows_for([("t1", "attempt-1/result.json", True), ("t2", "attempt-2/result.json", True)]))
    second = adapter.completed_turn(path, after=head.position, prompt_marker="attempt-2/result.json")
    assert second.position.turn_id == "t2" and second.position.end_line > head.position.end_line
    assert adapter.completed_turn(path, after=None, prompt_marker="attempt-2/result.json") is None  # wrong predecessor


@pytest.mark.parametrize("mode, sid, rows_for, home_env, relpath", [
    ("codex_exec_jsonl_stdout", CODEX_SID, _codex_rows, "CODEX_HOME", f"sessions/a/rollout-x-{CODEX_SID}.jsonl"),
    ("claude_stream_json_stdout", CLAUDE_SID, _claude_rows, "CLAUDE_CONFIG_DIR", f"projects/p/{CLAUDE_SID}.jsonl"),
])
def test_open_turn_and_ambiguity_are_reported_not_guessed(tmp_path, monkeypatch, mode, sid, rows_for, home_env, relpath) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv(home_env, str(home))
    adapter = native_store_adapter(mode)
    path = home / relpath
    _jsonl(path, rows_for([("t1", "m1", True), ("t2", "m2", False)]))
    head = adapter.head(path)
    assert head.open_turn is True and head.position.turn_id == "t1"
    assert adapter.completed_turn(path, after=head.position, prompt_marker="m2") is None
    copy = path.with_name("copy-" + path.name) if mode.startswith("codex") else path.parent.parent / "q" / path.name
    _jsonl(copy, rows_for([("t1", "m1", True)]))
    located = adapter.locate(sid)
    assert located.path is None and located.ambiguous is True


def test_unknown_mode_has_no_adapter_and_env_is_not_required(monkeypatch) -> None:
    monkeypatch.delenv("CODEX_HOME", raising=False)
    assert native_store_adapter("omp_json_stdout") is None
    assert native_store_adapter("codex_exec_jsonl_stdout").home == Path.home() / ".codex"


def test_codex_accumulator_counts_completed_turns() -> None:
    from orchestrator.providers.session_transport import CodexExecJsonlAccumulator
    acc = CodexExecJsonlAccumulator()
    acc.feed(b'{"type":"thread.started","thread_id":"%s"}\n{"type":"turn.started"}\n{"type":"turn.completed"}\n' % CODEX_SID.encode())
    metadata, error = acc.finalize(expected_session_id=None, require_terminal=True)
    assert error is None and metadata["turns_completed"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_provider_native_store.py -q`
Expected: FAIL — `ModuleNotFoundError: orchestrator.providers.native_store`.

- [ ] **Step 3: Implement the adapters**

```python
# orchestrator/providers/native_store.py
"""Read-only position and completion evidence from provider-native session stores (D1, D7)."""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .types import ProviderSessionMetadataMode


@dataclass(frozen=True)
class NativePosition:
    turn_id: str
    end_line: int

    def record(self) -> dict[str, Any]:
        return {"turn_id": self.turn_id, "end_line": self.end_line}

    @classmethod
    def from_record(cls, row: Any) -> "NativePosition":
        if not isinstance(row, dict) or set(row) != {"turn_id", "end_line"} or not isinstance(row["turn_id"], str) \
                or type(row["end_line"]) is not int or row["end_line"] < 1:
            raise ValueError("native position record is malformed")
        return cls(row["turn_id"], row["end_line"])


@dataclass(frozen=True)
class NativeHead:
    locator: str
    path: Path
    position: NativePosition | None
    open_turn: bool


@dataclass(frozen=True)
class NativeTurn:
    position: NativePosition
    user_line: int


@dataclass(frozen=True)
class NativeLocate:
    path: Path | None
    ambiguous: bool = False


class NativeStoreError(ValueError):
    """The store is unreadable or structurally unsupported; never a permission to append."""


class NativeStoreAdapter(Protocol):
    metadata_mode: str
    home: Path
    def locate(self, locator: str) -> NativeLocate: ...
    def head(self, path: Path) -> NativeHead: ...
    def completed_turn(self, path: Path, *, after: NativePosition | None, prompt_marker: str) -> NativeTurn | None: ...


def _read_jsonl(path: Path) -> list[tuple[int, dict[str, Any]]]:
    def unique(pairs):
        row = {}
        for key, value in pairs:
            if key in row:
                raise ValueError("duplicate native JSON key")
            row[key] = value
        return row
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise NativeStoreError(f"native store unreadable: {exc}") from exc
    rows = []
    for number, line in enumerate(raw.split(b"\n"), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line.decode("utf-8"), object_pairs_hook=unique,
                             parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v)))
        except (UnicodeDecodeError, ValueError) as exc:
            raise NativeStoreError(f"native store line {number} is malformed: {exc}") from exc
        if not isinstance(row, dict):
            raise NativeStoreError(f"native store line {number} is not an object")
        rows.append((number, row))
    return rows


def _identity(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _texts(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                parts.append(str(block.get("text", "")))
                parts.extend(str(t) for t in block.get("text_elements", []) if isinstance(t, str))
        return "".join(parts)
    return ""


def _unique_match(candidates: list[Path]) -> NativeLocate:
    if len(candidates) == 1:
        return NativeLocate(candidates[0])
    return NativeLocate(None, ambiguous=len(candidates) > 1)


class _Codex:
    metadata_mode = ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value

    def __init__(self) -> None:
        self.home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")

    def locate(self, locator: str) -> NativeLocate:
        store = self.home / "sessions"
        if not store.is_dir():
            return NativeLocate(None)
        found = []
        for path in sorted(store.rglob("rollout-*.jsonl")):
            if locator not in path.name:
                continue
            try:
                rows = _read_jsonl(path)
            except NativeStoreError:
                continue
            if rows and rows[0][1].get("type") == "session_meta" and (rows[0][1].get("payload") or {}).get("id") == locator:
                found.append(path)
        return _unique_match(found)

    def _events(self, path: Path):
        rows = _read_jsonl(path)
        if not rows or rows[0][1].get("type") != "session_meta" or not _identity((rows[0][1].get("payload") or {}).get("id")):
            raise NativeStoreError("codex session_meta is missing")
        locator = rows[0][1]["payload"]["id"]
        events = []
        for line, row in rows:
            if row.get("type") == "event_msg" and isinstance(row.get("payload"), dict) and isinstance(row["payload"].get("type"), str):
                events.append((line, row["payload"]["type"], row["payload"]))
        return locator, events

    def head(self, path: Path) -> NativeHead:
        locator, events = self._events(path)
        active, last = None, None
        for line, kind, payload in events:
            turn = payload.get("turn_id")
            if kind == "task_started":
                active = turn if _identity(turn) else None
            elif kind == "task_complete" and _identity(turn):
                last, active = NativePosition(turn, line), None
        return NativeHead(locator, path, last, active is not None)

    def completed_turn(self, path: Path, *, after: NativePosition | None, prompt_marker: str) -> NativeTurn | None:
        _locator, events = self._events(path)
        start_line = 0 if after is None else after.end_line
        completed = [(line, p["turn_id"]) for line, k, p in events if k == "task_complete" and line > start_line and _identity(p.get("turn_id"))]
        if len(completed) != 1:
            return None
        end_line, turn_id = completed[0]
        users = [line for line, k, p in events if k == "item_completed" and p.get("turn_id") == turn_id
                 and isinstance(p.get("item"), dict) and p["item"].get("type") == "UserMessage"
                 and prompt_marker in _texts(p["item"].get("content"))]
        if len(users) != 1 or not (start_line < users[0] < end_line):
            return None
        return NativeTurn(NativePosition(turn_id, end_line), users[0])


class _Claude:
    metadata_mode = ProviderSessionMetadataMode.CLAUDE_STREAM_JSON_STDOUT.value

    def __init__(self) -> None:
        self.home = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")

    def locate(self, locator: str) -> NativeLocate:
        store = self.home / "projects"
        if not store.is_dir():
            return NativeLocate(None)
        return _unique_match(sorted(store.rglob(f"{locator}.jsonl")))

    @staticmethod
    def _turns(path: Path):
        """Submitted user rows and, per turn, its unique final row or None (incomplete, forked or unsupported)."""
        records = _read_jsonl(path)
        by_id = {row["uuid"]: (line, row) for line, row in records if _identity(row.get("uuid"))}
        if len(by_id) != sum(_identity(row.get("uuid")) for _l, row in records):
            raise NativeStoreError("claude store duplicates a message uuid")
        rows = [(line, row) for line, row in records if row.get("isSidechain", False) is False]
        users = [(line, row) for line, row in rows if row.get("type") == "user" and isinstance(row.get("message"), dict)
                 and not _claude_tool_result(row) and _identity(row.get("promptId")) and _identity(row.get("uuid"))]
        finals: dict[str, tuple[int, dict] | None] = {}
        for index, (start, user) in enumerate(users):
            next_line = users[index + 1][0] if index + 1 < len(users) else len(records) + 1
            turn = [(line, row) for line, row in rows if start < line < next_line and row.get("sessionId") == user.get("sessionId")
                    and row.get("type") in {"assistant", "user"}]
            lineage_ok = all(_claude_descendants(row.get("parentUuid"), user["uuid"], by_id, child_line=line,
                                                 session_id=user["sessionId"], prompt_id=user["promptId"])
                             and ("promptId" not in row or row["promptId"] == user["promptId"]) for line, row in turn)
            ends = [(line, row) for line, row in turn
                    if (row.get("type") == "assistant" and (row.get("message") or {}).get("stop_reason") == "end_turn")
                    or (row.get("type") == "user" and row.get("toolEndsTurn") is True
                        and _claude_structured_result(line, row, by_id) is not None)]
            trailing = [r for r in turn if ends and r[0] > ends[0][0]]
            padding_ok = not trailing or (len(trailing) == 1 and index + 1 < len(users)
                                          and _claude_resume_padding(trailing[0][1], ends[0][1]["uuid"], user["sessionId"]))
            finals[user["promptId"]] = ends[0] if lineage_ok and len(ends) == 1 and padding_ok else None
        return rows, users, finals

    def head(self, path: Path) -> NativeHead:
        rows, users, finals = self._turns(path)
        locator = next((row.get("sessionId") for _l, row in rows if _identity(row.get("sessionId"))), None)
        if locator is None:
            raise NativeStoreError("claude store exposes no sessionId")
        last, open_turn = None, False
        for _line, user in users:
            final = finals.get(user["promptId"])
            if final is None:
                open_turn = True            # incomplete, forked or unsupported: never a position
            else:
                last, open_turn = NativePosition(user["promptId"], final[0]), False
        return NativeHead(locator, path, last, open_turn)

    def completed_turn(self, path: Path, *, after: NativePosition | None, prompt_marker: str) -> NativeTurn | None:
        _rows, users, finals = self._turns(path)
        start_line = 0 if after is None else after.end_line
        later = [(line, user) for line, user in users if line > start_line]
        if len(later) != 1 or prompt_marker not in _texts(later[0][1]["message"].get("content")):
            return None
        line, user = later[0]
        final = finals.get(user["promptId"])
        if final is None or final[0] <= line:
            return None
        return NativeTurn(NativePosition(user["promptId"], final[0]), line)


# `_claude_tool_result`, `_claude_descendants`, `_claude_structured_result` and `_claude_resume_padding` are the probe's
# functions (`native_session_cli_evidence.py:259-371`), copied verbatim.


def native_store_adapter(metadata_mode: str | None) -> NativeStoreAdapter | None:
    """Select the store reader structurally from the template's metadata mode."""
    for adapter in (_Codex, _Claude):
        if metadata_mode == adapter.metadata_mode:
            return adapter()
    return None
```

Codex accumulator: count `turn.completed` events in `_consume_line` (`self._turns_completed += 1`) and add `"turns_completed": self._turns_completed` to the `finalize` metadata dict (`session_transport.py:449-455`).

- [ ] **Step 4: Amend `specs/providers.md` (new subsection after `:63`)**

"Native session stores (target 2.38 agent sessions)": the Codex store is `$CODEX_HOME` (default `~/.codex`) `sessions/**/rollout-*<thread id>.jsonl` whose first row is `session_meta`; the Claude store is `$CLAUDE_CONFIG_DIR` (default `~/.claude`) `projects/**/<session id>.jsonl`. The orchestrator reads them to establish the head position (last completed turn id and its terminal line) and to bind one completed turn to one attempt (the user message carrying the attempt's result path); it never writes them, never selects a per-run home and never provisions credentials. A locator matching zero or more than one file is `agent_session_unavailable` at the runtime (Plan B); an open (incomplete) head refuses a new append. Operator limit (D1): the check-then-append window against a concurrent external writer (an operator resuming the same native session from a shell) is not closed; external advancement inside the window is detected at the next turn. Retention: native history stays in the provider default home under the provider's own retention; the orchestrator neither deletes nor garbage-collects it and promises no remote durability; the run retains only receipts and proofs. These facts are evidence for the memo, not authority.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_provider_native_store.py tests/test_provider_session_transport.py tests/experiments/test_native_session_cli_evidence.py -q`
Expected: PASS; `wc -l orchestrator/providers/native_store.py` <= 500.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/providers/native_store.py tests/test_provider_native_store.py
git commit -m "feat: read Codex and Claude native session stores for head position and completed turns" -- orchestrator/providers/native_store.py orchestrator/providers/session_transport.py specs/providers.md tests/test_provider_native_store.py
```

---

### Task 6: Deterministic fake CLIs and transport proofs through `ProviderExecutor`

**Files:**
- Create: `tests/agent_session_shims.py`
- Create: `tests/test_agent_session_transport.py`

**Interfaces:**
- Produces: `FAKE_CODEX`, `FAKE_CLAUDE`, `install_agent_shims(bin_dir, monkeypatch, *, codex_home, claude_home, plan)`, `shim_requests(root)`. Plan: `{"codex": [step, ...], "claude": [step, ...]}`; each step `{"mode": <mode>, "result": <json>}`; steps consumed per tool in call order; env `AGENT_SHIM_PLAN`. Both shims write the native store under the given homes, write `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` with `result` (or an invalid document under `invalid-result`), emit the provider's stdout protocol and append a row `{"tool","argv","session","mode","cwd","prompt_sha256"}` to `requests.jsonl` in the cwd.

- [ ] **Step 1: Write the shims**

```python
# tests/agent_session_shims.py
"""Fake `codex` and `claude` CLIs that keep a native store and speak each provider's stdout protocol."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

COMMON = r'''import hashlib, json, os, sys, time, uuid
from pathlib import Path
prompt = sys.stdin.buffer.read().decode("utf-8")
tool = Path(sys.argv[0]).name
argv = sys.argv[1:]
log = Path("requests.jsonl")
rows = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()] if log.exists() else []
plan = json.loads(os.environ["AGENT_SHIM_PLAN"])
step = plan[tool][sum(1 for r in rows if r["tool"] == tool)]
mode = step.get("mode", "success")
def log_request(session):
    with log.open("a", encoding="utf-8") as out:
        out.write(json.dumps({"tool": tool, "argv": argv, "session": session, "mode": mode, "cwd": os.getcwd(),
                              "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()}) + "\n")
def write_result():
    for name, text in step.get("files", {}).items():
        Path(name).parent.mkdir(parents=True, exist_ok=True); Path(name).write_text(text, encoding="utf-8")
    target = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
    payload = {"ok": "not-bool"} if mode == "invalid-result" else step["result"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload), encoding="utf-8")
def emit(event):
    sys.stdout.write(json.dumps(event) + "\n"); sys.stdout.flush()
def finish():
    if mode == "complete-then-hang":
        time.sleep(30)
    if mode == "linger" and os.fork() == 0:
        time.sleep(30); os._exit(0)
if mode == "timeout":
    time.sleep(30)                      # before any store write: the adapter can prove no advance
if mode == "nonzero-before-append":
    sys.exit(9)                         # before any store write
'''

FAKE_CODEX = COMMON + r'''
resume = "resume" in argv
session = argv[argv.index("resume") + 1] if resume else str(uuid.uuid4())
store = Path(os.environ["CODEX_HOME"]) / "sessions"
files = [p for p in store.rglob("rollout-*.jsonl") if session in p.name] if store.exists() else []
if resume and (mode == "lose-locator" or not files):
    log_request(session)
    sys.stderr.write(f"no rollout found for thread id {session}\n"); sys.exit(1)
path = files[0] if resume else store / "2026" / f"rollout-{session}.jsonl"
path.parent.mkdir(parents=True, exist_ok=True)
rows = [] if not resume else [json.loads(l) for l in path.read_text().splitlines()]
if not resume:
    rows.append({"type": "session_meta", "payload": {"id": session}})
def turn(turn_id, text, complete, result_text="{}"):
    rows.append({"type": "event_msg", "payload": {"type": "task_started", "turn_id": turn_id}})
    rows.append({"type": "event_msg", "payload": {"type": "item_completed", "turn_id": turn_id, "thread_id": session,
                 "item": {"id": "u-" + turn_id, "type": "UserMessage", "content": [{"text_elements": [text]}]}}})
    if complete:
        rows.append({"type": "event_msg", "payload": {"type": "item_completed", "turn_id": turn_id, "thread_id": session,
                     "item": {"id": "a-" + turn_id, "type": "AgentMessage", "phase": "final_answer", "content": [{"type": "Text", "text": result_text}]}}})
        rows.append({"type": "event_msg", "payload": {"type": "task_complete", "turn_id": turn_id, "last_agent_message": result_text}})
if mode == "overlap":
    turn("foreign-" + str(uuid.uuid4())[:8], "external operator turn", True)
turn_id = str(uuid.uuid4())
turn(turn_id, prompt, mode not in {"interrupted", "nonzero"})
path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
log_request(session)
emit({"type": "thread.started", "thread_id": session})
emit({"type": "turn.started"})
if mode == "interrupted":
    os._exit(137)
if mode == "nonzero":
    sys.exit(9)
write_result()
emit({"type": "item.completed", "item": {"type": "agent_message", "text": "done"}})
emit({"type": "turn.completed"})
finish()
'''

FAKE_CLAUDE = COMMON + r'''
resume = "--resume" in argv
session = argv[argv.index("--resume") + 1] if resume else str(uuid.uuid4())
store = Path(os.environ["CLAUDE_CONFIG_DIR"]) / "projects" / "ws"
path = store / f"{session}.jsonl"
if resume and (mode == "lose-locator" or not path.exists()):
    log_request(session)
    sys.stderr.write(f"No conversation found with session ID: {session}\n"); sys.exit(1)
store.mkdir(parents=True, exist_ok=True)
rows = [json.loads(l) for l in path.read_text().splitlines()] if resume else []
parent = next((r["uuid"] for r in reversed(rows) if r["type"] == "assistant"), None)
def turn(prompt_id, text, complete):
    global parent
    user_id = str(uuid.uuid4())
    rows.append({"type": "user", "uuid": user_id, "parentUuid": parent, "sessionId": session, "promptId": prompt_id,
                 "isSidechain": False, "message": {"role": "user", "content": text}})
    if complete:
        final_id = str(uuid.uuid4())
        rows.append({"type": "assistant", "uuid": final_id, "parentUuid": user_id, "sessionId": session, "promptId": prompt_id,
                     "isSidechain": False, "message": {"role": "assistant", "stop_reason": "end_turn", "content": [{"type": "text", "text": "ok"}]}})
        parent = final_id
if mode == "overlap":
    turn(str(uuid.uuid4()), "external operator turn", True)
prompt_id = str(uuid.uuid4())
turn(prompt_id, prompt, mode not in {"interrupted", "nonzero"})
path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
log_request(session)
emit({"type": "system", "subtype": "init", "session_id": session, "model": "fake"})
if mode == "interrupted":
    os._exit(137)
if mode == "nonzero":
    sys.exit(9)
write_result()
emit({"type": "assistant", "session_id": session, "message": {"role": "assistant", "content": [{"type": "text", "text": "ok"}]}})
emit({"type": "result", "subtype": "success", "is_error": False, "session_id": session, "result": "ok"})
finish()
'''


def install_agent_shims(bin_dir: Path, monkeypatch, *, codex_home: Path, claude_home: Path, plan: dict) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    for tool, body in (("codex", FAKE_CODEX), ("claude", FAKE_CLAUDE)):
        (bin_dir / tool).write_text(f"#!{sys.executable}\n" + body, encoding="utf-8")
        (bin_dir / tool).chmod(0o700)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude_home))
    monkeypatch.setenv("AGENT_SHIM_PLAN", json.dumps(plan))


def shim_requests(root: Path) -> list[dict]:
    path = root / "requests.jsonl"
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []
```

- [ ] **Step 2: Write the failing transport tests**

```python
# tests/test_agent_session_transport.py
"""Fresh, resume, overlap, interruption and locator loss through the real executor and store adapters."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.providers.executor import ProviderExecutor
from orchestrator.providers.native_store import native_store_adapter
from orchestrator.providers.registry import ProviderRegistry
from orchestrator.providers.types import ProviderParams, ProviderSessionMode, ProviderSessionRequest
from tests.agent_session_shims import install_agent_shims, shim_requests

TEMPLATES = {"codex": "codex", "claude": "claude_unrestricted_workspace"}


def _executor(root: Path) -> ProviderExecutor:
    return ProviderExecutor(root, ProviderRegistry(), provider_observation_enabled=False)


def _run(root, tool, request, result_path, timeout=20):
    executor = _executor(root)
    invocation, error = executor.prepare_invocation(provider_name=TEMPLATES[tool], params=ProviderParams(params={}, input_file=None),
        context={}, prompt_content=f"turn for {result_path}", session_request=request,
        env={"ORCHESTRATOR_OUTPUT_BUNDLE_PATH": str(result_path)}, secrets=None, timeout_sec=timeout,
        provider_call_policy={"model": "m", "effort": "low"}, provider_session_dir=None, provider_session_identity=None)
    assert error is None, error
    return invocation, executor.execute(invocation, cwd=root, stream_output=False, session_runtime=None)


@pytest.mark.parametrize("tool", ["codex", "claude"])
def test_fresh_then_resume_advance_one_native_store(tmp_path, monkeypatch, tool) -> None:
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude",
                        plan={tool: [{"mode": "success", "result": {"ok": True}}] * 2})
    invocation, first = _run(tmp_path, tool, ProviderSessionRequest(mode=ProviderSessionMode.FRESH), tmp_path / "r1.json")
    assert invocation.command_variant == "fresh_command" and first.exit_code == 0, first.error
    sid = first.provider_session["session_id"]
    adapter = native_store_adapter(invocation.metadata_mode)
    path = adapter.locate(sid).path
    head1 = adapter.head(path)
    assert head1.open_turn is False and adapter.completed_turn(path, after=None, prompt_marker="r1.json") is not None
    invocation2, second = _run(tmp_path, tool, ProviderSessionRequest(mode=ProviderSessionMode.RESUME, session_id=sid), tmp_path / "r2.json")
    assert invocation2.command_variant == "resume_command" and second.exit_code == 0, second.error
    assert second.provider_session["session_id"] == sid
    head2 = adapter.head(path)
    assert head2.position.end_line > head1.position.end_line
    assert adapter.completed_turn(path, after=head1.position, prompt_marker="r2.json").position == head2.position
    assert [r["session"] for r in shim_requests(tmp_path)] == [sid, sid]
    assert json.loads((tmp_path / "r2.json").read_text()) == {"ok": True}


@pytest.mark.parametrize("tool", ["codex", "claude"])
def test_overlapping_external_append_moves_the_head_before_our_turn(tmp_path, monkeypatch, tool) -> None:
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude",
                        plan={tool: [{"mode": "success", "result": {}}, {"mode": "overlap", "result": {}}]})
    invocation, first = _run(tmp_path, tool, ProviderSessionRequest(mode=ProviderSessionMode.FRESH), tmp_path / "r1.json")
    sid = first.provider_session["session_id"]
    adapter = native_store_adapter(invocation.metadata_mode)
    path = adapter.locate(sid).path
    before = adapter.head(path).position
    _run(tmp_path, tool, ProviderSessionRequest(mode=ProviderSessionMode.RESUME, session_id=sid), tmp_path / "r2.json")
    # two completed turns follow `before`: the exact-completion test rejects the append as not uniquely bound
    assert adapter.completed_turn(path, after=before, prompt_marker="r2.json") is None
    assert adapter.head(path).position.end_line > before.end_line


@pytest.mark.parametrize("tool", ["codex", "claude"])
def test_interrupted_turn_leaves_an_open_head_and_no_terminal(tmp_path, monkeypatch, tool) -> None:
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude",
                        plan={tool: [{"mode": "interrupted", "result": {}}]})
    invocation, result = _run(tmp_path, tool, ProviderSessionRequest(mode=ProviderSessionMode.FRESH), tmp_path / "r1.json")
    assert result.exit_code != 0 and result.provider_session is None
    sid = shim_requests(tmp_path)[0]["session"]
    adapter = native_store_adapter(invocation.metadata_mode)
    head = adapter.head(adapter.locate(sid).path)
    assert head.open_turn is True and head.position is None
    assert not (tmp_path / "r1.json").exists()


@pytest.mark.parametrize("tool", ["codex", "claude"])
def test_lost_locator_is_rejected_by_the_native_cli_and_absent_from_the_store(tmp_path, monkeypatch, tool) -> None:
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude",
                        plan={tool: [{"mode": "lose-locator", "result": {}}]})
    sid = "00000000-0000-4000-8000-000000000000"
    invocation, result = _run(tmp_path, tool, ProviderSessionRequest(mode=ProviderSessionMode.RESUME, session_id=sid), tmp_path / "r.json")
    assert result.exit_code == 1 and result.provider_session is None
    assert native_store_adapter(invocation.metadata_mode).locate(sid).path is None


@pytest.mark.parametrize("mode, store_written", [("timeout", False), ("complete-then-hang", True)])
def test_timeout_reaps_the_process_tree_and_the_store_tells_the_two_cases_apart(tmp_path, monkeypatch, mode, store_written) -> None:
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude",
                        plan={"codex": [{"mode": mode, "result": {"ok": True}}]})
    invocation, result = _run(tmp_path, "codex", ProviderSessionRequest(mode=ProviderSessionMode.FRESH), tmp_path / "r.json", timeout=2)
    assert result.exit_code == 124 and result.error["type"] == "timeout"
    adapter = native_store_adapter(invocation.metadata_mode)
    requests = shim_requests(tmp_path)
    assert bool(requests) is store_written
    if store_written:
        head = adapter.head(adapter.locate(requests[0]["session"]).path)
        assert head.open_turn is False and head.position is not None and (tmp_path / "r.json").exists()


def test_nonzero_before_append_leaves_no_native_trace_and_linger_leaves_a_child(tmp_path, monkeypatch) -> None:
    install_agent_shims(tmp_path / "bin", monkeypatch, codex_home=tmp_path / "codex", claude_home=tmp_path / "claude",
                        plan={"codex": [{"mode": "nonzero-before-append", "result": {}}, {"mode": "linger", "result": {"ok": True}}]})
    _i, first = _run(tmp_path, "codex", ProviderSessionRequest(mode=ProviderSessionMode.FRESH), tmp_path / "r1.json")
    assert first.exit_code == 9 and not (tmp_path / "codex").exists() and shim_requests(tmp_path) == []
    from orchestrator.providers.control import ProviderExecutionControl
    control = ProviderExecutionControl()
    executor = _executor(tmp_path)
    invocation, error = executor.prepare_invocation(provider_name="codex", params=ProviderParams(params={}, input_file=None), context={},
        prompt_content="p", session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH),
        env={"ORCHESTRATOR_OUTPUT_BUNDLE_PATH": str(tmp_path / "r2.json")}, secrets=None, timeout_sec=20,
        provider_call_policy={"model": "m", "effort": "low"}, provider_session_dir=None, provider_session_identity=None)
    assert error is None
    second = executor.execute(invocation, cwd=tmp_path, stream_output=False, session_runtime=None, control=control)
    assert second.exit_code == 0 and control.terminal_result is not None and control.terminal_result.pgid is not None
    import os
    os.killpg(control.terminal_result.pgid, 0)          # the lingering grandchild keeps the process group alive
    result = control.cancel_and_reap(grace=0.5)
    assert result.pgid_empty is True
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_agent_session_transport.py -q`
Expected: the Claude parametrizations fail until Task 4 and Task 5 are merged; with them merged everything passes except any shim bug. If a test fails for a shim reason, fix the shim (it is test infrastructure), never the adapter semantics.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_agent_session_transport.py tests/test_provider_native_store.py tests/test_provider_session_transport_claude.py -q` then `pytest --collect-only tests/test_agent_session_transport.py -q`.
Expected: PASS (12 items collected).

- [ ] **Step 5: Commit**

```bash
git add tests/agent_session_shims.py tests/test_agent_session_transport.py
git commit -m "test: add deterministic codex and claude session CLIs with native-store transport proofs" -- tests/agent_session_shims.py tests/test_agent_session_transport.py
```

---

### Task 6a: Claude plain-form transport mini-probe (paid, opt-in; authorized by D8a)

**Files:**
- Modify: `scripts/experiments/native_session_cli_probe.py:236-301` (`_command` gains `command_form: str`; `plain` builds exactly the adapter's commands from Task 4 — `claude -p --output-format stream-json --verbose [--resume <id>] --model <model> --effort low --permission-mode bypassPermissions` with the prompt on stdin — and skips `--json-schema`), `:922-935` (`--command-form {schema,plain}`, default `schema`, and `--max-calls N` bounding the campaign), `:690-720` (`_run_campaign` honours `--max-calls`, runs only phases fresh → resume → resume for `plain`, and **stages credentials only for a real CLI**: the existing `executable, fake = _provider_executable(provider)` result gates `_stage_auth` so the offline path never reads `~/.claude/.credentials.json`; the same gate is applied at `:650` for the alternate-home stage)
- Create: `tests/experiments/test_native_session_cli_probe_plain_form.py` (fake-executable test that the plain form emits the adapter's argv, reads stdin, and stops at `--max-calls`)
- Create: `docs/reports/2026-10-14-claude-plain-form-mini-probe.md` (receipt; private evidence under `/tmp/claude-plain-form-<token>/`)

**Interfaces:**
- Consumes: Task 4 commands, Task 5 `_Claude.head`/`completed_turn`.
- Produces: the receipt `completion_marker ∈ {end_turn, tool_ends_turn, NOT_OBSERVED}` plus the observed head positions; Plan B may start only when the receipt is `end_turn` or `tool_ends_turn`; `NOT_OBSERVED` returns to Task 5 to revise the completion rule (and to the design owner if no store-only completion exists).

- [ ] **Step 1: Write the failing test**

```python
# tests/experiments/test_native_session_cli_probe_plain_form.py
"""The plain command form uses the adapter's own argv and stdin prompt, and the campaign stops at --max-calls."""
from __future__ import annotations

import json, os, subprocess, sys
from pathlib import Path

from scripts.experiments import native_session_cli_probe as probe

FAKE = "#!%s\nimport sys, json\nopen('argv.jsonl','a').write(json.dumps({'argv': sys.argv[1:], 'stdin': sys.stdin.read()})+'\\n')\n" \
       "print(json.dumps({'type':'result','subtype':'success','is_error':False,'session_id':'s'}))\n" % sys.executable
PRIVATE_HOME_HINT = "the probe never reads credentials when NATIVE_SESSION_PROBE_FAKE_CLAUDE names the executable"


def test_plain_form_builds_adapter_argv_with_stdin_prompt(tmp_path: Path) -> None:
    (tmp_path / "schemas").mkdir(); (tmp_path / "schemas" / "schema-1.json").write_text("{}")
    command = probe._command("claude", "claude", "haiku", tmp_path, "review", "n0nce", None, None, command_form="plain")
    assert command[:5] == ["claude", "-p", "--output-format", "stream-json", "--verbose"]
    assert "--json-schema" not in command and "--permission-mode" in command and command[-1] == "bypassPermissions"
    resumed = probe._command("claude", "claude", "haiku", tmp_path, "write", "n1", "sess-1", "t0", command_form="plain")
    assert resumed[resumed.index("--resume") + 1] == "sess-1"


def test_max_calls_bounds_the_campaign_and_fake_mode_never_touches_credentials(tmp_path: Path, monkeypatch) -> None:
    binary = tmp_path / "bin" / "claude"; binary.parent.mkdir(); binary.write_text(FAKE); binary.chmod(0o700)
    monkeypatch.setenv("NATIVE_SESSION_PROBE_FAKE_CLAUDE", str(binary))       # the probe's existing offline path (:194-205)
    monkeypatch.setenv("HOME", str(tmp_path / "empty-home"))                  # belt and braces: an empty home has no credentials
    (tmp_path / "empty-home").mkdir()
    monkeypatch.chdir(tmp_path)
    rc = probe.main(["--provider", "claude", "--execute", "--model", "haiku", "--output-dir", str(tmp_path / "out"),
                     "--command-form", "plain", "--max-calls", "2"])
    assert rc in {0, 1}
    assert len((tmp_path / "argv.jsonl").read_text().splitlines()) <= 2
    assert not list((tmp_path / "out").rglob(".credentials.json"))            # no staging happened in fake mode
```

The offline path is the probe's existing `NATIVE_SESSION_PROBE_FAKE_CLAUDE` override (`_provider_executable`, `:194-205`). Staging gate to add in `_run_campaign` (`:717-718`) and at `:650`:

```python
        if not fake:
            auth_copy = provider_home / ("auth.json" if provider == "codex" else ".credentials.json")
            _stage_auth(provider, provider_home, auth_copy)
```

so a synthetic CLI runs against an empty private home and the user's real credential file is never opened or copied.

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/experiments/test_native_session_cli_probe_plain_form.py -q`
Expected: FAIL — `TypeError: _command() got an unexpected keyword argument 'command_form'`; the credential assertion also fails until the staging gate exists.

- [ ] **Step 3: Implement the probe flags** (keep every existing default so the recorded campaigns reproduce; the `plain` form reuses `_prompt`, `_invoke`, `_native_snapshot`, `ProcessTracker` quiescence and the receipt writer unchanged) and make the test pass.

- [ ] **Step 4: Run the bounded live probe in tmux (the only paid step in Plan A; 2–3 `haiku` calls)**

```bash
python scripts/experiments/native_session_cli_probe.py --provider claude --execute --model haiku \
  --command-form plain --max-calls 3 --output-dir /tmp/claude-plain-form-$(date +%s)
```

Then, offline, run `native_store._Claude().head(snapshot)` and `completed_turn(snapshot, after=<previous position>, prompt_marker=<the probe's nonce>)` over the three native snapshots and record, per call: the final row kind observed (`end_turn` assistant, `toolEndsTurn` user, or neither), the head position, whether `completed_turn` bound the turn, quiescence from the tracker, and the CLI version. Write `docs/reports/2026-10-14-claude-plain-form-mini-probe.md` with the command, counts (<= 3), SHA-256 of each snapshot, the `completion_marker` verdict and the sentence "This probe qualifies nothing; it feeds PQ-1a and gates Plan B on the Claude completion rule."

- [ ] **Step 5: Gate**

If `completion_marker == NOT_OBSERVED`: amend Task 5's Claude completion rule to what was observed (if a store-only completion exists) or stop and return to the design owner; Plan B does not start. Otherwise proceed.

- [ ] **Step 6: Commit**

```bash
git add tests/experiments/test_native_session_cli_probe_plain_form.py docs/reports/2026-10-14-claude-plain-form-mini-probe.md
git commit -m "test: probe the Claude plain stream-json form for end-of-turn and head position" -- scripts/experiments/native_session_cli_probe.py tests/experiments/test_native_session_cli_probe_plain_form.py docs/reports/2026-10-14-claude-plain-form-mini-probe.md
```

---

### Task 7: Session request and observation handle pass-through in the evaluated provider path

**Files:**
- Modify: `orchestrator/workflow/evaluated/providers.py:215-258` (`launch_provider`), `:269-289` (`_prepare_provider_invocation`), add `provider_delivery_name_for_template`
- Modify: `orchestrator/workflow/evaluated/effect_execution.py:56-64` (keep behavior; `launch_provider` now returns the execution result, `perform_external` ignores it)
- Create: `tests/test_workflow_evaluated_provider_session_request.py`

**Interfaces:**
- Produces: `launch_provider(..., session_request=None, observation_handle=None, control=None) -> ProviderExecutionResult`; `_prepare_provider_invocation(node, resolved, result_path, executor, *, session_request=None)`; `provider_delivery_name_for_template(template) -> "legacy" | "file/2"` (`legacy` iff `template.session_support is not None and template.session_support.metadata_mode == OMP_JSON_STDOUT.value`, or `template.command_metadata_mode == OMP_JSON_STDOUT.value`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_workflow_evaluated_provider_session_request.py
"""The evaluated provider launcher forwards a session request and observation handle without changing ordinary calls."""
from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.providers.executor import ProviderExecutor
from orchestrator.providers.registry import ProviderRegistry
from orchestrator.providers.types import ProviderSessionMode, ProviderSessionRequest
from orchestrator.workflow.evaluated import providers as evaluated_providers
from orchestrator.workflow.evaluated.providers import ResolvedProviderInput, launch_provider, provider_delivery_name_for_template
from orchestrator.workflow.workspace_files import WorkspaceFiles
from tests.agent_session_shims import install_agent_shims, shim_requests

NODE = {"k": "perform", "class": "provider", "provider": "codex", "prompt": {"template": "t", "fills": []},
        "inputs": [], "dependencies": None, "policy": {}, "contract": {"kind": "output_bundle", "payload": {}},
        "result": {"kind": "record", "name": "R", "fields": [{"name": "ok", "type": {"kind": "primitive", "name": "Bool"}}]}}


def _resolved(text="prompt body") -> ResolvedProviderInput:
    return ResolvedProviderInput(prompt=text, policy={"model": "m", "effort": "low", "timeout_sec": 20}, input_parts={}, expected_outputs=[])


def _spy(monkeypatch):
    calls = []
    prepare = ProviderExecutor.prepare_invocation
    def spy(self, *args, **kwargs):
        calls.append(kwargs); return prepare(self, *args, **kwargs)
    monkeypatch.setattr(ProviderExecutor, "prepare_invocation", spy)
    return calls


def _launch(root, monkeypatch, **extra):
    install_agent_shims(root / "bin", monkeypatch, codex_home=root / "codex", claude_home=root / "claude",
                        plan={"codex": [{"mode": "success", "result": {"ok": True}}]})
    (root / "attempt").mkdir()
    attempt_files = WorkspaceFiles(root / "attempt"); workspace_files = WorkspaceFiles(root)
    try:
        return launch_provider(NODE, _resolved(), "workflow:main::run / x", executor=ProviderExecutor(root, ProviderRegistry(), provider_observation_enabled=False),
            attempt_files=attempt_files, workspace_files=workspace_files, result_path="attempt/result.json", **extra)
    finally:
        attempt_files.close(); workspace_files.close()


def test_ordinary_launch_keeps_session_request_none_and_base_command(tmp_path, monkeypatch) -> None:
    calls = _spy(monkeypatch)
    execution = _launch(tmp_path, monkeypatch)
    assert calls[0]["session_request"] is None and calls[0]["provider_session_dir"] is None
    assert execution.exit_code == 0 and execution.provider_session is None
    assert "--json" not in shim_requests(tmp_path)[0]["argv"]


def test_session_launch_selects_fresh_command_and_exposes_the_session(tmp_path, monkeypatch) -> None:
    calls = _spy(monkeypatch)
    execution = _launch(tmp_path, monkeypatch, session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH))
    assert calls[0]["session_request"].mode is ProviderSessionMode.FRESH
    assert execution.provider_session["session_id"] == shim_requests(tmp_path)[0]["session"]
    assert "--json" in shim_requests(tmp_path)[0]["argv"]
    assert (tmp_path / "attempt" / "prompt.txt").exists() and (tmp_path / "attempt" / "stdout.txt").exists()


def test_control_is_forwarded_and_binds_the_child_process_group(tmp_path, monkeypatch) -> None:
    from orchestrator.providers.control import ProviderExecutionControl
    control = ProviderExecutionControl()
    execution = _launch(tmp_path, monkeypatch, session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH), control=control)
    assert execution.exit_code == 0 and control.terminal_result is not None and control.terminal_result.pgid is not None


def test_preopened_observation_handle_receives_display_and_is_not_finalized(tmp_path, monkeypatch) -> None:
    class Handle:
        def __init__(self): self.chunks, self.finalized, self.health = [], 0, 0
        def append_display(self, data): self.chunks.append(data)
        def check_health(self): self.health += 1
        def finalize(self): self.finalized += 1
    handle = Handle()
    _launch(tmp_path, monkeypatch, session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH), observation_handle=handle)
    assert b"".join(handle.chunks) != b"" and handle.finalized == 0


@pytest.mark.parametrize("name, expected", [("codex", "file/2"), ("claude_unrestricted_workspace", "file/2"), ("omp", "legacy")])
def test_delivery_name_is_structural(name, expected) -> None:
    assert provider_delivery_name_for_template(ProviderRegistry().get(name)) == expected
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_workflow_evaluated_provider_session_request.py -q`
Expected: FAIL — `TypeError: launch_provider() got an unexpected keyword argument 'session_request'` / `ImportError: provider_delivery_name_for_template`.

- [ ] **Step 3: Implement the pass-through**

```python
# orchestrator/workflow/evaluated/providers.py
def provider_delivery_name_for_template(template) -> str:
    """`legacy` for OMP JSON transports (parent-materialized output), else the file/2 rendering."""
    omp = ProviderSessionMetadataMode.OMP_JSON_STDOUT.value
    session = template.session_support
    if template.command_metadata_mode == omp or (session is not None and session.metadata_mode == omp):
        return "legacy"
    return "file/2"


def launch_provider(node, resolved, identity, *, executor, attempt_files, workspace_files, result_path,
                    stream_output=False, launch_cwd=None, logical_workspace_root=None,
                    session_request=None, observation_handle=None, control=None):
    attempt_files.create("prompt.txt", resolved.prompt.encode("utf-8"), exclusive=True)
    stdout, stderr = b"", b""
    try:
        invocation, error = _prepare_provider_invocation(
            node, resolved, str(attempt_files.workspace / "result.json"), executor, session_request=session_request)
        if error is not None or invocation is None:
            raise ProviderPerformerError("provider_preparation_failed", str(error or "provider invocation missing"),
                                         exit_info={"error": error})
        execution = executor.execute(
            invocation, cwd=launch_cwd or workspace_files.workspace, stream_output=stream_output,
            **({"logical_workspace_root": logical_workspace_root} if logical_workspace_root is not None else {}),
            session_runtime=None, observation_handle=observation_handle, control=control,
            execution_env_overlay={"ORCHESTRATOR_PROVIDER_ATTEMPT_SITE_KEY": "sha256:" + sha256(identity.encode("utf-8")).hexdigest()},
        )
        stdout = execution.raw_stdout if execution.raw_stdout is not None else execution.stdout
        stderr = execution.stderr
        if execution.exit_code != 0 or execution.error is not None:
            raise _provider_execution_failure(execution)
    finally:
        attempt_files.create("stdout.txt", stdout, exclusive=True)
        attempt_files.create("stderr.txt", stderr, exclusive=True)
    if invocation.metadata_mode == ProviderSessionMetadataMode.OMP_JSON_STDOUT.value:
        ...unchanged...
    return execution
```

`_prepare_provider_invocation(node, resolved, result_path, executor, *, session_request=None)` passes `session_request=session_request` (was the literal `None`). `effect_execution.perform_external` is unchanged except it no longer binds the return value (`launch_provider(...)` then `return ExternalOutcome(result_path=path)`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_workflow_evaluated_provider_session_request.py tests/test_workflow_evaluated_providers.py tests/test_workflow_evaluated_provider_delivery.py tests/test_workflow_evaluated_invalidate_smoke.py -q`
Expected: PASS; `test_complete_provider_request_preserves_preparation_and_dispatch_contract` still sees `session_request=None`. `wc -l orchestrator/workflow/evaluated/providers.py` is about 352 (334 + the keyword forwarding and `provider_delivery_name_for_template`).

- [ ] **Step 5: Commit**

```bash
git add tests/test_workflow_evaluated_provider_session_request.py
git commit -m "feat: let the evaluated provider launcher forward a session request and observation handle" -- orchestrator/workflow/evaluated/providers.py orchestrator/workflow/evaluated/effect_execution.py tests/test_workflow_evaluated_provider_session_request.py
```

---

## Plan A closeout

- [ ] Run the broad suite in tmux: `pytest -q -n 16 --dist=worksteal` and record the pass/fail counts against the baseline run taken before Task 1 (record both in `docs/reports/2026-10-14-agent-sessions-plan-a-closeout.md`, a short file this step creates: commands, counts, commit hashes, and the statement that no provider was invoked).
- [ ] Verify the interface table above against the code with `grep -n` for each produced name; fix the table or the code, never leave them disagreeing, because Plan B starts from the table.
- [ ] Record the Task 6a verdict in the closeout; Plan B starts only on `end_turn` or `tool_ends_turn`.
- [ ] Commit: `git add docs/reports/2026-10-14-agent-sessions-plan-a-closeout.md && git commit -m "docs: record agent sessions plan A closeout" -- docs/reports/2026-10-14-agent-sessions-plan-a-closeout.md`.

Follow-on (not in this plan): the second slice, the `reviewed_change` coder variant with its turn shape selected then (owner decision D3).
