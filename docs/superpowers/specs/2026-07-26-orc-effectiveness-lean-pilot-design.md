# `.orc` Effectiveness Lean Pilot Design

## Metadata

- **Status:** accepted by owner direction for implementation
- **Kind:** experiment design and architecture decision
- **Owner:** agent-orchestration maintainers
- **Domain owner for a prospective PtychoPINN benchmark:** PtychoPINN maintainers
- **Reviewers:** owner-directed program revision on 2026-07-26; implementation reviews occur only at the three named evidence gates
- **Created:** 2026-07-26
- **Last material update:** 2026-07-27
- **Supersedes:** [the 2026-07-23 evidence-platform experiment design](2026-07-23-orc-vs-one-shot-experiment-design.md)
- **Implementation plan:** [`.orc` Effectiveness Lean Pilot Implementation Plan](../plans/2026-07-26-orc-effectiveness-lean-pilot.md)
- **Related evidence:** [effectiveness doubts report](../../reports/2026-07-22-compelling-example-search-and-effectiveness-doubts.md) and [historical control-plane feasibility report](../../reports/2026-07-23-experiment-control-plane-feasibility.md)
- **Implementation target:** one minimal three-treatment pilot harness, evaluator calibration, a controlled-task pilot, a deterministic readiness record, and an explicit owner-decision handoff

Purpose: determine whether further investment in a realistic `.orc` versus one-shot comparison is justified before building a reusable experiment platform or completing unrelated runtime capabilities.

Authority: this document owns the current experiment design and claim boundaries. Normative Workflow Lisp and provider behavior remains owned by `specs/`, accepted component designs, and current tests. This design does not change runtime behavior, authorize a PtychoPINN product change, or promote a benchmark output.

Copy safety: this is a target experiment design. It is not evidence that the pilot has run or that `.orc` is effective.

Implementation status: the reusable contracts, workspace, runner, treatment
parity, evaluation, and reporting slices are implemented and focused green.
The oversized runner, evaluation, and reporting modules have been split into
thin public facades over private responsibility owners, and their scoped
quality re-review approved. Calibration is the active next step. No
calibration provider session, pilot lock, smoke, or live block has run.

## Summary

Build the smallest reproducible apparatus that can answer two preliminary questions:

1. Does the complete bounded ORC method show enough directional product-quality value over one ordinary provider invocation to justify a realistic prospective trial?
2. Holding prompts, phase topology, provider policy, and call bounds constant, does the `.orc` representation/runtime behave differently from a minimal conventional coordinator?

The first live tranche is a three-treatment, three-block pilot on the controlled `A1` nanoBragg entrypoint task:

- `DIRECT`: exactly one ordinary provider invocation;
- `COORDINATOR`: the frozen ORC topology implemented by a small conventional Python coordinator; and
- `ORC`: the same topology implemented as one `.orc` workflow.

`DIRECT` versus `ORC` estimates end-to-end method effectiveness, including additional inference, decomposition, review, and correction. `COORDINATOR` versus `ORC` estimates the marginal representation/runtime effect only when parity checks pass. No first-tranche comparison isolates additional inference from orchestration topology.

The pilot is exploratory. It produces no confirmatory, general-domain, or prospective PtychoPINN claim. A prospective `F1`/`F2` plan is written only after the pilot reports reviewer discrimination, treatment viability, discordance, elapsed time, provider usage, and observed cost. There is no default ten-pair confirmatory series.

The implementation retains five public responsibility surfaces under
`orchestrator.experiments`: contracts, workspace, runner, evaluation, and
reporting. Runner, evaluation, and reporting are thin facades over private
modules split by the already-defined responsibilities. Every production
module in that package is capped at 500 physical lines. This is code
ownership, not a broader experiment API or an expansion of the four-record
evidence model.

Provider-phase information isolation is an independent runtime capability. Its public run/resume completion is not a prerequisite for deterministic apparatus work, evaluator calibration, treatment parity, or this exploratory controlled-task pilot. Any visibility limitation of the actual pilot environment is recorded and narrows the claim; it does not silently become a claim of strict causal isolation.

## Context And Authority

The superseded 2026-07-23 design correctly identified distinct estimands, paired inputs, blinded evaluation, method-failure accounting, and downstream-consumer consequences. It also coupled the entire experiment to a reusable provider-isolation subsystem, planned thirty-five schemas and thirteen functional package modules, placed the same-topology control after the prospective trial, and supplied no fixed statistical operating rule.

The historical `G0_BLOCKED` report remains valid evidence about the runtime tested on 2026-07-23. It prevents claims that the current public runtime enforces strict phase visibility. It does not require every later exploratory experiment to wait for a reusable public isolation feature when the later experiment explicitly disclaims that stronger claim.

The existing operational record already supplies observational evidence for durable execution and resume. This pilot therefore does not include interruption/resume efficacy, prompt A/B tests, unrelated-domain transfer, or general runtime hardening.

## Problem

The project needs decision-useful evidence about whether `.orc` orchestration improves realistic repository work enough to justify its additional calls, authoring complexity, and runtime surface. The immediate uncertainty is the size and consistency of any product-quality effect, not whether the project can build a comprehensive evidence platform.

