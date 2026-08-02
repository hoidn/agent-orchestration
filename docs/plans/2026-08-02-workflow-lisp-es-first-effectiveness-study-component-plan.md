# Workflow Lisp ES First Effectiveness Study Component Plan

## Metadata

- **Status:** accepted for provider-free ES execution; Task 0 review is closed
  and Task 1 is selected; live allocation remains Task-6 owner-adoption gated
- **Owner:** agent-orchestration maintainers; the scientific decision-lock
  choices require a separate personal adoption by Ollie before live work
- **Selected stage:** ES only — the post-`PASS_E2` first effectiveness study
  that is a mandatory input to the E3 continue/narrow/stop review
- **Implementation baseline:** commit
  `319380b5353843f23a7ea2499c93be3f5de3730d`, tree
  `641629a9e1744b768176b115bfad7ef3208ed51c`
- **Predecessor:** `PASS_E2` at commit
  `8aad035ddc0024f1e5f4b121b5dda98dbaf3b6f4`, tree
  `aafa31c09730544a12e33dbc692847a24726a54f`
- **Required ordered plan verdicts:** `ES_PLAN_SPEC_APPROVED`, then
  `ES_PLAN_QUALITY_APPROVED`
- **Required ordered final verdicts:** `ES_FINAL_SPEC_APPROVED`, then
  `ES_FINAL_QUALITY_APPROVED`
- **Reviewed plan candidate:** commit
  `27be07e27825c161145671a70219143a3b8aa624`, tree
  `e669471ac908be3b1a937336a6e7b337b046b143`, plan SHA-256
  `b34a05f748a9dbc471251b5b59a4927a9d1ccf6675fd19112172565562b756a4`
- **Plan review:**
  `artifacts/review/es-first-effectiveness-study-plan-review.md`
  (`sha256:5d8b2f9d4b107b4fe1530a4c411b7cd560efed1bc3d2180d4725032d684e20ba`);
  `ES_PLAN_SPEC_APPROVED`, then `ES_PLAN_QUALITY_APPROVED`
- **Selection authority:**
  `docs/plans/2026-08-01-workflow-lisp-post-e2-stage-sequencing.md`
  (`sha256:cf374698d66475fee17095808be01039a5c873f75d347dcdb828dfd068d93011`)
  and the E1-E3 owner selection
  (`sha256:a3ec1dcdd0d307f4ddfb3eecca7643c175b47d2173f3ba00fc99b7aa9b243e9d`)
- **Governing inputs:**
  - `docs/reports/2026-08-01-lean-pilot-forensics-and-e2-study-inputs.md`
    (`sha256:2ce755636747796051d151b4c71390aa3c0135beec2117a9eb7dcf31b4049380`)
  - `docs/superpowers/specs/2026-07-26-orc-effectiveness-lean-pilot-design.md`
    (`sha256:8659c795a5f4a12698a4c3b8cd23799c401c5ef8bfc1780e5b49093fec760e21`)
  - the F1 task and evaluator clauses salvaged from
    `docs/superpowers/specs/2026-07-23-orc-vs-one-shot-experiment-design.md`
    (`sha256:6c608a6ba0cdd6c9b5f31dc2232da3a9c138daec3c7dc410cb6a43c1571beb37`)
  - `docs/design/workflow_lisp_trial_runs.md`
    (`sha256:ed4b4090b71f4310e09aa59d3f347245c640c0727eceec8baf1344a14c53cf53`)
  - `docs/design/workflow_lisp_program_search_boundaries.md`
    (`sha256:a42a1db72b887eb94cfa7c3fe93fe6e7269e99daa2867ccd484d16bbe0f0d41b`)
  - the digest-bound E2 final review
    (`sha256:03ae6a57fb38f6d2d093004eac0ce851f256da8e19b0ff75d24f9859a5ee2d83`)

## Authority reconciliation

The current E roadmap and post-E2 sequencing record are authoritative. ES is
not historical E0, the lean A1 pilot, E2 Task 10, E2O, or E3. It is one new,
task-specific prospective screen over the landed E0-E2 execution substrate.
It supplies evidence to the later E3 readiness review; it neither implements
an evolutionary controller nor promotes a product candidate.

The 2026-07-23 experiment design is superseded as a program. This plan imports
only its already-selected F1 source/task, solution-neutral lifecycle boundary,
candidate-evidence separation, hard-evaluation criteria, blinded review order,
and claim limits. It does not revive the thirty-five-record apparatus, F2,
consumer chains, provider-isolation program, or historical ten-pair planning
assumption. In particular, because F2 is omitted, ES makes no downstream
edit-locality or schema-evolution claim.

