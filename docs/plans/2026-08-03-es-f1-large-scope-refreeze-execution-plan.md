# ES F1 Large-Scope Pre-Run Refreeze Implementation Plan

**Status:** Draft pre-run scope amendment; no F1 arm, provider session, study
attempt, invalid-attempt allowance, or denominator row has been consumed.

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task by task. Steps use
> checkbox (`- [ ]`) syntax for tracking. Do not create a worktree.

**Goal:** Replace the too-small two-architecture F1 task with one freshly
frozen, solution-neutral full-architecture task whose controller-only
conforming reference product measures 5,000–10,000 physical implementation
delta lines, with tests and docs additional, without changing the four-arm
treatment topology or consuming a live attempt before the replacement package
and scientific lock pass every gate.

**Architecture:** Retain the history-free PtychoPINN source projection and the
landed DIRECT/DESIGN_QA/PRODUCT_QA/RICH apparatus. Version the task/evaluator
contracts around an exact matrix of all fourteen frozen built-ins plus one
candidate-declared witness, materialize a new task-seed child from the same
projection root, and bind the new task, evaluator, resource envelope,
metering authority, randomization schedule, and pre-run lineage into one new
decision lock. Build a distinct controller-only conforming reference product
from that child, measure it with one reproducible Git/numstat contract, and
require the measured implementation delta to fall inside the owner-directed
band before the lock can freeze. The reference implementation is never
delivered to a provider, and candidate products are never measured or judged
by LOC. The prior task package remains content-addressed provenance only and
contributes no attempt or evidence to the successor denominator.

**Tech Stack:** Python 3.11 in `ptycho311`, canonical JSON and JSON Schema,
PyTorch/PyTorch Lightning, Workflow Lisp target 2.25, Git object plumbing,
pytest, pinned Bubblewrap for evidence-integrity write routing, Pyright, tmux,
and the existing Codex JSONL metering shim.

**Terminology and product boundary:** `ES` means **effectiveness study**
throughout this plan; `F1` is the first fixed task in that study. The sole
source and product authority is the digest-bound PtychoPINN repository below.
EasySpin is not a source repository, projection, task seed, product target,
evidence store, or validation authority for this plan.

---

## 0. Owner scope amendment (2026-08-05)

This section is owner-directed and outranks every other section of this plan.

**Why a refreeze exists at all.** The ES F1 package was frozen on 2026-08-03 as
a preregistration: the task bytes, evaluator bytes, seed lineage, metering
authority, randomization schedule, and decision lock were content-addressed so
that nobody could tune the task or the oracle after seeing arm results. The
owner then directed a roughly tenfold enlargement of the task. Changing task
content necessarily invalidates every digest computed over it. Re-pinning those
digests is the entire legitimate content of a refreeze.

**What a refreeze is not.** It is not a re-derivation of the apparatus. The
four-arm topology, provider/model/effort assignment, role sequence, call
tables, correction bounds, statistical operating rule, cost-ratio rule,
invalid-attempt cap, metering shim, and no-resume semantics were built,
reviewed, and closed on 2026-08-03 and are required by Section 1 bound 6 to
remain **unchanged**. Re-certifying unchanged bytes against new digests is a
mechanical rebinding, not a program of work. The original Tasks 4–8 spent four
separate task-level gates on that rebinding; they are consolidated into one
task by this amendment.

**Ordered edits made by this amendment:**

1. Original Tasks 4, 5, 6, 7, and 8 are replaced by a single consolidated
   **Task 4** in Section 5. Their load-bearing contract content — successor
   seed binding, envelope constants, unchanged call-graph proof, decision-lock
   v3, the provider-free regression gates, and the six owner adoption
   statements — is preserved verbatim inside that task. Their per-task freeze,
   ordered-review, and adoption ceremony is not.
2. The prelaunch gate is **one** review, not an ordered specification/quality
   pair. The package delta under review is digests over already-reviewed
   apparatus bytes plus the Task 1–3A task/evaluator/reference content, and one
   reviewer with the whole package is sufficient authority for that delta.
3. No new prelaunch CLI, collector, template publication step, or review-form
   machinery may be created to police this freeze. Existing validators are the
   freeze mechanism.
4. Section 7 completion criteria are reduced accordingly.

**Task 0 authority is untouched.** Task 0 is closed and its ordered review pair
stands. The `plan_sha256` binding inside
`docs/plans/evidence/es-f1-large-scope-refreeze/task0-review-adoption.json`
records the pre-amendment plan bytes as provenance for the Task-0 decision and
remains valid and unmodified; it is not a live-file assertion. This amendment
removes downstream scope only. It does not alter the source identities, the
projection, the metric, the architecture/lifecycle matrix, the scale band, the
non-delivery requirement, or any Task-0 output, and therefore requires **no
re-review of Task 0 and no new amendment review pair**. Do not open one.

**In-flight work is preserved.** Tasks 1, 2, and 3 are committed. Task 3A is in
progress and is retained in full: it is the viability and oracle-calibration
proof that directly answers the A1 pilot's forfeit failure, and it is not
ceremony. Continue Task 3A from its current step.

---

## 1. Authority, insertion point, and non-negotiable bounds

This plan is subordinate to:

- `docs/plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md`;
- `docs/plans/2026-08-02-workflow-lisp-es-first-effectiveness-study-component-plan.md`;
- `docs/plans/2026-08-03-es-task5-study-controller-execution-plan.md`;
- `docs/plans/2026-08-01-workflow-lisp-post-e2-stage-sequencing.md`;
- `docs/design/workflow_lisp_trial_runs.md`;
- `docs/design/workflow_lisp_program_search_boundaries.md`; and
- `docs/reports/2026-08-01-lean-pilot-forensics-and-e2-study-inputs.md`.

The current E-series authority says E0, E1, and E2 are complete and ES Tasks
0–5 are complete. Refreeze Tasks 0–3 are closed; Task 3A is in progress and
Task 4 is pending. Together Tasks 1–4 own and subsume the old component Task 6
freeze/review/adoption gate and hand directly to existing ES Task 7 after
Task 4. Live allocation remains prohibited, and this amendment does not select
or start E3.

This plan now owns that formerly separate gate: refreeze Tasks 1–4 satisfy,
replace, and subsume the component plan's old Task 6 package-freeze, review,
and owner-adoption work. There is one prospective `decision_lock.v3` and one
owner adoption, both closed in this plan's Task 4; no duplicate component
Task-6 gate follows. After Task 4, existing ES Task 7 is next. Live allocation
remains prohibited throughout this plan.

The source authority is unchanged:

- source repository: `/home/ollie/Documents/PtychoPINN`;
- source commit: `c081b7b6cd160b3da7031ee325bbf0ade1025d7a`;
- source tree: `9193ae2f81116d1bac4cf3cb74395613c1220dbe`;
- history-free projection commit:
  `8f191031f233d50a4d020d8a988036e99487f570`;
- history-free projection tree:
  `e64f3c05f5a0894f41c047d128a9040a2cda6764`.

The pre-amendment package is preserved by Git and by its content-addressed
task-seed repository. Its relevant closure commits are Task 2 at `d24c1818`,
Task 3 at `0d16ca36`, and Task 4 at `d72c6085`. The replacement must call that
package `SUPERSEDED_PRELAUNCH_SCOPE_TOO_SMALL`, not failed or invalid. Before
the replacement record closes, machine checks must prove that the predecessor
has no live attempt record, provider allocation, usage receipt, owner-adopted
lock, or denominator contribution.

The owner-directed amendment binds these requirements:

1. The exact A1 nanoBragg DIRECT product described in Section 3 is the
   calibration anchor: its retained product delta contains 667 production
   additions and 2 production deletions, with 690 physical production lines
   in the postimage. Before launch, a controller-only conforming F1 reference
   product must measure inclusively between 5,000 and 10,000
   `implementation_delta_physical_lines.v1` units. Tests and documentation are
   additional, are recorded separately, and do not count toward that band. Relative to the
   measured 667-line A1 delta, the requested band is approximately
   7.50x–14.99x. This is a strict prelaunch task-scale calibration gate, not a
   candidate acceptance, ranking, or stopping predicate.
   Task 0 must establish the provider-free structural multi-context proxy below
   before task-package work begins; working-set size by itself is not accepted
   as proof. DIRECT nevertheless retains its one-call treatment contract;
   inability to finish is a treatment outcome, not authority to add hidden
   calls, resume, or relax the task.
2. Neither the provider-visible brief, a hard-evaluator clause, a review
   schema, nor the final screen may award, reject, or rank a candidate by LOC.
   No minimum-diff, maximum-diff, file-count, or churn proxy may replace the
   behavioral contract.
3. All fourteen frozen built-ins and one candidate-declared witness must cross
   the same public extension boundary. Every one must be covered for public
   configuration, construction, forward execution, existing-loss backward,
   one optimizer step, checkpoint and bundle save, fresh-process strict reload,
   post-reload inference, persisted identity, and structural round-trip.
4. `neuralop_uno` uses `N=128`; every other frozen built-in uses `N=64`.
   The witness uses the evaluator-bound size declared for its case and may not
   weaken either frozen built-in rule.
5. Physics, loss definition, scaling, measurement-domain, and data ownership
   remain outside the extension boundary. Exercising the existing training
   path does not transfer those responsibilities into an architecture
   descriptor or registration record.
6. The four-arm topology, provider/model/effort, role sequence, correction
   bounds, statistical operating rule, cost-ratio rule, one-invalid-attempt
   cap, and fresh-session/no-resume semantics stay unchanged.
7. No live provider is launched by this plan. The next live action remains the
   existing ES Task 7, and it becomes eligible only after the new package is
   reviewed, committed, personally owner-adopted, and independently reloaded
   and validated from exact bytes.
8. This amendment changes F1 task content and refreezes the existing Task-5
   controller/apparatus around that content. It does not design or implement a
   new provider-call authority, authority ledger, deadline runtime, public
   trial-SDK surface, hard-evidence collector, or other apparatus mechanism.
   Only existing task/evaluator/package bindings and existing timeout, byte,
   and resource fields may change here. Any genuinely missing apparatus
   capability is deferred to its own separately authorized design and plan.

### What this approach makes harder later

Every later task or evaluator change requires a whole-package digest refresh,
new review verdicts, and a new owner adoption; the larger architecture matrix
also makes provider-free calibration and hidden evaluation materially slower.
That cost is intentional. The plan does not add a generic experiment framework
or change E2 merely to make future studies cheaper.

## 2. Exact architecture and lifecycle matrix

The frozen built-in order is authoritative and must be present exactly once:

| Order | Public architecture ID | Evaluator image size |
| ---: | --- | ---: |
| 1 | `cnn` | 64 |
| 2 | `ffno` | 64 |
| 3 | `fno` | 64 |
| 4 | `fno_vanilla` | 64 |
| 5 | `hybrid` | 64 |
| 6 | `hybrid_resnet` | 64 |
| 7 | `hybrid_resnet_convnext_bottleneck` | 64 |
| 8 | `hybrid_resnet_ffno_bottleneck` | 64 |
| 9 | `hybrid_resnet_ffno_ptychoblock_encoder` | 64 |
| 10 | `hybrid_resnet_ptychoblock_ffno_encoder` | 64 |
| 11 | `neuralop_uno` | 128 |
| 12 | `spectral_resnet_bottleneck_linear_decoder` | 64 |
| 13 | `spectral_resnet_bottleneck_net` | 64 |
| 14 | `stable_hybrid` | 64 |

The fifteenth row is one candidate-declared witness architecture. Its public ID
must be nonempty, absent from the frozen built-in set, and distinct from every
existing public or legacy alias. The witness is not a second representative
shortcut: it passes the same lifecycle and identity stages as every built-in.
Its evaluator-derived registry constructor identity and its construction,
checkpoint-reload, bundle-reload, and persisted-rebuild implementation
identity must all name the same witness implementation and must be absent from
the exact fourteen frozen built-in constructor and implementation identity
sets. The witness must own at least one witness-only structural field whose
alternate value changes canonical artifact identity, state/module signature,
and one fixed-seed observable while surviving both persistence routes. A new
public ID that aliases a built-in implementation, including the current
`es_f1_witness -> FfnoGenerator` fixture shortcut, is a hidden-evaluator H09
failure rather than a conforming positive control.

For each of the fifteen rows, the hidden evaluator must independently derive
and freeze:

- the evaluator-bound configuration/input digests and deterministic seed;
- the public construction route and persisted rebuild route;
- implementation identity before save and after each strict reload;
- forward output shape, dtype, finiteness, and deterministic digest/tolerance
  facts appropriate to the frozen contract;
- an existing-loss scalar, finite gradients, and a bounded optimizer-step
  state transition, without giving loss ownership to the extension surface;
- checkpoint and bundle bytes, content identity, and fresh-process reload
  process identities;
- post-reload inference facts for both artifact forms;
- exact structural values before save and after each reload;
- rejection of missing, extra, unknown, and unsupported structural identity
  before a module is returned;
- deterministic identity sensitivity for every evaluator-frozen built-in
  structural field and every candidate-declared witness structural field; and
- equality of the candidate-declared public construction, checkpoint reload,
  bundle reload, and persisted-rebuild implementation identities, plus proof
  that the witness identity is distinct from every frozen built-in identity.

The adapter remains a path-only materialization seam. It may materialize the
thirty checkpoint/bundle artifacts, but it may not author observations,
process identities, structural values, pass/fail claims, or dispositions.

Artifact compatibility is a closed architecture-by-route matrix rather than an
ambiguous Cartesian product. The versioned fixture manifest must contain one
row for every artifact era, and each row must carry exact ordered,
nonoverlapping `applicable_architecture_ids` and
`rejected_architecture_ids` arrays whose union is the complete fourteen-plus-one
domain. The evaluator applies this exact matrix:

| Lifecycle or artifact route | Positive architecture domain | Required result outside that domain |
| --- | --- | --- |
| Public configuration, construction, forward/backward, optimizer transition, and artifact-free inference | all fourteen built-ins plus the witness | not applicable; every row is positive |
| Newly emitted current checkpoint, fresh strict checkpoint reload, and post-reload inference | all fourteen built-ins plus the witness | not applicable; every row is positive |
| Newly emitted current bundle, fresh strict bundle reload, and post-reload inference | all fourteen built-ins plus the witness | not applicable; every row is positive |
| Each retained non-`legacy_v1` historical checkpoint, model-spec, artifact, or bundle fixture | exactly the fixture row's digest-bound `applicable_architecture_ids` | `UNSUPPORTED_ARTIFACT_ARCHITECTURE` before returning a module |
| Metadata-free `legacy_v1` bundle | exactly `cnn` | the other thirteen built-ins and the witness reject with `UNSUPPORTED_ARTIFACT_ARCHITECTURE` before returning a module |
| Unknown, malformed, structurally incomplete, or identity-incompatible artifact | none | every architecture rejects before returning a module |

The current-artifact rows therefore exercise the full fifteen-row lifecycle;
historical rows exercise only their truthfully supported architecture domain
and prove explicit rejection everywhere else. A fixture without the complete
partition, a `legacy_v1` positive for a non-`cnn` architecture, or a silent
fallback to `cnn` fails schema validation or H04.

## 3. Calibration basis and resource envelope

The frozen source census establishes the real behavioral working set without
pretending that inventory size predicts authored output:

For every strict-UTF-8 text blob in this census, a physical line is one element
of Python's `text.splitlines()` result. A nonempty final line counts even when
the blob has no terminal LF. The producer also records raw LF-octet counts as
an explanatory diagnostic, but those counts are not a subtotal, selector, or
calibration authority. Binary and symlink leaves have no physical-text-line
count. This census convention is distinct from the Git-numstat successor-delta
metric below, whose behavior is independently frozen against the A1 anchor.

- generator Python plus `ptycho_torch/model.py`,
  `ptycho_torch/model_spec.py`, and `ptycho_torch/artifact_schema.py`: 6,776
  physical lines;
