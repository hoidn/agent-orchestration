# Project Audit Working Notes, 2026-11-11

**Status: Historical record (captured evidence), not a contract.** These are
the working notes of the 2026-11-11 project audit: four independent read-only
reviewers, each covering one slice, at commit `bb63b03b`. They are copied
unchanged from the session that produced them. They informed the
[current roadmap](../../plans/2026-11-11-orc-usable-pipelines-then-evolution-roadmap.md),
which owns the decisions; specs and accepted designs own behavior. Do not copy
from these notes as guidance.

Scratch paths inside the notes (under `/tmp`) point at probe files from the
audit session; they are not durable and may no longer exist. Figures the notes
quote from reports are owned by those reports; where they disagree, the report
wins (see [what the experiments established](../2026-11-11-what-the-experiments-established.md)).

| File | Slice |
| --- | --- |
| [core.md](core.md) | Core implementation under `orchestrator/`, judged from code and provider-free probes. |
| [roadmaps.md](roadmaps.md) | Language and runtime roadmaps and pending designs. |
| [research.md](research.md) | Research and experiment track: evidence ledger, yield, methodology, directions. |
| [authoring.md](authoring.md) | Authoring surface: examples, stdlib and guides, with provider-free probes. |
