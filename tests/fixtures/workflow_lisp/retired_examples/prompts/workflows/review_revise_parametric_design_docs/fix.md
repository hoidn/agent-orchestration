Take the role of the design-doc reviser for the parametric Workflow Lisp review
loop design set.

Revise the provided design docs to address the review findings. Keep the edits
scoped to consistency/correctness and architectural soundness for the
review/revise stdlib integration, structural parametric constraints, and
compile-time parametric specialization designs.

Preserve the intended architecture unless the review identifies a concrete
technical flaw:

- reusable review/revise behavior should come from ordinary imported `.orc`
  stdlib definitions plus generic language machinery, not review-loop-specific
  compiler semantics;
- type parameters, ProcRefs, provider refs, prompt refs, and specialization
  details remain compile-time only;
- structural constraints should improve ergonomics while reducing compiler
  special casing and maintaining proof-gated union behavior;
- reports and summaries remain views, while typed state and validated artifacts
  remain semantic authority.

Write concise revisions in place and produce the requested progress/revision
report through the output contract.