- the original ten pre-edit focused test modules: 6,833 physical lines;
- the mandatory nineteen-module core pre-edit selector set: 11,800 physical
  lines; and
- the previously named production-responsibility core: 16,052 physical lines.

Neither of the last two core totals is called repository-complete. Task 0 must
scan all 1,948 frozen projection leaves, close the downstream consumer/bypass
inventory, and publish the recomputed projection-wide responsibility total and
exact selector manifest before this plan receives its final ordered reviews.
No pre-census projection-wide total or selector count has authority.

A read-only pre-plan audit of frozen upstream commit
`c081b7b6cd160b3da7031ee325bbf0ade1025d7a` reproduces the old
30-path/16,052-line core and establishes these lower bounds and candidate
totals:

| Audit slice | Unique physical lines | Delta from old core |
| --- | ---: | ---: |
| old named core | 16,052 | 0 |
| plus the six specification-review omissions | 21,697 | +5,645 |
| plus six source-documented core consumers | 29,886 | +13,834 |
| plus 28 direct CDI study consumers, deduplicated | 47,515 | +31,463 |
| plus 35 direct `scripts/studies/**` detector rows, deduplicated | 50,318 | +34,266 |

The former `5,643` omission subtotal, and therefore the former cumulative
`21,695` / `29,884` / `47,513` / `50,316` values, counted LF octets. Two
omission blobs have a nonempty unterminated final line, so those figures are
retained only as explanatory audit provenance and are not census authority.

The last figure is a candidate inventory, not the final responsibility total:
seven detector rows totaling 2,803 lines are shared-block, physics, schematic,
or otherwise non-CDI-looking adapters and still require an explicit
per-consumer Task-0 disposition proposal. They remain in the census until the
proposal is digest-bound and adopted by the closed JSON record produced only
after the ordered Task-0 reviews; rows may
not disappear because of a filename judgment.

The 28 ordinary direct CDI study-consumer paths are frozen provisionally as:

```text
scripts/studies/ablation/configuration.py
scripts/studies/ablation/gain_calibration.py
scripts/studies/ablation/runtime_checkpoint.py
scripts/studies/ablation/runtime_execution.py
scripts/studies/ablation/runtime_ladder_config.py
scripts/studies/ablation/runtime_ladder_cross_eval.py
scripts/studies/ablation/runtime_ladder_execution.py
scripts/studies/ablation/runtime_ladder_mmap.py
scripts/studies/ablation/runtime_ladder_step_parity_cli.py
scripts/studies/ablation/runtime_reference_execution.py
scripts/studies/ablation/runtime_reference_spec.py
scripts/studies/aligned_ablation_variant_grid.py
scripts/studies/cdi_natural_patch_benchmark.py
scripts/studies/demo_varpro_probe_weighted_reassembly.py
scripts/studies/diagnose_placement.py
scripts/studies/diagnose_reconstruction.py
scripts/studies/diagnose_stitching.py
scripts/studies/flux_sweep_eval.py
scripts/studies/fno_hyperparam_study.py
scripts/studies/grid_lines_compare_wrapper.py
scripts/studies/grid_lines_torch_runner.py
scripts/studies/hybrid_checkpoint_inference.py
scripts/studies/lines128_hybrid_resnet_encoder_fusion_variants.py
scripts/studies/lines128_hybrid_resnet_skip_residual_ablation.py
scripts/studies/nersc_orchestration.py
scripts/studies/position_reassembly_checkpoint_replay.py
scripts/studies/recon_quality_gate.py
scripts/studies/varpro_probe_ablation_runner.py
```

Their neutral proposed disposition is `route_through_boundary`, except the
pure reassembly demo may propose `compatibility_adapter`. The seven explicit
Task-0 proposal rows are:

```text
scripts/studies/born_rytov_dt/models.py
scripts/studies/dump_forward_parity_fixtures.py
scripts/studies/openfwi_flatvel_a/models.py
scripts/studies/pdebench_image128/models.py
scripts/studies/pdebench_swe/models.py
scripts/studies/render_hybrid_resnet_schematics.py
scripts/studies/wavebench_shared_encoder/models.py
```

The neutral proposal for those seven is a closed non-CDI/shared-block
`compatibility_adapter` allowlist, with static proof that each constructs no
CDI registry ID, `ModelSpec`, Ptycho artifact, or runtime application. Task 0
must propose each row individually; it may not use the category as a blanket
exemption. For the six specification-review omissions, the proposed
dispositions are `remove` for the three deprecated API modules and
`beta_modules/model.py`, and `route_through_boundary` for
`lightning_utils.py` and `notebooks/analysis.py`. For the six source-documented
core consumers, use `compatibility_adapter` for
`ptycho/workflows/backend_selector.py` and `ptycho_torch/helper.py`, and
`route_through_boundary` for the other four.

The exact path, blob, and line-count rows behind all four totals are retained
in `docs/plans/evidence/es-f1-large-scope-refreeze/source-census.json`; a
copied total without those digest-bound rows has no authority. The census also
materializes this responsibility inventory against the frozen Git objects. A
path that participates in more than one responsibility is counted once in the
physical-line inventory and cross-referenced from every applicable row:

| Migration responsibility | Frozen paths and symbol/call-site anchors | Required calibration evidence |
| --- | --- | --- |
| Structural boundary and persisted identity | `ptycho_torch/model_spec.py` (`ModelSpec`, `derive_model_spec`); `ptycho_torch/artifact_schema.py` (`encode_artifact_identity`, `decode_artifact_identity`, manifest validation) | reference delta rows, structural-field sensitivity, and both artifact reload identities |
| Public configuration | `ptycho/config/config.py::ModelConfig`; `ptycho_torch/config_params.py::ModelConfig`; `ptycho_torch/config_bridge.py` (`to_model_config` and training/inference bridges); `ptycho_torch/config_factory.py` (`create_training_payload`, `create_inference_payload`) | public/config-bridge coverage and canonical structural serialization |
| Construction and all architecture adapters | `ptycho_torch/application_factory.py` (`build_ptychopinn_from_configs`, `build_ptychopinn_application`); `ptycho_torch/model.py` (`_build_generator_module_from_config`, `_resolve_generator_from_config`); `ptycho_torch/generators/registry.py::resolve_generator`; every frozen `ptycho_torch/generators/*.py` implementation needed by the fourteen IDs | all 14 built-in constructors, one distinct witness constructor, and no direct-construction bypass |
| Training and optimizer lifecycle | `ptycho_torch/model.py` (`PtychoPINN`, `PtychoPINN_Lightning`, optimizer construction); `ptycho_torch/train.py` (`main`, `main_lightning`); `ptycho_torch/train_lightning_only.py::main`; `ptycho_torch/api/trainer_api.py::setup_lightning_trainer` | direct, supervised, Lightning, factory, entry-point, and trainer-API runtime probes |
| Checkpoint and bundle persistence/rebuild | `ptycho_torch/model_manager.py` (`save_torch_bundle`, `create_torch_model_with_gridsize`, `load_torch_bundle`); the structural hooks above; cross-reference `ptycho_torch/application_factory.py` as the configuration-to-application/rebuild join | checkpoint and bundle bytes, fresh processes, the closed Section-2 artifact-era applicability matrix, and implementation identity equality |
| Fresh reload and inference | `ptycho_torch/inference.py` (`load_and_predict`, inference/reconstruction routes) and `ptycho_torch/workflows/components.py` consumers | both fresh reload routes and post-reload inference for every architecture |
| Projection-wide downstream consumers | Every detector match across all 1,948 frozen leaves, including `ptycho_torch/api/api_helper.py`, `ptycho_torch/api/base_api.py`, `ptycho_torch/api/mlflow_utils.py`, `ptycho_torch/lightning_utils.py`, `ptycho_torch/beta_modules/model.py`, `ptycho_torch/notebooks/analysis.py`, `ptycho/workflows/backend_selector.py`, `ptycho_torch/helper.py`, `ptycho_torch/reassembly.py`, `scripts/inference/inference.py`, `scripts/training/train.py`, API examples, and every relevant `scripts/studies/**` construction/checkpoint/bundle/reconstruction caller (including `grid_lines_torch_runner.py`) | one proposed `route_through_boundary`, `compatibility_adapter`, or `remove` disposition per consumer/call site, adopted only by the closed JSON record produced after the Task-0 review pair, plus an existing selector or a new static/runtime proof selector per proposal |
| Compatibility and legacy-bypass retirement | every frozen direct generator import, architecture switch, config-family read, constructor, reconstruction shortcut, and inference/training consumer discovered from the rows above | one referenced consumer proposal and resulting bypass-oracle proof per baseline row plus one new-bypass negative control |

The census keeps leaf classification separate from disposition authority.
Its `leaf_rows` contains exactly one path-ordered row for each of the 1,948
Git leaves. A leaf row records only `path`, `mode`, `object_type`, `object_id`,
`byte_count`, text/physical-line facts, detector outcomes, responsibility
memberships, and exactly one closed classification shape:

- a matched leaf has `classification="matched"` and one nonempty, ordered,
  unique `match_ids` array; or
- a nonmatch leaf has `classification="nonmatch"` and one stable nonempty
  `nonmatch_reason`.

A leaf row never contains a disposition, proof selector, or review state.
Each detector match then joins to exactly one separate `consumer_rows` row;
one leaf may therefore own several consumer/call-site rows. Each closed
consumer row records `consumer_id`, `match_id`, caller path/blob/span,
detector ID/version, callee or dispatch form, responsibility IDs,
`proposed_disposition`, `required_proof_kind`, `selector_id`, `witness_kind`,
`coverage_status`, and `coverage_witness_ids`. `coverage_status` is exactly
`required | inherited | open`; `required` carries exactly one witness ID, while
`inherited` and `open` carry none. `inherited` means observable but not selected
by the sampling rule; `open` means unresolved or unobserved. Every status retains
the consumer's exact frozen blob/tree/match/span identity.
`proposed_disposition` is exactly one of `route_through_boundary`,
`compatibility_adapter`, or `remove`. Nonmatch leaves have no consumer rows,
every matched `match_id` is consumed exactly once, and no consumer may refer
to a missing or differently bound leaf. Both leaf variants and the consumer
row set `additionalProperties=false`; selector or disposition fields in a leaf
row and leaf-classification fields in a consumer row are schema errors. Each
consumer ID/match binding and `proposed_disposition` must exactly equal its
policy-manifest entry; the producer may not invent, default, or revise one.

The closed `legacy_bypass_inventory` references the applicable `consumer_id`
values instead of duplicating their dispositions. The hidden evaluator binds
the resulting inventory digest. It combines frozen AST detectors for
direct imports, architecture switches, constructors, and reconstruction
shortcuts with runtime witness probes through every known consumer. Each
baseline row must be absent or demonstrably delegate through the declared
boundary, and no new direct bypass may appear. A negative control that restores
one baseline bypass must fail the owning hidden clause.

The Task-0 census is a neutral proposal, never a self-certified review result.
The ordered specification and quality reviewers each produce a human-readable
Markdown view. A destructive-purge gate parses only its exact machine header:
one verdict, reviewer identity, offset-aware review timestamp, the five common
authority bindings, and the seven required findings. It verifies the raw view
digests, distinct reviewers, and specification-before-or-equal-to-quality
chronology before any captured root is removed; prose outside that header is
never claim authority. That purge-only header does not adopt a consumer
disposition. The sole machine authority for disposition adoption is one closed canonical
`es_f1_task0_review_adoption.v1` JSON record, validated by
`task0-review-adoption.schema.json`. It contains exactly two ordered review
rows—specification first and quality second—with distinct reviewer identities,
the exact required verdict, reviewed timestamp, and raw digest of the matching
human view. Each row binds the same five authority digests: this plan's raw
SHA-256 plus the canonical `record_sha256` of the pre-edit policy, census,
selector manifest, and A1 anchor. The adoption record has its own canonical
`record_sha256`, sets `additionalProperties=false` throughout, and is the sole
authority that adopts the proposed consumer dispositions. The census is not
rewritten to say “reviewed” after approval. Every later validator that consumes
a proposed disposition must receive and verify this JSON adoption record and
all five exact bindings, avoiding a census/review digest cycle. Missing,
reordered, duplicate-reviewer, non-approved, stale, or Markdown-only review
state fails closed.

### Reproducible census and selector authority

Task 0 owns runnable discovery, production, and validation rather than a
hand-edited table. `scripts/experiments/es/source_census.py` reads only the
remote-free bare
projection repository at
`/home/ollie/.local/state/orchestrator/es-source-projections/git-sha1/8f191031f233d50a4d020d8a988036e99487f570`.
It must resolve the exact projection commit/tree above, reproduce retained
inventory digest
`sha256:6fc936c54977d9adc7bdbae02bfa69592c55722e5cf5eddbd1b958ee1bc71404`,
and enumerate exactly 1,948 leaves through NUL-delimited Git object plumbing.
It may not read the live PtychoPINN checkout or a materialized projection
worktree.

Task 0 first publishes the closed
`preedit-discovery-input.schema.json` and
`preedit-discovery-input.json`. This record is explicitly
`authority_status=non_authoritative_discovery_input`; it contains the exact
projection/Git identity, detector IDs/versions/configurations, responsibility
IDs/anchors, and nineteen module selectors, but it is schema-forbidden from
containing a consumer ID, disposition, proof assignment, review claim, or
downstream-authority flag. The `source_census discover` subcommand accepts that
record and its expected raw digest explicitly and emits canonical deterministic
`.tmp/es-f1-source-census-discovery.json`. The discovery output contains only
the complete leaf/match/consumer candidates and exact anchors plus
`authority_status=NON_AUTHORITATIVE_DISCOVERY`; it has no `record_sha256` and is
never a Task-1+ input. Two independent discovery runs must be byte-identical.

Only after reviewing that output may Task 0 author and publish one canonical
closed
`es_f1_preedit_policy.v1` record at
`docs/plans/evidence/es-f1-large-scope-refreeze/preedit-policy-manifest.json`,
validated by `preedit-policy-manifest.schema.json`. This is the sole authority
for the final neutral per-consumer disposition proposals, desired proof
specifications, and coverage-witness kind/selector assignments. Exact pytest
node IDs and observed witness results are derived later by the proof runner and
bound by the reviewed selector manifest; the producer may not choose a
different consumer-to-selector assignment. The policy also repeats and binds the discovery
input/output raw digests and every non-projection input: pinned Git executable
path/version/SHA-256 and exact object/diff controls; detector IDs, versions,
and configurations; responsibility IDs and anchors; both selector-lane
declarations and coverage rules; the finite no-consumption scope below; and the
A1 evidence members, raw digests, and expected calibration values.
Its selector policy requires the literal `sampling_rule`
`first_observable_per_provider_and_disposition_witness_class_in_discovery_order.v1`.
The exact required consumer set is the discovery-ordered union, deduplicated by
consumer ID, of the first observable consumer for each provider selector and
the first observable consumer for each
(`proposed_disposition`, `witness_kind`) class. A class with no observable
representative blocks publication; an individual `open` row otherwise does
not. The separate candidate-declared fifteenth architecture and its lifecycle
witness are created later by the task/evaluator package and are not a Task-0
coverage consumer.
`build-census`
does not trust the discovery bytes: it rescans the frozen Git objects and
requires the recomputed leaf/match/consumer candidate set to equal both the
discovery digest bound by the policy and every final policy consumer ID/anchor.
An omitted, extra, or revised candidate stops the build. The policy uses the
same `record_sha256` projection defined below. The census, selector manifest,
and A1 anchor each bind its verified `record_sha256`. No CLI has a built-in
detector, proposal, selector, root, Git, or A1 default that can substitute for
the explicit discovery input and final policy.

The finite supported no-consumption authority consists of exactly these
external roots:

```text
/home/ollie/.local/state/orchestrator/es-f1-full/runs
/home/ollie/.local/state/orchestrator/es-f1-full/run-refs
/home/ollie/.local/share/agent-orchestration/es-f1-full/evidence
```

