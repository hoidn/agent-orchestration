(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defworkflow guidance-example-effectful ()
    -> (result Bool :example
         (command-result forbidden-example
           :argv ("python" "scripts/forbidden.py")
           :returns Bool))
    true))
