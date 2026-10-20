"""Private renames preserve module diversity; labels and routing retain meaning."""

import re

import pytest

from experiments.orc_structural_search import records
from experiments.orc_structural_search.readout import diversity


SOURCE = '''
(defproc helper ((x String)) -> String
  (provider-result providers.coder :prompt prompts.ask :inputs (x) :returns String))
(defproc other ((x String)) -> String x)
(defworkflow run ((x String)) -> String (helper x))
'''


def rename(source, old, new):
    return re.sub(rf"(?<![\w:-]){old}(?![\w-])", new, source)


def metrics(source, definitions):
    options = dict(definitions=definitions, module_entry="direct::run")
    return records.skeleton_hash(source, **options), records.provider_allocation(source, **options)


def test_module_private_callable_rename_is_terminal_only_and_target_change_is_distinct():
    parent = metrics(SOURCE, ("run", "helper", "other"))
    child = metrics(rename(SOURCE, "helper", "renamed"), ("run", "renamed", "other"))
    assert child == parent
    assert metrics(SOURCE.replace("(helper x)", "(other x)"), ("run", "helper", "other"))[0] != parent[0]
    row = dict(skeleton=child[0], parent_skeleton=parent[0], provider_allocation=child[1],
               parent_provider_allocation=parent[1])
    assert diversity([row])["terminal_only_share"] == 1
    swapped = metrics(SOURCE.replace("providers.coder", "providers.reviewer"), ("run", "helper", "other"))
    assert swapped[0] == parent[0]
    assert swapped[1] != parent[1]


TYPE_SOURCE = '''
(defrecord Review (text String))
(defunion Decision (ACCEPT (review List[direct/Review])))
(defenum Color RED BLUE)
(defproc helper ((Review List[Review]) (color Color)) -> Decision
  (variant Decision ACCEPT :review Review))
(defworkflow run ((x String)) -> List[Review]
  (let* ((Review (record Review :text x)) (color Color.RED))
    (list (record direct/Review :text Review.text))))
'''


def test_module_private_types_normalize_composites_constructors_and_enum_qualifiers():
    before = metrics(TYPE_SOURCE, ("run", "Review", "Decision", "Color", "helper"))
    after = TYPE_SOURCE.replace("Review", "Assessment").replace("Decision", "Verdict").replace("Color", "Shade")
    assert metrics(after, ("run", "Assessment", "Verdict", "Shade", "helper")) == before


@pytest.mark.parametrize("before,after", [("text", "body"), ("ACCEPT", "PASS"), ("RED", "GREEN")])
def test_module_preserves_field_variant_and_enum_member_labels(before, after):
    assert metrics(TYPE_SOURCE.replace(before, after), ("run", "Review", "Decision", "Color", "helper"))[0] != metrics(
        TYPE_SOURCE, ("run", "Review", "Decision", "Color", "helper"))[0]


def test_module_type_value_and_label_scopes_do_not_alias():
    source = '''(defrecord Review (Review String))
      (defproc helper :forall (Review) ((Review Review))
        :where ((Review has-field Review String)) -> Review Review)
      (defworkflow run ((Review Review)) -> Review (record Review :Review Review.Review))'''
    renamed = source.replace("(defrecord Review", "(defrecord Assessment").replace(
        "(defworkflow run ((Review Review)) -> Review (record Review",
        "(defworkflow run ((Review Assessment)) -> Assessment (record Assessment")
    assert metrics(source, ("run", "Review", "helper")) == metrics(renamed, ("run", "Assessment", "helper"))
    assert metrics(source.replace("(Review String)", "(label String)"), ("run", "Review", "helper"))[0] != metrics(
        source, ("run", "Review", "helper"))[0]


def test_module_refs_follow_private_names_and_local_proc_shadowing():
    source = SOURCE.replace("(helper x)", "(let-proc ((helper (x) x)) (proc-ref helper))")
    source = source.replace("String x)", "String (workflow-ref worker))") + "(defworkflow worker () -> String \"x\")"
    assert metrics(source, ("run", "helper", "other", "worker")) == metrics(
        rename(rename(source, "helper", "ask"), "worker", "work"), ("run", "ask", "other", "work"))


def test_module_prompt_addition_and_rename_do_not_shift_declaration_ordinals():
    parent = metrics(SOURCE, ("run", "helper", "other"))
    source = '(defprompt ask () -> String "ask")' + SOURCE
    assert metrics(source, ("run", "ask", "helper", "other")) == parent
    assert metrics(source.replace("defprompt ask", "defprompt question"), ("run", "question", "helper", "other")) == parent


def test_module_type_renames_cover_return_guidance_and_callable_types():
    source = '''(defrecord Review (text String))
      (defproc helper ((x ProcRef[Review->List[Review]])) -> (result Review :description "Review")
        (provider-result providers.coder :prompt prompts.ask :returns (result Review :description "Review")))
      (defworkflow run () -> String "x")'''
    assert metrics(source, ("run", "Review", "helper")) == metrics(
        source.replace("Review", "Assessment"), ("run", "Assessment", "helper"))


def test_module_labels_and_lexical_values_can_share_a_private_callable_name():
    source = '''(defproc helper ((x String)) -> String x)
      (defrecord Box (helper String))
      (defunion Choice (helper))
      (defenum Color helper)
      (defworkflow run ((helper String)) -> String helper)'''
    assert metrics(source, ("run", "helper", "Box", "Choice", "Color")) == metrics(
        source.replace("defproc helper", "defproc ask"), ("run", "ask", "Box", "Choice", "Color"))


def test_module_proc_ref_uses_procedure_scope_instead_of_value_scope():
    source = '''(defproc helper () -> String "x")
      (defworkflow run ((helper String)) -> ProcRef[()->String] (proc-ref helper))'''
    renamed = source.replace("defproc helper", "defproc ask").replace("proc-ref helper", "proc-ref ask")
    assert metrics(source, ("run", "helper")) == metrics(renamed, ("run", "ask"))


def test_legacy_metrics_keep_authored_declaration_names():
    assert records.skeleton_hash(SOURCE, definitions=("run", "helper", "other")) != records.skeleton_hash(
        rename(SOURCE, "helper", "renamed"), definitions=("run", "renamed", "other"))
    assert tuple(records.provider_allocation(SOURCE, definitions=("run", "helper", "other"))) == ("run", "helper", "other")
    source = '(defproc helper ((x String)) -> String x) (defworkflow run ((x String)) -> String (helper x))'
    assert records.skeleton_hash(source, definitions=("run", "helper")) == (
        "91b87a1b702be1902e435911d52a78ccc334b4a5102ae764697bee3cd9e8acf2")