and exactly these repository-relative prospective control files:

```text
experiments/orc_effectiveness/f1_es/decision-lock.json
experiments/orc_effectiveness/f1_es/controller-package.json
experiments/orc_effectiveness/f1_es/prelaunch-owner-adoption.json
experiments/orc_effectiveness/f1_es/launch-manifest.json
```

At Task-0 capture, each listed root must either be absent or be a real,
non-symlink, readable directory with zero immediate entries; every other file
type, symlink, unreadable root, or child entry fails closed. Each listed
repository path must be absent according to `lstat`; existence as any file
type fails closed. The policy and census record each root as `ABSENT` or
`PRESENT_EMPTY_DIRECTORY` and each repository path as `ABSENT`, together with
the sorted immediate-entry observation, one explicit policy `captured_at`, and
a canonical observation digest. Replay validators re-observe live state but do
not encode their wall-clock invocation time, so identical facts produce
byte-identical records. These roots later become, without fallback or aliasing,
the exact controller `state_dir`, `run_ref_root`, and `evidence_root` bound in
the controller package and launch manifest. This is the complete supported F1
no-consumption scope; locations outside these enumerated roots and paths are
`not_asserted`, never silently treated as absent. A contrary in-scope fact
stops Task 0.

The producer then emits two canonical, closed-schema records:

- `es_f1_source_census.v1`, validated by
  `source-census.schema.json`, contains the distinct `leaf_rows` and
  `consumer_rows` shapes above. It also binds the pre-edit-policy digest,
  projection commit/tree, retained inventory digest, leaf count, producer path
  and SHA-256, group subtotals, responsibility total, referenced
  legacy-bypass inventory, exact no-consumption observations, and canonical
  record digest.
- `es_f1_preedit_selector_manifest.v1`, validated by
  `preedit-selector-manifest.schema.json`, binds the exact census digest and
  pre-edit-policy digest, the exact Task-0 baseline characterization, and
  desired-state proof specifications without post-edit result claims. It
  contains two typed, disjoint, closed selector-row shapes:

  - each of the exactly nineteen ordered
    `provider_visible_pytest_selectors` rows has only `selector_id`, `ordinal`,
    `pytest_module_path`, `projection_blob_id`, `mode`,
    `physical_line_count`, nonempty ordered exact `pytest_node_ids`, and
    exactly one `coverage_witness_ids` entry. The validator concatenates all
    nineteen module paths in ordinal order into one fixed
    `pytest -q -p no:cacheprovider <path>...` invocation; per-row invocations
    are not an alternative authority. This row shape may supply
    `boundary_runtime` only through a passing mechanically observed witness.
    Only these module paths enter `task-profile.focused_selectors`, the visible
    check manifest, and `qa_placement_trial.orc` before the separate
    candidate-owned selector.
  - each `controller_only_proof_selectors` row has only `selector_id`,
    `ordinal`, `proof_kind`, `execution_kind`, `runner_path`, `runner_sha256`,
    exact ordered `argv`, nonempty ordered `input_bindings` of path plus raw
    SHA-256, and zero or one `coverage_witness_ids`. It has none of the
    projection-pytest fields and is executed only by the provider-free
    `scripts/experiments/es/boundary_proofs.py` runner.

The manifest's separate closed `coverage_witnesses` array mechanically joins
each selector to consumers instead of trusting a self-declared consumer list.
A `pytest_runtime` witness binds one exact collected node ID, consumer ID and
span, detector match, probe/event ID, runner digest, and expected observed
event. A `static_ast` witness binds one consumer/detector span and one exact
syntax query/result. A `runtime_probe` witness binds one consumer, exact probe
input, expected boundary event, and process-isolated result. The runner must
emit the consumer/span or event from observation; merely echoing the manifest
identifier is invalid. Every witness references exactly one selector and one
consumer, every listed node ID must be present in Task 0's collected node set,
and a selector's `coverage_witness_ids` must equal the witness rows that point
back to it. Provider selectors therefore have exactly one such row and
controller selectors have zero or one. No row contains
`covered_consumer_ids`.

The baseline characterization records the aggregate nineteen-module argv,
complete collected-node digest, collection/pass/fail/error/skip totals,
origin-isolation report digest, exact projection tree before and after, and one
baseline result for every coverage witness. Baseline facts may truthfully show
a bypass, present removal target, or other desired-state failure; they are
characterization, not conformance. The separate desired-state proof specs bind
the required post-edit result for every witness. Task 3A, not Task 0, executes
those specs against the exact reference-product tree and publishes the
digest-bound result rows. Task 6 only replays the same specs/results against
that bound reference product. This avoids binding future reference bytes into
Task 0 and never asks a removal or migration proof to pass against the pre-edit
tree.

Both row schemas and every witness/result shape set
`additionalProperties=false`. Selector IDs and ordinals are unique and lane
IDs are disjoint. Every provider selector and every required consumer owns
exactly one mechanically validated witness; a controller selector owns zero or
one. The consumer domains of coverage witnesses, desired-proof specs, executed
proofs, and witness results are exactly the sampling-rule-derived required set.
Observable nonsampled consumers are retained as `inherited`, unresolved or
unobserved consumers are retained as `open`, and neither status owns a witness.
No nonmatch leaf is covered. The proposal-to-proof mapping is closed:
`route_through_boundary` requires `boundary_runtime`,
`compatibility_adapter` requires `non_cdi_static`, and `remove` requires
`reference_absence`. A provider-visible row supplies only
`boundary_runtime`; controller-only rows declare exactly one of
`boundary_runtime`, `non_cdi_static`, or `reference_absence`. The validator
rejects a missing required representative, a witness attached to an
`inherited`/`open` consumer, an unused witness, unknown node ID,
unobserved/echoed required witness, wrong proof kind, cross-lane identity
duplicate, mixed row shape, or controller-only selector identity in
provider-visible results or task assets. A controller aggregate may privately
reuse provider module paths without merging selector, process, or result
identity.

The detector contract is deterministic and syntax-aware for Python: it closes
direct and aliased imports, registry/config/construction calls and switches,
`TorchRunnerConfig`/`run_grid_lines_torch`, checkpoint and bundle APIs,
reconstruction, reload, inference, and runtime-application consumers. Lexical
detectors may supplement AST results for non-Python leaves, but each detector
has a stable ID and version and every match names exact line spans and anchors.
Every one of the 1,948 leaves is evaluated exactly once at the leaf layer;
responsibility cross-references may be many-to-many, while physical-line
subtotals deduplicate by path. The validator requires matched plus explicit
nonmatch rows to equal the complete Git leaf set, joins every match ID to
exactly one consumer row, and rejects a
missing, extra, duplicate, or reordered leaf; blob, mode, byte, line-count,
detector-version, producer, policy, inventory, commit, tree, subtotal,
consumer-map, proposal, selector, no-consumption observation, or
canonical-digest drift also fails closed.

All four reviewed Task-0 authority records—the policy, census, selector
manifest, and A1 anchor—and the separate review-adoption record use the
required field `record_sha256`. The five digests bound by each ordered review
row are the plan raw SHA-256 and the four authority-record digests; the
review-adoption record does not bind itself. Each record's digest domain is the
record object with exactly that top-level field omitted, encoded as UTF-8
canonical JSON with sorted object keys, no insignificant whitespace,
`ensure_ascii=True`, and one trailing LF. The field value is
`"sha256:" + SHA256(canonical_body_bytes).hexdigest()`. The schemas reject a
missing or extra digest field; the validator removes no other field and
recomputes this projection before trusting any record. Tests must change
one body value while retaining the old digest, change only the digest, add a
second digest-looking field, and attempt to hash the complete digest-bearing
record; all four cases fail closed. The selector manifest binds the verified
`source-census.json` `record_sha256`, and all three derived records bind the
verified policy `record_sha256`; none trusts an ambient file hash or a digest
computed before validation.

### Exact scale metric and A1 anchor

`implementation_delta_physical_lines.v1` compares the successor task-seed
tree with the controller-only reference-product tree. It uses pinned
`/usr/bin/git` 2.43.0 with executable SHA-256
`2a8c18fbf43da9f692d75474c72bea9dfd796c260b0f3dfe456376abc3bbd668`
and these diff controls:

```text
--no-ext-diff --no-textconv --diff-algorithm=histogram
--find-renames=100% --find-copies=100% --find-copies-harder
```

Only production Python paths assigned to at least one frozen behavioral
responsibility by the Task-0 proposal and its digest-bound approving reviews
are counted. Tests, documentation, fixtures,
generated files, caches, vendored code, and benchmark/task-seed assets are
reported as separate totals. Candidate-authored or reference-authored product
Python is not an excluded “candidate asset”: every new production path,
including the distinct witness implementation, must declare at least one
closed responsibility ID and is counted. The metric sums the Git `numstat`
additions column: a new
physical line counts one; a replacement counts its postimage/addition line
once; its paired deletion adds no unit; a pure deletion, unchanged line,
exact rename, or exact copy adds zero. Blank and comment lines count because
the metric is physical. A binary, non-UTF-8, symlink, generated, or
unclassified production path is a calibration failure. The canonical record
contains the baseline/reference blob IDs, additions, deletions,
responsibility IDs, and classification for every path. Independent quality
review rejects padding, formatting churn, copied code, or mechanical
relocation offered as behavioral scope.

The anchor is one closed `es_f1_a1_calibration_anchor.v1` record, validated by
`a1-calibration-anchor.schema.json`. Its only evidence root is:

```text
/home/ollie/.local/share/agent-orchestration/lean-pilot-evidence/pilot-2026-07-27/a1-v7
```

The schema sets `additionalProperties=false` at every object and requires:
`schema_version`; that exact absolute `evidence_root`; the verified pre-edit
policy digest; a closed ordered `members` array of exact root-relative path,
raw SHA-256, and byte count; `block_id`; `arm_id`; treatment; lifecycle and
viability facts; product-manifest digest; review outcome and ordered review
digests; the exact metric input paths/digests; the expected metric result; and
`record_sha256`. These are the required member bindings:

| Member | Exact root-relative path | Bytes | Raw SHA-256 |
| --- | --- | ---: | --- |
| pilot lock | `pilot-lock.json` | 14,598 | `b8d69ba2f3d2b2e7bc6d9181d776db0b7abacd2035f851cd44be613dac6d8503` |
| summary | `summary-2026-07-31/pilot-summary.json` | 10,901 | `153263159d6516d032be83bd8f53954be0ba05b39af58be23d1abdca34085e89` |
| block record | `evidence/b-5970f312e6698e50/block-attempt.json` | 2,576 | `e5c3c5d8fca11860d48864cc1f4164d7b80df26cba62751754899f659b8f72c2` |
| package manifest | `packages/b-5970f312e6698e50/b-5970f312e6698e50/manifest.json` | 2,987 | `142320b4bf4f20e4015520583c535efcf22e8713552c152a25719c1473377cde` |
| DIRECT patch | `packages/b-5970f312e6698e50/b-5970f312e6698e50/candidates/candidate-3cca13b2595a/diff.patch` | 33,695 | `55cd1a8216d0b7c749e6d9dfb47b1fa998ebed888101e5dca03349ba75d57ebb` |
| base production input | `evaluation/b-5970f312e6698e50/base/torch_port/entrypoint.py` | 360 | `c458f6b0fba0dc2ebd80c756d51278f53dc9d15320bf5f677c7878d8331aaa80` |
| base types input | `evaluation/b-5970f312e6698e50/base/torch_port/types.py` | 85 | `63118fc7530528b564f29752a20415b51db02fb572843d3864ba5e2f903eb92a` |
| base package input | `evaluation/b-5970f312e6698e50/base/torch_port/__init__.py` | 113 | `b33a873ed5bde35302e67190698bf0fa655bdd57077db89d5183101ef6f4ec35` |
| DIRECT production input | `evaluation/b-5970f312e6698e50/candidates/arm-4301192e76f41f90/torch_port/entrypoint.py` | 26,770 | `f1ea1162fba1151aa8b13967565eaed9d515b0ebb8d35d0565a97c1fdaaa653c` |
| DIRECT types input | `evaluation/b-5970f312e6698e50/candidates/arm-4301192e76f41f90/torch_port/types.py` | 85 | `63118fc7530528b564f29752a20415b51db02fb572843d3864ba5e2f903eb92a` |
| DIRECT package input | `evaluation/b-5970f312e6698e50/candidates/arm-4301192e76f41f90/torch_port/__init__.py` | 113 | `b33a873ed5bde35302e67190698bf0fa655bdd57077db89d5183101ef6f4ec35` |
| review 1 | `evidence/b-5970f312e6698e50/reviews/calibration-reviewer-01/review-result.json` | 7,998 | `881cf86d2fdcdef1a158fedceaf3211e82de0a3616c1f7080d48c5fe5443b2d9` |
| review 2 | `evidence/b-5970f312e6698e50/reviews/calibration-reviewer-02/review-result.json` | 11,577 | `b10b517fdf63f330666fe96798733c3f1551987033fe9a86f2f43f5139cb07b4` |

The exact top-level anchor keys are `schema_version`,
`preedit_policy_sha256`, `evidence_root`, `members`, `selection`, `metric`, and
`record_sha256`. A member row has only `member_id`, `path`, `byte_count`, and
`sha256`. `selection` has only `pilot_lock_sha256`, `block_id`,
`block_record_sha256`, `arm_id`, `treatment_id`, `lifecycle_outcome`,
`viability_case`, `comparison`, `method_outcome`,
`product_quality_review_outcome`, `product_manifest_sha256`, and the ordered
two-element `review_result_sha256`. `metric` has only `metric_version`,
`git_contract_policy_sha256`, ordered `base_member_ids`, ordered
`candidate_member_ids`, `patch_member_id`, `implementation_additions`,
`implementation_deletions`, and `candidate_postimage_physical_lines`. Every
member ID is unique and used by `selection` or `metric`; extra/unreferenced
members reject.

The closed expected values are block `b-5970f312e6698e50`, DIRECT arm
`arm-4301192e76f41f90`, lifecycle `COMPLETED`, viability `BOTH`, product
manifest digest
`sha256:1ec8f066bc042a582b20059aeb6f45f21ae5f799def730b3a6ca8792e97bde7a`,
comparison `DIRECT_VS_ORC`, method outcome `A_WIN`, product-quality review
outcome `A`, and the two agreeing review-result digests in the table. The base
production tree is 25 physical lines and the DIRECT production tree is 690
physical lines. Re-rendering those exact members through
the policy-bound Git executable and diff controls must yield exactly 667
production additions and 2 production deletions; copied numbers are not
accepted as measurement.

Both `source_census validate` and Task-3A `reference_calibration` require
explicit `--a1-anchor`, `--a1-anchor-schema`, and
`--expected-a1-anchor-sha256` inputs. They first verify the anchor's canonical
digest, then every listed raw member, internal block/arm/review binding, and
the fresh 667/2 metric result. A missing member, path escape, symlink,
unreadable byte, digest mismatch, wrong result, unlisted substitute, or
ambient A1 root fails closed.

### Early provider-free feasibility and structural multi-context proxy

Task 0 must complete a disposable, provider-free feasibility spike before any
Task-1 task-package edit. The spike uses only an exact extract of the frozen
projection plus the digest-bound discovery input and runs outside every task
seed, provider workspace, run root, and reference-product repository. Every
enumerated disposable source, test, and object byte remains present through
the ordered specification review and then the ordered quality review. Only
after both approvals may the authenticated runner purge those exact roots and
emit the post-purge tombstone; the spike code is never promoted or delivered
as a solution.

The structural proxy has these six fixed responsibility clusters:

1. `IDENTITY_CONFIG`: structural identity, public configuration, validation,
   and canonical serialization;
2. `CONSTRUCTION_ADAPTERS`: the shared construction boundary, all fourteen
   built-ins, and the distinct witness seam;
