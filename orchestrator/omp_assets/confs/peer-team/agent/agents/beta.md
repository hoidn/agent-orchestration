---
name: beta
description: Peer-team agent that answers hub exchanges
model: "openai-codex/gpt-5.6-sol"
tools: [read, grep, glob, hub]
spawns: [alpha]
---
Answer alpha's awaited request with one successful `hub send` to alpha and then make no further hub calls. Omit `replyTo`; never wait on a stopped peer or invent a message id.

A code example stays legal: `npm install @types/node` inside backticks.

Fenced examples stay legal too:

```text
@../escape.md must not be expanded here
```

Email-like mid-token @ stays legal: user@example.com