The prior program tried to answer four questions in one implementation effort:

- practical end-to-end method value;
- mechanism value;
- `.orc` representation/runtime value;
- transfer to prospective architecture work.

That ordering delayed all experimental data behind a large reusable prerequisite and scheduled the representation control after the headline prospective comparison. A clean but underpowered result would not justify that implementation burden.

## Goals And Non-Goals

### Goals

- Freeze all three treatment definitions before any live pilot outcome exists.
- Start each block from byte-identical source archives and the same task contract.
- Keep provider family, model, effort, tools, timeout, and visible task inputs equal where the treatments permit.
- Define `DIRECT` as exactly one provider invocation with normal repository inspection, editing, and test execution inside that invocation.
- Make `COORDINATOR` and `ORC` logically equivalent in prompts, result contracts, phase order, branch bounds, provider policy, and visible checks.
- Calibrate the blinded reviewers on static comparisons with known expected outcomes before live treatment evaluation.
- Preserve treatment-specific compiler, runtime, provider, timeout, and output failures as outcomes.
- Report product quality, viability, elapsed time, provider calls, observed usage/cost, and reviewer disagreement separately.
- Produce enough pilot evidence to choose one of three next actions: stop, revise and repeat the controlled pilot, or authorize a separately planned prospective PtychoPINN `F1`/`F2` series.
- Require a numeric decision policy and sample-size calculation before any confirmatory or prospective claim.

### Non-Goals

- Building a general experiment service or persistent experiment lifecycle engine.
- Completing or weakening provider-phase information isolation.
- Claiming strict history, phase, network, or control-plane non-interference from the first-tranche environment.
- Isolating extra inference from topology in the first tranche.
- Running `E2` review/fix, `E4` prompt, `E5` transfer, or `E6` resume experiments.
- Making a universal `.orc`, Workflow Lisp, or agent-orchestration effectiveness claim.
- Treating `A1` as representative of PtychoPINN architecture work.
- Automatically adopting any benchmark candidate into PtychoPINN.
- Creating schemas for intermediate events that are neither cross-process contracts nor final evidence.

## Decision

### 1. Use a three-treatment block

Every live block contains opaque assignments of `DIRECT`, `COORDINATOR`, and `ORC` to three fresh source trees. All three start within one bounded launch window.

Two comparisons are predeclared:

| Comparison | Valid interpretation | Invalid interpretation |
| --- | --- | --- |
| `DIRECT` versus `ORC` | Complete-method directional effectiveness and cost | `.orc` language causality or compute-matched advantage |
| `COORDINATOR` versus `ORC` | Marginal representation/runtime behavior when parity passes | General orchestration value |

A future budget-matched plain treatment is allowed only under a new design if the owner wants to separate extra inference from topology. It is not inferred from either first-tranche contrast.

### 2. Freeze the coordinator before live outcomes

The conventional coordinator must exist, pass deterministic route parity, and have its exact source digest bound into the pilot lock before the first live block starts. Its implementation cannot be authored or repaired using observed live treatment outcomes without creating a new pilot definition.

### 3. Calibrate evaluation before live scoring

Two independent blinded reviewers evaluate three static calibration
comparisons built from the separate `A0` linear-classifier port:

1. an evaluator-passing `A0` reference candidate versus the unsolved `A0`
   base, with opaque labels;
2. the same comparison with labels reversed; and
3. the `A0` reference candidate versus a byte-identical copy.

Each reviewer/package judgment runs in a fresh isolated session, for six
sessions per calibration round. No session sees both label orientations or the
identity package.

The frozen `A0` evaluator must independently prove the reference passes and
the base fails before either reviewer receives a package. Calibration passes
only when both reviewers prefer the reference in both directional cases and
return `TIE` or `INDETERMINATE` for the identity case. A third adjudicator does
not convert a failed calibration into a pass. One rubric/package revision is
allowed before any live candidate is shown. If the second locked calibration
round fails, the pilot stops as `CALIBRATION_FAILED`; it does not add reviewers
or relax the criterion.

No reviewer sees an `A1` reference implementation or prior `A1` candidate
during calibration.

Calibration is governed by a prospective, strict
`calibration-lock.v1` controller artifact. It is control apparatus, not a
fifth cross-process evidence-record kind. Before package creation, the
controller verifies its exact schema and identity; round/revision and failed
predecessor semantics; task and reference-patch bytes; rubric, selected-file,
evaluator-module, dynamically loaded oracle, environment, visible-check,
hidden-evaluator, expected-contrast, reviewer, package, and mapping-seed
bindings. Its closed `base_identity` contains exactly the repository identity,
revision identity, digest of the complete unexcluded base archive, and digest
of the projected product manifest. Package construction receives that identity
explicitly, requires exact equality with the lock, and freshly freezes both the
complete and projected base trees before accepting either digest.

Round 1 is revision 0 and accepts no predecessor. The only optional retry is
round 2/revision 1. It requires the explicit retained round-1/revision-0 lock,
its canonical on-disk controller mapping and explicit controller root, and all
six prior review records. The predecessor digest and declared failed status
must match the retained lock, the complete prior round must still validate, and
its result must be a substantive reference-preference, label-order, or
identity-control failure. A missing, fabricated, passing, malformed, or merely
session-reuse predecessor fails closed.

