# Functional Calibration Command-Recovery Plan

> **For agentic workers:** Use `superpowers:subagent-driven-development` for bounded task-fixture preparation and independent review. The coordinator retains selection, integration, declarations and final verification.

**Goal:** Test a naturally produced, commands-only PRR difficulty point with four fresh solutions and one blind judgment.

**Architecture:** Keep the accepted RT8 harness, full derived-pure replay/profile contract and public APIs. Restrict the new settled-failure recovery extension to eligible ordinary commands; calls retain their existing selection, restoration and retry rules. Create a separate public task package and reuse existing natural intake, pooling, sandbox, metering and canonical summary interfaces.

**Tech stack:** Existing Python comparison harness, typed Workflow Lisp compiler/runtime, Git, Bubblewrap, tmux and installed Codex CLI. No runtime change, general runner/framework or new environment is selected.

## Authority and selected task delta

Start at [the documentation index](../index.md), the [LS8 isolation plan](2026-10-23-functional-calibration-filesystem-isolation-plan.md), and the [LS9 shared-contract plan](2026-10-23-functional-calibration-shared-contract-rejudging-plan.md). LS9 closed canonically at `/home/ollie/sc-evidence/LS9-20261023/combined-readout.json`, SHA256 `d85986050ae087d8625cc63c660c3d1a1af3d8638160ef0104d758e3969f4de2`: RPI Luna 4/4, Sol 5/6; PRR Luna 4/3, Sol 2/2. Both tasks failed qualification. All original captures and scores remain unchanged; RPI is not altered or rerun here.

The coordinator selects PRR commands-only as a prospective intermediate hypothesis. LS5's Sol mean 6 without the full extension and LS9's Sol mean 2 with it are historical motivation, not a controlled difficulty curve, proof of monotonicity or prediction of model ordering. LS10 must observe its own results.

The new `pure-result-replay-command-recovery` task retains the complete normal `derived_pure_replay.v1` profile, replay, shells, persistence surfaces, validation and importable APIs from PRR. Its item 4 adds settled-failure recovery only for an ordinary command using `reuse_validated_structured_output`, under the exact already persisted profile, with the matching integral/restorable node-local checkpoint, failed row, visit and containing-frame identity. It restores that command's environment/overlay and retries through normal command execution. It adds no route that recovers a failed call or nested call-frame lineage in place to reach an inner command. Existing call selection/restoration/retry, interruption barriers and persisted profiles remain unchanged; no backfill or upgrade is admitted.

Public fixture alignment is part of this task change. The LS8 seed's `test_settled_failed_call_resume.py` explicitly demands same-frame call recovery and is executed by its dev-check. Copying it unchanged would contradict the reduced requirement. Preserve all LS8 files; omit that module from the new seed and replace only its dev-check selector with a small public ordinary-command fixture. Keep `base_commit` and `seed/tests/test_runtime_step_lifecycle.py` byte-identical to LS8. The remaining dev-check selectors and timeout stay unchanged. The resulting seeded compare base is new and must be derived and verified before dispatch.

## Frozen prospective protocol: LS10-20261023

| Item | Selection |
| --- | --- |
| Task | Only `pure-result-replay-command-recovery`; full `task.txt` equals `intent.txt` byte-for-byte |
| Base | PRR LS8 `f80e551a6cdeca6a2913ce640326495be1ae1cc5`; new declared command-only seed |
| Fresh generation | `direct_task`: two `gpt-5.6-luna` high; `sol_low`: two `gpt-6.1-sol` low |
| Conditions | Same task, seeded baseline, tools and limits across arms; two paired waves `(Luna1, Sol1)`, then `(Luna2, Sol2)`, at most two generators concurrently; 14,400 seconds and one physical call per generation |
| Judge | One fresh `gpt-6.1-sol` high call, 3,600 seconds; four anonymous final clones in one batch |
| Judge contract | Exact full task actually delivered to solvers, through existing `score-inputs.intent` |
| Rubric | Existing `score_functional.orc`, one holistic functional S0–S8 score; no independent style/scaffolding credit |
| Qualification | Sol mean − Luna mean ≥ 2, Sol mean > 3 and Sol mean < 5; all three required |
| Spend | Four fresh generations + one judge = five planned, hard new cap five; 68 historical + five = overall cap 73 |
| Forbidden | Claude, Fable, native delegation, extra roots, hidden tests, reference/control clones, automatic retries, replacements and artificial solution flaws |
| Claims | This task's difficulty only; no evaluator qualification, C1, sealed-task readiness or quality/cost Pareto claim |

