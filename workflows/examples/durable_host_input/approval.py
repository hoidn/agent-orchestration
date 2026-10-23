"""Native Python authoring for the same durable approval flow as approval.orc."""

from enum import Enum

from orchestrator.py import (
    Command, Doc, HostReply, Prompt, Provider, RelPath, Text, Value,
    ask, match, proc, record, when, workflow,
)

TARGET = "2.40"


class Evidence(RelPath, under="artifacts", must_exist=True):
    pass


class Guide(RelPath, under="docs", must_exist=True):
    pass


class Cause(Enum):
    BROKEN_RECORD = "BROKEN_RECORD"
    MISSING_METADATA = "MISSING_METADATA"


class Approval(Enum):
    APPROVED = "APPROVED"
    DENIED = "DENIED"


@record
class Diagnosis:
    cause: Cause
    summary: str


@record
class Verification:
    cause: Cause
    summary: str
    evidence: Evidence


@record
class Outcome:
    status: str
    reason: str
    cause: Cause
    diagnosis: str


diagnose_prompt = Prompt(
    text="Diagnose this recovery input: {problem}",
    fills={"problem": Text},
    returns=Diagnosis,
)
approval_prompt = Prompt(
    text="A local verification command checked cause {cause}: {summary}",
    fills={"cause": Value[Cause], "summary": Text, "guide": Doc[Guide]},
    returns=Approval,
)

diagnoser = Provider("providers.diagnose")
verify = Command("verify", returns=Verification)
action = Command("action", returns=Outcome)


@proc(returns=HostReply[Approval])
def approval(cause: Cause, summary: str, evidence: Evidence, guide: Guide):
    return ask(
        approval_prompt(cause=cause, summary=summary, guide=guide),
        returns=Approval,
        timeout_sec=3600,
        show=(evidence,),
    )


@workflow(returns=Outcome)
def recover(problem: str, report: Evidence, guide: Guide):
    diagnosis = diagnoser(
        diagnose_prompt(problem=problem), model="local-stub", effort="low"
    )
    checked = verify("python", "action.py", "verify", diagnosis.cause,
                     diagnosis.summary, report)
    reply = approval(checked.cause, checked.summary, checked.evidence, guide)
    return match(
        reply,
        ANSWERED=lambda answer: when(
            answer.value == Approval.APPROVED,
            then=lambda: action(
                "python", "action.py", "repair", checked.cause, checked.summary
            ),
            else_=lambda: action(
                "python", "action.py", "escalate", "denied", checked.cause, checked.summary
            ),
        ),
        CANCELLED=lambda _: action(
            "python", "action.py", "escalate", "cancelled", checked.cause, checked.summary
        ),
        EXPIRED=lambda _: action(
            "python", "action.py", "escalate", "expired", checked.cause, checked.summary
        ),
    )