The lock also owns one closed `reviewer_execution` object because calibration
precedes `pilot_lock.v1`: provider family, model, reasoning effort, tool policy,
positive timeout, a canonical absolute resolved regular CLI entry path with
exact file digest and version identity, a closed environment identity with
nonempty unique allowed-key names and a credential-key subset, and the
invocation-payload-schema digest. Calibration package construction receives
that execution object explicitly from its caller, verifies its complete shape
and CLI bytes, and requires exact equality with the prospective lock. No
provider, model, CLI, environment, credential, tool, or timeout value is
inferred from ambient state. This contract binds later execution but does not
itself launch a reviewer or add another evidence-record kind.

### 4. Run only an exploratory controlled-task pilot first

The first live series targets exactly three valid three-treatment blocks on
`A1` within a fixed maximum of five live block attempts. Before the pilot lock
exists, one provider-free integration gate exercises all three frozen treatment
argv values through the real staged launchers and standard manifests with a
test-only provider executable prepended to `PATH`. The test asserts that this
provider executable and corresponding `PATH` value are the only
production-environment differences. After the lock exists, one unscored
real-provider apparatus smoke precedes the live series. Neither gate contributes
treatment evidence.

The smoke uses the exact locked closed environment and standard manifests. Its
gate is mechanical: all three attempt executions must be recorded, all process
groups quiesced, all products frozen, call accounting parsed, and blind
packages generated. A treatment-specific failure is preserved and does not
authorize treatment changes or prevent the locked live series. A shared
apparatus defect stops the pilot as `STOP_APPARATUS_NOT_VIABLE`; repairing it
requires a separately locked rerun, not mutation of this pilot.

Three valid blocks are directional evidence only. The program reports every
valid, invalid, aborted, or surviving `STARTED` attempt and does not extend the
series after viewing results. If three valid blocks do not accrue within five
live attempts, the pilot stops as `INSUFFICIENT_VALID_BLOCKS`. Any additional
controlled series receives a new lock and denominator.

### 5. Make prospective work conditional

A future prospective PtychoPINN plan may be authorized only when the locked pilot report establishes all of the following facts:

- all three treatments can run from the same source/task contract;
- coordinator/ORC parity passed before live execution;
- reviewers passed calibration and their live disagreements are visible;
- all three valid live blocks completed within the five-attempt cap;
- per-treatment calls, elapsed time, available usage/cost, and failures are reported;
- the owner supplies numeric practical-effect and cost thresholds for the prospective decision lock; and
- exact non-tied `N`, valid-block cap `M`, and invalid-attempt cap are derived from those thresholds and frozen before prospective results exist.

This gate does not require the pilot to favor ORC. A DIRECT win, no discordance, excessive ORC cost, or repeated ORC viability failure may close the program without `F1`.

`pilot_summary.v1` reports only deterministic evidence readiness:
`STOP_APPARATUS_NOT_VIABLE`, `STOP_INSUFFICIENT_VALID_BLOCKS`, or
`EVIDENCE_COMPLETE_OWNER_DECISION_REQUIRED`. It does not turn a directional
three-block result into an investment decision. After reading the locked
evidence, the owner separately chooses to stop, commission a newly locked
controlled-pilot revision, or author the prospective decision policy.

### 6. Keep provider isolation independent

The provider-phase isolation design remains a valid independent target. Its implementation plan is paused and may resume only from its recorded handoff under separate owner prioritization.

The lean pilot records the environment and any known visibility limitations. Controlled-task results under that environment are exploratory. A future confirmatory protocol may choose the completed reusable isolation capability, an external disposable environment, or another reviewed launcher contract. That choice belongs to the future protocol and is not preselected here.

## Treatment Contracts

### Shared block inputs

Each block lock binds:

- task profile and task brief digests;
- source repository identity and exact archive digest;
- provider family, model, reasoning effort, tool policy, and timeout;
- one explicit apparatus control root as canonical absolute POSIX text, plus a
  content manifest whose entries are unique canonical relative POSIX paths and
  SHA-256 digests;
- canonical relative role paths for the task and the unmodified standard
  Workflow Lisp provider-extern, prompt-extern, and command-boundary manifests,
  each naming exactly one content-manifest entry;
- environment identity, a nonempty explicit allowlist of environment-key names,
  and unique credential-key names that are a subset of the allowlist but
  exclude controller-owned `HOME` and `TMPDIR`; no ambient key is implied;
- the visible-check argv and positive timeout, with no default command or
  timeout;
- treatment command/source digests and one distinct canonical relative command
  configuration path per treatment, with each command path naming a manifest
  entry whose digest equals that treatment's locked command digest; each
  launcher configuration supplies exactly the allowed environment keys that
  are neither controller-owned nor credential-backed;
- explicit canonical relative product-projection exclusions, which may be an
  empty list;
- positive maximum-start-skew and quiescence-grace bounds, with no timing
  defaults;