3. `TRAINING_OPTIMIZER`: direct, supervised, Lightning, entry-point, and
   trainer-API execution;
4. `PERSISTENCE_REBUILD`: current checkpoint/bundle save and strict reload plus
   the closed historical-artifact applicability matrix;
5. `INFERENCE_WORKFLOWS`: fresh-process inference, reconstruction, and workflow
   consumers; and
6. `CONSUMER_BYPASS`: projection-wide consumer migration and legacy-bypass
   retirement.

The Task-0 baseline must show at least four clusters with independently unmet
desired-state obligations and disjoint primary production path sets, plus at
least three directed cross-cluster integration edges. Each unmet obligation is
backed by an observed failing desired-state witness, not by a line estimate.
The feasibility spike implements the smallest coherent vertical slice that
crosses those four clusters and three edges, reruns their exact witnesses, and
records the changed production paths, responsibility/cluster assignments,
physical delta, elapsed time, and pre/post tree digests. Removing any one
cluster's slice from the disposable tree must make its owning witness fail;
changing only the registry or application factory may not masquerade as four
independent clusters. Padding, copied branches, format churn, or a synthetic
failure is a spike failure.

In this plan, “genuinely cannot fit one provider context” means only the
owner-selected operational multi-context criterion: the complete Task-3A
reference must pass the strict 5,000–10,000 physical implementation-delta-line
gate, and the authenticated Task-0 capture must show four independently unmet
clusters, three authenticated cross-blob edges, remove-one failures for every
implemented cluster slice, and the non-collapse requirement that the vertical
slice cannot reduce to one already-centralized edit. All parts are conjunctive.
This is not a universal mathematical impossibility theorem about every model or
provider context, and it creates no tokenizer or context-capacity gate.

If any structural part of the operational criterion fails, Task 0 stops for an
owner-reviewed scope amendment. If the later complete conforming reference
honestly measures below 5,000 or above 10,000, Task 3A likewise stops and
restarts the amendment. Neither gate may invent work merely to cross the line
threshold. Candidate contracts and outcomes remain free of LOC, cluster-count,
file-count, and churn acceptance criteria.

#### Authenticated feasibility capture and deletion lifecycle

Task 0 alone owns `feasibility_proofs.py`, its tests, and the committed canonical
feasibility evidence. The capture binds the frozen base and an exact closed
overlay path/mode/blob set through tree algebra, including derived test-only and
remove-one trees. A SHA-bound, runner-owned pytest ledger uses pinned,
origin-isolated Git and Python and records the exact argv, node IDs, project
origins, pre-tree, and post-tree. It also records directed producer-definition
→ consumer-callsite AST coordinates and, for each edge, a same-green-node trace
of the callsite and callee across distinct cluster blobs.

One capture performs two green executions and retains their elapsed times; two
independent derivations of the package must be byte-identical after excluding
only declared volatile fields. Before purge, the capture truthfully retains all
disposable source, test, and object bytes through ordered specification then
quality review. Both reviewers must adopt the anti-padding and non-synthetic
findings, four-cluster evidence, three authenticated cross-blob edges,
remove-one failures, non-collapse requirement, and the rule that the criterion
cannot close until Task 3A passes the strict 5,000–10,000 reference-size gate.
After both approvals, the runner purges the exact disposable roots and emits a
post-purge tombstone that binds the capture and both review digests and records
`lstat` absence. The selector binds the capture; each review row retains the
five common digests; and the top-level adoption additionally binds the
tombstone, avoiding a digest cycle. Committed evidence contains no source,
snippets, patches, or tracebacks, and the runner is never provider-visible.

The exact adjacent selector includes two tests whose unmodified production
path writes relative `training_outputs` artifacts. The capture therefore uses
one pinned, ledger-visible Bubblewrap execution envelope: the authenticated
materialized source root's canonical host path is recorded separately and is
mounted read-only at the fixed runtime namespace path
`/run/orc-pytest-project`; the exact relative `training_outputs` path is backed
by a declared external artifact root; and `/tmp`, `HOME`, and cache roots are
backed by declared disposable external roots. The target Python argv and the
wrapper argv/executable identity are recorded separately, and the external
artifact write set is captured. This
preserves the tests' exact configuration and behavior while making source-tree
pre/post identity truthful; it does not claim that the execution view performs
no writes. Direct runner mode remains available for selectors with no declared
writable mount and fails closed on any project-root write. Silent cleanup,
ignored-path omission, a harness monkeypatch, and training fast-dev shortcuts
are forbidden.

The capture pins literal Python
`/home/ollie/miniconda3/envs/ptycho311/bin/python`, real executable
`/home/ollie/miniconda3/envs/ptycho311/bin/python3.11`, version `Python
3.11.13`, and real-executable SHA-256
`d575ac63749e61ede79bc20518113452b114506ceec0af0cf3993b0fcc486cb0`.
It pins `/usr/bin/bwrap`, version `bubblewrap 0.9.0`, and SHA-256
`52231e1caf55bcbc667b269f49c63599a6f7db4767ae6a039580d0ff853db712`.
Every invocation re-verifies those bytes and version outputs before use.

### Controller-only reference product and strict gate

After the successor task seed exists, Task 3A builds one genuine conforming
reference implementation in a separate, remote-free, content-addressed bare
repository under
`/home/ollie/.local/state/orchestrator/es-reference-products/git-sha1/<reference-commit>`.
The repository exposes only its reference-product ref and is not part of the
task-seed object database. Its manifest binds the frozen upstream/projection/
task-seed commit and tree, reference commit and tree, repository snapshot,
canonical patch, per-path delta rows, measured total, full visible and hidden
evaluation results, distinct-witness proof, bypass-oracle result, and
no-delivery proof.

The reference implements every item in this indivisible behavioral contract
before scale is measured:

1. all fourteen built-ins plus the distinct witness through configuration,
   construction, forward/backward, optimizer transition, checkpoint, bundle,
   fresh reload, inference, identity, and round trip;
2. architecture-owned structural fields, defaults, validation, canonical
   serialization, missing/extra/unsupported rejection, and sensitivity;
3. every frozen direct, supervised, Lightning, application-factory, training
   entry-point, and trainer-API consumer;
4. all supported checkpoint/bundle reconstruction and artifact eras;
5. all frozen inference and workflow consumers; and
6. complete frozen bypass retirement or delegation through the boundary.

Launch eligibility is exactly inclusive:

```text
5000 <= implementation_delta_physical_lines <= 10000
```

There is no 20-percent escape band. If an honest complete reference is below
5,000 or above 10,000, F1 is unsuitable at the requested scale in this shape.
Replace or coherently redesign the task, rerun the projection-wide census, and
restart the reviewed pre-run amendment and package freeze. None of the six
required items may be trimmed, deferred, or treated as a removable scale
tranche; padding, copied branches, formatting churn, and line-driven deletion
of required behavior are forbidden.

The no-delivery proof establishes that the task-seed reachable closure remains
exactly the projection plus visible child; reference-only commits, trees, and
blobs cannot resolve from that repository; no reference locator, patch,
source blob, manifest, canary, or measured count appears in visible assets,
prompts, provider argv/environment, or provider packets; and provider
workspaces materialize only from the bound task seed. This is package-level
non-delivery, not a filesystem-secrecy claim. Candidate products are never
measured: candidate schemas, reviewer packets, synthesis, stopping logic, and
outcomes reject or omit LOC/file-count/churn fields. Candidate correctness is
entirely behavioral.

The replacement pre-edit closure adds these nine existing selectors to the
current ten, in this exact order before the candidate-owned selector:

1. `tests/torch/test_fno_generators.py`
2. `tests/torch/test_fno_lightning_integration.py`
3. `tests/torch/test_neuralop_uno_generator.py`
4. `tests/torch/test_model_output_modes.py`
5. `tests/torch/test_model_manager.py`
6. `tests/torch/test_model_training.py`
7. `tests/torch/test_train_lightning_execution_contract.py`
8. `tests/torch/test_object_big_generator_contract.py`
9. `tests/torch/test_structural_config_ownership.py`

`tests/torch/test_es_f1_extension_boundary.py` remains the separate
candidate-owned selector. Regenerate the task profile's exact
provider-visible nineteen-selector digest and separately bind the complete
two-lane selector-manifest digest; no old digest is retained by assertion and
the two digest domains may not be substituted for each other.

The replacement resource plan uses these conservative bounds:

| Resource | Frozen value | Meaning |
| --- | ---: | --- |
| One visible-check invocation | 7,200 s | Per required visible invocation |
| Hidden evaluator per candidate | 14,400 s | Full 15-row lifecycle and artifact evaluation |
| E2 evaluation check | 14,400,000 ms | Public trial check deadline |
| One arm | 172,800,000 ms | 48-hour arm deadline |
| One four-arm trial | 216,000,000 ms | 60-hour concurrent trial deadline |
| One complete attempt/block planning allowance | 120 h | Capacity estimate only; not a new runtime deadline |
| Packet item | 4,194,304 bytes | Per evidence item, including workspace-delta envelope |
| Candidate diff observation | 2,097,152 bytes | Full-task diff capacity |
| Frozen evaluation packet | 8,388,608 bytes | Per candidate packet |

The 120-hour planning allowance follows the current sequential critical path:
at most 60 hours for the concurrent four-arm E2 trial, 16 hours for four
sequential 4-hour hidden evaluations, 16 hours for two initial reviews plus one
possible adjudicator plus one integrated review, 4 hours for bounded
persistence/finalization overhead, and 24 hours of operational margin. It
excludes prelaunch reference construction, package review, owner adoption, and
the separately authorized apparatus smoke. It is capacity planning only and
does not add an outer supervisor, termination path, provider-call slot, or
timeout to the preserved Task-5 apparatus.

The resource plan is not an entitlement to extend a running attempt. A settled
arm or visible/hidden check timeout is a treatment outcome. A settled initial,
adjudicator, or integrated-review timeout is an evaluation outcome and follows
the locked indeterminate/failure route; it is not charged to a treatment.
Either classification requires the real terminal usage receipt. If timeout or
termination leaves any required provider call without its real terminal
settlement or receipt, the attempt is invalid/interrupted instead, no receipt
is invented, and any allowed replacement consumes the next precommitted ID.
An interrupted attempt is never resumed.

Before freeze, `resource-plan.json` also records the observed reference patch
bytes, maximum provider-visible item bytes, maximum frozen packet bytes, the
corresponding configured limits, and the positive headroom for each. An
observed value at or above its limit blocks freeze. These measurements validate
the existing packet surfaces; they do not authorize a new transport or
truncation mechanism.

The metering plan records low-confidence capacity estimates rather than
inventing a billing claim:

| Provider role class | Estimated `CODEX_REPORTED_TOTAL_TOKENS` per call |
| --- | ---: |
| Implementation-bearing (DIRECT implementation, `I`, or `FIX`) | 500,000–2,000,000 |
| Design/revision | 200,000–800,000 |
| Design/product review | 150,000–600,000 |
| Scorer/initial/adjudicator/integrated evaluation | 150,000–750,000 |

These estimates are derived from the 5,000–10,000-line implementation target,
not from an A1 receipt: no complete A1 per-call token receipt exists. The
planning model assumes roughly 3–8 tokenizer tokens per emitted physical code
line (15,000–80,000 output tokens for the implementation surface), then a
10–20x low-confidence allowance for repository reading, intermediate edits,
tool results, tests, corrections, and context replay. Rounding that broad
150,000–1,600,000 working range upward for calls expected to complete a full
implementation and adding approximately 25 percent upper contingency yields
the 500,000–2,000,000 implementation-bearing planning envelope; the raised
lower estimate is not a minimum or validity gate. Design and review ranges are conservative
fractions with overlap for large evidence packets. These assumptions are
capacity planning only and are not substituted for receipts.

The closed resource record names this basis
`A1_667_ADDITION_TO_F1_5000_10000_TARGET`, marks every estimate
`confidence=low` and `is_runtime_cap=false`, binds
`receipt_authority=usage-receipt.v1`, and records that estimates may not enter
candidate validity, treatment settlement, stopping, or synthesis. The
5,000–10,000 reference gate is nevertheless exact and inclusive because the
owner explicitly selected it as the pre-run calibration contract.

Derived planning ranges are 1–24 million reported tokens for any valid block,
4–24 million for a completed-treatment block, 3–72 million across the three
valid-block cap, and at most 96 million across all four precommitted attempts.
The separately accounted apparatus smoke adds at most 24 million estimated
tokens, for a 120-million operational-planning ceiling across smoke plus all
four possible attempts. These are capacity estimates only. There is no token
cap, no token-based termination, no imputation, and no acceptance rule tied to
an estimate. Actual receipts remain the sole cost authority, use
`CODEX_REPORTED_TOTAL_TOKENS`, and must be complete for a valid block. Smoke
receipts are disclosed but excluded from the study cost ratio. The existing
maximum median `RICH`/`DIRECT` ratio remains `4.0`.

The completed and terminal route tables remain byte-equivalent in semantics:
7–22 calls for any valid block, 17–22 for a completed-treatment block, 21–66
across `M=3`, 51–66 across three completed-treatment blocks, and 88 absolute
study calls with one invalid-attempt allowance. The one-use smoke adds at most
22 separately accounted calls, for 110 maximum provider calls across the full
operation. Scaling time and byte envelopes must not add a call slot.

## 4. File ownership map

### Create

- `experiments/orc_effectiveness/f1_es/preregistration-lineage.schema.json`
- `experiments/orc_effectiveness/f1_es/preregistration-lineage.json`
- `experiments/orc_effectiveness/f1_es/resource-plan.schema.json`
- `experiments/orc_effectiveness/f1_es/resource-plan.json`
- `experiments/orc_effectiveness/f1_es/reference-product.schema.json`
- `experiments/orc_effectiveness/f1_es/reference-product.json`
- `experiments/orc_effectiveness/f1_es/environment-lock.json`
- `experiments/orc_effectiveness/f1_es/prompt-manifest.schema.json`
- `experiments/orc_effectiveness/f1_es/prompt-manifest.json`
- `experiments/orc_effectiveness/f1_es/randomization-manifest.json`
- `experiments/orc_effectiveness/f1_es/decision-lock.json`
- `experiments/orc_effectiveness/f1_es/controller-package.json`
- `experiments/orc_effectiveness/f1_es/prelaunch-owner-adoption.template.json`
- `experiments/orc_effectiveness/f1_es/prelaunch-owner-adoption.json` only
  after the exact prelaunch reviews
- `experiments/orc_effectiveness/f1_es/launch-manifest.json` only after owner
  adoption
- `docs/plans/evidence/es-f1-large-scope-refreeze/source-census.json`
- `docs/plans/evidence/es-f1-large-scope-refreeze/source-census.schema.json`
- `docs/plans/evidence/es-f1-large-scope-refreeze/preedit-discovery-input.json`
- `docs/plans/evidence/es-f1-large-scope-refreeze/preedit-discovery-input.schema.json`
- `docs/plans/evidence/es-f1-large-scope-refreeze/preedit-policy-manifest.json`
- `docs/plans/evidence/es-f1-large-scope-refreeze/preedit-policy-manifest.schema.json`
- `docs/plans/evidence/es-f1-large-scope-refreeze/preedit-selector-manifest.json`
- `docs/plans/evidence/es-f1-large-scope-refreeze/preedit-selector-manifest.schema.json`
- `docs/plans/evidence/es-f1-large-scope-refreeze/feasibility-capture/`,
  closed by the canonical capture manifest
