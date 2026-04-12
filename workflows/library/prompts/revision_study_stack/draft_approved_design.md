Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `revision_design_seed` and `revision_context` artifacts before acting.

Create an approved revision-study design candidate from the seed design. Treat the seed design as immutable provenance: do not edit it in place.

The approved design should be specific enough to support implementation planning. Include:
- reviewer issue and manuscript scope being addressed
- source data, scripts, figures, tables, and manuscript files likely to be touched
- dependency or provenance decisions that must be made before execution
- pivot criteria for narrowing claims or switching to text-only response if the study cannot be made clean
- required final assets, including manuscript, changelog, checklist, metrics, figure, table, and manifest updates where relevant
- verification commands and inspection checks

For the output contract's `approved_design_path`, read the path recorded in that pointer file and write the approved design document there.
