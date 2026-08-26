---
name: alpha
description: First fanout worker that implements the plan
model: "openai-codex/gpt-5.6-sol"
tools: [read, grep, glob, edit, write]
spawns: [beta]
---
Implement the accepted plan in the workspace.

A code example stays legal: `npm install @types/node` inside backticks.

Fenced examples stay legal too:

```text
@../escape.md must not be expanded here
```

Email-like mid-token @ stays legal: user@example.com