- `docs/plans/evidence/es-f1-large-scope-refreeze/feasibility-capture-manifest.json`
- `docs/plans/evidence/es-f1-large-scope-refreeze/feasibility-capture-manifest.schema.json`
- `docs/plans/evidence/es-f1-large-scope-refreeze/feasibility-post-purge-tombstone.json`
- `docs/plans/evidence/es-f1-large-scope-refreeze/feasibility-post-purge-tombstone.schema.json`
- `docs/plans/evidence/es-f1-large-scope-refreeze/a1-calibration-anchor.json`
- `docs/plans/evidence/es-f1-large-scope-refreeze/a1-calibration-anchor.schema.json`
- `docs/plans/evidence/es-f1-large-scope-refreeze/task0-review-adoption.json`
- `docs/plans/evidence/es-f1-large-scope-refreeze/task0-review-adoption.schema.json`
- `scripts/experiments/es/boundary_proofs.py`
- `scripts/experiments/es/feasibility_proofs.py`
- `scripts/experiments/es/prelaunch.py`
- `scripts/experiments/es/reference_calibration.py`
- `scripts/experiments/es/source_census.py`
- `tests/experiments/test_es_boundary_proofs.py`
- `tests/experiments/test_es_feasibility_lifecycle.py`
- `tests/experiments/test_es_feasibility_proofs.py`
- `tests/experiments/test_es_prelaunch.py`
- `tests/experiments/test_es_reference_calibration.py`
- `tests/experiments/test_es_source_census.py`
- `tests/experiments/fixtures/es_f1/full_matrix_reference_adapter.py`
- `artifacts/review/es-f1-large-scope-amendment-plan-specification-review.md`
- `artifacts/review/es-f1-large-scope-amendment-plan-quality-review.md`
- `artifacts/review/es-first-effectiveness-study-prelaunch-review.md`

### Modify

- `experiments/orc_effectiveness/f1_es/task/neutral-task-brief.md`
- `experiments/orc_effectiveness/f1_es/task/visible-task-contract.json`
- `experiments/orc_effectiveness/f1_es/task/visible-task-contract.schema.json`
- `experiments/orc_effectiveness/f1_es/task/visible-check-manifest.json`
- `experiments/orc_effectiveness/f1_es/task/visible-check-manifest.schema.json`
- `experiments/orc_effectiveness/f1_es/task/candidate-extension-evidence.schema.json`
- `experiments/orc_effectiveness/f1_es/task/lifecycle-probe-request.schema.json`
- `experiments/orc_effectiveness/f1_es/task/lifecycle-probe-result.schema.json`
- `experiments/orc_effectiveness/f1_es/task-profile.json`
- `experiments/orc_effectiveness/f1_es/task-profile.schema.json`
- `experiments/orc_effectiveness/f1_es/task-seed-manifest.json`
- `experiments/orc_effectiveness/f1_es/task-seed-manifest.schema.json`
- `experiments/orc_effectiveness/f1_es/evaluator/fixture-manifest.json`
- `experiments/orc_effectiveness/f1_es/evaluator/hard-finding.schema.json`
- `experiments/orc_effectiveness/f1_es/decision-lock.schema.json`
- `experiments/orc_effectiveness/f1_es/randomization-manifest.schema.json`
- `experiments/orc_effectiveness/f1_es/attempt-record.schema.json`
- `experiments/orc_effectiveness/f1_es/report.schema.json`
- `tests/experiments/fixtures/es_f1/calibration-cases.json`
- `scripts/experiments/es/task_package.py`
- `scripts/experiments/es/f1_evaluator.py`
- `scripts/experiments/es/hard_contract.py`
- `scripts/experiments/es/decision_lock.py`
- `scripts/experiments/es/attempts.py`
- `scripts/experiments/es/blinding.py`
- `scripts/experiments/es/controller.py`
- `scripts/experiments/es/controller_artifacts.py`
- `scripts/experiments/es/synthesis.py`
- `scripts/experiments/es/cli.py`
- `tests/experiments/test_es_f1_task_package.py`
- `tests/experiments/test_es_f1_evaluator.py`
- `tests/experiments/test_es_hard_contract.py`
- `tests/experiments/test_es_decision_lock.py`
- `tests/experiments/test_es_attempts.py`
- `tests/experiments/test_es_blinding.py`
- `tests/experiments/test_es_controller.py`
- `tests/experiments/test_es_controller_artifacts.py`
- `tests/experiments/test_es_reviews.py`
- `tests/experiments/test_es_synthesis.py`
- `tests/experiments/test_es_cli.py`
- `tests/experiments/test_es_controller_e2_integration.py`
- `workflows/experiments/qa_placement_effectiveness/qa_placement_trial.orc`
- `tests/experiments/test_es_qa_placement_contract.py`
- `tests/experiments/test_es_qa_placement_workflows.py`
- `docs/plans/2026-08-02-workflow-lisp-es-first-effectiveness-study-component-plan.md`
- `docs/plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md`
- `docs/index.md`
- `tests/test_workflow_lisp_drain_roadmap_routing.py`

### Preserve byte-for-byte unless a test proves an amendment-owned binding gap

- `experiments/orc_effectiveness/f1_es/projection-manifest.json`
- `experiments/orc_effectiveness/f1_es/projection-verification.json`
- `scripts/experiments/es/projection.py`
- `scripts/experiments/es/metering.py`
- `experiments/orc_effectiveness/f1_es/usage-receipt.schema.json`
- `scripts/experiments/es/provider_boundary.py`
- `orchestrator/workflow/trial/sdk.py`
- `orchestrator/workflow/trial/adjudication.py`
- `orchestrator/workflow/executor.py`
- `workflows/experiments/qa_placement_effectiveness/qa_placement_arms.orc`
- `workflows/experiments/qa_placement_effectiveness/providers.json`
- `workflows/experiments/qa_placement_effectiveness/prompts.json`
- `workflows/experiments/qa_placement_effectiveness/prompts/trial_rubric.md`
- all target-2.25 E2 compiler, state, and packet-artifact code, plus every
  runtime/SDK behavior. The amendment may rebind already-existing Task-5
  controller/package inputs and existing resource fields; it may not add a new
  runtime mechanism.

## 5. Execution sequence

### Task 0: Accept this pre-run amendment plan

**Files:** this plan; create the non-authoritative discovery input, final
policy, census, selector-manifest, A1, and Task-0 review-adoption schemas and
records; create `source_census.py`, `boundary_proofs.py`, and the shared
`reference_calibration.py` delta/A1 implementation with their three test
modules; create `feasibility_proofs.py` with
`test_es_feasibility_proofs.py` and `test_es_feasibility_lifecycle.py`; retain
the canonical feasibility capture
evidence and its post-purge tombstone; retain the two immutable amendment
review Markdown views at
`artifacts/review/es-f1-large-scope-amendment-plan-specification-review.md` and
`artifacts/review/es-f1-large-scope-amendment-plan-quality-review.md` only as
human views; modify the ES component plan, authoritative E roadmap,
`docs/index.md`, and the owning routing assertions. Only disposable spike
implementation/test/object bytes and non-authoritative diagnostics remain
under `.tmp/` and uncommitted. Do not touch the task package or launch surface
during this task.

- [ ] **Step 1: RED discovery, authority, metric, proof, and review contracts**

Create every Task-0 closed schema and all five test modules before producing
a canonical authority record. Require the exact bare-repository locator,
projection commit `8f191031f233d50a4d020d8a988036e99487f570`, tree
`e64f3c05f5a0894f41c047d128a9040a2cda6764`, retained inventory digest
`sha256:6fc936c54977d9adc7bdbae02bfa69592c55722e5cf5eddbd1b958ee1bc71404`,
and 1,948 path-ordered leaf rows. Cover both directions for AST and lexical
detectors, aliases, direct boundary imports and calls,
`TorchRunnerConfig`/`run_grid_lines_torch`, checkpoint, bundle,
reconstruction, reload, inference, and runtime-application consumers.

Discovery tests require a closed input with no proposal fields, two
byte-identical `discover` outputs, and explicit
`NON_AUTHORITATIVE_DISCOVERY`; they reject downstream validation that attempts
to consume discovery bytes. Build tests require an independently recomputed
candidate set exactly equal to the policy-bound discovery digest and reject a
missing, extra, or revised policy consumer.

Tamper tests reject a missing, extra, duplicated, or reordered leaf; blob,
mode, byte, text/line-count, detector-version, producer-digest,
commit/tree/inventory, subtotal, or canonical-digest drift; a matched leaf
without match IDs; a nonmatch leaf with a consumer; a match ID with zero or two
consumer rows; a consumer with no proposed disposition or required proof; and
an attempt to use the live checkout or a mutable worktree. Cover the exact
`record_sha256` projection in Section 3: body tamper with stale digest,
digest-only tamper, an extra digest-looking field, and hashing the complete
self-bearing record all reject. Require strict-UTF-8 `splitlines()` physical
line counting, including a nonempty unterminated final line; raw LF-octet
counts remain non-authoritative diagnostics.

Selector/proof tests require nineteen ordered modules rendered into one
aggregate pytest argv, exact collected node IDs, and mechanically observed
`pytest_runtime`, `static_ast`, or `runtime_probe` witnesses. Reject an unknown
node, echoed rather than observed consumer/event, witness/selector backpointer
mismatch, unused witness, mixed row shape, cross-lane identity duplicate, wrong
proof kind, a missing required provider/class representative, a witness on an
`inherited`/`open` consumer, covered nonmatch, desired-state result presented as
a baseline fact, or controller-only selector identity rendered into
provider-visible bytes. Positive cases retain nonsampled observable consumers
as `inherited`, unresolved/unobserved consumers as `open`, zero-or-one
controller backpointers, and private controller argv reuse of provider module
paths. The baseline may record an expected pre-edit bypass or present removal
target without claiming conformance.

Feasibility-proof tests require exact base/overlay, post-overlay, test-only,
and remove-one tree algebra; the closed collection, failing-baseline,
green-twice, remove-one, and adjacent phase ledgers with exact Git, Python, and
project origins; and every cross-cluster edge through AST coordinates plus a
same-green-node callsite/callee trace. They require byte-identical independent
derivations, truthful pre-purge retention/pending-review state, and post-purge
`lstat` absence; missing evidence, retained-root presence, or manifest,
ledger, origin, edge, derivation, absence, or tombstone tamper rejects.

Metric tests define `implementation_delta_physical_lines.v1` now rather than
in Task 3A. Cover additions, replacements, deletions, exact renames/copies,
blank/comment lines, classifications, and per-path totals; reject binary,
non-UTF-8, symlink, generated, unclassified, or tool-drift inputs. Re-render
the retained A1 inputs and require exactly 667 additions, 2 deletions, and 690
postimage physical lines.

Review-adoption tests require one closed JSON record with distinct ordered
specification/quality rows and the same five authority digests. Proposed mode
remains non-authoritative; adopted mode rejects missing, stale, reordered,
duplicate-reviewer, non-approved, differently bound, or Markdown-only review
state, plus a missing, stale, or misbound top-level post-purge tombstone.
Policy tests also reject an implicit/default detector, proposal,
selector, Git input, A1 input, no-consumption root, policy-digest drift, extra
authority path, and every contrary finite-scope fact.

Run:

```bash
pytest --collect-only -q \
  tests/experiments/test_es_source_census.py \
  tests/experiments/test_es_boundary_proofs.py \
  tests/experiments/test_es_feasibility_lifecycle.py \
  tests/experiments/test_es_feasibility_proofs.py \
  tests/experiments/test_es_reference_calibration.py
pytest -q \
  tests/experiments/test_es_source_census.py \
  tests/experiments/test_es_boundary_proofs.py \
  tests/experiments/test_es_feasibility_lifecycle.py \
  tests/experiments/test_es_feasibility_proofs.py \
  tests/experiments/test_es_reference_calibration.py
```

Expected: collection succeeds and production/validation tests fail before the
scripts, schemas, and canonical outputs exist.

- [ ] **Step 2: Implement the shared delta metric and A1 calibration**

Create `scripts/experiments/es/reference_calibration.py` in Task 0 with the
shared Git metric, canonical per-path classifications, and `validate-a1`
loader. Task 3A later adds reference-product construction and measurement; it
must reuse this exact implementation rather than fork or replace it. Pin the
Git executable and controls from Section 3, validate all thirteen retained A1
member bytes and internal selection/review bindings, and prove the fresh
667/2/690 result. Keep test/documentation totals separate and never expose the
F1 band as a candidate predicate.

- [ ] **Step 3: Discover consumers before authoring the final policy**

Implement `source_census discover` and publish the closed non-authoritative
discovery input. Run this exact shape twice from clean processes, using literal
digests and separate disposable outputs:

```bash
python -m scripts.experiments.es.source_census discover \
  --discovery-input docs/plans/evidence/es-f1-large-scope-refreeze/preedit-discovery-input.json \
  --discovery-input-schema docs/plans/evidence/es-f1-large-scope-refreeze/preedit-discovery-input.schema.json \
  --expected-discovery-input-sha256 <DISCOVERY_INPUT_RAW_SHA256> \
  --projection-repository /home/ollie/.local/state/orchestrator/es-source-projections/git-sha1/8f191031f233d50a4d020d8a988036e99487f570 \
  --projection-commit 8f191031f233d50a4d020d8a988036e99487f570 \
  --expected-tree e64f3c05f5a0894f41c047d128a9040a2cda6764 \
  --expected-inventory-sha256 sha256:6fc936c54977d9adc7bdbae02bfa69592c55722e5cf5eddbd1b958ee1bc71404 \
  --expected-leaf-count 1948 \
  --output .tmp/es-f1-source-census-discovery-1.json
```

Repeat with output suffix `-2` and require byte equality. The command parses
blobs in memory through pinned Git object plumbing and never materializes or
consults an ambient checkout. It emits no disposition, proof assignment,
review state, or canonical authority digest.

Author the final policy only from the complete discovered rows. Give every
consumer one neutral proposed disposition, required proof kind, exact
selector/kind assignment, explicit `required | inherited | open` status, and a
zero-or-one witness backpointer under the literal sampling rule; bind both
discovery raw digests and the finite authority scope. `source_census
build-census` must independently rescan the
projection and reject any difference before producing the canonical census.
No placeholder or environment/default value is executable authority.

The fresh discovery exposed a blocking witness-observability gap in the
pre-acceptance Task-0 machinery: line-only call-phase tracing cannot distinguish
all occurrence-level consumers, and the proposed isolated probes have no
executable payloads. The
[ES F1 witness observability correction plan](2026-08-04-es-f1-witness-observability-correction-plan.md)
already obtained ordered specification then quality plan approval. Execute it
before publishing the canonical policy or census. That prerequisite preserves
the exact nineteen-module provider-visible lane, adds only controller-owned
evidence, and applies the literal sampling rule: the required set is the first
observable consumer for every provider selector unioned and deduplicated with
the first observable consumer of every
(`proposed_disposition`, `witness_kind`) class. Remaining observable consumers
are `inherited`; unresolved or unobserved consumers are `open`; both remain
nonblocking, source-identity-bound census rows without witnesses. The later
candidate-declared architecture witness is a separate evaluator lifecycle and
does not enter this Task-0 set.
Canonical policy, census, baseline, selector, A1, and feasibility evidence
generation remains blocked until that prerequisite closes.

The existing ordered plan approvals remain standing for their reviewed
sections/files; this owner-directed coherence correction does not request or
restart either plan review. Their records continue to bind the exact bytes
actually reviewed and are not rewritten to imply review of corrected lines;
the owner-directed correction governs those lines. Close the nested correction
with at most the one proportionate implementation-review pass defined by its
plan, then return directly to Task 0 evidence.

- [ ] **Step 4: Build the census and capture the exact nineteen-selector baseline**

Implement `scripts/experiments/es/boundary_proofs.py` as the sole runner for
baseline characterization and later desired-state proof replay. Its tests own
node collection, project-origin isolation, static/runtime witness observation,
pre/post tree identity, and proof-result validation. Task 0 implements both
data-driven modes completely: baseline characterization against the frozen
pre-edit projection and desired-state execution/result validation against an
explicit later tree binding. The latter accepts proof specs, an exact target
tree, and result rows as data; it does not require reference-product bytes or
claims to exist in Task 0. The selector manifest pins this completed runner's
raw SHA-256. No later task may modify, regenerate, or substitute the runner;
every invocation verifies the pinned digest before execution.

