# Workflow Lisp L4 Editor Lifecycle Probe

- **Status:** completed design evidence
- **Observed:** 2026-07-28
- **Editor:** Neovim `0.12.0-dev-703+g66f02ee1fe`
- **Server:** production `python -m orchestrator.lsp` at `3d558903`
- **Authority:** evidence for L4 design selection only; not runtime authority

## Question

Stage L4 must decide whether an accepted diagnostic should remain published
while its compile entry is dirty or pending, and whether a generic editor
client actually exposes LSP work-done progress. The governing roadmap forbids
assuming UI behavior from protocol capability names alone.

## Diagnostic Observation

A headless Neovim client opened the real invalid fixture
`tests/fixtures/workflow_lisp/modules/invalid/path_mismatch/neurips/bad.orc`
through the production stdio server. After the first diagnostic was visible,
the client replaced the first buffer line without saving and waited for the
resulting `didChange`.

Observed result:

```json
{
  "accepted_generation_in_client_diagnostic": 1,
  "diagnostic_count_after_dirty": 1,
  "diagnostic_count_before_dirty": 1,
  "editor": "nvim",
  "same_visible_diagnostic": true,
  "work_done_progress_advertised": true
}
```

Neovim retained the same visible diagnostic after the unsaved edit. The
server's `accepted_generation=1` survived in the client-side diagnostic data,
but it did not create a visible freshness distinction. Retaining the current
publication therefore leaves a stale squiggle on text the compiler did not
analyze.

The same client capabilities advertised diagnostic data and the standard
`Unnecessary` / `Deprecated` tags, but did not advertise
`publishDiagnostics.versionSupport`. A pushed diagnostic version is therefore
not a portable freshness treatment for this observed client, and the roadmap
separately forbids using `Unnecessary` as a stale marker.

The probe was read-only: the edit existed only in the editor buffer, the
fixture bytes were unchanged, and the server created no workspace state.

## Progress Observation

A minimal pygls probe server used the same transport dependency as production.
After Neovim advertised `window.workDoneProgress=true`, the server completed
`window/workDoneProgress/create` and sent one `$/progress` begin, report, and
end sequence.

Observed result:

```json
{
  "editor": "nvim",
  "final_status": "",
  "progress_events": ["begin", "report", "end"],
  "status_samples": [
    "Workflow Lisp: Compiling",
    "Workflow Lisp: Checking current sources",
    "Workflow Lisp: Compilation complete"
  ],
  "work_done_progress_advertised": true
}
```

The editor surfaced each lifecycle phase and cleared its status after `end`.
This proves the generic protocol surface is visible in at least one supported
client without an editor extension. It does not prove identical presentation
in every client.

## Design Consequence

The evidence supports:

1. hiding non-current diagnostic contributions from publication while
   retaining their ownership internally, because generation metadata alone is
   not a visible freshness treatment; and
2. capability-gated, balanced work-done progress around one serialized
   compile-pump busy interval, because a real generic client advertises and
   displays that lifecycle.

The probe does not authorize unsaved-buffer compilation, a diagnostic tag
repurposing, progress percentages, telemetry, or editor-specific integration.
