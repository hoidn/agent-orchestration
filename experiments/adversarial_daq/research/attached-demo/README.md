# DAQ debug agent: the five-moment demo

A TMO run stalls at 2 a.m. An agent reads the logs and proposes a fix from the
on-call playbooks; a deterministic check confirms the evidence is real and the
playbook's preconditions hold on its target; DAQ on-call decides; the
playbook runs. One workflow in typed Python, one terminal, one on-call
console, about twelve minutes.

The stalls are synthetic but built from public SLAC sources: the failure modes
and their fixes from the DAQ team's Confluence pages, the log formats, cnf
lines, XPM PVs, `/proc/datadev_0` and DRP metrics from the psdaq and
aes-stream-drivers source. Tables the facility would render (the XPM link table,
the hsdpva summary) say so in their headers. None of the failures shown
depends on the model being dumb: the ones on screen are what real models did in
rehearsal (`rehearsal/TRIALS.md`).

| # | Moment | What's on screen | Status quo |
|---|---|---|---|
| 1 | How is it built, and what will it touch? | the Python workflow; the compiler's site table: 5 effects, one of them a person's answer; the playbook reachable only through `DIAGNOSED → APPLICABLE → ANSWERED → APPROVED`; the model step's permission rules, and a recorded Sonnet session refused a shell | a SKILL.md says in prose what to do; the harness hands the agent a shell |
| 2 | What did the model see, and what is DAQ on-call asked? | run 412 (the opal node's timing link to the XPM stopped locking): the prompt on disk, the model's reply (labelled replayed or live), the typed result, the check reading the XPM's link PVs, the run *suspended* on DAQ on-call's request, the request in the console | the output format is prose; approval is a thumbs-up on a summary, not on the steps |
| 3 | Change it under the pending approval | an edited evidence file: the answer is refused (`shown_evidence_changed`); an edited playbook: the resume is refused (`effect_input_diverged`) | a yes in a chat thread is not tied to what it approved |
| 4 | DAQ on-call says yes. Then the power goes out | `input answer --by tmo-daq-oncall`; the playbook starts; kill -9 during step 2; resume refuses to repeat it (`must_not_repeat`); the record | the agent retries its last command, or nobody knows how far it got |
| 5 | The next page | run 431, "100% deadtime again", and the elog says how 412 ended and that `hsd_7` was commented out at 03:31: a zombie HSD the playbooks don't cover; the model says `UNLISTED`, with the right analysis, and it goes to a person | the agent reruns last night's fix, or acts on its own suggestion |

The deck: https://claude.ai/artifact/2EZhw2GHXSwiQewA2wJdV6 (private until shared from its Share menu).

## Run it

```
# agent-orchestration main (Python frontend + durable host input); on macOS use fix/py-frontend-macos
AO_REPO=/path/to/agent-orchestration ./demo.sh                          # replayed model: deterministic rehearsal
AO_REPO=... PROVIDER=real ./demo.sh                                      # the real `claude`, confined (~3 min of model time)
AO_REPO=... PROVIDER=real MODEL=claude-sonnet-5-5 ./demo.sh              # another model under test
DEMO_NOPAUSE=1 AO_REPO=... ./demo.sh                                     # straight through, no browser
AO_REPO=... tests/smoke.sh                                               # every moment's payoff, plus the uninterrupted path
python3 tests/test_evidence.py                                           # the quote check's rules
AO_REPO=... tests/trials.sh claude-haiku-5-5 412 412 431 431             # what a real model does, in parallel workspaces
```

Needs python3 >= 3.11 with jsonschema and PyYAML. `demo.sh` deletes
`.orchestrate/runs/` and `artifacts/` at the start, and restores the evidence
file and `scripts/playbooks.py` on exit even if interrupted mid-edit. The
console (`artifacts/console.html`) opens in the browser at moment 2 and
refreshes itself; keep it beside the terminal.

On macOS, agent-orchestration main fails `py build` twice: a `/var` vs
`/private/var` temporary-path mismatch and a Linux-only `renameat2` in snapshot
publication. Branch `fix/py-frontend-macos` (worktree
`../agent-orchestration-py-macos`, rebased on main) fixes both, with tests;
`demo.sh` says so if `py check` fails.

## What is in the kit

```
workflows/daq_diagnosis.py      the workflow: typed Python at target 2.40, 4 commands, 1 model call, 1 question to a person
workflows/prompts/diagnose.md   the prompt (the SKILL.md analogue): text only; the contract is appended by the runtime
scripts/playbooks.py            the four on-call playbooks (deadtime_link, stuck_transitions, hsd_link, kcu_buffers):
                                steps, and the precondition each reads from the bundle; partition members only
scripts/check_playbook.py       the evidence is real, and the proposed playbook applies to its target (not "the diagnosis is right")
scripts/evidence.py             what counts as a quote: copied from one line of the bundle, not rewritten
scripts/daq_logs.py             tool-layer stand-in: gathers a stall's sources into artifacts/daq/<run>/<orchestrator run>/bundle.txt
scripts/daq_recover.py          the actuator, dry run: walks the playbook's steps, logs each; must_not_repeat
scripts/console.py              the on-call page: approval requests, escalations, interrupted recoveries, records
scripts/check_effects.py        moment 1: py build, compile, and list every effect from the closed program
scripts/show_run.py             presenter views of a run: memo, audit trail, verdict fields
confine/claude                  the model step under Claude Code permission rules (dontAsk, no shell, no kit files,
                                two writable files, none of the operator's own settings or plugins)
bin/claude                      the scripted provider: replays recorded real-model output (rehearsal/replay/)
fixtures/stall-412, stall-431   the two stalls: elog, control log, XPM pvget and link table, archiver query of the
                                link PVs, DRP metrics, hsdpva, /proc/datadev_0, the run's own tmo.cnf, DRP logs
inputs/                         providers.json, commands.json (bindings, closures, must_not_repeat), run_412.json, run_431.json
rehearsal/TRIALS.md             what Opus, Sonnet and Haiku did on these stalls, judged
rehearsal/refused.txt           a recorded Sonnet session reaching for a shell, and the permission rule refusing it
tests/smoke.sh, tests/trials.sh rehearsal check; real-model trials
tests/test_evidence.py          unit tests of the quote check, from what models actually quoted
```

## The stalls, and where they come from

- **Run 412.** The KCU1500 timing link from the ATM opal's node
  (drp-srcf-cmp026) back to `DAQ:NEH:XPM:2` relocks after the reset at
  Configure, then drops after Enable and stays down: readout group 0 goes to 100%
  deadtime, every DRP times out on Disable phase 2, and only `LinkRxReady4`,
  `DeadFLnk[4]` and the archiver history of the link show which one. The
  documented fix is a TxPhyPllReset on that KCU (or an xpmmini→LCLS2 toggle),
  then reading the link back before Disable/Enable. Source: "Link And Firmware
  Robustness Issues" (camlink/epix100 deadtime-link incidents, 2025). The elog's
  02:09 camlink cable swap is a red herring: that cable carries camera data in
  the hutch, not the KCU's timing fiber at SRCF.
- **Run 431.** The same symptom an hour and a half later. The elog records how
  412 ended (the recovery was cut off and finished by hand) and that `hsd_7`
  (HSD 3E:B) was commented out of `tmo.cnf` at 03:31. The card's enable was left
  set, so it fills, never drains, and holds readout group 0 dead through link 6:
  a "zombie". No on-call playbook covers it, and every playbook refuses a target
  that is not in the run's cnf. Source: "Debugging DAQ" (zombie HSD with a stuck
  enable bit). The elog invites repeating last night's fix.