The phrase "2x2 factorial ... plus DIRECT" is resolved as exactly four cells:
DIRECT is the no-design-QA/no-product-QA `00` cell. There is no fifth
orchestrated `00` arm. The rich cell composes the two bounded QA placements;
it does not inherit the old pilot's discovery call or second implementation
review. These choices are frozen before results and are not reinterpreted
afterward.

The accepted E2 trial owns concurrent child execution, complete settlement,
freezing, opaque packet construction, one scorer attempt per cell, and
failure-as-outcome behavior. ES owns only the study profile, source
projection, arm workflows, metered usage receipts, additional F1 review and
hard evaluation, exact decision lock, and deterministic synthesis. Native E2
cost remains `UNKNOWN` on the current runtime. ES therefore does not use the
native E2 verdict as its cost or roadmap decision; a separately reviewed,
digest-bound study join must account for every invocation with no unknown
column. This avoids changing E1/E2 behavior solely for one study.

Phase ME may later delete the superseded `orchestrator.experiments` package.
Nothing in ES may import or extend that package. The frozen lean-pilot control
tree and A1 evidence root remain byte-untouched.

## Objective

Run one preregistered, task-specific internal admission screen on the frozen
PtychoPINN reloadable-generator extension-boundary task. Four independently
allocated arms receive identical task-repository bytes, task contract,
provider/model/effort, environment, deadlines, checks, evaluators, and
observation limits. They differ only in whether design QA and product QA are
present:

| Arm | Design QA | Product QA | Bounded treatment route |
| --- | --- | --- | --- |
| `DIRECT` | absent | absent | one implementation call |
| `DESIGN_QA` | present | absent | design, review, optional one revision, one single-shot implementation |
| `PRODUCT_QA` | absent | present | implementation, review, optional one fix |
| `RICH` | present | present | the two bounded protocols composed |

The primary contrast is `RICH` versus `DIRECT`. The two middle cells are
precommitted mechanism evidence: they show whether any observed difference is
associated with design QA, product QA, their combination, or neither. They do
not create separate outcome-dependent denominators.

The candidate task must produce working product code/tests, an ADR, a concise
extension-author guide, a versioned candidate-evidence manifest, and the fixed
solution-neutral lifecycle adapter. The hard evaluator exercises configure,
construct, forward, loss/backward, a bounded optimizer step, save, and
fresh-process reload/inference for one migrated representative architecture
and one small witness architecture. It independently verifies facts instead
of trusting the candidate manifest.

## Direct architecture and deliberate limits

Use the smallest study-owned layer over target 2.25:

1. a deterministic, history-free source projector and verifier;
2. one four-arm Workflow Lisp trial plus role-specific prompt assets;
3. a PATH-front metering shim around the pinned noninteractive Codex CLI;
4. a strict `decision_lock.v1` exact-rational validator and deterministic
   synthesis command; and
5. F1 task, lifecycle, hidden-evaluator, review, and report assets.

The study is rooted under `experiments/orc_effectiveness/f1_es/`, its thin
commands under `scripts/experiments/es/`, and its `.orc` programs under
`workflows/experiments/qa_placement_effectiveness/`. It uses the public E2
trial entry rather than a second runner or trial service.

This narrow choice makes multi-task generalization, F2 consumer consequences,
native E2 monetary accounting, adaptive denominators, and arbitrary future
study profiles harder. Those are intentional non-goals. A later study must
write a new lock rather than broaden this one after observing results.

## Frozen F1 source projection

The source repository is `/home/ollie/Documents/PtychoPINN` at commit
`c081b7b6cd160b3da7031ee325bbf0ade1025d7a`, tree
`9193ae2f81116d1bac4cf3cb74395613c1220dbe`. E1 correctly rejects that tree
because it contains `.gitmodules` and five gitlinks. ES must not weaken E1.

The projector excludes exactly these six rows and nothing else:

| Path | Source identity |
| --- | --- |
| `.gitmodules` | blob `165ea65e122d37eeb153035b129f05f3c959a155` |
| `.claude` | gitlink `7a651838d6203f1e9493ceb1c5b14dea29e29bfa` |
| `PtychoNN` | gitlink `d6f6ac7627c135fab32348cd537f3ef694264cb8` |
| `notebooks/archive/ePIE_recon_simulation` | gitlink `9fa2b986256501fe119192bff33cf24ef4aa7ae1` |
| `ptycho/FRC` | gitlink `56626c85aabf39b5ed8a94430077b4f57e418d33` |
| `scripts/orchestration` | gitlink `2a3127bc4941ab335dd16299e36ded22a9e0a366` |

