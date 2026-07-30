(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.18")
  (defmodule pure_result_replay_effect_barrier)
  (export orchestrate)
  (defrecord SeedProjection
    (value Int))
  (defrecord EffectResult
    (delta Int)
    (use-effect Bool))
  (defrecord DerivedValue
    (seed-value Int)
    (effect-value Int))
  (defrecord ReplayResult
    (seed-value Int)
    (effect-value Int)
    (finished Bool))
  (defworkflow orchestrate
    ((seed Int)
     (enabled Bool))
    -> ReplayResult
    (let* ((a
             (if enabled
               (record SeedProjection
                 :value seed)
               (record SeedProjection
                 :value 0)))
           (e1
             (command-result count-e1
               :argv ("python" "scripts/count_e1.py")
               :returns EffectResult))
           (b
             (if e1.use-effect
               (record DerivedValue
                 :seed-value a.value
                 :effect-value e1.delta)
               (record DerivedValue
                 :seed-value a.value
                 :effect-value 0)))
           (e2
             (command-result finish-e2
               :argv ("python" "scripts/finish_e2.py")
               :returns Bool)))
      (record ReplayResult
        :seed-value b.seed-value
        :effect-value b.effect-value
        :finished e2))))
