(workflow-lisp (:language "0.1") (:target-dsl "2.40")
  (defmodule prov) (export run)
  (defrecord Review (ok Bool))
  (defworkflow run ((n Int :default 0)) -> Int
    (let* ((s1 (command-result step :argv ("./t.py" "s1" n) :returns Int))
           (p (provider-result providers.review :prompt prompts.base :inputs (s1)
                :model "chosen-model" :effort "low" :returns Review))
           (s3 (command-result step :argv ("./t.py" "s3" s1) :returns Int)))
      s3)))