The required retained projection has 1,948 leaves and tree
`e64f3c05f5a0894f41c047d128a9040a2cda6764`. Its one root commit has no
parent and contains no unrelated source objects. The canonical recipe uses
author and committer
`E-series source projection <e-series-source-projection@invalid>`, timestamp
`1784674813 -0700`, and the following exact UTF-8 commit message, including
its final newline (204 bytes,
`sha256:b183cb771aca6398acdcb01f4983f110c92b43ad7cc148a01ca48f7719e464be`):

```text
E-series F1 deterministic source projection

Source-Commit: c081b7b6cd160b3da7031ee325bbf0ade1025d7a
Source-Tree: 9193ae2f81116d1bac4cf3cb74395613c1220dbe
Projection-Policy: e-series-source-projection.v1
```

The exact commit content begins with these headers, followed by one blank line
and the message above; it has no `parent` header:

```text
tree e64f3c05f5a0894f41c047d128a9040a2cda6764
author E-series source projection <e-series-source-projection@invalid> 1784674813 -0700
committer E-series source projection <e-series-source-projection@invalid> 1784674813 -0700
```

The complete commit content is 430 bytes with
`sha256:c2989a3daeb32130711591a4941b0eaf3345e1a3f3816430dd8583d945411e31`;
framing it as `commit 430\0<content>` must produce Git object ID
`8f191031f233d50a4d020d8a988036e99487f570`. Visible F1 assets are then
added in one separately bound task-seed commit.

The manifest binds the original rows, six-row exclusion digest
`8f7b02d2fe83700990f133e523e25c7a808c4057c15710567896d7496cee4141`,
filtered inventory digest
`6fc936c54977d9adc7bdbae02bfa69592c55722e5cf5eddbd1b958ee1bc71404`,
all retained `(path, mode, type, OID)` rows, the projection recipe, task-seed
assets, environment, checks, fixtures, and static/dynamic closure evidence.
Generation from an archive or reconstructed tree must not copy original
history or unreachable objects.

`ptycho/FRC` is not globally dispensable: packaging, FRC metrics, and broader
evaluation use it. ES therefore runs in place under `ptycho311`, performs no
install/build, excludes `ptycho.evaluation` and FRC claims, and proves the
smaller F1 closure dynamically. The focused baseline is exactly:

- `tests/torch/test_generator_registry.py`;
- `tests/torch/test_construction_consolidation.py`;
- `tests/torch/test_generator_adapter.py`;
- `tests/torch/test_config_bridge.py`;
- `tests/torch/test_model_spec.py`;
- `tests/torch/test_model_spec_v2.py`;
- `tests/torch/test_lightning_checkpoint.py`;
- `tests/torch/test_artifact_schema.py`;
- `tests/torch/test_artifact_schema_v2.py`; and
- `tests/torch/test_workflows_components.py`.

The final task profile binds each path and digest. Full-repo equivalence is not
claimed.

## Arm and evaluation contract

Every arm returns `Bool`, so target 2.25's common arm-result rule is satisfied.
Every provider alias uses the same pinned Codex executable, model, effort,
timeout, noninteractive stdin transport, and the exact
`--dangerously-bypass-approvals-and-sandbox --skip-git-repo-check` flags. No
interactive TUI or directory-trust dialog is in the execution path. Calls use
fresh sessions; resume and cross-arm session reuse are forbidden.

Completed treatment-route call bounds are:

| Arm | Minimum | Maximum |
| --- | ---: | ---: |
| `DIRECT` | 1 | 1 |
| `DESIGN_QA` | 3 | 4 |
| `PRODUCT_QA` | 2 | 3 |
| `RICH` | 4 | 6 |

An `APPROVE` review skips its revision/fix. `REVISE` permits exactly one
correction. A second rejection or blocked correction terminates that arm and
remains a treatment outcome. There is no ceremonial correction. Design review
includes the recorded parsimony criterion: reject a boundary whose surface
exceeds the task. A terminal arm may make fewer calls than its completed-route
minimum, including zero when child compilation or materialization fails before
the first provider checkpoint. The decision lock therefore enumerates every
terminal route and its exact call count rather than treating the completed
route minima as universal lower bounds.

