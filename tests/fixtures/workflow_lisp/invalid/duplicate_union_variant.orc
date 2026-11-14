(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defunion DuplicateVariants
    (COMPLETED
      (status String))
    (COMPLETED
      (status Int))))
