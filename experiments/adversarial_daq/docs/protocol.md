# Experiment contract

This package implements the adversarial process. The adversaries build the
claim-appropriate harness and comparative implementations during a run. It does not ship a
pretend successful DAQ comparison. The unit-test suite is explicitly synthetic
control-flow verification and supplies no evidence of model quality.

## What counts as convergence

Each round has four provider calls, using only two roles:

1. **Builder / BUILD** submits one scoped claim, common experiment harness and
   independent oracle, Orc Python-API implementation, source manifest and dossier.
2. **Skeptic / CHALLENGE** implements the strongest relevant baseline, audits the
   oracle and adds adversarial cases in its own files.
3. **Mechanical runner** copies declared sources, runs both arms with identical
   seeds and fresh state, and records results and raw logs. This is a command,
   not another model.
4. **Skeptic / REVIEW** evaluates execution evidence against the declared claim.
5. **Builder / ANSWER** accepts or rebuts the strongest objection and result.
6. **Integrity check** rehashes the report, source snapshot, manifests, results
   and raw logs after both review turns. `Round.intact=false` prevents acceptance.

The only early successful exit requires matching ADVANTAGE positions, identical
nonempty scoped claim text, the exact current evidence digest, valid runner
evidence, unchanged evidence files, no blockers and both votes' fairness,
relevance and reproduction fields true. It returns `DEMO_SUPPORTED`: a supported
bounded demonstration, not a mathematical theorem.

COUNTEREXAMPLE records a refutation/parity result for one criterion; it does not
end the search. NEEDS_EXPERT defers that criterion and preserves its missing
evidence, false eligibility fields and blockers. These positions, REVISE,
disagreement or invalid evidence all preserve the round and continue while the
configured budget remains. Exhaustion returns `INCONCLUSIVE` with full history,
never universal impossibility. There is no active terminal refutation status.
A narrowly formal impossibility argument may appear in a dossier with its
assumptions and proof; empirical exhaustion cannot substitute for it.

The full typed history is passed into the next construction/challenge phase.
History contains artifact references; agents must read their contents. Stable
claim and objection IDs live in dossiers, with dispositions and exact evidence.
Rounds are append-only by protocol. No new unreviewed revision is created after
the final round. Provider exceptions/timeouts or invalid typed results fail the
run visibly; they are not silently counted as consensus or an experimental loss.

## Criteria and dossier requirements

Each dossier maintains a concise criteria map: candidate, user value, proposed
measure/falsifier, and tested/refuted/deferred/unmeasured status. Consider
materially different plausible benefits, such as static composition/error
coverage before expensive effects, runtime recovery/provenance, or measured
authoring/integration/maintenance effort. These are examples, not an exhaustive
list or a quota. Both roles may challenge relevance and suggest future criteria.
After parity/refutation, explore a materially different plausible benefit or
justify why a specific repair is more decisive; renaming a fault or metric is
insufficient. Runtime parity leaves unmeasured compiler/engineering benefits open.

Before paired measurement, freeze the selected claim ID, scope, complete cases,
comparator, primary measure, acceptance rule and meaningful margin. Criteria may
change only between new experiments/rounds, with a new claim ID and preserved
prior evidence. Retract any superseded/narrowed claim explicitly. No post-hoc
metric selection, favorable secondary-measure relabeling or erased failures.

Use a harness appropriate to the claim. Static-contract claims may use program
variants, an independent rejection oracle and an effect recorder. Score expected
compiler/DUT rejection as data. Physical-state/recovery claims require a causal
stateful DAQ simulation, realistic observations/actions, fresh readback and
restored objective or appropriate bounded escalation. An engineering-effort
claim requires evidence for that effort; LOC alone is not measured human effort.

Both roles must maintain:

- Falsifiable claim, scope, primary source URLs/dates, useful objective, and
  explicit relevance/DAQ realism assumptions with unverified facts named.
- Predeclared criteria, margin, case/control list and independent oracle review.
  Record rejection phase/effects for static claims; observations, actions,
  transitions and recovery postconditions for state/recovery claims.
- Equal model/version, prompt information, permissions, observations, seeds,
  retry/time/token budgets and development allowance. A stronger model on one
  arm invalidates attribution to its orchestration framework.
- Exact library versions/lockfile, all source/glue, useful dependency/API diagrams,
  compile/preflight/run commands, and actual static/dynamic failure timing.
- Complete costs for both paths: baseline preflight and Orc compilation, shared
  and custom guards/validators, adapters and implementation/maintenance burden.
  Also measure applicable unsafe/duplicate actions, false success, unnecessary
  escalation/disruption, expensive effects before rejection, recovery time and
  model usage. Report distributions/uncertainty, not only favorable averages.
- A direct/simple baseline and ablation when needed to isolate the feature. Pair
  one strongest baseline per experiment; other comparators need new rounds or
  explicitly parameterized cases.
- Development/held-out split, all failed trials, counterexamples, answered
  objections and a concise presentation/reproduction recipe. Independent expert
  or held-out evidence must be real; agreement does not supply missing receipts.

A corpus-wide claim cannot be accepted by retreating to a cherry-picked case.
Bare Python expressibility is rarely the differentiator when both sides can
call Python.

## Files and command interface

The builder and skeptic return `Submission {document, manifest}`. Both fields
must be existing workspace-relative files under `artifacts/`. Give each run a
unique experiment ID and each round its own directory. The outer controller
and prompts remain fixed. Package dependencies must already be installed in the
interpreter used for the runner; do not install them during a measured trial.

Example builder manifest for a recovery claim, written next to its sources:

