# Criteria exploration implementation plan

> For agentic workers: use superpowers:subagent-driven-development for implementation and independent review.

**Goal:** Make criteria selection part of the defender's adversarial work, with fresh criteria between experiments and fixed criteria within each measured experiment; continue the bounded search after individual refutations or expert-dependent hypotheses.

**Architecture:** Keep the existing two roles, four calls per round, append-only typed history, mechanical runner and acceptance/integrity checks. Prompts own selection and relevance of criteria; `.orc` owns continuation. A supported bilateral ADVANTAGE is the only early successful exit. Other positions remain in history; exhaustion returns INCONCLUSIVE. Criteria exploration lives in the existing dossiers, not an extra model phase or prose-parsing router.

**Tech stack:** Pinned orchestrator bb9cb30d, target 2.39, Python pytest, deterministic provider fixtures and the existing confined deployment smoke.

## Authority, scope and tradeoffs

The owner approved this design in conversation by asking to make the required changes after discussing mutable criteria between experiments, fixed criteria within one experiment, and continuation after a scoped refutation. No further confirmation or live experiment is needed. This is implementation and offline verification, not authorization for a new provider-funded debate.

Work only in the existing isolated, untracked `experiments/adversarial_daq` package. A parent-repository worktree would not include this untracked package or its prepared pinned environment; preserve a source preimage instead of copying historical trial trees or touching the parent's unrelated dirty files. Preimages and hashes are under `artifacts/criteria-revision-20261023/before`; parent dirty-file and historical-run hashes are recorded beside them. The prior run and its 15 already-changed SQLite SHM files remain exactly as found. Do not open evidence databases or rewrite original verification records.

Tradeoffs: more of the existing four-round allowance may be used after a local failure; a refuted hypothesis no longer provides an early terminal search result. Criterion diversity/relevance remains a cross-reviewed judgment in the dossiers, not a mechanical proof or a required quota of predetermined metrics. Fixture tests demonstrate control flow, not improved researcher behavior. Old completed-run resume is not a new evaluation and may refuse changed source/prompts; any future evaluation must use a new run.

## Required behavior

1. BUILD considers materially different value dimensions before choosing a falsifiable claim. Examples include static composition/error coverage before expensive effects, runtime recovery/provenance, and measured authoring/integration/maintenance effort. These are examples, not an exhaustive list or mandatory winner. Record a concise criteria map in the existing dossier: candidate, user value, proposed measure/falsifier, and tested/refuted/deferred/unmeasured status.
2. After parity/refutation, explore a materially different plausible benefit or justify why a specific repair of the existing experiment is more decisive. A renamed fault or metric alone is not diversity. Retain all prior refutations and uncertainty. Both roles may challenge criterion relevance and propose future criteria.
3. Freeze the chosen claim, scope, cases, comparator, primary measure and margin before the paired experiment. Changing them creates a new round/submission with a new claim ID. No post-hoc relabeling, selecting favorable secondary metrics, erasing failures, or treating runtime parity as a refutation of unmeasured compiler/engineering benefits.
4. Use an experiment appropriate to the claim. Stateful causal simulation is required for recovery/physical-state claims; static-contract claims can use program variants and an independent rejection/effect recorder. Expected compiler/DUT failures are scored observations, not runner crashes. Preserve the runner's existing interface/bounds. Compare matching static checks and the complete validation path; do not charge Orc compilation while omitting baseline preflight from a total-cost claim. Count custom validators/glue on both sides; LOC is not measured human effort.
5. Keep Vote positions unchanged. Remove terminal CLAIM_REFUTED from active Outcome status. A fair/relevant/reproduced, intact, digest- and claim-matched bilateral ADVANTAGE still returns DEMO_SUPPORTED. COUNTEREXAMPLE, REVISE, NEEDS_EXPERT, disagreement or invalid evidence continue while rounds remain, preserving blockers. NEEDS_EXPERT defers that criterion and never grants false eligibility. After the configured limit, return INCONCLUSIVE with full history. Preserve malformed-provider failure and invalid-budget no-dispatch behavior.
6. Keep both `adversarial.orc` and deployed `adversarial_live.orc` behavior aligned; retain deployed model/effort, provider confinement, commands and 4-round/16-site bound. No new types, phases, judge, manifest parser or framework abstraction are needed.

## Tasks