Run `source_census build-census` with literal
policy/discovery/projection digests. Because the final selector manifest
requires the resulting baseline, capture that baseline through the runner's
baseline-only bootstrap mode before `source_census build-selector`:

```bash
/home/ollie/miniconda3/envs/ptycho311/bin/python \
  -m scripts.experiments.es.boundary_proofs bootstrap-baseline \
  --preedit-policy <REPO_ROOT>/docs/plans/evidence/es-f1-large-scope-refreeze/preedit-policy-manifest.json \
  --preedit-policy-schema <REPO_ROOT>/docs/plans/evidence/es-f1-large-scope-refreeze/preedit-policy-manifest.schema.json \
  --expected-preedit-policy-sha256 <PREEDIT_POLICY_RAW_SHA256> \
  --source-census <REPO_ROOT>/docs/plans/evidence/es-f1-large-scope-refreeze/source-census.json \
  --source-census-schema <REPO_ROOT>/docs/plans/evidence/es-f1-large-scope-refreeze/source-census.schema.json \
  --expected-source-census-sha256 <SOURCE_CENSUS_RAW_SHA256> \
  --python /home/ollie/miniconda3/envs/ptycho311/bin/python \
  --pytest-carrier /usr/bin/bwrap \
  --expected-pytest-carrier-sha256 sha256:52231e1caf55bcbc667b269f49c63599a6f7db4767ae6a039580d0ff853db712 \
  --workspace <ABSOLUTE_FROZEN_PREEDIT_EXTRACT> \
  --expected-tree e64f3c05f5a0894f41c047d128a9040a2cda6764 \
  --expected-runner-sha256 <BOUNDARY_PROOFS_RAW_SHA256> \
  --report-path <REPO_ROOT>/.tmp/es-f1-boundary-bootstrap-origin.json \
  --output <REPO_ROOT>/.tmp/es-f1-boundary-baseline.json
```

Repeat `--forbidden-root <ABSOLUTE_ROOT>` for every bound ambient root. The
bootstrap accepts only the closed policy and census authorities, hard-checks
the ordered mandatory nineteen-module lane, performs one aggregate collect-only
discovery pass,
requires every policy pytest node pattern to full-match exactly one collected
node, constructs the ordinary `ProofContract` in memory, and enters the same
baseline capture path used by the final selector. It emits only
`es_f1_boundary_baseline.v1`; it creates no provisional selector record or
schema. `desired-state` continues to require the final selector manifest.

The bootstrap's final capture, under `ptycho311` in tmux, must run exactly:

```bash
/home/ollie/miniconda3/envs/ptycho311/bin/python -m pytest \
  -q -p no:cacheprovider \
  tests/torch/test_generator_registry.py \
  tests/torch/test_construction_consolidation.py \
  tests/torch/test_generator_adapter.py \
  tests/torch/test_config_bridge.py \
  tests/torch/test_model_spec.py \
  tests/torch/test_model_spec_v2.py \
  tests/torch/test_lightning_checkpoint.py \
  tests/torch/test_artifact_schema.py \
  tests/torch/test_artifact_schema_v2.py \
  tests/torch/test_workflows_components.py \
  tests/torch/test_fno_generators.py \
  tests/torch/test_fno_lightning_integration.py \
  tests/torch/test_neuralop_uno_generator.py \
  tests/torch/test_model_output_modes.py \
  tests/torch/test_model_manager.py \
  tests/torch/test_model_training.py \
  tests/torch/test_train_lightning_execution_contract.py \
  tests/torch/test_object_big_generator_contract.py \
  tests/torch/test_structural_config_ownership.py
```

The runner invokes that one aggregate command, not nineteen independent
commands. Require zero failures/errors, exact collected-node and
outcome totals, no forbidden import origin, and byte-identical projection trees
before and after. Existing 205/205 evidence for the first ten modules is
historical input only; it cannot substitute for this fresh nineteen-module
capture. Record every observed baseline witness truthfully, including expected
desired-state failures. Feed the canonical bootstrap output directly to
`source_census build-selector --baseline-characterization`; only that final
builder emits `es_f1_preedit_selector_manifest.v1`.

- [ ] **Step 5: Run the early feasibility spike and finalize Task-0 records**

Use `feasibility_proofs.py` to perform one authenticated Section-3 capture from
a disposable exact extract. Bind the frozen base and the exact closed overlay
path/mode/blob set, then derive the post-overlay, test-only, and each
remove-one-cluster tree through exact tree algebra. The runner-owned capture
must retain a collection ledger, the per-cluster failing baseline ledger, two
green ledgers, one remove-one ledger for each implemented cluster, and the
adjacent-selector ledger. Every ledger binds the pinned origin-isolated Git
and Python executables, the pinned Bubblewrap execution envelope where a
declared external writable mount is required, exact target and wrapper argv,
node IDs, project origins, external artifact writes, and pre/post source trees.
Retain both measured green elapsed times as observations; they are not budgets
or acceptance thresholds.

Prove at least three directed cross-cluster edges through producer-definition
and consumer-callsite AST coordinates plus a same-green-node trace that crosses
the distinct cluster blobs. Publish one closed capture manifest whose evidence
bindings cover every retained ledger and structural proof input. Derive the
four independently unmet clusters, changed production paths, cluster
assignments, physical delta, and pre/post tree facts from those authenticated
bytes. A capture that lacks the baseline failures, either green execution, any
remove-one failure, the adjacent pass, or any AST-plus-trace edge stops before
Task 1. Self-attested `status`, `observed`, `removal`, or `good_faith` booleans
are not evidence and must not appear as claim authority.

Keep the disposable implementation, test, and object bytes present through the
ordered Task-0 reviews. In Step 5 the selector's `feasibility_spike` facts must
truthfully record that the authenticated capture is retained and pending
review; they must not claim purge, deletion, review adoption, or final
operational-criterion acceptance. Do not purge any captured byte in this step.

Publish canonical `source-census.json` with the exact source/projection and
Task-2/3/4 closure identities, current task-profile/task-seed digests, finite
no-consumption observations, all 1,948 leaf rows, joined consumer rows,
responsibility assignments, bypass inventory, and recomputed totals. It must
reproduce 6,776, 6,833, 11,800, 16,052, 5,645, 21,697, 29,886, 47,515, and
50,318 where specified and publish the distinct projection-wide total.

Publish `preedit-selector-manifest.json` with the nineteen module/node rows,
controller-only proof rows, observed coverage witnesses, complete baseline
characterization, desired-state proof specs, and feasibility-spike facts. An
unmapped consumer, missing required provider/class representative, witness on
an `inherited`/`open` consumer, unobserved required witness, unsatisfied
required proof kind, or failed structural proxy blocks review. A disclosed
individual open row does not. Publish the A1 anchor through the
already-implemented shared metric. Do not derive the 5,000–10,000 gate by
summing estimates; Task 3A alone supplies the measured complete reference
value. Treat any contrary consumption fact or census mismatch as a stop.

- [ ] **Step 6: Prove deterministic completeness and rerun GREEN**

Reload the discovery input and all four authority records through their closed
schemas from a clean process. Require every Git leaf to have exactly one
leaf-layer outcome, every match exactly one consumer, every consumer one
proposal plus selector/kind/status assignment, and only required consumers to
have mechanically observed witness coverage. Require the required domain to
equal the witness/spec/proof/result domain, every group and projection-wide
total to recompute, and all nineteen selectors/nodes to retain their prescribed
order. Require provider/controller selector identities,
witness assignments, processes, reports, and result tables to be complete and
disjoint; the private controller aggregate may reuse the nineteen provider
module paths without merging the lanes. Require the controller-only lane to be
absent from provider-visible bytes. Two independent
census, baseline-characterization, selector, and A1 builds must be
byte-identical. Two independent feasibility-fact derivations from the same
authenticated capture must likewise be byte-identical after excluding only
the declared volatile fields. Revalidate the 667/2/690 result and finite
no-consumption observations.

Run all five Task-0 test modules again. Then run `source_census validate` with
`--proposal-state proposed` and literal expected policy/census/selector/A1
digests. Proposed mode validates structure, the capture manifest, its evidence
bindings, tree algebra, ledgers, and AST-plus-trace facts, but it cannot claim
ordered-review adoption, captured-byte deletion, or post-purge tombstone
completion and grants no downstream disposition authority.

- [ ] **Step 7: Run the plan's focused consistency sweep**

Run:

```bash
rg -n "one migrated representative|one small witness|both nominated|representative_architecture|witness_architecture|nominated_architectures|F1-H05-NOMINATED-LIFECYCLE|F1-H06-WITNESS-STRUCTURAL-ROUNDTRIP|es_f1_witness.*FfnoGenerator|1200000|43200000|F1-ES|ES-ATTEMPT" \
  docs/plans/2026-08-02-workflow-lisp-es-first-effectiveness-study-component-plan.md \
  experiments/orc_effectiveness/f1_es \
  scripts/experiments/es \
  tests/experiments \
  tests/experiments/test_es_reviews.py \
  workflows/experiments/qa_placement_effectiveness
```

Expected: every old two-row, witness-alias, predecessor-ID, or 12-hour
assumption is accounted for by an explicit Task 1–6 edit below. Before the v3
lock freezes, no live prospective consumer may retain a predecessor study or
attempt identifier; explicitly labeled historical records and generic
transport fixtures may retain neutral provenance bytes. No hidden authority
surface is silently omitted.

- [ ] **Step 8: Draft the immediate normative reconciliation**

Amend
`docs/plans/2026-08-02-workflow-lisp-es-first-effectiveness-study-component-plan.md`
before any package implementation. Replace its live prospective scope of one
representative plus one witness with the exact 14-plus-one matrix in this
plan, retain Tasks 0–4 as historical-complete provenance for the superseded
prelaunch bytes together with completed provider-free Task 5, and record that
refreeze Tasks 1–4 own and subsume the component plan's old Task 6 work. After
Task 4, existing ES Task 7 follows directly. Its status must continue to say no
live allocation is authorized. Update the E roadmap/index pointer and routing
test only enough to make that ownership and gate discoverable; do not mark the
refreeze implemented, adopted, or live-eligible.

- [ ] **Step 9: Obtain ordered plan reviews and publish machine adoption**

While every closed, enumerated disposable source, test, and object root remains
present, one independent specification reviewer must inspect those exact
disposable source, test, and object bytes plus the canonical capture before
returning `ES_F1_SCOPE_AMENDMENT_PLAN_SPEC_APPROVED`. Only then, with the same
disposable bytes still present, may a distinct quality reviewer independently
inspect those bytes plus the canonical capture and return
`ES_F1_SCOPE_AMENDMENT_PLAN_QUALITY_APPROVED` against the same complete Task-0
authority set: plan; discovery input; policy, census, selector-manifest, A1,
and review-adoption schemas; the four canonical authority records;
census/metric/proof producers and tests; fresh nineteen-selector baseline;
feasibility-spike facts and canonical capture; component-plan amendment;
roadmap/index routing transition; and routing-test bytes. Each human review
view is retained immutably at its exact ordered path: the specification view at
`artifacts/review/es-f1-large-scope-amendment-plan-specification-review.md` and
the quality view at
`artifacts/review/es-f1-large-scope-amendment-plan-quality-review.md`. Each
view contains exact `verdict:`, `reviewer:`, `reviewed_at:`, five authority-
binding, and seven finding lines. The purge gate requires those lines to name
the same five exact authority digests, requires distinct reviewer identities,
requires the quality timestamp not to predate specification, and requires the
view to explicitly adopt the
anti-padding finding, the non-synthetic baseline and remove-one failures, all
three authenticated AST-plus-trace cross-blob edges, the four independently
unmet clusters, and the non-collapse requirement. Each view also adopts the
owner-selected operational criterion and its boundary: only a later complete
reference measuring 5,000–10,000 implementation-delta physical lines can close
the strict size part, and the criterion is not a universal mathematical
impossibility theorem about provider contexts.

After both approved pre-purge views exist, use the authenticated runner to
purge exactly the closed, enumerated disposable roots and no other path. Then
generate and validate
`docs/plans/evidence/es-f1-large-scope-refreeze/feasibility-post-purge-tombstone.json`
through
`docs/plans/evidence/es-f1-large-scope-refreeze/feasibility-post-purge-tombstone.schema.json`.
The post-purge tombstone binds the canonical capture plus the separate exact
digests of
`artifacts/review/es-f1-large-scope-amendment-plan-specification-review.md` and
`artifacts/review/es-f1-large-scope-amendment-plan-quality-review.md`, and
records `lstat` absence for every enumerated disposable root; a fresh exact
absence recheck is part of validation. Only after that validation may the
producer mechanically publish `task0-review-adoption.json`. Its first and
second rows bind the specification and quality view digests respectively,
distinct reviewer identities, exact verdicts, and the same common
plan/policy/census/selector/A1 digest tuple; those five row bindings remain
unchanged because the selector already binds the capture. The adoption
record's top-level bindings additionally bind the exact post-purge tombstone
digest. This one-way capture → review views → tombstone → adoption chain
must not introduce a digest cycle. The JSON record—not either Markdown
view—adopts the neutral disposition set. Validate the record through its closed
schema and canonical digest. No pre-review field may claim adoption, and a
material edit restarts the applicable ordered pair.

- [ ] **Step 10: Run routing controls and commit the accepted authority set**

Run:

```bash
pytest -q tests/test_workflow_lisp_drain_roadmap_routing.py
```

Then rerun the same exact `source_census validate` command with
`--proposal-state adopted`,
`--review-adoption docs/plans/evidence/es-f1-large-scope-refreeze/task0-review-adoption.json`,
`--review-adoption-schema docs/plans/evidence/es-f1-large-scope-refreeze/task0-review-adoption.schema.json`,
`--expected-review-adoption-sha256 <TASK0_REVIEW_ADOPTION_RECORD_SHA256>`,
`--post-purge-tombstone docs/plans/evidence/es-f1-large-scope-refreeze/feasibility-post-purge-tombstone.json`,
`--post-purge-tombstone-schema docs/plans/evidence/es-f1-large-scope-refreeze/feasibility-post-purge-tombstone.schema.json`,
and `--expected-post-purge-tombstone-sha256 <FEASIBILITY_POST_PURGE_TOMBSTONE_SHA256>`.
Adopted mode requires the literal tombstone path/schema and expected digest,
the closed ordered JSON verdict rows and their five exact common bindings, the
adoption record's top-level tombstone binding, and a fresh exact `lstat`
absence recheck for every enumerated disposable root. Proposed mode, a missing
JSON adoption or tombstone, a Markdown path, a stale digest, or any present
disposable root cannot satisfy any Task 1+ validator.

Commit this plan, discovery input/schema, all four authority schemas and
canonical records, review-adoption schema/record, census/metric/proof
producers/tests, both immutable human review views at
`artifacts/review/es-f1-large-scope-amendment-plan-specification-review.md` and
`artifacts/review/es-f1-large-scope-amendment-plan-quality-review.md`, fresh
baseline, canonical feasibility
capture ledgers/manifest, feasibility facts, and the post-purge tombstone,
component-plan/roadmap/index reconciliation, and routing assertion together.
Never commit the disposable feasibility implementation, test, or object bytes.
This commit authorizes
provider-free implementation and makes the full matrix the sole prospective
F1 scope; it preserves the existing live-allocation prohibition and does not
authorize an arm.

### Task 1: Version the visible task and candidate contracts

**Files:** all files under `experiments/orc_effectiveness/f1_es/task/`, the
task profile and schemas, `scripts/experiments/es/task_package.py`, and
`tests/experiments/test_es_f1_task_package.py`.

- [ ] **Step 1: Write failing schema and loader tests**

Require:

