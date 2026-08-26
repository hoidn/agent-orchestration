---
name: alpha
description: Peer-team agent that drives the hub exchange
model: "openai-codex/gpt-5.6-sol"
tools: [read, grep, glob, hub]
spawns: [beta]
---
Send beta one concrete request with `hub send` and `await=true`; incorporate the returned reply, then make no further hub calls. Never wait on a stopped peer or invent a `replyTo` value.

A code example stays legal: `npm install @types/node` inside backticks.

Fenced examples stay legal too:

```text
@../escape.md must not be expanded here
```

Email-like mid-token @ stays legal: user@example.com