E2 performs exactly one non-retried scorer call for each of the four frozen
cells. Those absolute score rows remain visible as E2 apparatus evidence but
do not replace the F1 review sequence. Before hard evaluation, two fresh
independent reviewers each receive the same four opaque candidate packages in
a precommitted presentation order, assess each independently, and then return
the frozen pairwise vector. Their distinct, frozen perspectives are
`SCIENTIFIC_APPLICATION_SEMANTICS` and
`API_PERSISTENCE_MIGRATION_MAINTAINABILITY`; neither substitutes for the
other. Material disagreement invokes at most one fresh adjudicator. After the
initial records are sealed, hard evaluation runs on immutable candidate
copies; one fresh integrated reviewer then sees the initial records and hard
evidence without editing either.

The imported F1 hard contract is behavior-level and includes all of the
following before launch:

- existing declared focused suites;
- candidate evidence-manifest and lifecycle-adapter schema conformance;
- unchanged construction and state signatures for existing built-ins;
- supported artifact-era model, checkpoint, and bundle fixtures continuing to
  decode and strict-load;
- both nominated architectures completing evaluator-owned construct, forward,
  backward, optimizer-step, save, fresh-process reload, and inference;
- the witness architecture preserving every structural value across save and
  fresh-process reload;
- missing, extra, unknown, or unsupported structural identity failing before
  a module is returned;
- declared structural fields changing frozen artifact/content identity
  deterministically;
- equality between the candidate-declared supported public construction route
  and the implementation selected by persisted rebuild; and
- existing physics, loss, scaling, and data ownership remaining outside the
  extension boundary.

Every hard finding has exactly one frozen disposition:
`PRODUCT_DEFECT`, `ORACLE_DEFECT`, `SPEC_AMBIGUITY`, `INFRASTRUCTURE`, or
`UNRESOLVED`. Only a confirmed critical violation of the frozen product
contract is a product-blocking finding; oracle and infrastructure defects stay
visible and cannot be silently charged to a candidate.

A valid block has 7–22 provider invocations across all terminal routes: zero
to fourteen treatment calls, four E2 scorer calls, two initial-review calls,
zero or one adjudication call, and one integrated-review call. The completed
treatment-route subrange is 17–22. Any reviewed topology or terminal-route
change must regenerate the route table and aggregate bounds before owner
adoption.

## Metering and cost contract

The pinned executable is Codex CLI `0.145.0`, currently resolved through
`/home/ollie/.nvm/versions/node/v20.19.4/bin/codex`; its resolved launcher
digest is
`sha256:134063e133f0b4244fa3b251acf973d4fe4aeeacbdc135211bf480f59f1477`.
The environment lock must re-resolve and bind the executable chain, version,
Node interpreter, config/profile inputs, and authenticated provider identity
before any live attempt.

The PATH-front shim adds `--json` while preserving the required unrestricted
and skip-check flags, tees canonical raw JSONL to a unique attempt receipt,
passes through exit status and output, and extracts exactly one terminal usage
event. Missing, duplicate, malformed, conflicting, or unbound usage fails the
study attempt closed. A receipt binds block, arm or reviewer role, provider
attempt, prompt/contract digest, process identity, raw JSONL digest, terminal
event digest, token fields, and exit status. No receipt is inferred from wall
time.

ES uses `CODEX_REPORTED_TOTAL_TOKENS` as its locked cost unit: the exact
terminal total-input plus output token counts reported by the provider, with
cached-input facts retained separately. It makes no USD, billing, or marginal
subscription-cost claim. The study report contains no unknown token or cost
cell; absence of a valid receipt prevents a valid block. This is preferable to
inventing a pricing schedule that is not applicable to the account.

## Proposed scientific decision lock

The complete canonical lock is generated only after every source, task, arm,
prompt, evaluator, fixture, environment, randomization, and reporting digest
is frozen. The following authored choices are a recommendation, not an owner
attestation:

| Field | Proposed value |
| --- | --- |
| Purpose/claim class | `INTERNAL_ROADMAP_ADMISSION_SCREEN`; task-specific and exploratory |
| Primary contrast | `RICH` versus `DIRECT`, favorable direction `RICH` |
| Sampling unit | one four-arm fresh-allocation F1 block |
| Budget policy | equal structure; fixed role/correction bounds, not equal calls |
| Null non-tied RICH win probability | `0.5` |
| Minimum practical non-tied RICH win probability | `0.9` |
| One-sided alpha | `0.25` |
| Desired power | `0.8` |
| Maximum planning tie/indeterminate rate | `0.25` |
| Minimum accrual assurance | `0.8` |
| Maximum valid blocks | mechanically derived |
| Maximum invalid attempts | `1` |
| Maximum median `RICH`/`DIRECT` token-cost ratio | `4.0` |
| Unknown accounting | invalid block; no imputation |
| Viability rule | across the fixed valid blocks, `RICH` has no more treatment failures than `DIRECT` |