Retain `terminal-single-call-patch-v1`, exact arm IDs, model/effort bindings, the frozen LS9 price table and unavailable Luna/Sol price declarations. Complete legitimate failed or false-valued terminal captures stay in the original four-observation denominator; completion is not proof that the task works. Do not carry LS8/LS9 observations or scores into LS10.

Roots:

- Runtime: `/home/ollie/sc-runtime-functional-filesystem-isolation`, clean commit `6e75c90ceeac6b027557e5da80f8250ccc62a3b4`.
- Evidence: `/home/ollie/sc-evidence/LS10-20261023`.
- Freeze: `/home/ollie/sc-evidence/freeze-functional-command-recovery-20261023`.
- Work: `/home/ollie/sc-luna-sol-command-recovery-work`.
- Pool: `/home/ollie/sc-pools/pure-result-replay-command-recovery/LS10-20261023`.

## Task 1: Complete and review the public task package

New files under `experiments/compare/tasks/pure-result-replay-command-recovery/`:

- `task.txt`, `intent.txt`, `base_commit`.
- `seed/dev-check.json`, `seed/tests/test_runtime_step_lifecycle.py`.
- `seed/tests/test_settled_failed_command_resume.py` — implementation pending; the package is not launch-ready until this fixture exists and is verified.

- [x] Review the new task's scoped delta against the full frozen LS8 PRR contract. Preserve normal replay/profile behaviour and APIs; remove only the settled failed-call/nested-frame recovery extension and align the fixture accordingly. Change no original task or RPI file.
- [x] Implement the small public command-only fixture using existing compiler/runtime and fixture patterns. Compile and run a typed root with an earlier committed ordinary effect and an eligible ordinary command that genuinely settles failed while an external prerequisite is absent. Enable that prerequisite and resume: require checkpoint-matched command recovery, correct typed output and no repeated earlier committed effect. Do not create or recover a child call frame for this positive case.
- [x] Prove that the fixture reaches a real terminal failed command and a present, integral/restorable node-local checkpoint matching its actual failed row/visit/frame before its recovery assertion. Preserve the existing fail-closed requirement for unavailable checkpoint authority; add a small behavioural negative case if needed to cover the new fixture's authority boundary. Do not fabricate/backfill checkpoint identities, weaken runtime behaviour or introduce a deliberate implementation defect.
- [ ] Keep all other dev-check selectors and its 1,800-second timeout unchanged; replace only the old call-fixture selector. Run collection for the new fixture, its scoped baseline/precondition proof and the existing public task-package smoke through accepted interfaces. A baseline target failure is expected where the requested feature is absent; distinguish it from a broken fixture/import/precondition. Do not manufacture a passing candidate solution as a control.
- [ ] Verify `task.txt == intent.txt`, original `base_commit`/lifecycle-test bytes, and the complete new seed manifest. Derive and record the new seeded Git compare base. Independently review the final task/fixture delta before freezing; reuse accepted RT8/native/tool/environment evidence without a broad-suite rerun.

## Task 2: Freeze and run four fresh natural generations

- [ ] Freeze the full completed package, criterion, public fixture proof, exact source/tool bindings and four distinct prepared units/private homes. Use accepted preparation/sandbox APIs and bounded study glue only; never edit or monkeypatch frozen LS8/LS9 helpers/globals.
- [ ] Bind one byte-identical task and seeded compare base across all four authors. Verify the exact full task in each actual solver input/rendered prompt, model/effort, 14,400-second timeout, one-call guard, no-Claude/delegation guards and positive filesystem grants. Reuse prior apparatus proofs; check only this new package and its actual new commands/grants with inert backends.
- [ ] Independently review the concrete generation packet, then record its criterion/packet-bound coordinator declaration for five planned starts, 68 historical, cap 73. This is the coordinator's bounded selection under the owner's iterative-calibration direction, not an invented numeric owner approval.
- [ ] Inventory the twelve completed LS8/LS9 units plus every prepared LS10 unit using accepted metadata/classifier logic: four generators before pooling, then those four plus the judge created by `pool.write_pool`. Reserve all five planned starts from the outset without inventing a judge home before its clones exist. Preserve the older physical floor 56: twelve earlier starts + zero LS10 = 68; four generations give 72 with one reserved judgment; all five give 73. Do not reset the floor, double-count reused history or import old globals with altered constants.
- [ ] Run generation in tmux with at most two concurrent authors and no retry/replacement. Retain original terminal/result/patch/native/receipt/scan artifacts, including legitimate failures. On apparatus, model, delegation or contamination incidents, stop further dispatch and preserve best-effort metering with explicit incomplete/unavailable diagnostics.
- [ ] Independently review all four captures. Preserve before/after crosswalks for justified scan-only adjudication; never repair outcomes, result values or patches. All four observations remain in the denominator.

## Task 3: Prepare, review and run one blind judge

