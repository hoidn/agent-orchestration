(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.40")
  (defmodule std/host)
  (export HostReply)
  (defunion HostReply :forall (A)
    (ANSWERED (value A) (by String))
    (CANCELLED (by String))
    (EXPIRED)))