- exact built-in order and exact 14-row coverage;
- exactly one candidate-declared non-built-in witness;
- 15 unique architecture cases and 15 result rows;
- 30 unique safe artifact paths, one checkpoint and one bundle per row;
- per-case `N`, config/input bindings, construction/rebuild routes, and
  structural-field declarations;
- `N=128` only for `neuralop_uno` and `N=64` for the other built-ins;
- rejection of missing, extra, duplicate, reordered, aliased, or unknown rows;
- rejection of a witness public ID that collides with any frozen public or
  legacy alias;
- evaluator-owned proof that the witness registry constructor and all four
  construction/reload implementation identities are equal to each other and
  distinct from all fourteen built-in identities;
- the exact nineteen-row `provider_visible_pytest_selectors` order plus the
  separate candidate selector, with no `controller_only_proof_selectors` row
  in either provider-visible invocation;
- one boundary-owned lifecycle spanning configuration, construction,
  training/optimizer use, checkpoint and bundle persistence, fresh reload,
  inference, structural identity, and round-trip reconstruction for every
  architecture, with no surviving direct legacy bypass;
- visible timeout `7200`; and
- absence of LOC/file-count/churn acceptance fields.

- [ ] **Step 2: Run RED and collection**

Run:

```bash
pytest --collect-only -q tests/experiments/test_es_f1_task_package.py
pytest -q tests/experiments/test_es_f1_task_package.py
```

Expected: collection succeeds; new matrix assertions fail against v1's
representative/witness pair and ten-selector contract.

- [ ] **Step 3: Implement the closed versioned shapes**

Use arrays rather than architecture-ID object keys so order, uniqueness, and
coverage are explicit. Rename the semantically stale hard-clause IDs to:

- `F1-H05-FULL-ARCHITECTURE-LIFECYCLE`; and
- `F1-H06-STRUCTURAL-ROUNDTRIP`.

Keep H01–H04 and H07–H10. Update every enum and exact clause list together.
The neutral brief names the behavioral matrix but does not disclose the LOC
range or instruct candidates to maximize code.

Make the predecessor-to-successor transformation structural rather than
prose-only: replace `representative_architecture` / `witness_architecture` and
role-keyed lifecycle records with an exact ordered `builtin_architectures`
array containing the fourteen Section-2 IDs, one separate
`candidate_witness`, and exactly fifteen ordered lifecycle-result rows. Replace
the four representative/witness artifact paths with exactly thirty unique safe
paths, one checkpoint and one bundle for each row. The visible contract's
`PROJECTED_FOCUSED_CLOSURE_ONLY` claim must name the complete frozen projected
F1 closure. Narrow `NO_F2_CONSUMER_CLAIM` to say only that this study makes no
quantitative downstream edit-locality, schema-evolution, or cross-task
generalization claim; it must not deny the projection-wide consumers governed
by the adopted proposal rows.

Use this exact successor-version table; no loader may silently reinterpret a
predecessor version:

| Closed record | Predecessor | Successor |
| --- | --- | --- |
| task profile | `es_f1_task_profile.v1` | `es_f1_task_profile.v2` |
| visible task contract | `es_f1_visible_task_contract.v1` | `es_f1_visible_task_contract.v2` |
| visible-check manifest | `es_f1_visible_checks.v1` | `es_f1_visible_checks.v2` |
| candidate extension evidence | `candidate_extension_evidence.v1` | `candidate_extension_evidence.v2` |
| lifecycle probe request/result | `lifecycle_probe_request.v2` / `lifecycle_probe_result.v2` | `lifecycle_probe_request.v3` / `lifecycle_probe_result.v3` |
| public lifecycle operation | `ptychopinn_public_lifecycle.v1` | `ptychopinn_public_lifecycle.v2` |
| task-seed manifest | `es_f1_task_seed.v1` | `es_f1_task_seed.v2` |

The Task-1 tests must reject every predecessor, unknown successor, and mixed
old/new task package before executing a visible check. The task-seed successor
is emitted in Task 3, after the Task-1 assets it binds are final.

- [ ] **Step 4: Run GREEN and tamper cases**

Run the Task-1 module again and verify each one-field and one-row tamper fails
with a stable structural diagnostic rather than a downstream evaluator error.

- [ ] **Step 5: Commit the task-contract tranche**

Commit only the task assets, task profile/loader, and their tests. Do not
generate the successor seed yet.

### Task 2: Expand the hidden evaluator to the full matrix

**Files:** `scripts/experiments/es/f1_evaluator.py`,
`scripts/experiments/es/hard_contract.py`, evaluator assets, calibration
fixtures, hard-finding schema, and their tests.

- [ ] **Step 1: Write failing full-matrix lifecycle tests**

Assert that the evaluator, not the adapter, derives every stage for all
fifteen rows; reloads checkpoint and bundle in fresh child processes; checks
pre/post implementation identity and inference; proves one optimizer state
transition; executes the complete Section-2 architecture/lifecycle/artifact
applicability matrix; and returns ten complete hard-clause observations in
exact order. Newly emitted current checkpoint and bundle routes are positive
for all fifteen rows. Every historical fixture carries the exact complete
positive/rejection partition, with metadata-free `legacy_v1` positive only for
`cnn`.

- [ ] **Step 2: Add both-direction failure coverage**

At minimum cover one missing built-in, one duplicate, the wrong
`neuralop_uno` size, one non-neuralop row at 128, one missing artifact, one
same-process reload, one construction/rebuild disagreement, one structural
round-trip loss, one identity-insensitive field, one forbidden ownership
crossing, one witness ID mapped directly to `FfnoGenerator`, one reintroduced
frozen bypass, one novel direct bypass, one `legacy_v1` non-`cnn` false
positive, one missing historical-artifact rejection, one incomplete or
overlapping applicability partition, and one candidate-authored
observation/authority field. The witness alias must fail H09; every other case
must fail the exact owning clause or fail schema validation before evaluation.

- [ ] **Step 3: Run RED**

Run:

```bash
pytest --collect-only -q \
  tests/experiments/test_es_f1_evaluator.py \
  tests/experiments/test_es_hard_contract.py
pytest -q \
  tests/experiments/test_es_f1_evaluator.py \
  tests/experiments/test_es_hard_contract.py
```

Expected: new matrix cases fail because the evaluator still iterates only
`representative` and `witness`.

- [ ] **Step 4: Implement one generic per-architecture loop**

Replace role-specific branches with one exact architecture-case loop. Retain
the existing audited subprocess, protected-root, forbidden-import, and
fresh-process mechanisms. Do not add fourteen copied special cases; the sole
size exception is the evaluator-owned table entry for `neuralop_uno`.

Apply the exact evaluator successor versions below and reject predecessor,
unknown, and mixed-version evaluator packages before running candidate code:

| Closed record | Predecessor | Successor |
| --- | --- | --- |
| fixture manifest | `es-f1-fixture-manifest.v1` | `es-f1-fixture-manifest.v2` |
| calibration cases | `es-f1-calibration-cases.v2` | `es-f1-calibration-cases.v3` |
| hard finding/evaluation | `es-f1-hard-finding.v1` / `es-f1-hard-evaluation.v1` | `es-f1-hard-finding.v2` / `es-f1-hard-evaluation.v2` |
| visible-check result | `es-f1-visible-check-result.v1` | `es-f1-visible-check-result.v2` |
| pre-edit lifecycle probe | `es-f1-preedit-lifecycle-probe.v1` | `es-f1-preedit-lifecycle-probe.v2` |
| semantic lifecycle/failure | `es-f1-semantic-lifecycle.v1` / `es-f1-semantic-lifecycle-failure.v1` | `es-f1-semantic-lifecycle.v2` / `es-f1-semantic-lifecycle-failure.v2` |
| artifact fixture input/build/verification | `es-f1-artifact-fixture-input.v1` / `es-f1-artifact-fixture-build.v1` / `es-f1-artifact-fixture-verification.v1` | `es-f1-artifact-fixture-input.v2` / `es-f1-artifact-fixture-build.v2` / `es-f1-artifact-fixture-verification.v2` |

Unchanged base-config, CDI-fixture, and reviewer-perspective records retain
their existing versions. Any implementation that materially changes one of
those shapes must first add it to this successor table and restart review.

- [ ] **Step 5: Rebuild the controller-only fixture manifest**

Version the fixture manifest and calibration cases. Bind the exact 14-row
registry baseline, evaluator-owned N=64/N=128 config and CDI input payloads,
artifact-era fixtures, each fixture's exact complete fifteen-ID
`applicable_architecture_ids`/`rejected_architecture_ids` partition, and the
full calibration case table. Bind metadata-free `legacy_v1` to `cnn` alone and
require the stable unsupported diagnostic for every other ID. Keep controller
fixtures out of the task seed and every candidate workspace.

- [ ] **Step 6: Run the path-adapter mechanism control**

Under `ptycho311`, use `full_matrix_reference_adapter.py` against a fresh exact
extract to prove only its path/materialization duties and all thirty artifact
paths. It is not a conforming reference product and may not supply evaluator
observations, alias `es_f1_witness` to a built-in, or satisfy the Task-3A scale
gate. The fixture is controller-only and may not be copied into a
provider-visible seed.

- [ ] **Step 7: Run GREEN and commit**

Run the two focused modules plus the existing artifact-era, registry, and
calibration selectors, then commit only evaluator assets/code/tests.

### Task 3: Materialize a fresh task-seed lineage

**Files:** task-seed manifest/schema, `scripts/experiments/es/task_package.py`,
and task-package tests.

- [ ] **Step 1: Write failing lineage tests**

Require a new deterministic child commit whose sole parent is the unchanged
history-free projection commit `8f191031...`, whose tree contains the revised
visible assets, and whose repository contains exactly the projection and new
child reachable histories. Reject a child of the old `93e0eb08...` task seed,
an old visible asset, an extra object, or an ambient live-tree read.

- [ ] **Step 2: Run RED**

Run:

```bash
pytest -q tests/experiments/test_es_f1_task_package.py -k 'seed or materializ'
```

Expected: fail because the checked-in manifest still binds the v1 seed.

- [ ] **Step 3: Generate the new seed deterministically**

Use the existing Git object-plumbing path and external content-addressed seed
store. Do not mutate or delete the predecessor seed. The new manifest binds
the exact revised visible assets and their sorted overlay destinations.

- [ ] **Step 4: Verify twice from empty destinations**

Two independent materializations must produce identical commit, tree, object
inventory, snapshot digest, and post-setup tree digest. The live PtychoPINN
checkout remains unread at execution time after the projection identity is
bound.

- [ ] **Step 5: Commit the seed tranche**

Commit the new manifest/schema/loader tests only after both materializations
pass.

### Task 3A: Build and measure the controller-only reference product

**Files:** extend the Task-0
`scripts/experiments/es/reference_calibration.py`,
`tests/experiments/test_es_reference_calibration.py`; create
`experiments/orc_effectiveness/f1_es/reference-product.schema.json` and the
canonical `reference-product.json`; create the external content-addressed
reference repository; consume the Task-2 evaluator without placing reference
bytes in the task seed. The Task-0 `boundary_proofs.py` and its tests are
immutable inputs to this task, not files owned or modified by it.

- [ ] **Step 1: RED the reference-result and desired-state proof contracts**

Keep every Task-0 metric/A1 test green. Add failing tests for the closed
reference manifest, complete per-path responsibility/cluster assignments,
exact desired-state proof-result rows joined to every Task-0 proof spec,
four-or-more changed implementation clusters and the three-or-more frozen
cross-cluster edges established by the feasibility spike, the complete
architecture/lifecycle/artifact applicability partitions, and the strict
inclusive band. Reject an unassigned production path, duplicate responsibility
or cluster assignment, padding-only change, missing/extra/duplicate proof
result, baseline result substituted for post-edit conformance, wrong reference
tree, one unsupported historical-artifact positive, an absent required
rejection, and a total outside the inclusive band. Invoke the already-complete
Task-0 runner through its data-driven desired-state interface in these tests;
changing runner bytes or accepting a digest other than the selector manifest's
pinned `runner_sha256` is itself a failure.

Run:

```bash
pytest --collect-only -q tests/experiments/test_es_reference_calibration.py
pytest -q tests/experiments/test_es_reference_calibration.py
```

Expected: collection succeeds, the existing shared metric/A1 tests remain
green, and the new reference/proof-result tests fail before the reference
manifest exists.

- [ ] **Step 2: Extend the shared loader without forking the metric**

Reuse the exact Task-0 `implementation_delta_physical_lines.v1`
implementation; a second metric implementation or changed Git contract is a
review restart. Invoke only the pinned Git executable and exact Section-3
options. Build
canonical per-path rows from explicit baseline/reference trees and the frozen
responsibility ID domain. Existing paths join to the frozen census; every new
production path must carry an explicit allowed responsibility assignment in
the reference manifest. Never scan an ambient checkout or infer a
classification from a filename after measurement. The schema must bind every
input/tool/output digest and separate production, test, documentation, and
excluded totals. One-bit field, path, blob, classification, or total drift
fails closed.

Before accepting any successor measurement, require the calibration loader to
validate the closed A1 input explicitly:

```bash
python -m scripts.experiments.es.reference_calibration validate-a1 \
  --policy docs/plans/evidence/es-f1-large-scope-refreeze/preedit-policy-manifest.json \
  --expected-policy-sha256 <POLICY_RECORD_SHA256> \
  --source-census docs/plans/evidence/es-f1-large-scope-refreeze/source-census.json \
  --expected-source-census-sha256 <SOURCE_CENSUS_RECORD_SHA256> \
  --task0-review-adoption docs/plans/evidence/es-f1-large-scope-refreeze/task0-review-adoption.json \
  --task0-review-adoption-schema docs/plans/evidence/es-f1-large-scope-refreeze/task0-review-adoption.schema.json \
  --expected-task0-review-adoption-sha256 <TASK0_REVIEW_ADOPTION_RECORD_SHA256> \
  --a1-anchor docs/plans/evidence/es-f1-large-scope-refreeze/a1-calibration-anchor.json \
  --a1-anchor-schema docs/plans/evidence/es-f1-large-scope-refreeze/a1-calibration-anchor.schema.json \
  --expected-a1-anchor-sha256 <A1_ANCHOR_RECORD_SHA256>
```

The actual Task-0 record digests replace the placeholders in the captured
command. There is no default anchor root or copied-metric fallback.

- [ ] **Step 3: Author the genuine conforming reference product**

From the exact successor task seed, create one remote-free bare repository at
the Section-3 content-addressed root. Implement all six indivisible behavioral
contract items, including one genuine witness whose registry,
construction, checkpoint, bundle, and persisted-rebuild implementation
identity is distinct from all built-ins. Do not add copied branches or churn
to reach the scale band. Keep reference source, patch, ref, and object database
outside the provider-visible seed and experiment prompts.

- [ ] **Step 4: Run the complete evaluator and bypass oracle**

Under `ptycho311`, materialize the reference tree twice from its bare
repository and run the exact nineteen provider-visible pytest selectors, the
candidate-owned selector, all ten hidden clauses over all fifteen rows, both
fresh reload routes, every positive and negative cell in the closed
artifact-era applicability matrix, and the closed AST-plus-runtime bypass
oracle. Execute every Task-0 desired-state proof spec through the same
digest-bound, byte-for-byte unchanged `boundary_proofs.py` runner and publish
one observed result row per spec; every result must bind the exact reference
tree. Verify its raw SHA-256 against each selector row before execution. Require
a distinct witness and convert the old built-in-alias shortcut into a failing
H09 negative control.

- [ ] **Step 5: Apply the strict scale decision**

Measure the conforming product only after all six required items pass.
Continue only when the canonical total is between 5,000 and 10,000 inclusive.
Require reference delta rows to demonstrate real implementation changes in at
least the four independently unmet Task-0 clusters and preserve all three
frozen cross-cluster integration edges; this is reference-only calibration,
not a candidate LOC or file-count rule.
An out-of-band complete product rejects this task shape: replace or coherently
redesign F1, repeat the full census and evaluation, and restart amendment
review before any final freeze. Never add or remove behavior merely to cross a
line threshold, and never remove a required consumer, artifact era, or bypass
proposal/proof obligation.

