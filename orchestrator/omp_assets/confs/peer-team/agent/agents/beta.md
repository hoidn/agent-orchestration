---
name: beta
description: Peer-team agent that answers hub exchanges
model: "x-ai/grok-code-fast:high"
tools: [read, grep, glob, hub]
spawns: [alpha]
---
Answer alpha's hub exchanges and confirm the shared outcome.

A code example stays legal: `npm install @types/node` inside backticks.

Fenced examples stay legal too:

```text
@../escape.md must not be expanded here
```

Email-like mid-token @ stays legal: user@example.com
