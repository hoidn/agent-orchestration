(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.14")
  (defunion DuplicateVariants
    (COMPLETED
      (status String))
    (COMPLETED
      (status Int))))