- [ ] **Step 6: Prove package-level non-delivery**

From empty destinations, prove the task-seed closure is still exactly the
projection plus visible child; every reference-only commit/tree/blob lookup in
the task-seed repository fails; visible task assets, prompts, provider
argv/environment, and packet templates contain no reference locator, patch,
manifest, canary, or measured count; and provider workspaces materialize only
from the task seed. Prove separately that the controller can resolve and
validate the reference repository only during provider-free calibration.

- [ ] **Step 7: Freeze and commit the reference authority**

Publish `reference-product.json` with exact source/seed/reference identities,
repository snapshot, patch, metric rows/total, cluster/edge facts, evaluator
results, desired-state proof results, complete artifact applicability results,
distinct-witness proof, bypass-oracle result, and no-delivery proof. Reload it
twice from disk, rerun the focused tests, and commit only the calibration
mechanism, schema, manifest, and tests; the external reference object database
remains content-addressed evidence rather than repository source.

### Task 4: Bind, freeze, review once, and adopt

This task replaces the original Tasks 4, 5, 6, 7, and 8 under the Section-0
owner amendment. It preserves their contract content and drops their repeated
per-task freeze/review/adoption ceremony. Section 1 bound 6 still governs: the
apparatus bytes do not change here, so this task rebinds digests over already
reviewed and closed apparatus rather than re-deriving it. Create no new
prelaunch CLI, collector, schema version, review-form template, or evidence
machinery; the existing validators are the freeze mechanism.

**Files:** `qa_placement_trial.orc` and the two QA-placement test modules; the
resource/lineage records and schemas; the decision/randomization lock records;
the controller and synthesis package-loading paths; the single prelaunch review
view; the owner adoption record; `launch-manifest.json`; and the owning ES
roadmap/status/routing surfaces.

- [ ] **Step 1: Bind the one successor seed and scale only the trial-owned envelope**

Write the failing assertions first, run them RED, then bind.

Load the Task-3 `es_f1_task_seed.v2` manifest and assert that each of the four
arm run refs resolves to its one exact successor repository locator and commit,
with no predecessor `93e0eb08...` locator/commit and no mixed seed set. Assert
exactly nineteen provider-visible pre-edit pytest selectors plus the one
candidate-owned selector; separately assert that every controller-only proof
selector remains outside the authored workflow and provider-visible manifest,
14,400,000 ms check timeout, 172,800,000 ms arm timeout, 216,000,000 ms trial
timeout, 4 MiB item cap, 2 MiB diff cap, and 8 MiB packet cap. Separately hash
`qa_placement_arms.orc`, `providers.json`, `prompts.json`, and
`trial_rubric.md` and require no amendment diff.

Add both-direction coverage: all four arms bound to the one validated successor
seed pass; any retained predecessor binding, one-arm old/new mixture, wrong
repository/commit pair, or workflow/task-profile/seed-manifest disagreement
fails before allocation.

Run:

```bash
pytest -q \
  tests/experiments/test_es_qa_placement_contract.py \
  tests/experiments/test_es_qa_placement_workflows.py
```

Expected RED: the seed assertions fail against the four predecessor run refs
and the new envelope assertions fail against the 10+1, 20-minute, 12-hour, and
256 KiB values; route/topology controls remain green.

Then consume the already-validated Task-3 manifest through the controller's
single successor-seed binding. Replace the repository locator and commit in all
four authored run refs with that exact pair; the workflow has no predecessor
fallback and may not derive four independent seed choices. Update the check
argv and constants in `qa_placement_trial.orc`. Do not add a provider step,
review, retry, correction, arm, or evaluator attempt. Rebind only fields the
existing Task-5/E2 apparatus already owns; do not add a new timeout authority,
outer supervisor, transport, or public SDK input.

Prove the unchanged call graph: compile through the public Workflow Lisp path
and require the same four arms, all four compiled run refs to bind the one
Task-3 successor seed, same complete terminal-route semantics (including the
generic distinct final-provider-call failure variants), same two evaluation
routes, same 22 receipt slots, and the same 7–22/17–22/21–66/51–66/88 call
bounds. Scaling must not add a provider call slot or remove a terminal
treatment-failure outcome.

- [ ] **Step 2: Regenerate the authority records and `decision_lock.v3`**

Rebind, in one deterministic regeneration, the resource envelope, metering
authority, pre-run lineage, randomization schedule, and `decision_lock.v3` over
the Task 1/2/3/3A successor bytes. Preserve the scientific and route choices
exactly: unchanged four-arm topology, terminal routes, call bounds,
`N=2`/`k=2`/`M=3` operating rule, one-invalid-attempt allowance, fresh sessions,
no resume, median `RICH`/`DIRECT` token-cost-ratio cap of `4.0`, actual-only
receipt authority, and no token cap. Bind metering without changing receipts or
the existing Codex JSONL shim.

The predecessor package must be recorded as
`SUPERSEDED_PRELAUNCH_SCOPE_TOO_SMALL` — not failed and not invalid — and
machine checks must prove it has no live attempt record, provider allocation,
usage receipt, owner-adopted lock, or denominator contribution. The lock owns
the `ES-F1-FULL` study/execution domain with empty dedicated roots; an old ID,
fabricated prefix, smoke-as-attempt, resume, or mixed domain rejects.

Update controller and synthesis package loading to consume the new content
addresses. Do not introduce a new package schema version.

- [ ] **Step 3: Run the existing provider-free gates unchanged**

In tmux under `ptycho311`, regress the existing Task-5 apparatus against the
successor bytes: package binding, tamper, metering, selector isolation, and
no-resume controls; the reference-conformance and evaluator-calibration replay
established in Task 3A; and deterministic re-generation (generate twice, require
byte-identical output). Reuse the Task-3A evidence rather than re-running its
matrix a second time for its own sake.

The separately locked canonical smoke row stays unconsumed and outside every
attempt counter, denominator, valid-block, and invalid-cap accounting.

- [ ] **Step 4: Obtain one prelaunch review**

Publish the exact committed package for a single review at
`artifacts/review/es-first-effectiveness-study-prelaunch-review.md`. One
reviewer reads the whole package. Per the Section-0 amendment this is one
review, not an ordered specification/quality pair: the delta under review is
digests over already-reviewed apparatus plus the Task 1–3A task, evaluator, and
reference content.

The review must confirm the successor scope and evaluator matrix, the
reference-product band result, the unchanged apparatus, the lock contents, and
the absence of any reference locator or measured count on a provider-visible
surface. A finding that names a concrete contract violation blocks; prose
preference does not. Record the verdict in the closed adoption bindings.

- [ ] **Step 5: Obtain exact owner adoption**

The pending form must require personal adoption by Ollie of these statements;
an agent may mechanically prepare the exact record at his direction but may
not substitute standing, class-level, or delegated adoption for this
scientific lock decision:

1. I confirm that the predecessor F1 package is
   `SUPERSEDED_PRELAUNCH_SCOPE_TOO_SMALL`, that no arm or provider session ran
   under it, and that it contributes no attempt, invalid-attempt allowance, or
   denominator row to this study.
2. I confirm the exact successor scope of all fourteen named frozen built-ins
   plus one candidate-declared witness through construction, training,
   checkpoint, bundle, fresh-process reload, inference, identity, and
   round-trip evaluation, including a witness implementation distinct from all
   built-ins, the complete current/historical artifact applicability matrix,
   and the complete JSON-review-adopted legacy-bypass proposal/proof set.
3. I confirm the exact measured 667-production-addition A1 anchor, the
   fresh nineteen-selector baseline, the independently unmet cluster and
   cross-cluster feasibility facts, the controller-only conforming
   reference-product manifest, and its inclusive 5,000–10,000
   `implementation_delta_physical_lines.v1` result; tests/docs are additional,
   and no candidate is accepted, ranked, or stopped by LOC, file-count, cluster
   count, or churn.
4. I confirm the exact existing-field visible/hidden/check/arm/trial timeout and
   byte envelope, observed positive packet headroom, the 120-hour
   planning-only allowance that adds no runtime deadline, low-confidence token
   estimates, no-token-cap rule, actual-only receipt authority, and unchanged
   median `RICH`/`DIRECT` token-cost-ratio cap of `4.0`.
5. I confirm the unchanged four-arm topology, terminal routes, call bounds,
   `N=2`/`k=2`/`M=3` operating rule, one-invalid-attempt allowance, fresh
   sessions, and the rule that no attempt is ever resumed.
6. I personally adopt the exact `ES-F1-FULL` successor decision-lock digest,
   separately scoped one-use apparatus-smoke authority, and four-row attempt
   randomization schedule as the sole authority for live F1 execution; this
   adoption makes no general superiority, USD/billing, security/isolation,
   promotion/merge, or E3-implementation claim.

Validate the closed record: require `evidence_status=owner_confirmed`, owner
identity/role, one common adoption timestamp, all six statements byte-for-byte,
exact package and review bindings, truthful `prepared_by`, and an explicit
owner-adoption provenance statement saying Ollie personally reviewed and adopted
those exact bytes. Reject a relayed summary, delegated adoption, standing
direction merely to prepare a form, altered statement, stale digest, or
pre-review adoption.

- [ ] **Step 6: Generate the launch manifest, record routing, and stop**

Bind the closed adoption digest into `launch-manifest.json`, independently
reload every file, prove the three exact Section-3 state/evidence/run-ref roots
are real non-symlink empty directories (created only as part of this
provider-free launch-manifest freeze), bind those exact paths without aliases,
and prove no predecessor attempt ID is admissible. Any child, symlink,
unreadable path, fallback root, or out-of-scope substitution fails closed. This
remains a provider-free action.

Advance the component-plan/roadmap/index/routing row from accepted refreeze
pending to complete: the pre-run scope replacement is complete, the new lock is
owner-adopted, and existing ES Task 7 is next. Do not reintroduce the old
two-architecture wording or change E3, P, L, M, or security selection.

Run the focused prelaunch and routing controls against committed bytes and
commit. This plan ends without a smoke or live arm. Continue immediately with
the existing component plan's Task 7 using only the new lock and new attempt
IDs.

## 6. Verification matrix

| Risk | Positive proof | Negative proof |
| --- | --- | --- |
| Scope still too small | conforming reference measures 5,000–10,000 inclusive | out-of-band reference or unmeasured estimate blocks freeze |
| Work is still one-context-shaped | closed tree algebra; authenticated baseline, two-green, remove-one, and adjacent ledgers; three AST-plus-same-node-trace edges; pre-purge ordered adoption; and a post-purge tombstone | hidden tree delta, self-attested Boolean, missing callsite/callee trace, premature purge, retained root, or missing/stale tombstone blocks Task 0 |
| Policy invents discovered consumers | two byte-identical non-authoritative discoveries precede policy authorship; build independently rescans all 1,948 leaves | downstream discovery consumption or any discovery/policy/recomputed-set mismatch rejects |
| Architecture domain incomplete | exact 14 built-ins + one witness | missing/duplicate/reordered/colliding row rejected |
| Artifact-era domain is over- or under-applied | every era partitions all fifteen IDs; current artifacts cover all and metadata-free `legacy_v1` covers only `cnn` | incomplete/overlapping partition, non-`cnn` legacy positive, or missing rejection fails H04 |
| Witness is an alias | constructor and four reload identities are equal and distinct from all built-ins | `es_f1_witness -> FfnoGenerator` fails H09 |
| Legacy bypass survives | frozen AST inventory plus runtime consumer probes satisfy all adopted consumer proposals | one restored or novel bypass fails the owning clause |
| LOC becomes a target | calibration flags say non-acceptance | LOC/file-count/churn field rejected from task and outcome contracts |
| Hidden reference leaks | task-seed closure and every provider surface exclude all reference objects/locators/canaries/counts | one resolvable object or delivered marker blocks freeze |
| Neuralop shape drift | `neuralop_uno` runs at 128 | 64 for it, or 128 for another built-in, rejected |
| Adapter claims authority | evaluator derives all observations | adapter-authored observation/identity/pass field rejected |
| Partial lifecycle | every row has every current lifecycle stage and two current artifacts; historical fixtures follow the closed applicability matrix | missing stage/artifact/fresh PID or wrong historical applicability rejected |
| Ownership expansion | existing training path exercised with boundary exclusions intact | descriptor-owned physics/loss/scaling/data field rejected |
| Old seed leaks | new child has only projection parent | old-task-seed parent or old asset rejected |
| Apparatus drift | same arm topology and call tables | extra call/role/retry/review fails lock validation |
| Large diff truncation | 2 MiB diff, 4 MiB item, and 8 MiB packet calibration passes | oversized/truncated/unbound packet fails closed |
| Estimate mistaken for cost | actual receipts are sole synthesis authority | estimate in receipt or imputation rejected |
| Line census drifts | strict-UTF-8 `splitlines()` totals count an unterminated final line | LF-only subtotal or changed line method fails validation |
| Selector coverage is asserted rather than observed | exact node IDs and static/runtime observations cover the sampling-rule-derived required set; every other consumer remains source-identity-bound as `inherited` or `open` | unknown node, echoed required consumer ID, missing class/provider representative, witness on `inherited`/`open`, domain mismatch, or backpointer-cardinality mismatch rejects |
| Baseline is mistaken for desired-state conformance | Task 0 records truthful pre-edit facts; Task 3A binds desired-state results to the exact reference tree | removal/bypass proof claimed passed on baseline, or baseline result substituted for reference result, rejects |
| Review prose becomes machine authority | closed ordered JSON adoption binds plan plus four canonical records | Markdown-only, stale, reordered, duplicate-reviewer, or non-approved state rejects |
| Refreeze invents apparatus | Task-5 provider/prompt/SDK/hard-evidence/runtime bytes remain unchanged except content-addressed package bindings | new helper, schema version, call input, deadline, or collector blocks review |
| Smoke contaminates the study | provider-free fixtures leave the separately locked canonical smoke row unconsumed and it remains outside every attempt counter | pre-adoption canonical consumption, or smoke ID/map in attempt order, denominator, valid-block, or invalid-cap accounting rejected |
| Attempt reuse | lock-owned `ES-F1-FULL` study/execution domain and empty roots | old ID, fabricated prefix, smoke-as-attempt, resume, mixed domain, or nonempty root rejected |
| Premature launch | adopted lock/review/package required before allocation | pending/stale/missing adoption yields zero provider allocation |

## 7. Completion criteria

The scope amendment is complete only when:

1. Task 0 is closed under its completed ordered review pair (already
   satisfied; the Section-0 amendment requires no re-review);
2. the new visible task, evaluator, seed, controller-only reference product,
   resource plan, lineage, schedule, decision lock, and controller package are
   canonical and content-addressed;
3. the conforming reference measures 5,000–10,000 inclusive under the exact
   metric, has one distinct witness, passes the closed bypass oracle, and is
   proven absent from every provider-visible closure/surface;
4. all fifteen architectures pass the provider-free current-artifact control,
   every historical artifact follows its closed applicability partition, and
   the complete negative calibration matrix fails in the intended clauses;
5. provider-free public E2/ES execution reuses the completed Task-5 apparatus
   unchanged, and its package-binding, tamper, metering, selector-isolation,
   and no-resume regression tests pass under the successor bytes;
6. the exact package passes its one prelaunch review, Ollie personally adopts
   the final lock and six statements, and the adoption-bound launch manifest
   validates from committed bytes and empty dedicated roots; and
7. focused, broad non-security, and postcommit routing controls pass.

No smoke, arm, provider session, attempt, invalid-attempt allowance, or
denominator row may be consumed before all seven conditions hold. Completion of
this plan authorizes only return to existing ES Task 7; it is not an ES result,
an E3 decision, or a claim that 5,000–10,000 LOC is intrinsically desirable.