- [ ] Intake all four original captures with existing `pool.natural_attempt` and preserve its rows/views. Build one fresh pool with `pool.write_pool`, four anonymous final clones, exact original raw patches and seeded Git joins, existing `docs/plans/evidence` review exclusion, no controls/references and no hidden acceptance.
- [ ] Assert actual `score-inputs.intent.encode()` equals the full frozen task bytes delivered to all four authors. Prepare a distinct fresh judge home and exact read-only clone grants. Pass the public dry run and actual new-pool inert qualification; preserve original rows, patches, records and clone indexes before/after.
- [ ] Freeze and independently review the concrete judging packet. Bind its declaration to the same original generation declaration, five-start selection and overall cap 73; four generation starts mean 72 overall, leaving exactly one selected judgment.
- [ ] Launch the exact Sol-high command in tmux, one call with the 3,600-second timeout and no retry. Preserve terminal/native/receipt/scan bytes and review integrity independently. Stop and preserve an incident rather than replacing an observation.

## Task 4: Close and report canonically

- [ ] Verify the pool with the existing public harness and close through `experiments.compare.summarize.summarize`. Report all four ratings using harness clone-ID → original-run joins and all three frozen predicates, including any failed observations.
- [ ] Verify exactly five new/73 overall physical starts, no extra roots/children or forbidden models. Report native usage and unavailable prices honestly, without a monetary total or Pareto claim.
- [ ] Preserve all historical tasks, captures, rubrics and readouts unchanged. The coordinator owns the LS10 report, routing and any later prospective selection. Neither a pass nor a failure here opens C1 or establishes evaluator qualification, call-recovery correctness or a monotonic difficulty curve.

## Decision ledger

| Decision | Basis / consequence |
| --- | --- |
| PRR-only intermediate hypothesis | LS9 canonical readout SHA `d8598605…` gives PRR Luna 4/3 and Sol 2/2; both LS9 tasks fail. Historical LS5 Sol 6 motivates exploration but predicts neither monotonicity nor model ordering. No RPI change is selected. |
| Ordinary-command recovery only | Preserve the full normal PRR profile/replay contract and APIs, while removing the new settled failed-call/nested-frame recovery route. This is a prospective task delta, not posthoc repair of an observation. |
| Explicit public seed delta | Review found that the LS8 positive call fixture requires the removed scope. Keep base/lifecycle bytes, omit that module, replace its dev-check selector and prepare a small command-only fixture plus a new seeded-baseline proof before dispatch. Original LS8 seed bytes remain untouched. |
| Preserve LS8 execution limits | Generations remain 14,400 seconds, judge 3,600 seconds. The initial shorthand of 3,600 for every call was corrected before task preparation/spend; there is no new time-limit confound. |
| Five fresh starts, overall cap 73 | Two Luna high, two Sol low and one Sol high judge; 68 historical starts. Concrete phase packets, independent review and truthful coordinator declarations precede calls; no retries or replacements are selected. |
| Bounded reuse | RT8, natural intake, pooling, positive isolation, metadata/classifier, metering and canonical scoring remain the accepted interfaces. No new runtime, environment, general framework or broad requalification is selected. |
| Stage-aware native inventory | Existing `pool.write_pool` creates the judge home from the final four-clone batch. Inventory twelve historical units plus four prepared generators, then plus the actual judge once prepared; reserve five starts from the initial declaration. No placeholder home/grants or accounting reset is introduced. |
| Pair models within each generation wave | Prepare and execute `(Luna1, Sol1)`, then `(Luna2, Sol2)`, at the existing width two. This gives both model arms an early and a later observation without adding calls, altering identities or changing limits. |
| Public command fixture reviewed | Fixture SHA256 `925c2fd038648c0198aa91c0d5129698cb45cbbce496f945c8f2b707426de0ff`; proof `/home/ollie/sc-evidence/preparation/LS10-command-fixture-proof.json`, SHA256 `fdd46b51f5c9d2a26d2cc7ea98c15e7eb29aa4e3f8c1e6980bb69ae2d572dfbb`; independent review `/home/ollie/sc-evidence/preparation/LS10-command-fixture-independent-review.json`, SHA256 `9bafe953ee298db3e477904a37eb99e5d2b72a6d9e9fc9ca9ca49aa44930f4ec`: PASS. Four tests collect in both contexts; unchanged historical baseline reaches the pure condition, settled command failure and matching restorable checkpoint, then fails the missing target feature. Negative cases stop at the absent-profile precondition, so they do not validate profiled checkpoint rejection. Actual state/checkpoint files are bound; raw command logs and the nested resume exit were not retained independently. No candidate success is claimed. Public package smoke and new seeded-baseline verification remain pending. |