- reviewer rubric and calibration evidence digests;
- randomization seed and opaque treatment mapping;
- exact valid-block target, maximum live-attempt count, one smoke ID, and an
  ordered list of five opaque live-attempt IDs;
- artifact root outside all candidate products; and
- claim level `exploratory_controlled_task`.

### `DIRECT`

`DIRECT` performs exactly one provider invocation. The prompt supplies the shared task and acceptance contract. The provider may inspect, plan, edit, add tests, run tools, and revise its work within that invocation. No follow-up provider call, reviewer feedback, or resume is permitted.

### `COORDINATOR`

`COORDINATOR` is a bounded Python program, not a reusable orchestration framework. It implements exactly the frozen topology below with the same provider prompts and result contracts used by `ORC`:

```text
discover
  -> plan
  -> review plan
     -> approve | blocked | revise once
  -> implement
  -> run visible checks
  -> review implementation
     -> approve | blocked | fix once
  -> terminal completed | blocked | exhausted
```

The shortest terminal route uses three provider calls when plan review blocks.
Completion-capable routes use five to nine provider calls. The maximum route
uses nine. The coordinator may not add retry, resume, dynamic DAG, generic
workflow, or persistence abstractions.
It reuses the same public provider adapter and request renderer as Workflow Lisp;
it does not implement a provider client or alternate prompt wrapper.

Every provider invocation starts a fresh provider session. Cross-phase context
flows only through the typed values named by the frozen topology; neither
orchestrated treatment receives hidden conversational carry-over.

### `ORC`

`ORC` is one ordinary Workflow Lisp run implementing the same three-to-nine-call
terminal topology and five-to-nine-call completion-capable topology. Compiler,
lowering, typed-output, runtime, and routing failures are treatment outcomes.
The pilot does not add language/runtime behavior to make the workflow fit.

For both orchestrated treatments, `discover`, `plan`, both plan-review calls,
`revise_plan`, and both implementation-review calls are judgment-only. A
controller-owned product-manifest command runs before and after each such
provider call. Any product change is a treatment protocol failure. Only
`implement` and the optional `fix_implementation` call may change the candidate.
The guard detects mutation; it does not claim to hide information from a phase.

### Parity contract

Before live execution, deterministic scripted-provider tests compare
`COORDINATOR` and `ORC` for:

- canonical complete provider-request payloads after substituting the same task
  inputs, including system/user messages, tool policy, typed-result schema, and
  provider parameters while excluding only transport-generated correlation IDs;
- result validation outcomes;
- phase order;
- branch and revision bounds;
- provider/model/effort/tool policy;
- visible-check invocations;
- identical product-manifest guard invocations and mutation dispositions;
- provider-call count per route; and
- terminal outcomes for immediate approval, plan revision, implementation fix, blocked, judgment-mutation, persistent-check-failure, and exhausted routes.

Any parity mismatch blocks the current live first tranche. Fix it before any
live outcome or stop; a package-only comparison requires a separate design and
lock rather than an implicit fallback.

The same provider-free gate also executes the frozen DIRECT, COORDINATOR, and
ORC treatment JSON argv through a flat staged apparatus, the real treatment
entrypoint, the real DIRECT/coordinator/Workflow Lisp paths, standard manifests,
and runtime-control visible check. Expected semantic results are DIRECT
`1/COMPLETED`, COORDINATOR `5/COMPLETED`, and ORC `5/COMPLETED`. This is a
provider-free integration test, not a `block_attempt.v1`, lock identity,
production provider mode, or substitute for the locked real-provider smoke.

## Minimal Evidence Model

The first tranche has four versioned cross-process records:

1. `pilot_lock.v1` — immutable task, content-addressed apparatus, treatment, environment, randomization, reviewer, block-count, and claim contract;
2. `block_attempt.v1` — one durable block identity and status, optional shared-invalidity reason, and zero to three nested treatment executions containing command, lifecycle outcome, product digest, checks, provider-call count, elapsed time, and available usage/cost; `VALID` requires all three;
3. `review_result.v1` — one blinded reviewer's evidence-cited candidate assessments and pairwise outcomes; and
4. `pilot_summary.v1` — deterministic aggregation of calibration, block validity, quality, viability, cost, disagreement, and next-decision inputs.

Intermediate logs remain evidence files referenced by these records. They do not each receive a new schema. Markdown reports are deterministic views over the four records.

Cross-process records contain no binary floating-point values. Durations and
token counts are integers; observed cost is a non-negative integer number of
micro-units of the locked currency or `UNKNOWN`; and derived ratios are reduced
`{numerator, denominator}` integer pairs or `UNKNOWN`. Future decision-lock
probabilities and ratios use canonical decimal strings parsed as exact
rationals. Markdown may render decimals but cannot become the source value.

