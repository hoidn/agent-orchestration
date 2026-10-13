# Provider Result Delivery Implementation Plan

> **For agentic workers:** Use `superpowers:subagent-driven-development` with
> `superpowers:test-driven-development` for behavior changes and
> `superpowers:verification-before-completion` before completion claims. The
> coordinator owns integration and final verification; use a reviewer distinct
> from the author. Tasks 1, 4 and 5 touch disjoint files and may run in
> parallel; Task 2 follows Task 1; Task 3 follows Task 2; Task 6 follows all.

**Status:** executed on 2026-10-13 on branch `feat/provider-result-delivery`; evidence in the [closeout](../reports/2026-10-13-provider-result-delivery-closeout.md). **Date:** 2026-10-13.
**Design:** [provider result delivery](../design/provider_result_delivery.md).
**Goal:** the evaluated route renders the delivery instruction for the file
transport it selects, replays committed effects under the rendering they
recorded, names the agent's reply in a missing-result failure, and gives
authors a typed shape for inability; the flat route composes identical bytes.
**Architecture:** one `delivery` keyword on the three structured-result
renderers, one additive provider input part, one diagnostic string, one
census script, one authoring recipe. No new target, header field, memo field,
transport or retry policy.
**Tech stack:** existing Python, Workflow Lisp, pytest, deterministic provider
fixtures under `tests/`; no new dependency.
**Tradeoff:** the `legacy` wording stays in the renderer for replay of
evaluated runs committed before this change, after the flat route is gone.

## Authorities And Selection

