(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defmodule neurips/macros)
  (import neurips/types :only (WorkReport ImplementationSummary))
  (export defworkflow-alias)
  (defmacro defworkflow-alias (name)
    (defworkflow name
      ((report_path WorkReport))
      -> ImplementationSummary
      (provider-result providers.execute
        :prompt prompts.implementation.execute
        :inputs (report_path)
        :returns ImplementationSummary))))