Record validation checks the apparatus shape, environment partition, and
manifest cross-bindings without reading the filesystem. Before writing
`STARTED`, allocating a workspace, or launching any treatment, the runner
resolves assets only beneath the locked `apparatus.control_root`, reads and
verifies every manifest entry's bytes against its SHA-256 digest, validates the
three role manifests through the standard Workflow Lisp extern-manifest
contract, requires every prompt extern to use `asset_file` and name verified
manifest bytes, and rechecks the task and three treatment
command-configuration bindings. Dynamic `input_file` prompt lookup is not part
of the locked apparatus. It constructs commands only from those verified
configuration bytes.
The provider manifest is never reinterpreted as a credential declaration, and
the command-boundary manifest is never reinterpreted as shared launcher
environment.

For each arm, the controller stages every verified manifest asset beneath one
private controller-owned apparatus root while preserving its normalized
relative path. Launcher substitution binds `{task_path}`, `{provider_config}`,
`{prompt_config}`, and `{command_config}` to the corresponding staged role
assets and binds `{apparatus_root}` to that private root. `HOME` and `TMPDIR`
come only from the controller; credential keys come only from
`SecretsManager`; and the treatment launcher supplies exactly the remaining
allowed keys. The resulting child environment has exactly the locked allowlist.
The original `apparatus.control_root` is never candidate-visible. The runner
never infers an asset from the current working directory, an installed package
location, or a fixed/hardcoded path.

Treatment processes receive one opaque raw-result path, not the shared evidence
root, peer paths, treatment map, or final attempt-record path. The controller
captures stdout/stderr, validates the raw result, measures lifecycle data,
freezes the product, and authors `block_attempt.v1`. This reduces accidental
evidence coupling but is not an OS confidentiality claim.

The raw result is one strict object with exactly `terminal_outcome`,
`provider_call_count`, `token_counts`, and `cost`. `terminal_outcome` is required
and is exactly one of `COMPLETED | BLOCKED | EXHAUSTED | PROTOCOL_FAILURE`.
After a successful process exit and valid raw result, the controller preserves
that semantic terminal as the arm lifecycle outcome. Launch failure, timeout,
nonzero exit, and an invalid or missing raw result take precedence over any
claimed semantic terminal. Provider-call bounds apply to every valid semantic
terminal, including `BLOCKED`, `EXHAUSTED`, and `PROTOCOL_FAILURE`; a bound
violation yields `PROTOCOL_FAILURE`. The final controller-owned visible check
changes only semantic `COMPLETED` to `CHECK_FAILURE`, leaving every other
semantic or transport outcome intact.

A block is invalid only when a shared controller or allocation fault prevents the intended three-treatment contrast before treatment execution. Treatment-specific timeouts, provider failures, compiler/runtime failures, bad patches, and failed checks remain outcomes.

After the pre-START apparatus byte verification and before archive allocation,
the controller atomically writes a validated `block_attempt.v1` with status
`STARTED`. It atomically replaces that record with `VALID`, `INVALID`, or
`ABORTED` after quiescence. A surviving `STARTED` record is an aborted
controller attempt and is never resumed or silently deleted. Thus summaries
regenerate invalid/aborted references from structured records rather than
inferring them from directories or logs.

Live attempts execute only as a contiguous prefix of the lock's ordered opaque
IDs. The runner refuses an out-of-order or reused ID. Synthesis loads those
exact record paths, permits a missing suffix only after three valid attempts
have accrued, and rejects a missing interior record. This prevents selective
omission without adding a database or discovery scan.

If the controller crashes, it preserves the incomplete block and uses the next
predeclared attempt ID. The first tranche has no resume or recovery state
machine.
Pairwise method outcomes use a fixed precedence so failures cannot disappear
into an excluded or indeterminate denominator:

1. an apparatus-invalid block is excluded in full and retained adjacent to the
   denominator;
2. when exactly one treatment in a contrast reaches the locked viable terminal
   condition, that treatment wins the method outcome;
3. when both treatments are viable, sealed blinded review decides
   `A_WIN | B_WIN | TIE | INDETERMINATE`;
4. when neither is viable but both frozen products are reviewable, blinded
   product-quality review is reported separately and the method outcome is
   `TIE_NONVIABLE`; and
5. when neither yields a reviewable frozen product, the method outcome is
   `TIE_NONVIABLE`.

Original lifecycle failures, hard findings, and conditional product-quality
reviews remain separately visible. This precedence is a practical method
comparison, not a weighted quality score.

## Evaluation

### Product freeze

After a treatment process exits or times out and its process group is quiescent, the controller records a sorted product-relative manifest with file type, mode, size, and SHA-256. Controller records and transient runtime paths are excluded by an explicit projection rule applied identically to all treatments.

Live package construction accepts only a complete valid `pilot_lock.v1` and a
`VALID` `LIVE` `block_attempt.v1` whose canonical lock digest, exact locked
treatment set, and frozen product-manifest digests match freshly re-frozen
explicit product roots under those locked exclusions. The block ID must equal
the lock's live-attempt ID at the block sequence index, each execution command
digest must equal its locked treatment command digest, and a fresh complete
freeze of the base with no exclusions must equal the lock's archive digest.
Base, product, package, and controller roots are explicit and pairwise
disjoint; IDs used in path joins are safe single components.

### Hard evidence

Frozen visible and held-out evaluators run on copies of frozen products. Their outputs are findings, not automatic total-order truth. A hard failure must cite the violated task contract or be labeled an evaluator defect/ambiguity.