Read the design, then `specs/providers.md` (prompt delivery, contract
appended once), `specs/io.md` (provider request and attempt files),
`specs/state.md` (evaluated profile, `input_parts`, replay), the
[evaluated execution design](../design/workflow_lisp_evaluated_execution.md)
§§ on identity, request contract R1 to R12 and resume, and
[design principle 30](../design/workflow_language_design_principles.md#30-provider-attention-is-a-bounded-resource-the-language-conserves).
Paths are repository-root relative.

Owner selection, recorded 2026-10-13: the current rendering name is
`file/1`; providers bound to `omp` templates stay on `legacy` (their delivery
is final assistant text materialized by the parent, `specs/providers.md`).

## Baseline And Evidence Location

Drafting baseline: `main` at `3f897f33`. The four observed failures and the
67-attempt local tally are in the design's §Problem and §Appendix; the memo
and attempt files that produced them are under
`.orchestrate/runs/20261013T072050Z-1zoj84`,
`/home/ollie/Documents/agent-orchestration-smoke/.orchestrate/runs/20261013T053409Z-p016fp`
and `/tmp/agent-chess-execution-auf1856l/live/.orchestrate/runs/20261013T065534Z-zk5mh3`
(the last is temporary; copy its memo and the Black attempt directory into the
evidence directory before Task 0 ends).

At execution create `docs/reports/2026-10-13-provider-result-delivery-closeout.md`
as the single evidence owner: commands, exits, revisions, fixture hashes,
census tables before and after, and review records.

## Task 0 — Capture The Pre-Change Fixture

**Depends on:** nothing. **Must finish before any renderer edit.**
**Owners:** `tests/test_workflow_evaluated_resume_replay.py` fixtures;
evidence directory.

- [ ] With the unmodified package, run a two-provider evaluated program through public `run` with deterministic fixture providers, interrupting after the first provider commits (reuse the kill helpers of `tests/test_workflow_evaluated_resume_kills.py`). Retain the run root as a test fixture: `memo.jsonl`, `closed_program.json`, `run.json`, the committed attempt directory.
- [ ] Record the fixture's committed `input_parts` and confirm it has no `delivery` key.
- [ ] Capture, with the same package, the composed prompt bytes of one flat-route step (target 2.34 or earlier) and of one evaluated provider effect for each renderer shape: non-record root, record, tagged union. Store them beside the fixture as byte oracles for Task 1's `legacy` check.
- [ ] Run the baseline census (Task 4's script does not exist yet; use the pairing in the design's appendix) and store the table. Record when it was taken.

**Done:** fixture and oracles exist with hashes recorded in the closeout.

## Task 1 — Renderer Selector And Relpath Predicate

**Depends on:** Task 0 oracles.
**Modify:** `orchestrator/contracts/prompt_contract.py`,
`orchestrator/workflow/evaluated/prompts.py`.
**Tests:** `tests/test_prompt_contract.py`, `tests/test_workflow_evaluated_prompts.py`.

- [ ] Add failing tests: for each of `render_output_bundle_contract_block`, `_render_root_output_bundle_contract_block` and `render_variant_output_contract_block`, `delivery="legacy"` equals the Task 0 oracle bytes for the same payload; `delivery="file"` contains the `- path:` line and the schema section, and contains the relpath guidance line iff the schema contains a `relpath` type (walk nested record fields, lists and variants). Assert structure and presence, not wording.
- [ ] Implement `delivery: str = "legacy"` on the three renderers, a private `_schema_mentions_relpath(field)` predicate, and the `file` opening lines (action first, real path, environment variable as the same target, reply does not deliver). Keep `_RELPATH_GUIDANCE` unconditional under `legacy`.
- [ ] Thread `delivery` through `_output_contract_prompt` and `assemble_provider_prompt` with default `legacy`; no caller opts in yet.
- [ ] Adjust `tests/test_workflow_evaluated_prompts.py::*match_flat_executor*` so the comparison forces `legacy`, or compares everything except the structured-result block; state which in the test docstring.
- [ ] Run narrow selectors, then `pytest -q tests/test_prompt_contract*.py tests/test_workflow_evaluated_prompts.py`.

**Done:** both selectors render; the whole suite is unchanged because nothing opts in.

## Task 2 — Record And Replay The Delivery Part

**Depends on:** Task 1; the Task 0 fixture.
**Modify:** `orchestrator/workflow/evaluated/providers.py`
(`resolve_provider_input`), `orchestrator/workflow/evaluated/effect_inputs.py`
(`_resolve_effect_input`, `_replay_committed_effect`).
**Tests:** `tests/test_workflow_evaluated_resume_replay.py`,
`tests/test_workflow_evaluated_providers.py`,
`tests/test_workflow_evaluated_public_identity.py`.

- [ ] Add failing tests through public entries: (a) resuming the Task 0 fixture reuses the committed effect without dispatch, dispatches the pending one, and its `started`/`committed` rows carry `delivery` equal to `canonical_sha256("file/1")`; (b) a completed run resumed twice yields identical memo bytes; (c) a committed row whose `delivery` is an unknown digest refuses with `effect_input_diverged` naming `delivery`, before any launch; (d) a fresh run's composed `prompt.txt` opens its contract block with the file action (assert the path line precedes the schema; no wording).
- [ ] Implement: a two-entry table `{canonical_sha256("legacy"): "legacy", canonical_sha256("file/1"): "file"}`; `_resolve_effect_input` selects from `commit.data["input_parts"].get("delivery")` when a commit is present (absent → `legacy`, unknown → `_EffectInputDiverged`), else the current name; `resolve_provider_input` takes `delivery` and records the part. New attempts use `file/1` except omp-backed providers, which use `legacy` until the open question closes.
- [ ] Confirm `tests/test_workflow_evaluated_public_identity.py` still passes: blank lines and moves change no identity; the part is not identity, it is input evidence.
- [ ] Run narrow selectors, then `pytest -q tests/test_workflow_evaluated_resume_replay.py tests/test_workflow_evaluated_providers.py tests/test_workflow_evaluated_public_identity.py tests/test_workflow_evaluated_resume_kills.py`.

**Done:** scenario 1 of the design passes through `orchestrator resume`.

## Task 3 — Missing-Result Diagnostic Excerpt

**Depends on:** Task 2 (shares `providers.py`).
**Modify:** `orchestrator/workflow/evaluated/providers.py` (`provider_result`).
**Tests:** `tests/test_workflow_evaluated_providers.py`, `tests/test_workflow_evaluated_views.py`.

- [ ] Add failing tests: a fixture provider that prints a JSON string and exits 0 without writing the file fails with `provider_result_missing` whose failure message (the failed terminal row's `message`, the view's `error.message`, `report`; memo `exit_info` stays `{}` per `specs/state.md`) contains the reply's head (bounded at 240 characters, whitespace collapsed); one that prints nothing has the unchanged message; `report` shows the error string. No result is committed; `resume` dispatches attempt 2.
- [ ] Implement the excerpt read from the attempt's `stdout.txt` inside the existing `FileNotFoundError` branch, replacing non-printable characters before collapsing whitespace. Memo row shape unchanged.
- [ ] Run the two modules.

**Done:** scenario 2 of the design passes.

## Task 4 — Census Script

**Depends on:** nothing (reads memo files only).
**Create:** `scripts/provider_delivery_census.py` (under 150 lines).
**Tests:** `tests/test_provider_delivery_census.py` over a generated memo fixture.

- [ ] Pair `started` rows with their `committed`/`failed` rows by identity and attempt; identify provider attempts by the presence of `prompt.txt` in the attempt directory; print per attempt: run, site (last identity segment), attempt, outcome (`committed`, `missing`, other failure code), delivery name from the part (absent → `legacy`), first 120 characters of `stdout.txt`; then counts by site, delivery and outcome and a total broken down by delivery, so roots that hold both renderings (a run resumed across the change, an omp provider, the baseline runs) are never summed together. Accept several `--state-dir` arguments. Read-only; stdlib only.
- [ ] Run it on the three baseline roots and store the table in the closeout; it must reproduce the 4 missing attempts (69 attempts, 64 committed, 1 open).

**Done:** the baseline table is reproduced by the script.

## Task 5 — Authoring Recipe And Chess Example

**Depends on:** nothing for the recipe; Task 2 for removing the prompt paragraphs (Task 1 switches no caller over, so a live game before Task 2 would meet the old block with no authored paragraph). Nothing from this task is merged or smoked before Task 2 lands.
**Modify:** `docs/lisp_workflow_drafting_guide.md`,
`experiments/agent_chess/{chess.orc,white.md,black.md,README.md}`.
**Tests:** the chess example's existing compile check; a deterministic
`Blocked` fixture in `tests/test_workflow_evaluated_consumers.py` or the
example's own test module.

- [ ] Add the guide section "A step that may be unable to answer": the `MoveOutcome` union, `match` routing to the loop's typed outcome, and the statement that prompts carry no transport instructions because the runtime renders delivery.
- [ ] Change `chess.orc` to `:returns MoveOutcome` for both moves; route `Blocked` to a typed loop outcome (`:on-exhausted` stays). Keep inputs, defaults and the board command unchanged.
- [ ] Remove the transport paragraph from `white.md` and `black.md`. Update the README's description.
- [ ] Add a fixture test: White returns `Blocked`; the run commits it, routes it, and retries nothing.
- [ ] Compile the example with its header command; run one real round after Task 2 lands (smoke, below).

**Done:** scenario 3 of the design passes; the example carries no transport prose.

## Task 6 — Specs, Routing, Smoke, Reviews

**Depends on:** Tasks 1 to 5.
**Modify:** `specs/providers.md`, `specs/state.md`, `specs/versioning.md`
(v2.35 additions), `docs/capability_status_matrix.md`, `docs/index.md`,
`docs/design/README.md`, `docs/reports/2026-10-13-claude-missing-result-file.md`.

- [ ] Amend the specs as the design's §Documentation Impact lists; the `input_parts` sentence in `specs/state.md` gains `delivery` and the replay rule.
- [ ] Add the matrix row and the two routing rows; point the chess report's "Suggested general fix" at the design.
- [ ] Smoke: one real-provider chess round through public `run` with the shipped inputs, and `plan_review_execute` through `--dry-run`. Record commands, exits and the composed `prompt.txt` of the chess round.
- [ ] Census after: the same chess sites with the same models over at least ten attempts each; report by shape beside the baseline. Absence of improvement is a finding, not a blocker (design §Stop / Revise).
- [ ] Collect added or renamed tests with `pytest --collect-only`; run narrow owners, then `pytest -q -n 16 --dist=worksteal -m "not e2e"` in tmux; account for every new failure against the known RED baseline; relax nothing.
- [ ] Independent code/evidence review and spec/design review; apply accepted findings; coordinator inspects the final diff and receipts.

## Verification Recipes

```bash
pytest --collect-only -q tests/test_prompt_contract.py tests/test_workflow_evaluated_prompts.py \
  tests/test_workflow_evaluated_resume_replay.py tests/test_workflow_evaluated_providers.py \
  tests/test_provider_delivery_census.py
pytest -q tests/test_prompt_contract.py tests/test_prompt_contract_injection.py tests/test_workflow_evaluated_prompts.py
pytest -q tests/test_workflow_evaluated_resume_replay.py tests/test_workflow_evaluated_providers.py \
  tests/test_workflow_evaluated_public_identity.py tests/test_workflow_evaluated_resume_kills.py \
  tests/test_workflow_evaluated_views.py
python scripts/provider_delivery_census.py --state-dir .orchestrate/runs
python -m orchestrator compile experiments/agent_chess/chess.orc --source-root experiments \
  --entry-workflow agent_chess/chess::run \
  --provider-externs-file experiments/agent_chess/providers.json \
  --prompt-externs-file experiments/agent_chess/prompts.json \
  --command-boundaries-file experiments/agent_chess/commands.json
pytest -q -n 16 --dist=worksteal -m "not e2e"
```

Set `PYTHONPATH` to the checkout for every command run outside the repository
root; the editable install points at a stale worktree.

**Completion:** the design's success criteria hold with evidence in the
closeout; the flat route's oracle bytes are unchanged; the pre-change fixture
resumes without dispatching its committed effect; the chess example carries no
transport prose and handles `Blocked`; reviews are PASS.
