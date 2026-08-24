---
name: beta
description: Second fanout worker that reviews the plan
model: "x-ai/grok-code-fast:high"
tools: [read, grep, glob]
spawns: [alpha]
---
Review the implemented plan and report findings.

A code example stays legal: `npm install @types/node` inside backticks.

Fenced examples stay legal too:

```text
@../escape.md must not be expanded here
```

Email-like mid-token @ stays legal: user@example.com