### Blinded review

At least two fresh independent reviewers receive:

- the shared task and public acceptance contract;
- a deterministic diff over the complete projected frozen base and final
  trees, including unselected changes, additions, deletions, and mode, type, or
  symlink deltas;
- relevant final files and candidate-authored documentation;
- visible and held-out check evidence only at the stage defined by the lock; and
- opaque candidate labels.

They do not receive treatment identity, workflow/coordinator source, prompts,
transcripts, provider-call count, elapsed time, or cost until reviews are
sealed. After each judgment but before unblinding, each reviewer records one
forced treatment guess per opaque candidate from
`DIRECT | COORDINATOR | ORC | UNKNOWN`. Material disagreement invokes one
blinded adjudicator or yields `INDETERMINATE`; original reviews remain
unchanged. Guess accuracy is a blinding diagnostic, not a reason to rewrite a
judgment.

Selected final-file snapshots and check evidence are explicit allowlists; they
do not narrow the complete product diff. Each reviewer package has a closed,
canonical manifest binding its package ID and every payload path, mode, size,
and digest. Ingestion binds the expected package ID and digest of the raw
canonical manifest, rejects noncanonical or coherently rewritten manifests,
duplicate/extra/unsafe paths, NUL-bearing paths, and undeclared regular or
non-regular filesystem nodes, and verifies every payload row before evaluating
top-level or per-dimension citations. Calibration review records additionally
bind the canonical calibration-lock digest, rubric digest, exact
package-manifest digest, and exact distinct two-label order. The closed,
canonical controller mapping is itself re-read from an explicit controller
root. Its package and six review-binding sets must be exact, and every evaluator,
oracle, patch, rubric, reviewer-CLI, environment-identity, raw-evidence,
package, and review binding is revalidated against the named file under that
root. The three package mappings use the same two opaque labels and bind,
respectively, `REFERENCE/BASE`, `BASE/REFERENCE`, and
`REFERENCE/REFERENCE`; role values or orientations cannot be supplied by a
retained failed result. The label map and evaluator/controller evidence never
enter reviewer packages.

### Pilot report

Summary synthesis consumes only the exact locked smoke/live attempt prefix,
validated `review_result.v1` objects, explicit closed review-to-package/path
bindings, and explicit controller-owned opaque-label-to-treatment bindings.
The bindings must cover each valid block exactly, preserve the original review
digests and paths, and on material disagreement either use the one locked
adjudicator or preserve both initial reviews and emit `INDETERMINATE`.
Opaque-label bindings are authenticated by recomputing the exact mapping from
the locked randomization seed, block ID, and treatment set; a complete but
repermuted mapping fails closed. Synthesis never discovers reviews, label maps,
or paths from a directory scan.

The direct synthesis interface enforces the same contiguous-prefix and
post-third-valid rules as the filesystem loader. A failed smoke admits no live
attempt. The loader accepts only a canonical absolute evidence root equal to
the lock and regular, non-symlink attempt records beneath safe single-component
locked IDs. Summary outputs are distinct new canonical paths outside the
evidence and input paths and are published atomically without overwrite.

For each block and across the three blocks, report:

- `DIRECT`/`ORC` and `COORDINATOR`/`ORC` win, tie, and indeterminate outcomes;
- hard-contract findings and dispositions;
- reviewer agreement and adjudication;
- reviewer treatment-guess accuracy and confusion after unblinding;
- treatment viability and failure classes;
- provider-call counts;
- elapsed-time ratios;
- available usage/cost ratios, or `UNKNOWN`; and
- all invalid or aborted blocks outside, but adjacent to, the valid denominator.

`pilot_summary.v1` carries these as closed typed comparison counts, per-treatment
viability/lifecycle/failure/call statistics, exact elapsed/cost/input-token/
output-token medians and ratios with `UNKNOWN` propagation, observed
`CHECK_FAILURE`/`PROTOCOL_FAILURE` hard-contract finding rows, and review
agreement, adjudication, and post-unblinding guess diagnostics. A hard-contract
row preserves the execution evidence references and disposition
`TREATMENT_OUTCOME_RETAINED`; it does not infer a violated clause or parse
free-form evidence. Other lifecycle failures remain in the lifecycle and
failure-class statistics. Cross-count arithmetic and the exact diagnostic and
metric row sets validate as part of the record contract. Review guesses cannot
alter the sealed product-quality or method outcomes. Markdown is regenerated
solely from that validated summary and renders every substantive typed summary
surface.

No weighted scalar score is required.

The observed three-block `A1` win fraction is not an estimator for general task
performance and cannot be copied directly into a prospective target effect.
Any later effect assumption must be justified for the exact frozen prospective
task and labeled task-specific.

## Statistical And Decision Contract

The three-block first tranche is exploratory and performs no confirmatory hypothesis test. It estimates feasibility, disagreement, discordance, cost, and failure rates.

Before any confirmatory or prospective series, a `decision_lock.v1` must bind a
one-sided exact paired-superiority rule and all of:

- the primary pairwise contrast and favorable direction;
- sampling unit, independent provider-allocation requirement, and randomization
  scheme;