The exact paired-superiority calculation gives required non-tied comparisons
`N=2`, critical RICH wins `k=2`, null tail `1/4`, achieved power `81/100`,
and fixed valid-block cap `M=3`. With non-tie probability `3/4`, accrual at
`M=3` is `27/32`; `M=2` reaches only `9/16`. Across all valid terminal
routes, three valid blocks require 21–66 calls; 51–66 is only the completed
treatment-route subrange. The absolute ceiling including one fully charged
invalid attempt is 88 calls.

Alpha `0.25` is deliberate: this is an internal investment screen whose only
positive consequence is eligibility for a separate reviewed E3 plan. A pass
is rendered `SCREEN_PASSED`, never confirmed or general superiority. The
stronger alpha-`0.05`, practical-effect-`0.9` alternative would require
`N=8`, `k=7`, and `M=12`; that cost is not proportionate to this first
task-specific gate. Any future confirmatory claim needs its own series.

The owner-adopted lock must include all authored choices above, exact derived
fractions and minimality witnesses, an exhaustive terminal-route table with
exact per-role call counts and derived aggregate bounds, a four-attempt
randomization schedule (`M` plus invalid-attempt capacity), digest bindings,
and the lock digest. Stage selection alone is not numeric adoption. Ollie must
personally adopt the final exact lock digest and authored-choice block, or
explicitly delegate this specific scientific decision authority, before the
first provider-bearing attempt.

## Block validity, stopping, and result routing

A valid block has one settlement for every arm (completed or method-failed),
all workspace/process freezes, complete usage receipts, both initial reviews,
hard-evaluator dispositions, and the integrated review. Arm-specific provider,
compiler, runtime, typed-output, check, timeout, or product failure is an
outcome and never invalidates or selectively reruns the block.

The authoritative primary sampling event is derived only from the sealed
typed field
`integrated_review.product_quality_outcome.rich_vs_direct`, whose closed
domain is `RICH | DIRECT | TIE | INDETERMINATE`. The deterministic hard-contract
override is applied before accrual:

1. if either primary candidate lacks a reproducible trusted product freeze,
   the derived outcome is `INDETERMINATE`;
2. if a candidate has an `UNRESOLVED` hard failure or a confirmed critical
   `PRODUCT_DEFECT`, that candidate cannot be the derived winner; a raw field
   selecting it becomes `INDETERMINATE`;
3. if both candidates have comparable confirmed critical defects, a raw
   winner becomes `INDETERMINATE`, while an authored `TIE` remains `TIE`; and
4. otherwise the derived outcome equals the exact sealed typed field.

Method nonviability never awards product quality to the other arm. It is
reported through the separate viability vector; when it prevents a trusted
freeze, rule 1 supplies `INDETERMINATE`. A derived `RICH` is one favorable
non-tied event, `DIRECT` is one unfavorable non-tied event, and `TIE` or
`INDETERMINATE` contributes no non-tied accrual. E2 scorer values, reviewer
prose, cost, and method viability cannot supply, repair, or replace this
primary field.

Invalidity is limited to predeclared shared/controller faults that prevent a
symmetrical block from existing: source/task binding failure, controller
launch failure before coherent allocation, common provider outage before any
treatment can begin, corrupted common scorer/evaluator bytes, impossible
blinding join, or incomplete accounting caused by the study apparatus rather
than a treatment call. The exact reason and every incurred call are retained.
At most one invalid attempt is allowed.

Study attempts are never resumed. An interruption preserves the attempt as an
outcome or invalid attempt under the locked rule; a permitted replacement uses
the next precommitted attempt ID and fresh sessions. No denominator or timeout
is extended after results exist. `M` exhausted before `N` non-tied primary
comparisons produces `INSUFFICIENT_EVIDENCE`.

The deterministic synthesis emits the full typed vector, factorial contrasts,
hard findings, viability, call/token/time distributions, failure classes, and
claim limits. The primary screen passes only if all of these hold:

1. two non-tied `RICH` versus `DIRECT` outcomes accrue within three valid
   blocks and both favor `RICH`;
2. the viability rule passes;
3. every cost cell is known and the median per-block token-cost ratio is at
   most the owner-adopted cap; and
4. no unresolved critical hard-contract failure belongs to `RICH`.

The reviewed ES closure then records one E3 readiness input:

- `BLACK_BOX_SUFFICIENT` when the screen passes and the evidence can support a
  bounded black-box E3 hypothesis;