- [x] Review this plan for scope and semantic gaps before implementation.
- [x] Add behavior tests first in `tests/test_workflow.py`: qualified counterexample then a different supported claim continues; an expert-dependent criterion then a supported different criterion continues; all refutations exhaust to INCONCLUSIVE; first-round support still ends early; complete resume adds no effects; history retains earlier claims/votes/evidence and reaches next provider. Retain gate-negative, malformed result and budget tests. No literal prompt-phrasing assertions.
- [x] Change both controller loops and terminal enum with the smallest shared behavioral edit.
- [x] Revise `prompts/builder.md`, `prompts/skeptic.md`, `docs/protocol.md`, `inputs.json`, `deployment/inputs.json`, and `README.md` coherently. Remove stale active descriptions of single-claim refutation/expert need ending the search. Keep historical records unchanged and label old verification evidence as historical where linked.
- [x] Update `deployment/check_workflow.py` to exercise the actual deployed entry over more than one round with deterministic providers, current evidence digests, preserved history and matching exact Sol/high bindings. Include the counterexample-to-new-claim route; do not accidentally invoke a real CLI. No changes to confinement or the evidence runner.
- [x] Collect changed tests; run narrow meaningful selectors before the package suite. Run full package tests in tmux with `pytest tests -q -n 16 --dist=worksteal`, plus compile/dry-run of both entries and deployed confined smoke. Reuse previously passed confinement checks because those files do not change.
- [x] Independently review specification compliance, then code/docs quality. Coordinator inspects the preimage diff and verification output and verifies unrelated files and old evidence remain unchanged.

## Behavioral simulation scope

Before/after source hashes and actual fixture event logs will accompany verification under `artifacts/criteria-revision-20261023`. Use three representative scenarios: (target) qualified recovery parity followed by a different static/engineering criterion; (hard) a criterion blocked by missing expert evidence followed by an independently eligible criterion; (simple) supported advantage on round one. The old controller ends the first two early; the new controller proceeds within the same bound. A fourth scenario of all refutations must remain INCONCLUSIVE at the limit.

Observed evidence: the previous real run used four related operational metrics; static checks were narrow controls, not primary claim measures. Specified delta: the routing above and dossier criteria search. Inferred behavior: researchers may explore broader criteria after the prompt revision. Fixture outputs are synthetic control-flow evidence, not proof of this inference or task-difficulty calibration. Falsifier: a future authorized run could still repeatedly choose equivalent dimensions, fail to predeclare criteria or make unsubstantiated engineering claims.

## Decision and verification ledger

- Plan created before implementation. Existing user approval covers the design and edits; no new live run or paid quality comparison is selected.
- Current owner routing was read from `docs/index.md`, current Lisp guide, capability matrix, DSL/provider/dependency contracts and workflow catalog. Retired YAML guidance does not select runtime behavior; the existing package uses the real pinned evaluated `.orc` route.
- Source, deployment and historical artifacts are preserved in the preimage/hash records. The original launch record remains historical; this plan owns only the new revision.
- Independent plan review approved the design without blockers. It specifically required removing blanket stateful-simulation/recovery wording from all current prompt/protocol obligations, including dossier requirements.
- Reuse Sol 6.1/high for implementation because controller, deployed entry, prompts, docs and fixtures require coordinated changes; retain the distinct Sol 6.1/high reviewer. These are development roles, not new experimental arms or live workflow launches.
- Implementation complete. The minimal controller change removes the two early exits and terminal refutation enum; acceptance checks, evidence runner and confinement are unchanged. The durable baseline still requires actual persistent LangGraph or an explicit technical justification for a stronger relevant alternative.
- Fresh verification: 21 workflow cases collected; the four routing selectors first produced three expected failures and one pass, then four passes. Full package suite: **37 passed in 17.46 seconds**, using `pytest tests -q -n 16 --dist=worksteal` in tmux. Both base and deployed controllers compiled and passed dry-run (four exits 0). Deployed smoke passed with eight fake Sol/high calls, twelve confined trials and checked round-to-round history; zero real provider calls.
- Independent specification review and separate code/docs quality review approved without actionable findings. The coordinator inspected the source-preimage diffs and saved command outputs. All 21 unrelated dirty tracked files and 5,685 prior run/evidence files retain their recorded hashes, including the earlier run's already-modified SHM files.
- The [behavior comparison](2026-10-23-criteria-search-simulation.md) and [verification evidence](../../artifacts/criteria-revision-20261023/verification.json) record the bounded routing result. No paid relaunch or live search-quality claim was made. Criteria diversity remains unmeasured model behavior.