- null non-tied win probability;
- minimum practically meaningful non-tied win probability;
- alpha;
- desired power;
- maximum acceptable tie/indeterminate rate;
- minimum probability of accruing the required non-tied comparisons;
- maximum acceptable median cost ratio;
- disposition when observed cost is `UNKNOWN` (a cost-threshold claim requires
  observed cost; `UNKNOWN` cannot be imputed from elapsed time);
- viability non-inferiority rule; and
- maximum invalid block attempts.

The sample-size tool must derive and print:

1. the smallest required count `N` of valid, non-tied primary comparisons;
2. the exact critical win count and achieved power;
3. the smallest fixed valid-block cap `M` whose binomial accrual probability
   reaches the declared assurance under the maximum tie/indeterminate rate;
4. the invalid-attempt cap; and
5. the minimum and maximum provider-call range.

The exact operating characteristics apply only to the locked sampling unit and
independence assumptions. Correlated retries, shared provider sessions, or
outcome-dependent seed/task selection invalidate the confirmatory inference
rather than reducing the denominator post hoc.

If `M` valid blocks are exhausted before `N` non-tied comparisons accrue, the
result is `INSUFFICIENT_EVIDENCE`; the series is not extended after unblinding.
Invalid blocks remain outside `M` but are bounded by the predeclared invalid
attempt cap. The tool must reject omitted parameters or a lock that copies a
default block count instead of deriving `N` and `M`.

The `COORDINATOR`/`ORC` contrast remains descriptive in the lean pilot. A
non-significant difference is not evidence of equivalence. Any later
equivalence or non-inferiority claim requires its own margin and operating
characteristics.

Pilot outcomes may inform the locked assumptions, but no prospective result may
exist before the resulting decision lock is immutable.

## Dependencies And Sequencing

```text
static evaluator calibration
        |
deterministic three-treatment route parity
        |
minimal archive/launch/freeze/report smoke
        |
three locked A1 live blocks
        |
locked pilot synthesis
        |
owner decision + numeric decision policy
        |
separate prospective F1/F2 design/plan, or stop
```

Provider-free contract, archive, blinding, calibration, parity, reporting, and sample-size work may proceed independently of provider-phase isolation. No task in this first tranche may mutate the paused isolation implementation.

The prospective PtychoPINN task remains the reloadable PyTorch architecture extension-boundary problem from the superseded design. Its exact profile, evaluator, consumer chain, environment, and sample size are not implemented by the lean-pilot plan. They are copied into a future plan only if the pilot gate authorizes that cost.

## Invariants And Failure Modes

- Treatment definitions are immutable before the first live outcome.
- The conventional coordinator is frozen before the first live outcome.
- DIRECT has exactly one provider invocation.
- COORDINATOR and ORC parity is machine-checked before a representation claim.
- All treatment-specific failures remain outcomes.
- Invalidity is symmetric across the full three-treatment block.
- Reviewers pass calibration before reviewing live candidates.
- Review packages remain blinded until all initial judgments are sealed.
- Unknown usage/cost remains unknown; it is not estimated from elapsed time.
- The pilot denominator cannot grow after results are visible.
- The pilot cannot authorize a general, prospective, or `.orc`-specific causal claim beyond its declared contrasts.
- Failure to obtain a discriminating pilot is a completed result, not a reason to build more apparatus automatically.

Expected stop/revise cases include:

- reviewer calibration fails;
- coordinator/ORC parity cannot be achieved without adding a second framework;
- the generic `.orc` workflow requires a language/runtime change;
- no treatment can complete the controlled task under the shared provider policy;
- live results expose an apparatus defect that changes treatment inputs or evaluation;
- the program cannot define a numeric prospective decision policy; or
- prospective planning expands beyond one bounded PtychoPINN task plus its withheld consumer consequence.

## Compatibility And Migration

The 2026-07-23 design and plan become historical, superseded records. Their benchmark research, task identities, and failure evidence remain useful, but their thirty-five-schema apparatus, Tasks 1–17 sequence, full-isolation prerequisite, and late same-topology control are not executable authority.

The historical control-plane feasibility report remains unchanged evidence for the runtime it tested. Current documentation must route experiment work to this design and its lean-pilot plan.

Provider-phase information isolation remains `Partial` in the capability matrix. Decoupling the exploratory pilot does not promote that runtime surface or weaken its own acceptance contract.

## Verification Strategy

### Deterministic checks

- Schema validation and canonical digest tests for all four records.
- Archive materialization tests proving no `.git` directory and byte-identical three-arm trees.
- Launch-barrier tests for three commands, treatment-specific failure accounting, timeout quiescence, and symmetric invalidation.
- Product-freeze projection and deterministic regeneration tests.
- Static calibration package tests for label reversal and identity comparison.
- Coordinator/ORC parity tests for all bounded routes.
- Report regeneration tests from structured records.
- Sample-size tests with known exact-binomial vectors and rejection of unspecified decision thresholds.
- A structural gate keeping every `orchestrator.experiments` production module
  at or below 500 physical lines while preserving the exact public facades.

### Integration checks