- `OBSERVATION_EXTENSION_REQUIRED` only when the screen passes but a specific
  predeclared missing observation prevents the selected E3 contrast; or
- `STOP_E3_HYPOTHESIS` for a failed/insufficient screen or invalid apparatus
  with no bounded correction.

No route is selected from prose sentiment. A positive route authorizes only a
separate E3 component-plan review. A stop route performs the roadmap's early
substrate-disposition step; it does not silently start E3.

## Exclusions

ES does not implement or modify:

- E3 candidate/genome/controller/optimizer/admission behavior;
- E2O, E3F, E4P/E4E, C1-C3, P-series, L6, Phase ME, or F2;
- the E1 source-submodule refusal or E1/E2 native accounting and verdict
  semantics;
- a provider-isolation, sandbox, permissions, secrets, safety, or security
  claim or test;
- current PtychoPINN, the original frozen source commit, any submodule, or the
  lean-pilot evidence root;
- a wheel/sdist/editable install, FRC metric, `ptycho.evaluation`, or whole-repo
  equivalence claim;
- prompt genes, adaptive sample size, provider retries, session resume,
  weighted scalar winner, promotion, or canonical product merge; or
- tests that assert literal prompt prose.

## Execution discipline

Use Subagent-Driven Development without worktrees. Every behavior task starts
with the narrowest RED, implements the direct solution, receives one
independent specification review followed by one distinct quality review, and
commits the exact reviewed paths. A material correction replays only that
task's ordered pair. Closed E0-E2 surfaces are not re-reviewed.

Use `ptycho311` for every projection baseline, smoke, and live workflow. Long
or broad commands run in tmux. Run new modules under `pytest --collect-only`
before execution; run narrow selectors first and the final broad non-security
suite as `pytest -q -n 16 --dist=worksteal` with the existing user-directed
security/safety/secrets/provider-isolation exclusions. No excluded test counts
as evidence.

## Task 0: Accept the exact ES preregistration and component plan

**Files:** this plan; create
`artifacts/review/es-first-effectiveness-study-plan-review.md`; update only the
current E roadmap/index/routing assertions needed to show plan status.

- [x] Commit the proposed, implementation-free plan candidate.
- [x] Obtain `ES_PLAN_SPEC_APPROVED` against exact bytes and governing
      digests.
- [x] Obtain distinct `ES_PLAN_QUALITY_APPROVED` against the same candidate.
- [x] Correct material findings, replay the pair only if bytes change, bind
      the accepted digest/commit/tree, and commit the plan-status transition.
- [x] Run routing/readiness controls postcommit.

Task 0 review closed against corrected commit `27be07e2`, tree `e669471a`,
after ordered `ES_PLAN_SPEC_APPROVED` then distinct
`ES_PLAN_QUALITY_APPROVED`. The correction bound every terminal-route call
count, the reproducible source-projection commit bytes, one authoritative
typed primary outcome with deterministic overrides, and the complete imported
F1 hard contract. The exact review and candidate bindings are recorded in
`artifacts/review/es-first-effectiveness-study-plan-review.md`. Task 1 may
begin after the routing transition; this gate authorizes no live ES call and
does not adopt the proposed scientific lock.

The acceptance transition committed at `2e4e39ea`. Its fresh postcommit
routing and route-readiness control passed all 112 tests in 6.31 seconds.
Task 0 is complete and Task 1 is active.

## Task 1: Build and prove the history-free F1 projection

**Files:** create `scripts/experiments/es/projection.py`, projection schema and
manifest assets under `experiments/orc_effectiveness/f1_es/`, and
`tests/experiments/test_es_f1_projection.py`.

- [ ] RED original-source identity mismatch, any exclusion-set drift,
      retained-row drift, parent/history leakage, extra/unreachable object,
      unsafe symlink, LFS marker, and noncanonical manifest.
- [ ] Generate the exact single-root projection from the literal 204-byte
      message and 430-byte commit-content vector above; independently verify
      its message SHA-256, content SHA-256, framed Git object ID, retained
      blobs/modes/symlinks, and expected tree/commit.
- [ ] Prove original F1 fails E1's existing submodule guard and the projection
      passes actual E1 materialization.
- [ ] Bind a content-addressed absolute projection locator outside the mutable
      checkout.
- [ ] Run static closure and import-origin proofs under `ptycho311`; no import
      may resolve to the live checkout or an excluded path.
- [ ] Run the ten-module projected focused baseline with cache/bytecode writes
      disabled and record exact totals/digests.
- [ ] Obtain ordered Task-1 reviews, commit, and rerun the postcommit controls.

