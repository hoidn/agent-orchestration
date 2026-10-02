; Experimental dynamic source; run through the adjacent README, not the public CLI.
(dynamic-core
  (:budget 200)
  (:inputs (goal String) (rubric String) (target_doc String))
  (:result Value)
  (:effects review annotate)

  (define (identity value) value)
  (define (apply-one callback value) (callback value))
  (define (make-annotator goal rubric)
    (fn (reviewed)
      (fn (candidate)
        (effect annotate
          (record
            (feedback
              (string/concat goal " | " rubric " | "
                (field reviewed "return__feedback") " | "
                (field candidate "title"))))))))

  (run
    (let* ((seed (identity (record (title "draft"))))
           (count (identity 1))
           (reviewed
             (effect review
               (record (goal goal) (rubric rubric) (target_doc target_doc))))
           (next
             (if (field reviewed "return__approved")
               (fn (candidate) candidate)
               ((make-annotator goal rubric) reviewed)))
           (callbacks (record (next next))))
      (apply-one (field callbacks "next") seed))))