- One provider-free actual-launcher integration gate across all three frozen
  treatments, using only an asserted test-specific `PATH`/provider executable
  difference.
- One real-provider unscored apparatus smoke after lock validation and before
  the locked live series.
- Up to five ordered live `A1` attempts to obtain three valid blocks, only
  after calibration, parity, and smoke pass.
- `pytest --collect-only` for new test modules, focused tests first, then affected broad suites.
- One end-to-end CLI invocation from protocol validation through pilot-summary regeneration.

Tests assert behavior, contracts, lineage, and routing, not literal prompt prose.

## Declarative Acceptance Scenarios

### Controlled pilot succeeds without proving a general claim

Given one immutable `pilot_lock.v1`, three fresh source archives per block, two calibrated blinded reviewers, and parity-approved COORDINATOR/ORC treatments, running three live blocks produces three final `block_attempt.v1` records and one deterministic summary. The report may favor any treatment, tie, or remain indeterminate. It labels all conclusions `exploratory_controlled_task` and creates no prospective or general claim.

### ORC fails while other treatments run

Given valid shared inputs, if the `.orc` compiler or runtime fails after launch while DIRECT and COORDINATOR complete, the block remains valid. ORC records a treatment viability failure; no arm is discarded and no selective rerun replaces it.

### Reviewer calibration fails

Given the two directional calibration packages and one identity package, if
either reviewer fails the expected outcomes, no live candidate is shown. The
evidence is preserved and the rubric/package may be revised once under a new
digest with six new sessions. A second failure closes the live route as
`CALIBRATION_FAILED`.

### Representation parity fails

Given deterministic scripted-provider routes, if COORDINATOR and ORC differ in complete
provider requests, calls, branches, validation, guards, or terminal outcome,
the mismatch is fixed before live outcomes or the current first tranche stops.

### Pilot does not justify prospective work

Given the complete pilot summary, if the owner does not supply numeric practical-effect, cost, and inference thresholds, the program closes at exploratory evidence. It does not create a default ten-pair `F1` series.

## Success Criteria

The reusable first-tranche implementation is accepted when:

- the four record contracts validate and have deterministic digests;
- DIRECT is structurally limited to one provider invocation;
- COORDINATOR and ORC pass every deterministic parity route;
- archive, runner, evaluation, reporting, and sample-size checks pass;
- every `orchestrator.experiments` production module is at or below 500 lines
  with no duplicated facade logic;
- no prospective/general claim or unrelated runtime capability is added; and
- focused, integration, and affected broad checks pass.

Evidence execution then ends truthfully at one of:

- `CALIBRATION_FAILED` after the second locked calibration round;
- `STOP_APPARATUS_NOT_VIABLE` after the single real-provider smoke;
- `STOP_INSUFFICIENT_VALID_BLOCKS` after five ordered live attempts; or
- `EVIDENCE_COMPLETE_OWNER_DECISION_REQUIRED` after exactly three valid live
  blocks and deterministic reviewed synthesis.

Every reached route preserves its applicable failures, disagreements,
treatment guesses, invalid/aborted attempts, and unknown usage/cost. Final
evidence review is required for routes that create a pilot summary.

## Stop / Revise Criteria

Revise this design rather than expanding implementation when:

- the minimal package grows beyond the four records or five public
  responsibility surfaces without an observed cross-boundary need; private
  owner modules required by the 500-line quality limit do not create new
  surfaces;
- a provider-isolation feature becomes mandatory merely because it exists or was previously planned;
- evaluator calibration cannot distinguish the known cases;
- the selected evaluator execution environment cannot run provider-authored
  product code at an accepted operational risk; choose a separately reviewed
  disposable environment rather than expanding this pilot into a sandbox;
- coordinator parity requires a reusable second orchestration framework;
- the live pilot needs a Workflow Lisp language/runtime change;
- a result can be made favorable only by excluding treatment failures;
- sample-size planning cannot name a practically meaningful effect; or
- a prospective task cannot remain one bounded architecture change with frozen downstream consequences.

## Documentation Impact

Implementation updates only:

- this design and its implementation plan;
- the superseded 2026-07-23 design and plan status/routing;
- the provider-isolation design/plan relationship to the experiment;
- `docs/index.md`;
- `docs/design/README.md`;
- `docs/capability_status_matrix.md`; and
- one eventual pilot evidence report.

No normative `specs/` change is authorized by this experiment design.

## Implementation Handoff

Use the linked lean-pilot plan. Implement in this order:

1. minimal records and canonical digests;
2. source archive and product freeze;
3. three-treatment runner;
4. frozen coordinator/ORC parity;
5. blinded evaluation packages and bounded reviewer calibration;
6. deterministic reporting and exact sample-size planning;
7. confirm the reviewed provider-free actual-launcher gate, then run one
   real-provider apparatus smoke and up to five live `A1` attempts to obtain
   three valid blocks;
8. deterministic synthesis and evidence review; and
9. an owner decision on whether to stop, rerun under a new lock, or commission
   a separate prospective `F1`/`F2` plan.

Do not resume provider-isolation Task 4, create `F1` infrastructure, or add deferred estimands as part of this plan.