What a person sees is real orchestrator state: the pending request comes from
`orchestrator input get`, the answer from `orchestrator input answer`.

## What the check does, and what the person does

No script can verify an open-ended diagnosis, and this one does not try.
`check_playbook.py` checks what a script can: every line the evidence quotes is
copied from one line of the bundle (a whole line or part of one, not rewritten);
and the proposed playbook's precondition holds on the
proposed target, read from the bundle's own data (the deadtime_link playbook
needs that target's XPM link down, and the only one down). Whether the diagnosis
is right is DAQ on-call's call, made with the steps, the checks, the model's
own words and the evidence in front of them. The request is durable host input:
the run sits suspended, the shown files are frozen (change one and the answer is
refused), an unanswered request expires after 30 minutes, and the answer records
who gave it. When the check blocks, or the model says UNLISTED or INCONCLUSIVE,
or the answer is DENIED, CANCELLED or EXPIRED, the run ends ESCALATED and nothing
acts.

## Stand-ins, and what replaces them

- **The model's credentials.** The runtime's binding is
  `claude_unrestricted_workspace`; `confine/claude` narrows it with Claude Code
  permission rules (no shell; writes only this run's evidence and result). In the
  facility the diagnosis step gets read-only credentials from the access-checked
  tool layer. A confined provider binding in agent-orchestration would replace
  the wrapper.
- **Who may approve what.** One approver, DAQ on-call, for every playbook here.
  A facility would tier it: a readback or a Clear by the on-call alone, a node
  power cycle or a firmware reload only with the DAQ expert. Each tier is one
  more `ask` with its own `show=`.
- **Attestation.** `input answer --by` is a typed name; `--attestation` takes an
  opaque token from an access layer the kit does not have.
- **The tools and the data.** Four scripts stand in for the access-checked
  `daq_logs`, the check and the recovery tool; the playbook is a dry run; both
  stalls are synthetic. The workflow does not change when the scripts become
  tool-layer calls.
- **Reconciling an interrupted recovery.** The runtime will not repeat a
  must-not-repeat effect, and offers no verb for "a person checked; continue":
  `invalidate` refuses an uncommitted effect. The demo's answer is to check the
  hardware and start a new run, which diagnoses the current state.
- **The scripted model** (`bin/claude`, `PROVIDER=fake`) replays recorded Opus
  output. Use `PROVIDER=real` to show the real thing.

## Useful commands afterwards

```
python3 -m orchestrator input get <run_id>                                   # the pending request
python3 -m orchestrator input answer <run_id> <request_id> --value '"APPROVED"' --by <you>
python3 -m orchestrator resume <run_id> --stream-output                      # continue after an answer
python3 -m orchestrator report --run-id <run_id> --format md                 # the full record
python3 -m orchestrator dashboard --workspace "$(pwd)"                       # the engineer's run table
less .orchestrate/runs/<run_id>/effects/*/attempt-1/prompt.txt
```
