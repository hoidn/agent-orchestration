"""DAQ debug agent: fetch the logs, diagnose, check, ask a person, act.

Typed Python that generates an ordinary Workflow Lisp program:

    python3 -m orchestrator py build workflows/daq_diagnosis.py --entry-workflow diagnose_and_recover \
        --provider-externs-file inputs/providers.json --command-boundaries-file inputs/commands.json

Each `match` arm nests the next effect, and the compiler names every effect by
the arms above it: the recovery is reached only through DIAGNOSED, APPLICABLE,
ANSWERED and an APPROVED answer.
Nothing routes on prose: the model's reply is never read, only its typed result.
The causes are the on-call playbooks in scripts/playbooks.py; a cause outside
them is UNLISTED, and goes to a person.
"""
from enum import Enum

from orchestrator.py import (Command, Doc, HostReply, Prompt, Provider, RelPath, Text, Value,
                             ask, match, proc, record, variant, when, workflow)

TARGET = "2.40"                    # durable host input (ask)


# --- contracts: what each effect must return, checked by the runtime ------------
class LogBundlePath(RelPath, under="artifacts/daq", must_exist=True): ...
class EvidencePath(RelPath, under="artifacts/daq", must_exist=True): ...
class RequestPath(RelPath, under="artifacts/daq", must_exist=True): ...


class FaultClass(Enum):            # one per on-call playbook in scripts/playbooks.py
    DEADTIME_LINK = "deadtime_link"
    STUCK_TRANSITIONS = "stuck_transitions"
    HSD_LINK = "hsd_link"
    KCU_BUFFERS = "kcu_buffers"


@record
class LogBundle:
    logs: LogBundlePath
    run_number: int


@variant
class DIAGNOSED:
    cause: FaultClass          # one of four playbook names, not free text
    target: str                # the cnf segment it acts on; the check resolves and tests it
    evidence: EvidencePath     # must exist under artifacts/daq, or the step fails
    fix: str                   # the model's own words; nothing routes on them


@variant
class UNLISTED:
    summary: str               # a cause the playbooks do not cover
    evidence: EvidencePath
    suggestion: str            # for the person on call; nothing routes on it


@variant
class INCONCLUSIVE:
    checked: list[str]
    missing: list[str]


Diagnosis = DIAGNOSED | UNLISTED | INCONCLUSIVE


@variant
class APPLICABLE:
    cause: FaultClass
    target: str
    steps: list[str]           # exactly what the playbook will do
    request: RequestPath       # the steps and the checks, written out for the approver
    detail: str


@variant
class BLOCKED:
    detail: str


PlaybookCheck = APPLICABLE | BLOCKED


class Decision(Enum):
    APPROVED = "APPROVED"
    DENIED = "DENIED"


@variant
class RECOVERED:
    summary: str
    approved_by: str


@variant
class DRY_RUN:
    summary: str
    approved_by: str


@variant
class ESCALATED:
    reason: str


Outcome = RECOVERED | DRY_RUN | ESCALATED


# --- effects: names bound in inputs/commands.json and inputs/providers.json -------
daq_logs = Command("daq_logs", returns=LogBundle)
check_playbook = Command("check_playbook", returns=PlaybookCheck)
daq_recover = Command("daq_recover", returns=Outcome)
claude = Provider("claude")

diagnose = Prompt(file="prompts/diagnose.md",
                  fills={"logs": Doc[LogBundlePath], "hutch": Text, "run_number": Value[int]},
                  returns=Diagnosis)

approve = Prompt(text="TMO run {run_number}: run the {cause} playbook on {target}? The steps, the "
                      "facility's checks and the model's evidence are attached.",
                 fills={"run_number": Value[int], "cause": Value[FaultClass], "target": Text},
                 returns=Decision)


@proc(returns=HostReply[Decision])
def ask_daq_oncall(run_number: int, cause: FaultClass, target: str, request: RequestPath,
                   evidence: EvidencePath):
    # The run suspends here. `orchestrator input answer` records the decision and who made
    # it; the attached files are frozen, so if either changes before the answer, the
    # answer is refused. Unanswered for 30 minutes, the request expires.
    return ask(approve(run_number=run_number, cause=cause, target=target),
               returns=Decision, timeout_sec=1800, show=(request, evidence))


# --- the workflow ---------------------------------------------------------------
@workflow
def diagnose_and_recover(hutch: str, run_number: int, model: str) -> Outcome:
    bundle = daq_logs("python3", "scripts/daq_logs.py", "--hutch", hutch, "--run", run_number)
    verdict = claude(diagnose(logs=bundle.logs, hutch=hutch, run_number=run_number),
                     model=model, effort="high", timeout_sec=900)
    return match(
        verdict,
        INCONCLUSIVE=lambda i: ESCALATED(reason="the model could not determine a cause"),
        UNLISTED=lambda u: ESCALATED(reason="no playbook covers the cause the model found"),
        DIAGNOSED=lambda d: match(
            check_playbook("python3", "scripts/check_playbook.py", "--cause", d.cause, "--target", d.target,
                           "--evidence", d.evidence, "--bundle", bundle.logs),
            BLOCKED=lambda b: ESCALATED(reason="the proposed playbook does not apply"),
            APPLICABLE=lambda p: match(
                ask_daq_oncall(run_number, p.cause, p.target, p.request, d.evidence),
                ANSWERED=lambda a: when(
                    a.value == Decision.APPROVED,
                    then=lambda: daq_recover("python3", "scripts/daq_recover.py",
                                             "--hutch", hutch, "--run", run_number, "--cause", p.cause,
                                             "--target", p.target, "--approved-by", a.by, "--dry-run"),
                    else_=lambda: ESCALATED(reason="DAQ on-call denied the recovery")),
                CANCELLED=lambda c: ESCALATED(reason="the approval request was cancelled"),
                EXPIRED=lambda e: ESCALATED(reason="nobody answered the approval request in time"),
            ),
        ),
    )