```json
{
  "version": 1,
  "scope": "One falsifiable claim; link claim C1 in the dossier",
  "suite": "suite.py",
  "files": ["suite.py", "simulator.py", "orc_arm.py", "debugger.py", "requirements.lock"],
  "cases": ["clean", "stale_config", "partial_transition", "unrecoverable"],
  "checks": ["safe", "objective_met", "honest_success", "bounded"],
  "metrics": ["expensive_operations", "recovery_ticks", "disruptions"],
  "seeds": [11, 23, 47],
  "timeout_sec": 120
}
```

Skeptic manifest (also next to its own declared source files):

```json
{
  "version": 1,
  "proposal": "artifacts/experiment-001/round-1/builder/proposal.json",
  "files": ["baseline.py", "countercases.py"],
  "cases": ["wrong_run_same_prefix"]
}
```

File paths are relative to the manifest's directory and copied to a shared
source root. They must be unique across the two submissions: the skeptic cannot
replace the builder's `suite.py`. Use disjoint module names. Declare individual
files, not directories, and every import/resource needed by the experiment.
No absolute paths, symlinks or `..`. Metadata names `contract.json`, `result.json`,
`stdout.txt`, `stderr.txt` and `home` are reserved. Paths under undeclared external
repositories are not a reproducible implementation; installed, pinned packages
are allowed and their versions are recorded. The frozen copies and manifests
are kept alongside the evidence.

For each arm and seed, the runner invokes:

```text
<pinned Python> suite.py orc|baseline SEED /absolute/trial/result.json
```

The working directory is a fresh source copy. `contract.json` contains the union
of builder and skeptic case IDs plus the required check/metric names. The suite
must read it, invoke the selected arm through an agreed neutral interface, and
obtain checks/metrics from the independent oracle and applicable effect/action
recorder. Execute program variants for static claims, a reproducible engineering
harness for engineering claims, or a stateful simulator for state/recovery
claims. Case/check/metric names describe the selected criterion; the recovery
example does not require recovery checks in unrelated experiments. Support the
documented extension interface when countercases are needed. The result is one
JSON document:

```json
{
  "arm": "orc",
  "seed": 11,
  "cases": [
    {
      "id": "stale_config",
      "checks": {"safe": true, "objective_met": true, "honest_success": true, "bounded": true},
      "metrics": {"expensive_operations": 0, "recovery_ticks": 2, "disruptions": 0}
    }
  ]
}
```

The example shows one row; execution requires exactly one row for EVERY declared
case, with every declared strict-boolean check and finite nonnegative numeric
metric. A failing check is valid experimental evidence. An exception, timeout,
missing result, wrong identity, missing case, duplicate JSON key or source change
invalidates evidence. Expected compiler rejections/DUT crashes must be captured by the suite and
scored according to the frozen oracle; a crashed oracle is invalid evidence.
For recovery claims, an unresolvable case may meet its objective through correct
bounded escalation; do not reward false recovery or penalize appropriate
abstention.

There must be 3–20 distinct seeds and 2–100 initial cases. These are smoke-test
floors/operational bounds, not statistical sufficiency. Suite timeout is 1–120
seconds per arm/seed. The runner alternates arm order, uses the same interpreter,
clears inherited credentials/environment from the trial process, supplies a
fresh HOME, terminates a timed-out process group, retains stdout/stderr and
records wall time. All imported third-party libraries must work under that
environment. For live-model experiments, deployment may set `DAQ_TRIAL_ENV` to a
comma-separated subset of `DAQ_MODEL_BASE_URL`, `DAQ_MODEL_NAME`,
`DAQ_MODEL_API_KEY`, `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `OPENAI_API_KEY`,
and `OPENAI_BASE_URL`. Only selected, already-set names are forwarded, identically
to both arms. The runner records names, never their values. Use a model gateway
or installed client that actually supports the selected variables; custom
`DAQ_MODEL_*` names require a shared adapter. Keep keys out of source, manifests
and child logs. Deployment must restrict network access to the model endpoint
and impose its usage limits. No credentials are forwarded by default. A recorded
replay must be labeled and cannot substantiate an agent-quality claim.

## Trust and deployment boundary

The runner is an evidence recorder for cooperative adversarial researchers,
**not an OS sandbox or independently certified DAQ oracle**. The suite is
agent-authored and must be cross-reviewed. It can lie about metrics if both
reviewers miss the defect. File hashes detect ordinary source drift, not a
malicious process that edits and restores files or tampers with its parent.
Provider roles share a workspace; write restrictions in prompts are not kernel
enforcement. Run actual generated code only in a disposable VM/container with
no facility access or host credentials, offline except for an explicitly selected
model endpoint when required. For state/recovery claims the simulator must expose
a narrow observation/action API to the debugger; fault truth belongs to the
evaluator. Static and engineering harnesses likewise keep expected answers and
oracle internals separate from the implementation under test.

Seeds in this manifest are **public development seeds**. A publication-quality
final evaluation requires a separately controlled evaluator, frozen candidates,
hidden program variants, fault combinations or task instances/seeds appropriate
to the criterion, and an independently supplied receipt. Merely
calling a filename 'holdout' does not make it hidden. Missing required holdout or
expert evidence must keep the agents' eligibility fields false. The controller
does not automatically certify those judgments or fabricate such a receipt.

An interrupted uncommitted runner command may execute again on resume. Every
trial is synthetic, starts fresh and writes a new evidence directory; never put
a real actuator in this command. Completed effects are memoized by Orc. Changed
source/closure/inputs may make upstream resume refuse; do not edit run-state
files to evade this. New experiments use new runs; semantic changes require
fresh evaluation. Approval of text is not validation of current machine state.