## Task 2: Freeze and calibrate the F1 task/evaluator package

**Files:** add visible task/schema/check assets beneath
`experiments/orc_effectiveness/f1_es/task/`; add the hidden evaluator and
tests under `scripts/experiments/es/` and `tests/experiments/`.

- [ ] Freeze the neutral task, one lifecycle-adapter path, versioned request,
      result, and candidate-evidence schemas, artifact-era fixtures, focused
      selectors, environment identity, claim limits, the complete ten-clause
      F1 hard contract, all five hard-finding dispositions, and the two
      distinct reviewer perspectives.
- [ ] Add the visible assets to one deterministic task-seed commit atop the
      projection and bind both identities.
- [ ] RED missing/extra/unknown structural identity, schema/version drift,
      public/Torch disagreement, fresh-run-only construction, non-fresh
      reload, unpreserved witness fields, unchanged artifact identity after a
      structural change, and any excluded import/path access.
- [ ] Calibrate the evaluator on controlled conforming and defective fixtures;
      evaluator copies must remain byte-identical.
- [ ] Prove configure, construct, forward/backward, optimizer step, save, and
      fresh-process reload/inference in the projected baseline closure,
      including unchanged built-in construction/state signatures, supported
      artifact-era decode plus strict load, public-construction/persisted-
      rebuild implementation equality, and preserved physics/loss/scaling/data
      ownership.
- [ ] Obtain ordered Task-2 reviews, commit, and rerun postcommit controls.

## Task 3: Land exact metering and decision-lock validation

**Files:** create `scripts/experiments/es/metering.py`,
`scripts/experiments/es/decision_lock.py`, their CLI façade, schemas/fixtures,
and focused tests. Do not import `orchestrator.experiments`.

- [ ] RED valid, missing, duplicate, malformed, conflicting, and
      cross-attempt Codex terminal-usage events; prove exact raw-event and
      receipt bindings.
- [ ] RED noncanonical decimals, floats, booleans-as-integers, open fields,
      bad domains, duplicate/unknown arms, reused sessions, adaptive selection,
      digest drift, call-bound drift, and every derived-field tamper.
- [ ] Derive the `N=2`, `k=2`, `M=3`, `1/4`, `81/100`, and `27/32`
      vector mechanically with exact reduced rationals and minimality
      witnesses; retain the alpha-`0.05` known vector as a test.
- [ ] Prove every exact terminal-route call row, complete per-role receipt
      joins, 7–22 calls across valid-block terminal routes, 21–66 calls at
      `M`, the 17–22/51–66 completed-treatment subranges, and 88 absolute calls
      with one invalid attempt.
- [ ] Generate the four-attempt randomization manifest and require exact
      cardinality/permutation bindings.
- [ ] Obtain ordered Task-3 reviews, commit, and rerun controls.

## Task 4: Implement the four treatment workflows

**Files:** create
`workflows/experiments/qa_placement_effectiveness/qa_placement_arms.orc`,
`qa_placement_trial.orc`, role prompt assets/config, and focused compiler/
runtime tests.

- [ ] RED the exact four-cell domain, common `Bool` result, role/correction
      paths, and 1/3–4/2–3/4–6 treatment bounds.
- [ ] Implement DIRECT, DESIGN_QA, PRODUCT_QA, and compositional RICH with
      fresh calls, one bounded correction per placement, and no ceremonial
      revision.
- [ ] Prove shared role prompts, provider policy, effort, timeouts, task bytes,
      check contract, and output responsibilities match wherever roles are
      intended to match.
- [ ] Prove design and product reviewers return typed decisions; downstream
      calls consume typed values and compiler-owned artifact paths rather than
      reparsing prose.
- [ ] Compile through ordinary target-2.25 WCC and run every route with
      scripted providers, including approve, revise, blocked, typed-output
      failure, and one sibling-preserving arm failure.
- [ ] Obtain ordered Task-4 reviews, commit, and rerun postcommit controls.

## Task 5: Assemble the study controller and provider-free end to end

**Files:** create `scripts/experiments/es/controller.py`, review packaging and
synthesis modules, fixtures, and E2 integration tests.

- [ ] RED every source/task/arm/prompt/provider/check/evaluator/environment/
      randomization/lock mismatch before launch.
- [ ] Exercise an entire four-arm E2 trial over deterministic providers:
      coherent concurrent launch, freeze, one scorer per cell, opaque packets,
      initial reviews, hard evidence, integrated review, receipt join, and
      deterministic report.
