(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.17")
  (defmodule real_peer_group_three)
  (export orchestrate)

  (defrecord RealPeerGroupResult
    (sender String)
    (received String)
    (witness Bool))

  (defworkflow orchestrate () -> RealPeerGroupResult
    (with-live-provider-peers
      ((sender
         (provider-result providers.sender
           :prompt prompts.sender
           :inputs ()
           :timeout-sec 300
           :returns String))
       (receiver
         (provider-result providers.receiver
           :prompt prompts.receiver
           :inputs ()
           :timeout-sec 300
           :returns String))
       (witness
         (provider-result providers.witness
           :prompt prompts.witness
           :inputs ()
           :timeout-sec 300
           :returns Bool)))
      (record RealPeerGroupResult
        :sender sender
        :received receiver
        :witness witness))))
