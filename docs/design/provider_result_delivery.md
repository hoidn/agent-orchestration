# Provider Result Delivery: Render The Transport The Runtime Selected

## Metadata

- **Title:** Provider result delivery rendering, versioned replay, and a typed channel for inability
- **Status:** implemented on 2026-10-13; execution record in the [closeout](../reports/2026-10-13-provider-result-delivery-closeout.md)
- **Nested presentation follow-on:** `file/2`; [implementation and verification](../reports/2026-10-13-provider-json-rendering.md)
- **Kind:** clarification and operational design
- **Owner:** evaluated runtime and prompt-contract maintainers
- **Reviewers:** one independent design reviewer; one code reviewer distinct from the implementer
- **Created:** 2026-10-13
- **Last material update:** 2026-10-13
- **Related docs / issues / plans:**
  [missing-result-file report](../reports/2026-10-13-claude-missing-result-file.md),
  [follow-up prompt review](../reports/2026-10-13-provider-prompt-review.md),
  [design principle 30](workflow_language_design_principles.md#30-provider-attention-is-a-bounded-resource-the-language-conserves),
  [evaluated execution](workflow_lisp_evaluated_execution.md),
  [prompt calculus](workflow_lisp_prompt_calculus.md),
  [executor retirement](workflow_lisp_executor_retirement.md),
  `specs/providers.md`, `specs/io.md`, `specs/state.md`;
  plan: [provider result delivery plan](../plans/2026-10-13-provider-result-delivery-plan.md)
- **Implementation target:** admitted evaluated targets 2.35 and later; no new target or admission change. The original through-2.34 byte comparison is historical qualification.

Execution scope after integration with [executor retirement](workflow_lisp_executor_retirement.md):
[the CLI cutoff](../../specs/cli.md#executable-support-boundary) rejects executable
entries through 2.34 and old-profile resume/invalidation. The original flat-route
comparisons and goals below refer to their pre-retirement release or retained
byte snapshots; they do not require a live flat executor in this package.
`legacy` rendering remains for replay of earlier evaluated effects and OMP
integration. The shared `orchestrator/workflow/prompting.py` composer remains
available; preserving its rendering contract is distinct from admitting flat
execution. Original qualification results remain in the linked closeout.

## Scope At Target 2.39

This design's delivery-rendering and ordinary replay rules describe composed
provider calls. Fragment-backed phased calls retain the `file/1` renderer for
their generated materialization contract even when ordinary calls select
`file/2`. The phased result file is a provisional candidate:
joint validation, natural shutdown and the evaluator's inline-proof memo commit
precede typed-result publication. The [phased contract](workflow_lisp_phased_contract_delivery.md#target-239-evaluated-migration)
and [State](../../specs/state.md#evaluated-phased-provider-attempts-target-239)
own phased commit, settlement and whole-visit recovery. The rendering selector
and authored phased-delivery policy are separate choices; this design does not
supply phased admission or its retry policy.

## Summary

Every ordinary file-transport provider call on the evaluated route delivers
its result through a file at the attempt's `result.json`, named to the agent by the
`ORCHESTRATOR_OUTPUT_BUNDLE_PATH` environment variable and by the contract
block's `- path:` line. The contract block the runtime appends to the prompt
does not say so. It opens with "Produce one JSON value", then offers a
conditional: write to the file if the variable is present, otherwise return
the value as assistant text. The runtime never accepts the second branch on
this route. Four of sixty-seven provider attempts observed on this machine
ended in `provider_result_missing`; in three of them the agent returned the
value, or a prose summary, in its reply.

This design makes the runtime render the delivery instruction for the
transport it selected, leading with the action and the real path; renders the
relpath guidance only when the contract contains a path type; records which
rendering a committed effect used, so that resume replays it without a false
`effect_input_diverged`; surfaces the agent's reply in the missing-result
diagnostic; and gives authors a typed way to say "I cannot" instead of
withholding the file. Authored prompts stop carrying transport instructions.
The original delivery change preserved flat-route composition bytes; that
pre-retirement comparison remains historical evidence, not current execution support.
OMP is a distinct, existing transport exception:
the parent exclusively materializes its validated normalized assistant output
into the attempt file before the same result validation. This is not a fallback
for an ordinary provider that omitted its file.

## Context And Authority

- `specs/providers.md` owns prompt delivery and the rule that the output
  contract is appended exactly once and the validated bundle remains result
  authority. `specs/io.md` ("Provider request and attempt files") states that
  the contract's `- path:` line is the attempt's `result.json` and that the
  evaluated route sets `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`. Neither spec fixes
  the block's wording.
- `specs/state.md` (evaluated profile) lists the provider `input_parts`:
  `declaration`, `values`, `policy`, `params`, `prompt`, `dependency_rows`,
  plus source and dependency digests. `prompt` is the SHA-256 of the fully
  assembled prompt, contract block included
  (`orchestrator/workflow/evaluated/providers.py::resolve_provider_input`).
  A committed result is reused on resume only when every recomputed part
  equals the recorded one (`effect_inputs.py::_replay_committed_effect`);
  a difference refuses with `effect_input_diverged` before any launch.
- The renderers live in `orchestrator/contracts/prompt_contract.py`:
  `render_output_bundle_contract_block` (records, delegating to
  `_render_root_output_bundle_contract_block` for a non-record root),
  and `render_variant_output_contract_block` (tagged unions). All three carry
  the conditional sentence and the unconditional `_RELPATH_GUIDANCE` line.
  Two callers share them: `orchestrator/workflow/evaluated/prompts.py`
  (evaluated route) and the retained shared `orchestrator/workflow/prompting.py`
  composer. Its original flat-executor caller is retired; shared composition
  checks do not require that executor.
- No test asserts the block's wording (repository rule: no tests of prompt
  phrasing). `tests/test_prompt_contract.py` and
  `tests/test_prompt_contract_injection.py` test structure and injection.
- [Design principle 30](workflow_language_design_principles.md#30-provider-attention-is-a-bounded-resource-the-language-conserves):
  an obligation the deterministic side can render must not be instructed in
  prose, and each guidance line in a rendered block is tracked debt that
  should name the missing mechanism.
- The [executor retirement design](workflow_lisp_executor_retirement.md)
  governs the selected executable cutoff and deletion. This design adds no
  executor port or exception to it.

## Problem

The observed failures, from local evaluated runs on 2026-10-13:

| Run, site, model | Authored transport paragraph present | What the agent did |
| --- | --- | --- |
| chess `zk5mh3`, Black, claude-fable-5-1 | no | Returned a fenced JSON string in its reply; no file |
| chess `1zoj84`, White, gpt-6.1-sol, early round | no | Printed a JSON object in its reply, also of the wrong shape (`{"position": ...}` for a `String` result); no file |
| chess `1zoj84`, White, gpt-6.1-sol, later round | yes | Declined explicitly: it would not invent a move without `python-chess`; wrote nothing |
| design smoke `p016fp`, `revised`, claude-sonnet-5-5 | no | Did the revision work and replied with a prose summary; no file |

Three shapes, not one. The first two are delivery: the contract names the
file but opens with the content and offers a reply as an alternative. The
third is not delivery at all: the agent had a legitimate reason not to
produce a `String`, and `:returns String` gave it no way to say so, so the
only honest move was to withhold the file and let the runtime fail the
attempt. The report's local fix, a paragraph in the authored prompt that
repeats the environment variable's name, is misplaced load under principle 30,
and it did not prevent the third case.

Two further defects compound this. The relpath guidance line is rendered for
every contract, including a bare `String`, where it is noise. And the
`provider_result_missing` failure says only "provider did not create <path>",
although the agent's reply is retained in the attempt's `stdout.txt`; the
operator has to open the file to learn which of the three shapes occurred.

Fixing the wording is not a local patch because the assembled prompt is
effect-input identity. Changing the renderer changes the `prompt` part of
every provider effect, so a run that committed effects under the old wording
could not resume: a hundred-round chess game would have to start over.

## Goals And Non-Goals

Goals:

1. On the evaluated route, the contract block states the selected delivery
   mechanism first, with the real result path, and offers no alternative.
2. Guidance prose that compensates for an absent mechanism is rendered only
   when the mechanism's input is present (relpath guidance only with a path
   type in the contract).
3. A run that committed provider effects under an earlier rendering resumes
   with those effects reused, never redispatched, and never refused for the
   rendering difference alone.
4. Original qualification: through-2.34 flat composition bytes remain
   identical in the retained-release comparison or stored byte oracles.
   Current checks preserve shared/`legacy` rendering without old execution.
5. A `provider_result_missing` failure names what the agent returned instead,
   without materializing it as a result.
6. Authors have a documented typed shape for a step that may be unable to
   answer, and the chess example uses it.
7. The effect of the rendering change is measured, not asserted.

Non-goals:

- Adding an assistant-text fallback for ordinary file-transport providers.
  OMP's existing normalized-text transport exception is governed by
  `specs/providers.md`; after parent materialization, the attempt file remains
  the result validator's input.
- Changing the result contract, validation, the memo wire beyond one additive
  provider input part, or the run header.
- Rendering changes for the flat route or for `expected_outputs` output
  positions; neither carries the conditional sentence's defect in the
  observed failures; the flat executable route is retired.
- A new provider transport, a prompt-position experiment beyond the measured
  variant named in §Open Questions, or any retry policy change.

## Decision

Render the delivery instruction for the transport the runtime selected, and
version that rendering per committed effect.

- The three structured-result renderers take a `delivery` selector. `legacy`
  reproduces the pre-change text exactly and remains the default for shared
  callers, earlier evaluated-effect replay and OMP integration.
  `file` preserves the evaluated route's `file/1` block: the write action first,
  pointing at the `- path:` line (the path itself appears exactly once in the
  prompt, rule R3 of the evaluated design), the environment variable as the
  same target, the statement that a reply does not deliver, then the schema. The relpath guidance is rendered
  under `file` only when the contract's schema contains a `relpath` type.
- New ordinary evaluated calls select `file/2`: the action and single path
  lead a nested JSON-shaped type notation. It displays real keys, complete
  union alternatives and guidance at the corresponding fields. Generated
  aliases and JSON pointers remain internal. The
  [JSON rendering plan](../plans/2026-10-13-provider-json-contract-rendering-plan.md)
  records this presentation change; transport and result validation stay the same.
- The evaluated route records the rendering it used as a provider input part,
  `delivery`, whose value is the canonical digest of the rendering name
  (`"legacy"`, `"file/1"` or `"file/2"`). On replay of a committed effect the runtime reads
  the committed row's `delivery` part, absent meaning `legacy`, and renders
  with that selector before comparing parts. New attempts use the current
  selector, `file/2`, for ordinary file transport; OMP keeps `legacy`.
- The `provider_result_missing` message carries a bounded excerpt of the
  attempt's `stdout.txt` (first 240 characters, whitespace collapsed) after
  the path. The memo `failed` row is unchanged (`specs/state.md` fixes its
  `exit_info` as `{}` for this code); the excerpt travels in the failure
  message, which reaches the failed terminal row's `message`, the view's
  `error.message` and `report`.
- Authors express inability with a tagged union result; the drafting guide
  documents the shape and the chess workflow adopts it. Authored prompts drop
  transport paragraphs.
- A census script over memo files reports provider attempts by site and
  outcome with the reply's head, so the rendering's effect can be compared
  before and after on the same sites and models.

Alternatives considered:

| Alternative | Why not |
| --- | --- |
| Keep the authored transport paragraph as the fix | Misplaced load (principle 30); duplicates the runtime's block; did not prevent the explicit-refusal case; must be copied into every prompt |
| Change the wording and accept one-time `effect_input_diverged` on in-flight runs | Breaks resume of every evaluated run with committed provider effects; contradicts the resume contract that a changed runtime must not force re-execution of committed work |
| Pin the rendering version in the run header | Needs a header profile change (`specs/state.md` fixes exactly fourteen keys) and a schema bump for an additive fact that the memo row can carry |
| Exclude the contract block from the `prompt` part | Also changes the recomputed digest of every existing row; the block's content (path, schema) is legitimately input |
| Treat an ordinary file-transport provider's assistant reply as a fallback result | Silently substitutes another delivery channel when the required file is absent; rejected by `specs/io.md` and the evaluated design. OMP's explicitly selected normalized-text transport is a separate existing contract and still undergoes result validation |
| Add a new memo field for the stdout excerpt | Memo wire change for a diagnostic the attempt directory already retains; the error string suffices |

Tradeoffs accepted: the `legacy` rendering stays in the codebase after the
flat route is deleted, because evaluated runs committed before this change
replay it; it is one string per renderer. The `file/1` wording is a new
identity input for runs that used it. `file/2` adds nested type presentation;
subsequent byte changes require another rendering name. Both historical
renderings remain replay obligations.

Left open: see §Open Questions (omp transport; the top-of-prompt delivery
line as a measured variant).

## Design Details

### Rendering

```text
assemble_provider_prompt(node, operands, ..., result_path, delivery)
  -> _output_contract_prompt(..., delivery)
     -> render_output_bundle_contract_block(payload, delivery=...)
        | render_variant_output_contract_block(payload, delivery=...)
        | file/2 nested shape from the checked result descriptor
```

Historical `delivery="file"` block for a non-record root (illustrative; the exact text
is owned by the renderer and is not a test oracle):

```text
## Output Contract
Write one JSON value to the file on the `- path:` line below, then stop.
Create it with a file-writing or shell tool before you finish. The
environment variable ORCHESTRATOR_OUTPUT_BUNDLE_PATH names the same file.
Returning the value in your reply does not deliver it.
- path: .orchestrate/runs/<run_id>/effects/<effect>/attempt-<n>/result.json
  format: JSON value
  type: string
```

Under `file/1`, records and tagged unions keep their field and discriminant sections; only
the opening sentences change. The `- path:` line remains the attempt's
workspace-relative `result.json` (R3). The relpath guidance line is appended
only when the schema spec, walked recursively, contains a `relpath` type.

Under `file/2`, the checked result descriptor supplies the nested structure,
including empty records, through the existing transport-schema converter.
The validated contract payload supplies constraints and authored guidance.
Their JSON pointers are decoded internally to attach annotations to actual
nodes; generated field names are never split to infer nesting. An explicitly
labelled type notation uses markers such as `<string>` and `<finite number>`;
only authored examples appear as example data. Complete union alternatives
repeat common fields to avoid a separate merge notation. Optional values
permit `null`; omission is described separately where the existing contract
permits it. Root scalar and `Value` results stay direct roots. Path notes
appear only at path nodes, and authored keys, tags and annotations are
JSON-encoded. The renderer cannot recover guidance already absent from the
compiled payload, including flattened empty-record guidance.

`delivery="legacy"` returns the pre-change text. The retained shared composer
(`orchestrator/workflow/prompting.py`) uses the renderer's default and preserves
those bytes. This remains a valid shared-composer check; it does not compile,
run or resume a retired flat entry.

### Identity and replay

`resolve_provider_input` gains a `delivery` argument and records
`parts["delivery"] = canonical_sha256(delivery_name)`. `_resolve_effect_input`
passes `commit.data["input_parts"].get("delivery")` when a commit is present,
mapping the digest back to a known rendering name and
treating absence as `legacy`; an unknown digest refuses with
`effect_input_diverged` naming the part. Without a commit it passes the
current name, `file/2`, for ordinary file transport (`legacy` for OMP).
The `started` row of a new attempt therefore carries
the part, and a later runtime replays it by the same rule.

Historical flat runs recorded no `delivery` part; this change does not rewrite
their data. Their execution/replay is retired under the CLI cutoff.

### Diagnostics

`provider_result` (evaluated `providers.py`) reads `stdout.txt` from the
attempt directory on `FileNotFoundError` of `result.json` and appends the
excerpt to the message. The excerpt is text for operators; nothing parses it.
Views and `report` already surface the failure message.

### Authoring

Drafting guide recipe, with the chess workflow as the example:

```lisp
(defunion MoveOutcome
  (Moved (position String))
  (Blocked (reason String)))

(provider-result providers.white :prompt prompts.white
  :inputs (state.position) :returns MoveOutcome)
```

`match` routes `Blocked` to a typed outcome of the loop instead of leaving the
runtime to fail the attempt. The chess example's `white.md` and `black.md`
drop the transport paragraph.

### Measurement

`scripts/provider_delivery_census.py --state-dir DIR ...` reads each
`memo.jsonl`, pairs `started` with `committed` or `failed` rows, and prints
one row per provider attempt: run, site, attempt, outcome, `delivery` name,
and the first 120 characters of `stdout.txt`, followed by counts by site and
outcome. It reads nothing but memo rows and attempt files and writes nothing.

## Contracts And Interfaces

| Contract | Old | New | Compatibility |
| --- | --- | --- | --- |
| Rendered contract block, evaluated route | Content-first sentence with a conditional alternative; relpath guidance always | Delivery-first file action and nested type shape; path notes attached to path nodes | New runs only; replay of committed rows renders what they recorded |
| Historical flat-route contract block / retained shared rendering | unchanged | unchanged | Original retained-release or snapshot comparison; no current flat execution |
| Provider `input_parts` (`specs/state.md`) | `declaration`, `values`, `policy`, `params`, `prompt`, `dependency_rows`, sources, dependencies | plus `delivery` | Additive; absence means `legacy` on replay |
| `provider_result_missing` failure message (terminal row `message`, view `error.message`, `report`) | `provider did not create <path>` | same, plus `; reply began: <excerpt>` when `stdout.txt` is non-empty | Message text only; the memo `failed` row keeps `exit_info` `{}` |
| Renderer Python API | `render_*_contract_block(payload, *, render_nominal_names=False)` | plus keyword `delivery="legacy"` | Existing callers unchanged |
| Authored prompt assets | May carry transport prose | Should not; the runtime renders delivery | Guidance, not enforcement |

Validation is unchanged: missing file, invalid JSON, wrong type and
must-exist checks keep their diagnostics.

## Dependencies And Sequencing

- No dependency on the retirement or consolidation work; the change is
  confined to the evaluated route and the shared renderer's new keyword.
- The spec amendments to `specs/providers.md` and `specs/state.md` land in
  the same change as the code.
- The authoring recipe and the chess example can land independently.
- The omp transport question in §Open Questions must be answered before
  `file/1` is rendered for an omp-backed provider; until then such providers
  render `legacy` and record it.

## Invariants And Failure Modes

- The result validator reads only the attempt's result file. Ordinary
  providers must create it; OMP's parent exclusively creates it from successful
  normalized transport output. Raw stdout, stderr and an ordinary provider's
  reply cannot substitute for the file. Existing or provider-planted leaves
  are never overwritten or accepted by OMP materialization. Phased candidates
  follow the separate publication contract above; the evaluated memo owns
  committed reuse.
- The contract block is appended exactly once (`specs/providers.md`).
- A committed effect is reused on resume if and only if its recorded input
  parts equal the recomputed ones, with the recomputation using the recorded
  `delivery`; a rendering change alone never diverges a committed effect.
- Retained `legacy`/shared-composer rendering matches its byte oracles; the
  original flat-route comparison is historical qualification only.
- An unknown `delivery` digest in a committed row refuses with
  `effect_input_diverged` and names the part; it never guesses a rendering.
- The stdout excerpt is bounded and never parsed.
- A `Blocked` variant is an ordinary committed result; it is never retried
  by the runtime.

## Security, Operations, And Performance

The excerpt in the failure message repeats up to 240 characters of provider
stdout into the terminal row of `memo.jsonl` and derived views, which already retain the full
`stdout.txt`; no new data class is exposed. The nested renderer walks the
existing checked schema; its performance has not been benchmarked. No
deployment or credential impact.

## Evidence And Implementation Boundaries

- Default path: `assemble_provider_prompt` with `delivery="file/2"` for new
  ordinary attempts, reached through public `run` and `resume`.
- The retained shared `PromptComposer` keeps the renderer default; direct
  shared-composition checks compare its bytes with retained snapshots. The
  original flat-step before/after comparison belongs to the pre-retirement
  release and does not require the removed executor.
- Replay of rows without the part exercises `legacy`; a fixture run recorded
  before the change, resumed after it, proves reuse through the public entry.
- The census script is evidence tooling, not a source of truth.

## Compatibility And Migration

Admitted evaluated runs started before delivery versioning resume unchanged: their committed
provider rows carry no `delivery` part and replay with `legacy`. Committed
`file/1` rows likewise replay their recorded bytes. The next new ordinary
attempt selects `file/2`, so one run may hold several rendering versions;
that is by design. No migration of existing memos or headers. Removing a
recorded selector would make its rows diverge. Any rollback must preserve
known selectors for replay and select a different version for new attempts.

## Verification Strategy

- Historical renderer: for each of the three renderers and both old selectors, the block
  contains the attempt path line and the schema; under `file` the relpath
  guidance is present if and only if the schema contains a `relpath`; under
  `legacy` the output equals a stored pre-change rendering for the same
  payload (structural and byte checks, no phrasing assertions).
- Current renderer: nested keys, complete alternatives, constraints and
  encoded guidance match the checked contract; direct roots, empty records,
  nullable/omittable fields and containers preserve their semantics.
- Identity: a public evaluated run with two provider effects, interrupted after
  the first commit under `legacy` or `file/1` rendering (fixtures captured
  before their successor), resumed after the change: the first effect is reused with no
  dispatch, the second runs with `file/2` and records the part; completed
  resume twice yields identical memo bytes.
- Divergence: a committed row with a fabricated unknown `delivery` digest
  refuses with `effect_input_diverged` naming `delivery`, before any launch.
- Shared composition: exercise the retained `PromptComposer` in
  `orchestrator/workflow/prompting.py` against stored byte oracles. Historical
  flat-executor comparisons require their original release/environment or
  retained snapshots, never an executable entry through 2.34 in this package.
- Diagnostic: a provider that writes no file but prints text fails with
  `provider_result_missing` whose error contains the excerpt; one that prints
  nothing has no excerpt suffix.
- Authoring: the chess workflow compiles with `MoveOutcome` and a deterministic
  provider returning `Blocked` routes to the loop's typed outcome.
- Initial delivery smoke: one real-provider round of the chess workflow and
  one `plan_review_execute` dry run. The nested-presentation follow-on uses
  public compile/run/resume with a fake provider and distinct guided contracts;
  this proves contract flow and replay, not improved model compliance.
- Measurement: the census over the four runs in §Problem reproduces 4 missing
  of 67 before the change; after it, the same sites with the same models over
  at least ten attempts each, reported by shape.

## Declarative Acceptance / Integration Scenarios

1. **Resume across the rendering change.** Given a run captured under the
   pre-change package with provider effect A committed and B pending, resuming
   with the post-change package through `orchestrator resume` reuses A without
   dispatch, dispatches B with a prompt whose contract block leads with the
   file action, records `delivery` on B's rows, and completes with the same
   terminal value as an uninterrupted run. Real provider transport is a
   deterministic fixture.
2. **Missing file with a reply.** A fixture provider prints a JSON string and
   exits 0 without writing the file: the attempt fails with
   `provider_result_missing`, the memo error carries the reply's head, no
   result is committed, and `resume` dispatches attempt 2.
3. **Typed inability.** The chess workflow with a fixture White that returns
   `Blocked` commits that result, routes through `match`, and ends the loop
   with its typed outcome; no attempt is retried.

## Success Criteria

All verification items pass through public entries; `specs/providers.md`,
`specs/state.md` and `specs/versioning.md` carry the amendments; the drafting
guide has the inability recipe; the chess prompts carry no transport prose;
the census script runs on the local runs; independent code and spec review
pass; the coordinator inspects the diff and receipts.

## Stop / Revise Criteria

- Replay cannot select the rendering from the committed row without a header
  change: return to design.
- Any provider on the evaluated route delivers results other than through the
  file (see the omp question): the selector gains a case or the design is
  revised before `file/1` reaches that provider.
- Measurement shows no reduction in the delivery shapes after at least ten
  attempts per site: keep the rendering (it is still correct under principle
  30) but revisit the top-of-prompt variant.

## Documentation Impact

- `specs/providers.md`: delivery instruction is rendered for the selected
  transport; the evaluated route selects the file.
- `specs/state.md`: provider `input_parts` gain `delivery`; replay rule.
- `specs/versioning.md`: v2.35 additions bullet.
- `docs/design/workflow_lisp_evaluated_execution.md`: the parity statements
  (R4, the admitted-class table, §8.4 and the feasibility row) say the prompt
  originally compared with the flat route apart from R3; those historical
  comparisons also record the contract block's opening-line change, without
  restoring a current flat-execution obligation.
- `docs/lisp_workflow_drafting_guide.md`: "A step that may be unable to
  answer" recipe; note that prompts carry no transport instructions.
- `docs/capability_status_matrix.md`: row for delivery rendering.
- `docs/index.md`, `docs/design/README.md`: routing rows.
- `docs/reports/2026-10-13-claude-missing-result-file.md`: pointer to this
  design; its "general fix" is this document.
- `experiments/agent_chess/{white,black}.md`, `chess.orc`, README.

## Implementation Handoff

Phases, in the order the plan executes them:

1. Renderer selector and relpath predicate in
   `orchestrator/contracts/prompt_contract.py`; evaluated composer threads
   `delivery` in `orchestrator/workflow/evaluated/prompts.py`.
2. Identity part and replay selection in
   `orchestrator/workflow/evaluated/providers.py` and
   `effect_inputs.py`; pre-change fixture capture before touching either.
3. Diagnostic excerpt in `orchestrator/workflow/evaluated/providers.py`.
4. Census script `scripts/provider_delivery_census.py`.
5. Authoring recipe, chess example, prompt cleanup.
6. Specs, guide, matrix, routing; smoke; reviews.

Original qualification compared evaluated composition with the flat executor
before retirement, forcing `legacy` or excluding the structured-result block.
Current `tests/test_workflow_evaluated_prompts.py` checks retained shared
composition/captured dataflow without the flat executor. Use the recorded
pre-change fixture and byte oracles; reproducing the original capture requires
its retained release/environment. The `file` rendering still keeps the
`- path:` line the specs cite.

Safe first step: phase 1 with the selector defaulting to `legacy`, so that the
whole suite is unchanged until the evaluated composer opts in.

## Open Questions

| Question | Owner | Blocking |
| --- | --- | --- |
| Resolved 2026-10-13: `specs/providers.md` states that OMP JSON-transport children never receive the binding; they emit one validated final assistant JSON value that the parent materializes. Providers bound to `omp` templates therefore keep `legacy`, whose text includes that branch; a dedicated text rendering is later work. Owner selection recorded in the plan | owner | No |
| Does a one-line delivery statement at the top of a long prompt (the 24 KB design case) reduce prose-only replies? | measured after phase 4, under a new rendering version if adopted (`file/2` is already assigned to nested presentation) | No |
| Should `report` render the excerpt distinctly from the error code? | views maintainer | No |

## Appendix

Local baseline on 2026-10-13, evaluated runs under the main checkout, the
`-smoke`, `-rerun` and `-repl` worktrees and the chess live workspace, as
reported by `scripts/provider_delivery_census.py`: 69 provider attempts, of
which 64 committed, 4 `provider_result_missing` (the sites and shapes in
§Problem) and 1 open (a `started` row with no end row, in the `-repl`
worktree's run `9azbib`). An earlier hand count gave 67 because it skipped
the open attempt and one commit; open attempts do not count toward a miss
rate.