- [ ] RED every primary-outcome mapping: exact `RICH`, `DIRECT`, `TIE`, and
      `INDETERMINATE`; no-trusted-freeze and nonviability behavior; one-sided
      and comparable critical defects; unresolved findings; and attempted
      substitution from scorer values or reviewer prose.
- [ ] Prove required-check failure, scorer/reviewer failure, arm timeout,
      common invalidity, interruption, fresh next-attempt replacement, and the
      absolute call ceiling. Never resume an attempt.
- [ ] Prove report regeneration from immutable records and reject any
      denominator extension, missing attempt, post-lock mutation, or identity
      disclosure in blinded packets.
- [ ] Obtain ordered Task-5 reviews, commit, and rerun postcommit controls.

## Task 6: Freeze the prelaunch package and obtain owner adoption

**Files:** canonical manifests/lock and an exact pending adoption form under
`experiments/orc_effectiveness/f1_es/`; create
`artifacts/review/es-first-effectiveness-study-prelaunch-review.md`.

- [ ] Freeze all task-seed, environment, apparatus, workflow, prompt,
      evaluator, fixture, schedule, report, hard-contract/disposition, and
      reviewer-perspective bytes.
- [ ] Generate the complete canonical decision lock and verify every derived
      field from scratch.
- [ ] Run the projected baseline, provider-free end to end, metering
      round-trip, tamper matrix, and dedicated-root emptiness/isolation checks.
- [ ] Obtain ordered prelaunch specification then quality reviews against the
      exact package.
- [ ] Publish the exact owner-adoption form containing the lock digest and all
      authored scientific choices. Stop before provider execution unless Ollie
      personally adopts it or explicitly delegates this specific decision.
- [ ] Verify the resulting closed adoption record and bind it into the launch
      manifest without changing any study choice.

## Task 7: Run the locked live series

**Files:** external content-addressed ES evidence root only until immutable
closure artifacts are ready; no canonical PtychoPINN mutation.

- [ ] Launch one live apparatus smoke under `ptycho311`; it is apparatus-only
      and outside the study denominator.
- [ ] Launch attempts in the precommitted order, using the pinned metered
      unrestricted noninteractive provider path and dedicated state/run-ref
      roots.
- [ ] Preserve every completed, failed, invalid, or interrupted attempt and
      all receipts. Never resume, selectively rerun, or extend the schedule.
- [ ] Stop when `N` non-ties accrue or `M` valid blocks are exhausted, subject
      to the one-invalid-attempt cap.
- [ ] Freeze and hash every workspace, packet, review, hard finding,
      disposition, receipt, and ledger before synthesis.

## Task 8: Synthesize, review, and close ES

**Files:** create the deterministic ES evidence report and review artifact;
update only current E routing/status surfaces and tests.

- [ ] Validate and regenerate the complete summary/report from immutable
      records; disclose every attempt, failure, unknown claim, call, token,
      elapsed-time value, and claim limit.
- [ ] Emit `SCREEN_PASSED`, `SCREEN_NOT_PASSED`,
      `INSUFFICIENT_EVIDENCE`, or `STOP_ES_INVALID` from the lock only.
- [ ] Obtain `ES_FINAL_SPEC_APPROVED`, then distinct
      `ES_FINAL_QUALITY_APPROVED`, against exact evidence and report bytes.
- [ ] Record `BLACK_BOX_SUFFICIENT`, `OBSERVATION_EXTENSION_REQUIRED`, or
      `STOP_E3_HYPOTHESIS` as the reviewed E3 readiness input.
- [ ] Commit the closure, run postcommit routing/readiness controls and the
      final broad non-security suite, and report exact fresh totals/digests.

## Task 9: Continue the selected E3 route

- [ ] If readiness is `BLACK_BOX_SUFFICIENT`, immediately draft and route the
      separate black-box E3 component plan through ordered specification then
      quality review before implementation.
- [ ] If readiness is `OBSERVATION_EXTENSION_REQUIRED`, execute only the
      separately reviewed E2O prerequisite route, then return to E3 planning.
- [ ] If readiness is `STOP_E3_HYPOTHESIS`, record the required early
      substrate disposition; do not implement E3 under the stopped hypothesis.
- [ ] In every case preserve E1/E2 and ES evidence identities and make no
      selection beyond the reviewed route.

## Completion criteria

ES is complete only when one immutable owner-adopted lock governs every live
attempt, all scheduled evidence has a validated accounting receipt and frozen
lineage, the deterministic report passes both ordered final reviews, the E3
readiness record is committed, and postcommit controls pass. Plan acceptance,
apparatus completion, a live smoke, or one favorable candidate is not ES
completion.
