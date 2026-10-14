"""Literal reader DTOs captured once from baseline 23eb9c97.

Projection metadata and IR node identity/order were captured from real bundles.
Unused execution configs, transfers, contracts, compiler-only trees/plans and
authored surface steps are omitted. These fixtures cannot load or execute source.
"""

from pathlib import Path
from types import MappingProxyType

from orchestrator.workflow.executable_ir import (
    CallBoundaryNode,
    ExecutableNodeKind,
    ExecutableWorkflow,
    FinalizationStepNode,
    ForEachNode,
    IfBranchMarkerNode,
    IfJoinNode,
    LeafExecutableNode,
    MatchCaseMarkerNode,
    MatchJoinNode,
    RepeatUntilFrameNode,
    WorkflowRegion,
)

from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle

from orchestrator.workflow.state_projection import (
    CallBoundaryProjection,
    CompatibilityNodeProjection,
    CompatibilityStepDefinition,
    IterationStepKeyProjection,
    StructuredSelectionProjection,
    WorkflowStateProjection,
)

from orchestrator.workflow.surface_ast import SurfaceWorkflow, WorkflowProvenance

HISTORICAL_OBSERVABILITY_BUNDLES = {
    'obs-test': LoadedWorkflowBundle(
        surface=SurfaceWorkflow(
            version='1.3',
            name='obs-test',
            steps=(),
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/obs-test.orc'),
                source_root=Path('historical'),
            ),
        ),
        core_workflow_ast=None,
        semantic_ir=None,
        ir=ExecutableWorkflow(
            schema_version='workflow_executable_ir.v1',
            version='1.3',
            name='obs-test',
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/obs-test.orc'),
                source_root=Path('historical'),
            ),
            body_region=('root.prep', 'root.draftplan'),
            finalization_region=(),
            finalization_entry_node_id=None,
            nodes=MappingProxyType(
                {
                    'root.prep': LeafExecutableNode(
                        node_id='root.prep',
                        step_id='root.prep',
                        presentation_name='Prep',
                        kind=ExecutableNodeKind.COMMAND,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'prep'),
                    ),
                    'root.draftplan': LeafExecutableNode(
                        node_id='root.draftplan',
                        step_id='root.draftplan',
                        presentation_name='DraftPlan',
                        kind=ExecutableNodeKind.PROVIDER,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'draftplan'),
                    ),
                },
            ),
        ),
        projection=WorkflowStateProjection(
            entries_by_node_id=MappingProxyType(
                {
                    'root.prep': CompatibilityNodeProjection(
                        node_id='root.prep',
                        step_id='root.prep',
                        presentation_key='Prep',
                        display_name='Prep',
                        region=WorkflowRegion.BODY,
                        compatibility_index=0,
                        step_definition=CompatibilityStepDefinition(
                            report_kind='command',
                            command=('bash', '-lc', 'echo prep'),
                            consumes=(
                                MappingProxyType(
                                    {
                                        'artifact': 'plan_doc',
                                        'as': 'plan',
                                    },
                                ),
                            ),
                        ),
                    ),
                    'root.draftplan': CompatibilityNodeProjection(
                        node_id='root.draftplan',
                        step_id='root.draftplan',
                        presentation_key='DraftPlan',
                        display_name='DraftPlan',
                        region=WorkflowRegion.BODY,
                        compatibility_index=1,
                        step_definition=CompatibilityStepDefinition(
                            report_kind='provider',
                            provider='codex',
                            expected_outputs=(
                                MappingProxyType(
                                    {
                                        'name': 'plan_path',
                                        'path': 'state/plan_path.txt',
                                        'type': 'relpath',
                                    },
                                ),
                            ),
                        ),
                    ),
                },
            ),
            node_id_by_compatibility_index=MappingProxyType(
                {
                    0: 'root.prep',
                    1: 'root.draftplan',
                },
            ),
            compatibility_index_by_node_id=MappingProxyType(
                {
                    'root.prep': 0,
                    'root.draftplan': 1,
                },
            ),
            presentation_key_by_node_id=MappingProxyType(
                {
                    'root.prep': 'Prep',
                    'root.draftplan': 'DraftPlan',
                },
            ),
            node_id_by_step_id=MappingProxyType(
                {
                    'root.prep': 'root.prep',
                    'root.draftplan': 'root.draftplan',
                },
            ),
        ),
        runtime_plan=None,
        imports=MappingProxyType({}),
        provenance=WorkflowProvenance(
            workflow_path=Path('historical/obs-test.orc'),
            source_root=Path('historical'),
        ),
    ),
    'obs-loop': LoadedWorkflowBundle(
        surface=SurfaceWorkflow(
            version='1.3',
            name='obs-loop',
            steps=(),
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/obs-loop.orc'),
                source_root=Path('historical'),
            ),
        ),
        core_workflow_ast=None,
        semantic_ir=None,
        ir=ExecutableWorkflow(
            schema_version='workflow_executable_ir.v1',
            version='1.3',
            name='obs-loop',
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/obs-loop.orc'),
                source_root=Path('historical'),
            ),
            body_region=('root.loop',),
            finalization_region=(),
            finalization_entry_node_id=None,
            nodes=MappingProxyType(
                {
                    'root.loop.inner': LeafExecutableNode(
                        node_id='root.loop.inner',
                        step_id='root.loop.inner',
                        presentation_name='Inner',
                        kind=ExecutableNodeKind.COMMAND,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'loop', 'inner'),
                    ),
                    'root.loop': ForEachNode(
                        node_id='root.loop',
                        step_id='root.loop',
                        presentation_name='Loop',
                        kind=ExecutableNodeKind.FOR_EACH,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'loop'),
                    ),
                },
            ),
        ),
        projection=WorkflowStateProjection(
            entries_by_node_id=MappingProxyType(
                {
                    'root.loop.inner': CompatibilityNodeProjection(
                        node_id='root.loop.inner',
                        step_id='root.loop.inner',
                        presentation_key='Inner',
                        display_name='Inner',
                        region=WorkflowRegion.BODY,
                        step_definition=CompatibilityStepDefinition(
                            report_kind='command',
                            command=('bash', '-lc', 'echo inner'),
                        ),
                    ),
                    'root.loop': CompatibilityNodeProjection(
                        node_id='root.loop',
                        step_id='root.loop',
                        presentation_key='Loop',
                        display_name='Loop',
                        region=WorkflowRegion.BODY,
                        compatibility_index=0,
                        step_definition=CompatibilityStepDefinition(report_kind='for_each'),
                    ),
                },
            ),
            node_id_by_compatibility_index=MappingProxyType(
                {
                    0: 'root.loop',
                },
            ),
            compatibility_index_by_node_id=MappingProxyType(
                {
                    'root.loop': 0,
                },
            ),
            presentation_key_by_node_id=MappingProxyType(
                {
                    'root.loop.inner': 'Inner',
                    'root.loop': 'Loop',
                },
            ),
            node_id_by_step_id=MappingProxyType(
                {
                    'root.loop.inner': 'root.loop.inner',
                    'root.loop': 'root.loop',
                },
            ),
            for_each_nodes=MappingProxyType(
                {
                    'root.loop': IterationStepKeyProjection(
                        node_id='root.loop',
                        frame_key='Loop',
                        nested_presentation_keys=MappingProxyType(
                            {
                                'root.loop.inner': 'Inner',
                            },
                        ),
                        nested_step_id_suffixes=MappingProxyType(
                            {
                                'root.loop.inner': 'inner',
                            },
                        ),
                    ),
                },
            ),
        ),
        runtime_plan=None,
        imports=MappingProxyType({}),
        provenance=WorkflowProvenance(
            workflow_path=Path('historical/obs-loop.orc'),
            source_root=Path('historical'),
        ),
    ),
    'obs-call': LoadedWorkflowBundle(
        surface=SurfaceWorkflow(
            version='2.5',
            name='obs-call',
            steps=(),
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/obs-call.orc'),
                source_root=Path('historical'),
            ),
        ),
        core_workflow_ast=None,
        semantic_ir=None,
        ir=ExecutableWorkflow(
            schema_version='workflow_executable_ir.v1',
            version='2.5',
            name='obs-call',
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/obs-call.orc'),
                source_root=Path('historical'),
            ),
            body_region=('root.run_review_loop',),
            finalization_region=(),
            finalization_entry_node_id=None,
            nodes=MappingProxyType(
                {
                    'root.run_review_loop': CallBoundaryNode(
                        node_id='root.run_review_loop',
                        step_id='root.run_review_loop',
                        presentation_name='RunReviewLoop',
                        kind=ExecutableNodeKind.CALL_BOUNDARY,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'run_review_loop'),
                    ),
                },
            ),
        ),
        projection=WorkflowStateProjection(
            entries_by_node_id=MappingProxyType(
                {
                    'root.run_review_loop': CompatibilityNodeProjection(
                        node_id='root.run_review_loop',
                        step_id='root.run_review_loop',
                        presentation_key='RunReviewLoop',
                        display_name='RunReviewLoop',
                        region=WorkflowRegion.BODY,
                        compatibility_index=0,
                        step_definition=CompatibilityStepDefinition(report_kind='call'),
                    ),
                },
            ),
            node_id_by_compatibility_index=MappingProxyType(
                {
                    0: 'root.run_review_loop',
                },
            ),
            compatibility_index_by_node_id=MappingProxyType(
                {
                    'root.run_review_loop': 0,
                },
            ),
            presentation_key_by_node_id=MappingProxyType(
                {
                    'root.run_review_loop': 'RunReviewLoop',
                },
            ),
            node_id_by_step_id=MappingProxyType(
                {
                    'root.run_review_loop': 'root.run_review_loop',
                },
            ),
            call_boundaries=MappingProxyType(
                {
                    'root.run_review_loop': CallBoundaryProjection(
                        node_id='root.run_review_loop',
                        presentation_key='RunReviewLoop',
                        step_id='root.run_review_loop',
                        import_alias='review_loop',
                    ),
                },
            ),
        ),
        runtime_plan=None,
        imports=MappingProxyType({}),
        provenance=WorkflowProvenance(
            workflow_path=Path('historical/obs-call.orc'),
            source_root=Path('historical'),
        ),
    ),
    'obs-repeat': LoadedWorkflowBundle(
        surface=SurfaceWorkflow(
            version='2.7',
            name='obs-repeat',
            steps=(),
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/obs-repeat.orc'),
                source_root=Path('historical'),
            ),
        ),
        core_workflow_ast=None,
        semantic_ir=None,
        ir=ExecutableWorkflow(
            schema_version='workflow_executable_ir.v1',
            version='2.7',
            name='obs-repeat',
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/obs-repeat.orc'),
                source_root=Path('historical'),
            ),
            body_region=('root.review_loop',),
            finalization_region=(),
            finalization_entry_node_id=None,
            nodes=MappingProxyType(
                {
                    'root.review_loop.iteration_body.writedecision': LeafExecutableNode(
                        node_id='root.review_loop.iteration_body.writedecision',
                        step_id='root.review_loop.iteration_body.writedecision',
                        presentation_name='WriteDecision',
                        kind=ExecutableNodeKind.SET_SCALAR,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'review_loop', 'iteration_body', 'writedecision'),
                    ),
                    'root.review_loop': RepeatUntilFrameNode(
                        node_id='root.review_loop',
                        step_id='root.review_loop',
                        presentation_name='ReviewLoop',
                        kind=ExecutableNodeKind.REPEAT_UNTIL_FRAME,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'review_loop'),
                    ),
                },
            ),
        ),
        projection=WorkflowStateProjection(
            entries_by_node_id=MappingProxyType(
                {
                    'root.review_loop.iteration_body.writedecision': CompatibilityNodeProjection(
                        node_id='root.review_loop.iteration_body.writedecision',
                        step_id='root.review_loop.iteration_body.writedecision',
                        presentation_key='WriteDecision',
                        display_name='WriteDecision',
                        region=WorkflowRegion.BODY,
                        step_definition=CompatibilityStepDefinition(report_kind='set_scalar'),
                    ),
                    'root.review_loop': CompatibilityNodeProjection(
                        node_id='root.review_loop',
                        step_id='root.review_loop',
                        presentation_key='ReviewLoop',
                        display_name='ReviewLoop',
                        region=WorkflowRegion.BODY,
                        compatibility_index=0,
                        step_definition=CompatibilityStepDefinition(report_kind='repeat_until'),
                    ),
                },
            ),
            node_id_by_compatibility_index=MappingProxyType(
                {
                    0: 'root.review_loop',
                },
            ),
            compatibility_index_by_node_id=MappingProxyType(
                {
                    'root.review_loop': 0,
                },
            ),
            presentation_key_by_node_id=MappingProxyType(
                {
                    'root.review_loop.iteration_body.writedecision': 'WriteDecision',
                    'root.review_loop': 'ReviewLoop',
                },
            ),
            node_id_by_step_id=MappingProxyType(
                {
                    'root.review_loop.iteration_body.writedecision': 'root.review_loop.iteration_body.writedecision',
                    'root.review_loop': 'root.review_loop',
                },
            ),
            repeat_until_nodes=MappingProxyType(
                {
                    'root.review_loop': IterationStepKeyProjection(
                        node_id='root.review_loop',
                        frame_key='ReviewLoop',
                        nested_presentation_keys=MappingProxyType(
                            {
                                'root.review_loop.iteration_body.writedecision': 'WriteDecision',
                            },
                        ),
                        nested_step_id_suffixes=MappingProxyType(
                            {
                                'root.review_loop.iteration_body.writedecision': 'iteration_body.writedecision',
                            },
                        ),
                        max_iterations=4,
                    ),
                },
            ),
        ),
        runtime_plan=None,
        imports=MappingProxyType({}),
        provenance=WorkflowProvenance(
            workflow_path=Path('historical/obs-repeat.orc'),
            source_root=Path('historical'),
        ),
    ),
    'obs-repeat-progress': LoadedWorkflowBundle(
        surface=SurfaceWorkflow(
            version='2.7',
            name='obs-repeat-progress',
            steps=(),
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/obs-repeat-progress.orc'),
                source_root=Path('historical'),
            ),
        ),
        core_workflow_ast=None,
        semantic_ir=None,
        ir=ExecutableWorkflow(
            schema_version='workflow_executable_ir.v1',
            version='2.7',
            name='obs-repeat-progress',
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/obs-repeat-progress.orc'),
                source_root=Path('historical'),
            ),
            body_region=('root.review_loop',),
            finalization_region=(),
            finalization_entry_node_id=None,
            nodes=MappingProxyType(
                {
                    'root.review_loop.iteration_body.writedecision': LeafExecutableNode(
                        node_id='root.review_loop.iteration_body.writedecision',
                        step_id='root.review_loop.iteration_body.writedecision',
                        presentation_name='WriteDecision',
                        kind=ExecutableNodeKind.SET_SCALAR,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'review_loop', 'iteration_body', 'writedecision'),
                    ),
                    'root.review_loop': RepeatUntilFrameNode(
                        node_id='root.review_loop',
                        step_id='root.review_loop',
                        presentation_name='ReviewLoop',
                        kind=ExecutableNodeKind.REPEAT_UNTIL_FRAME,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'review_loop'),
                    ),
                },
            ),
        ),
        projection=WorkflowStateProjection(
            entries_by_node_id=MappingProxyType(
                {
                    'root.review_loop.iteration_body.writedecision': CompatibilityNodeProjection(
                        node_id='root.review_loop.iteration_body.writedecision',
                        step_id='root.review_loop.iteration_body.writedecision',
                        presentation_key='WriteDecision',
                        display_name='WriteDecision',
                        region=WorkflowRegion.BODY,
                        step_definition=CompatibilityStepDefinition(report_kind='set_scalar'),
                    ),
                    'root.review_loop': CompatibilityNodeProjection(
                        node_id='root.review_loop',
                        step_id='root.review_loop',
                        presentation_key='ReviewLoop',
                        display_name='ReviewLoop',
                        region=WorkflowRegion.BODY,
                        compatibility_index=0,
                        step_definition=CompatibilityStepDefinition(report_kind='repeat_until'),
                    ),
                },
            ),
            node_id_by_compatibility_index=MappingProxyType(
                {
                    0: 'root.review_loop',
                },
            ),
            compatibility_index_by_node_id=MappingProxyType(
                {
                    'root.review_loop': 0,
                },
            ),
            presentation_key_by_node_id=MappingProxyType(
                {
                    'root.review_loop.iteration_body.writedecision': 'WriteDecision',
                    'root.review_loop': 'ReviewLoop',
                },
            ),
            node_id_by_step_id=MappingProxyType(
                {
                    'root.review_loop.iteration_body.writedecision': 'root.review_loop.iteration_body.writedecision',
                    'root.review_loop': 'root.review_loop',
                },
            ),
            repeat_until_nodes=MappingProxyType(
                {
                    'root.review_loop': IterationStepKeyProjection(
                        node_id='root.review_loop',
                        frame_key='ReviewLoop',
                        nested_presentation_keys=MappingProxyType(
                            {
                                'root.review_loop.iteration_body.writedecision': 'WriteDecision',
                            },
                        ),
                        nested_step_id_suffixes=MappingProxyType(
                            {
                                'root.review_loop.iteration_body.writedecision': 'iteration_body.writedecision',
                            },
                        ),
                        max_iterations=4,
                    ),
                },
            ),
        ),
        runtime_plan=None,
        imports=MappingProxyType({}),
        provenance=WorkflowProvenance(
            workflow_path=Path('historical/obs-repeat-progress.orc'),
            source_root=Path('historical'),
        ),
    ),
    'obs-provider-session': LoadedWorkflowBundle(
        surface=SurfaceWorkflow(
            version='2.10',
            name='obs-provider-session',
            steps=(),
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/obs-provider-session.orc'),
                source_root=Path('historical'),
            ),
        ),
        core_workflow_ast=None,
        semantic_ir=None,
        ir=ExecutableWorkflow(
            schema_version='workflow_executable_ir.v1',
            version='2.10',
            name='obs-provider-session',
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/obs-provider-session.orc'),
                source_root=Path('historical'),
            ),
            body_region=('root.askprovider',),
            finalization_region=(),
            finalization_entry_node_id=None,
            nodes=MappingProxyType(
                {
                    'root.askprovider': LeafExecutableNode(
                        node_id='root.askprovider',
                        step_id='root.askprovider',
                        presentation_name='AskProvider',
                        kind=ExecutableNodeKind.PROVIDER,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'askprovider'),
                    ),
                },
            ),
        ),
        projection=WorkflowStateProjection(
            entries_by_node_id=MappingProxyType(
                {
                    'root.askprovider': CompatibilityNodeProjection(
                        node_id='root.askprovider',
                        step_id='root.askprovider',
                        presentation_key='AskProvider',
                        display_name='AskProvider',
                        region=WorkflowRegion.BODY,
                        compatibility_index=0,
                        step_definition=CompatibilityStepDefinition(
                            report_kind='provider',
                            provider='codex',
                            provider_session_enabled=True,
                            provider_session_mode='fresh',
                        ),
                    ),
                },
            ),
            node_id_by_compatibility_index=MappingProxyType(
                {
                    0: 'root.askprovider',
                },
            ),
            compatibility_index_by_node_id=MappingProxyType(
                {
                    'root.askprovider': 0,
                },
            ),
            presentation_key_by_node_id=MappingProxyType(
                {
                    'root.askprovider': 'AskProvider',
                },
            ),
            node_id_by_step_id=MappingProxyType(
                {
                    'root.askprovider': 'root.askprovider',
                },
            ),
        ),
        runtime_plan=None,
        imports=MappingProxyType({}),
        provenance=WorkflowProvenance(
            workflow_path=Path('historical/obs-provider-session.orc'),
            source_root=Path('historical'),
        ),
    ),
    'variant-snapshot-report': LoadedWorkflowBundle(
        surface=SurfaceWorkflow(
            version='1.3',
            name='variant-snapshot-report',
            steps=(),
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/variant-snapshot-report.orc'),
                source_root=Path('historical'),
            ),
        ),
        core_workflow_ast=None,
        semantic_ir=None,
        ir=ExecutableWorkflow(
            schema_version='workflow_executable_ir.v1',
            version='1.3',
            name='variant-snapshot-report',
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/variant-snapshot-report.orc'),
                source_root=Path('historical'),
            ),
            body_region=('root.executeimplementation', 'root.selectimplementationoutcome'),
            finalization_region=(),
            finalization_entry_node_id=None,
            nodes=MappingProxyType(
                {
                    'root.executeimplementation': LeafExecutableNode(
                        node_id='root.executeimplementation',
                        step_id='root.executeimplementation',
                        presentation_name='ExecuteImplementation',
                        kind=ExecutableNodeKind.COMMAND,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'executeimplementation'),
                    ),
                    'root.selectimplementationoutcome': LeafExecutableNode(
                        node_id='root.selectimplementationoutcome',
                        step_id='root.selectimplementationoutcome',
                        presentation_name='SelectImplementationOutcome',
                        kind=ExecutableNodeKind.COMMAND,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'selectimplementationoutcome'),
                    ),
                },
            ),
        ),
        projection=WorkflowStateProjection(
            entries_by_node_id=MappingProxyType(
                {
                    'root.executeimplementation': CompatibilityNodeProjection(
                        node_id='root.executeimplementation',
                        step_id='root.executeimplementation',
                        presentation_key='ExecuteImplementation',
                        display_name='ExecuteImplementation',
                        region=WorkflowRegion.BODY,
                        compatibility_index=0,
                        step_definition=CompatibilityStepDefinition(
                            report_kind='command',
                            command=('bash', '-lc', 'echo execute'),
                        ),
                    ),
                    'root.selectimplementationoutcome': CompatibilityNodeProjection(
                        node_id='root.selectimplementationoutcome',
                        step_id='root.selectimplementationoutcome',
                        presentation_key='SelectImplementationOutcome',
                        display_name='SelectImplementationOutcome',
                        region=WorkflowRegion.BODY,
                        compatibility_index=1,
                        step_definition=CompatibilityStepDefinition(
                            report_kind='command',
                            command=('bash', '-lc', 'echo select'),
                        ),
                    ),
                },
            ),
            node_id_by_compatibility_index=MappingProxyType(
                {
                    0: 'root.executeimplementation',
                    1: 'root.selectimplementationoutcome',
                },
            ),
            compatibility_index_by_node_id=MappingProxyType(
                {
                    'root.executeimplementation': 0,
                    'root.selectimplementationoutcome': 1,
                },
            ),
            presentation_key_by_node_id=MappingProxyType(
                {
                    'root.executeimplementation': 'ExecuteImplementation',
                    'root.selectimplementationoutcome': 'SelectImplementationOutcome',
                },
            ),
            node_id_by_step_id=MappingProxyType(
                {
                    'root.executeimplementation': 'root.executeimplementation',
                    'root.selectimplementationoutcome': 'root.selectimplementationoutcome',
                },
            ),
        ),
        runtime_plan=None,
        imports=MappingProxyType({}),
        provenance=WorkflowProvenance(
            workflow_path=Path('historical/variant-snapshot-report.orc'),
            source_root=Path('historical'),
        ),
    ),
    'typed-surface-report': LoadedWorkflowBundle(
        surface=SurfaceWorkflow(
            version='2.10',
            name='typed-surface-report',
            steps=(),
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/typed-surface-report.orc'),
                source_root=Path('historical'),
            ),
            max_transitions=7,
        ),
        core_workflow_ast=None,
        semantic_ir=None,
        ir=ExecutableWorkflow(
            schema_version='workflow_executable_ir.v1',
            version='2.10',
            name='typed-surface-report',
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/typed-surface-report.orc'),
                source_root=Path('historical'),
            ),
            body_region=('root.generate_report',),
            finalization_region=(),
            finalization_entry_node_id=None,
            nodes=MappingProxyType(
                {
                    'root.generate_report': LeafExecutableNode(
                        node_id='root.generate_report',
                        step_id='root.generate_report',
                        presentation_name='GenerateReport',
                        kind=ExecutableNodeKind.COMMAND,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'generate_report'),
                    ),
                },
            ),
        ),
        projection=WorkflowStateProjection(
            entries_by_node_id=MappingProxyType(
                {
                    'root.generate_report': CompatibilityNodeProjection(
                        node_id='root.generate_report',
                        step_id='root.generate_report',
                        presentation_key='GenerateReport',
                        display_name='GenerateReport',
                        region=WorkflowRegion.BODY,
                        compatibility_index=0,
                        step_definition=CompatibilityStepDefinition(
                            report_kind='command',
                            command=('bash', '-lc', 'echo report'),
                        ),
                    ),
                },
            ),
            node_id_by_compatibility_index=MappingProxyType(
                {
                    0: 'root.generate_report',
                },
            ),
            compatibility_index_by_node_id=MappingProxyType(
                {
                    'root.generate_report': 0,
                },
            ),
            presentation_key_by_node_id=MappingProxyType(
                {
                    'root.generate_report': 'GenerateReport',
                },
            ),
            node_id_by_step_id=MappingProxyType(
                {
                    'root.generate_report': 'root.generate_report',
                },
            ),
        ),
        runtime_plan=None,
        imports=MappingProxyType({}),
        provenance=WorkflowProvenance(
            workflow_path=Path('historical/typed-surface-report.orc'),
            source_root=Path('historical'),
        ),
    ),
    'bundle-report': LoadedWorkflowBundle(
        surface=SurfaceWorkflow(
            version='2.10',
            name='bundle-report',
            steps=(),
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/bundle-report.orc'),
                source_root=Path('historical'),
            ),
        ),
        core_workflow_ast=None,
        semantic_ir=None,
        ir=ExecutableWorkflow(
            schema_version='workflow_executable_ir.v1',
            version='2.10',
            name='bundle-report',
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/bundle-report.orc'),
                source_root=Path('historical'),
            ),
            body_region=(
                'root.set_ready',
                'root.route_ready.approve_path',
                'root.route_ready.approve_path.write_approved',
                'root.route_ready.revise_path',
                'root.route_ready.revise_path.write_revision',
                'root.route_ready',
            ),
            finalization_region=('root.finally.cleanup.write_cleanup_marker',),
            finalization_entry_node_id='root.finally.cleanup.write_cleanup_marker',
            nodes=MappingProxyType(
                {
                    'root.set_ready': LeafExecutableNode(
                        node_id='root.set_ready',
                        step_id='root.set_ready',
                        presentation_name='SetReady',
                        kind=ExecutableNodeKind.SET_SCALAR,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'set_ready'),
                    ),
                    'root.route_ready.approve_path.write_approved': LeafExecutableNode(
                        node_id='root.route_ready.approve_path.write_approved',
                        step_id='root.route_ready.approve_path.write_approved',
                        presentation_name='RouteReady.then.WriteApproved',
                        kind=ExecutableNodeKind.COMMAND,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'route_ready', 'approve_path', 'write_approved'),
                    ),
                    'root.route_ready.approve_path': IfBranchMarkerNode(
                        node_id='root.route_ready.approve_path',
                        step_id='root.route_ready.approve_path',
                        presentation_name='RouteReady.then',
                        kind=ExecutableNodeKind.IF_BRANCH_MARKER,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'route_ready', 'approve_path'),
                    ),
                    'root.route_ready.revise_path.write_revision': LeafExecutableNode(
                        node_id='root.route_ready.revise_path.write_revision',
                        step_id='root.route_ready.revise_path.write_revision',
                        presentation_name='RouteReady.else.WriteRevision',
                        kind=ExecutableNodeKind.COMMAND,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'route_ready', 'revise_path', 'write_revision'),
                    ),
                    'root.route_ready.revise_path': IfBranchMarkerNode(
                        node_id='root.route_ready.revise_path',
                        step_id='root.route_ready.revise_path',
                        presentation_name='RouteReady.else',
                        kind=ExecutableNodeKind.IF_BRANCH_MARKER,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'route_ready', 'revise_path'),
                    ),
                    'root.route_ready': IfJoinNode(
                        node_id='root.route_ready',
                        step_id='root.route_ready',
                        presentation_name='RouteReady',
                        kind=ExecutableNodeKind.IF_JOIN,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'route_ready'),
                    ),
                    'root.finally.cleanup.write_cleanup_marker': FinalizationStepNode(
                        node_id='root.finally.cleanup.write_cleanup_marker',
                        step_id='root.finally.cleanup.write_cleanup_marker',
                        presentation_name='finally.WriteCleanupMarker',
                        kind=ExecutableNodeKind.FINALIZATION_STEP,
                        region=WorkflowRegion.FINALIZATION,
                        lexical_scope=('root', 'finally', 'cleanup', 'write_cleanup_marker'),
                    ),
                },
            ),
        ),
        projection=WorkflowStateProjection(
            entries_by_node_id=MappingProxyType(
                {
                    'root.set_ready': CompatibilityNodeProjection(
                        node_id='root.set_ready',
                        step_id='root.set_ready',
                        presentation_key='SetReady',
                        display_name='SetReady',
                        region=WorkflowRegion.BODY,
                        compatibility_index=0,
                        step_definition=CompatibilityStepDefinition(report_kind='set_scalar'),
                    ),
                    'root.route_ready.approve_path.write_approved': CompatibilityNodeProjection(
                        node_id='root.route_ready.approve_path.write_approved',
                        step_id='root.route_ready.approve_path.write_approved',
                        presentation_key='RouteReady.then.WriteApproved',
                        display_name='RouteReady.then.WriteApproved',
                        region=WorkflowRegion.BODY,
                        compatibility_index=2,
                        step_definition=CompatibilityStepDefinition(
                            report_kind='command',
                            command=('bash', '-lc', "printf 'approved\\n'"),
                        ),
                    ),
                    'root.route_ready.approve_path': CompatibilityNodeProjection(
                        node_id='root.route_ready.approve_path',
                        step_id='root.route_ready.approve_path',
                        presentation_key='RouteReady.then',
                        display_name='RouteReady.then',
                        region=WorkflowRegion.BODY,
                        compatibility_index=1,
                        step_definition=CompatibilityStepDefinition(report_kind='structured_if_branch'),
                    ),
                    'root.route_ready.revise_path.write_revision': CompatibilityNodeProjection(
                        node_id='root.route_ready.revise_path.write_revision',
                        step_id='root.route_ready.revise_path.write_revision',
                        presentation_key='RouteReady.else.WriteRevision',
                        display_name='RouteReady.else.WriteRevision',
                        region=WorkflowRegion.BODY,
                        compatibility_index=4,
                        step_definition=CompatibilityStepDefinition(
                            report_kind='command',
                            command=('bash', '-lc', "printf 'revise\\n'"),
                        ),
                    ),
                    'root.route_ready.revise_path': CompatibilityNodeProjection(
                        node_id='root.route_ready.revise_path',
                        step_id='root.route_ready.revise_path',
                        presentation_key='RouteReady.else',
                        display_name='RouteReady.else',
                        region=WorkflowRegion.BODY,
                        compatibility_index=3,
                        step_definition=CompatibilityStepDefinition(report_kind='structured_if_branch'),
                    ),
                    'root.route_ready': CompatibilityNodeProjection(
                        node_id='root.route_ready',
                        step_id='root.route_ready',
                        presentation_key='RouteReady',
                        display_name='RouteReady',
                        region=WorkflowRegion.BODY,
                        compatibility_index=5,
                        step_definition=CompatibilityStepDefinition(report_kind='structured_if_join'),
                    ),
                    'root.finally.cleanup.write_cleanup_marker': CompatibilityNodeProjection(
                        node_id='root.finally.cleanup.write_cleanup_marker',
                        step_id='root.finally.cleanup.write_cleanup_marker',
                        presentation_key='finally.WriteCleanupMarker',
                        display_name='finally.WriteCleanupMarker',
                        region=WorkflowRegion.FINALIZATION,
                        finalization_index=0,
                        step_definition=CompatibilityStepDefinition(
                            report_kind='finally',
                            command=('bash', '-lc', "printf 'cleanup\\n'"),
                        ),
                    ),
                },
            ),
            node_id_by_compatibility_index=MappingProxyType(
                {
                    0: 'root.set_ready',
                    1: 'root.route_ready.approve_path',
                    2: 'root.route_ready.approve_path.write_approved',
                    3: 'root.route_ready.revise_path',
                    4: 'root.route_ready.revise_path.write_revision',
                    5: 'root.route_ready',
                },
            ),
            compatibility_index_by_node_id=MappingProxyType(
                {
                    'root.set_ready': 0,
                    'root.route_ready.approve_path': 1,
                    'root.route_ready.approve_path.write_approved': 2,
                    'root.route_ready.revise_path': 3,
                    'root.route_ready.revise_path.write_revision': 4,
                    'root.route_ready': 5,
                },
            ),
            presentation_key_by_node_id=MappingProxyType(
                {
                    'root.set_ready': 'SetReady',
                    'root.route_ready.approve_path.write_approved': 'RouteReady.then.WriteApproved',
                    'root.route_ready.approve_path': 'RouteReady.then',
                    'root.route_ready.revise_path.write_revision': 'RouteReady.else.WriteRevision',
                    'root.route_ready.revise_path': 'RouteReady.else',
                    'root.route_ready': 'RouteReady',
                    'root.finally.cleanup.write_cleanup_marker': 'finally.WriteCleanupMarker',
                },
            ),
            node_id_by_step_id=MappingProxyType(
                {
                    'root.set_ready': 'root.set_ready',
                    'root.route_ready.approve_path.write_approved': 'root.route_ready.approve_path.write_approved',
                    'root.route_ready.approve_path': 'root.route_ready.approve_path',
                    'root.route_ready.revise_path.write_revision': 'root.route_ready.revise_path.write_revision',
                    'root.route_ready.revise_path': 'root.route_ready.revise_path',
                    'root.route_ready': 'root.route_ready',
                    'root.finally.cleanup.write_cleanup_marker': 'root.finally.cleanup.write_cleanup_marker',
                },
            ),
            finalization_node_id_by_index=MappingProxyType(
                {
                    0: 'root.finally.cleanup.write_cleanup_marker',
                },
            ),
            finalization_index_by_node_id=MappingProxyType(
                {
                    'root.finally.cleanup.write_cleanup_marker': 0,
                },
            ),
            structured_if_branches=MappingProxyType(
                {
                    'root.route_ready': MappingProxyType(
                        {
                            'then': StructuredSelectionProjection(
                                marker_step_id='root.route_ready.approve_path',
                                marker_presentation_key='RouteReady.then',
                                step_presentation_keys=('RouteReady.then.WriteApproved',),
                            ),
                            'else': StructuredSelectionProjection(
                                marker_step_id='root.route_ready.revise_path',
                                marker_presentation_key='RouteReady.else',
                                step_presentation_keys=('RouteReady.else.WriteRevision',),
                            ),
                        },
                    ),
                },
            ),
        ),
        runtime_plan=None,
        imports=MappingProxyType({}),
        provenance=WorkflowProvenance(
            workflow_path=Path('historical/bundle-report.orc'),
            source_root=Path('historical'),
        ),
    ),
    'bundle-projection-order': LoadedWorkflowBundle(
        surface=SurfaceWorkflow(
            version='2.10',
            name='bundle-projection-order',
            steps=(),
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/bundle-projection-order.orc'),
                source_root=Path('historical'),
            ),
        ),
        core_workflow_ast=None,
        semantic_ir=None,
        ir=ExecutableWorkflow(
            schema_version='workflow_executable_ir.v1',
            version='2.10',
            name='bundle-projection-order',
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/bundle-projection-order.orc'),
                source_root=Path('historical'),
            ),
            body_region=('root.write_one', 'root.write_two'),
            finalization_region=(),
            finalization_entry_node_id=None,
            nodes=MappingProxyType(
                {
                    'root.write_one': LeafExecutableNode(
                        node_id='root.write_one',
                        step_id='root.write_one',
                        presentation_name='WriteOne',
                        kind=ExecutableNodeKind.COMMAND,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'write_one'),
                    ),
                    'root.write_two': LeafExecutableNode(
                        node_id='root.write_two',
                        step_id='root.write_two',
                        presentation_name='WriteTwo',
                        kind=ExecutableNodeKind.COMMAND,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'write_two'),
                    ),
                },
            ),
        ),
        projection=WorkflowStateProjection(
            entries_by_node_id=MappingProxyType(
                {
                    'root.write_one': CompatibilityNodeProjection(
                        node_id='root.write_one',
                        step_id='root.write_one',
                        presentation_key='WriteOne',
                        display_name='WriteOne',
                        region=WorkflowRegion.BODY,
                        compatibility_index=0,
                        step_definition=CompatibilityStepDefinition(
                            report_kind='command',
                            command=('bash', '-lc', "printf 'one\\n'"),
                        ),
                    ),
                    'root.write_two': CompatibilityNodeProjection(
                        node_id='root.write_two',
                        step_id='root.write_two',
                        presentation_key='WriteTwo',
                        display_name='WriteTwo',
                        region=WorkflowRegion.BODY,
                        compatibility_index=1,
                        step_definition=CompatibilityStepDefinition(
                            report_kind='command',
                            command=('bash', '-lc', "printf 'two\\n'"),
                        ),
                    ),
                },
            ),
            node_id_by_compatibility_index=MappingProxyType(
                {
                    0: 'root.write_one',
                    1: 'root.write_two',
                },
            ),
            compatibility_index_by_node_id=MappingProxyType(
                {
                    'root.write_one': 0,
                    'root.write_two': 1,
                },
            ),
            presentation_key_by_node_id=MappingProxyType(
                {
                    'root.write_one': 'WriteOne',
                    'root.write_two': 'WriteTwo',
                },
            ),
            node_id_by_step_id=MappingProxyType(
                {
                    'root.write_one': 'root.write_one',
                    'root.write_two': 'root.write_two',
                },
            ),
        ),
        runtime_plan=None,
        imports=MappingProxyType({}),
        provenance=WorkflowProvenance(
            workflow_path=Path('historical/bundle-projection-order.orc'),
            source_root=Path('historical'),
        ),
    ),
    'bundle-ir-metadata': LoadedWorkflowBundle(
        surface=SurfaceWorkflow(
            version='2.10',
            name='bundle-ir-metadata',
            steps=(),
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/bundle-ir-metadata.orc'),
                source_root=Path('historical'),
            ),
        ),
        core_workflow_ast=None,
        semantic_ir=None,
        ir=ExecutableWorkflow(
            schema_version='workflow_executable_ir.v1',
            version='2.10',
            name='bundle-ir-metadata',
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/bundle-ir-metadata.orc'),
                source_root=Path('historical'),
            ),
            body_region=('root.generate_report',),
            finalization_region=('root.finally.cleanup.cleanup_step',),
            finalization_entry_node_id='root.finally.cleanup.cleanup_step',
            nodes=MappingProxyType(
                {
                    'root.generate_report': LeafExecutableNode(
                        node_id='root.generate_report',
                        step_id='root.generate_report',
                        presentation_name='GenerateReport',
                        kind=ExecutableNodeKind.COMMAND,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'generate_report'),
                    ),
                    'root.finally.cleanup.cleanup_step': FinalizationStepNode(
                        node_id='root.finally.cleanup.cleanup_step',
                        step_id='root.finally.cleanup.cleanup_step',
                        presentation_name='finally.Cleanup',
                        kind=ExecutableNodeKind.FINALIZATION_STEP,
                        region=WorkflowRegion.FINALIZATION,
                        lexical_scope=('root', 'finally', 'cleanup', 'cleanup_step'),
                    ),
                },
            ),
        ),
        projection=WorkflowStateProjection(
            entries_by_node_id=MappingProxyType(
                {
                    'root.generate_report': CompatibilityNodeProjection(
                        node_id='root.generate_report',
                        step_id='root.generate_report',
                        presentation_key='GenerateReport',
                        display_name='GenerateReport',
                        region=WorkflowRegion.BODY,
                        compatibility_index=0,
                        step_definition=CompatibilityStepDefinition(
                            report_kind='command',
                            command=('bash', '-lc', 'echo report'),
                            consumes=(
                                MappingProxyType(
                                    {
                                        'artifact': 'plan_doc',
                                        'as': 'plan',
                                    },
                                ),
                            ),
                            expected_outputs=(
                                MappingProxyType(
                                    {
                                        'name': 'report_path',
                                        'path': 'state/report_path.txt',
                                        'type': 'string',
                                    },
                                ),
                            ),
                        ),
                    ),
                    'root.finally.cleanup.cleanup_step': CompatibilityNodeProjection(
                        node_id='root.finally.cleanup.cleanup_step',
                        step_id='root.finally.cleanup.cleanup_step',
                        presentation_key='finally.Cleanup',
                        display_name='finally.Cleanup',
                        region=WorkflowRegion.FINALIZATION,
                        finalization_index=0,
                        step_definition=CompatibilityStepDefinition(
                            report_kind='finally',
                            command=('bash', '-lc', 'echo cleanup'),
                        ),
                    ),
                },
            ),
            node_id_by_compatibility_index=MappingProxyType(
                {
                    0: 'root.generate_report',
                },
            ),
            compatibility_index_by_node_id=MappingProxyType(
                {
                    'root.generate_report': 0,
                },
            ),
            presentation_key_by_node_id=MappingProxyType(
                {
                    'root.generate_report': 'GenerateReport',
                    'root.finally.cleanup.cleanup_step': 'finally.Cleanup',
                },
            ),
            node_id_by_step_id=MappingProxyType(
                {
                    'root.generate_report': 'root.generate_report',
                    'root.finally.cleanup.cleanup_step': 'root.finally.cleanup.cleanup_step',
                },
            ),
            finalization_node_id_by_index=MappingProxyType(
                {
                    0: 'root.finally.cleanup.cleanup_step',
                },
            ),
            finalization_index_by_node_id=MappingProxyType(
                {
                    'root.finally.cleanup.cleanup_step': 0,
                },
            ),
        ),
        runtime_plan=None,
        imports=MappingProxyType({}),
        provenance=WorkflowProvenance(
            workflow_path=Path('historical/bundle-ir-metadata.orc'),
            source_root=Path('historical'),
        ),
    ),
    'bundle-projection-metadata': LoadedWorkflowBundle(
        surface=SurfaceWorkflow(
            version='2.10',
            name='bundle-projection-metadata',
            steps=(),
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/bundle-projection-metadata.orc'),
                source_root=Path('historical'),
            ),
        ),
        core_workflow_ast=None,
        semantic_ir=None,
        ir=ExecutableWorkflow(
            schema_version='workflow_executable_ir.v1',
            version='2.10',
            name='bundle-projection-metadata',
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/bundle-projection-metadata.orc'),
                source_root=Path('historical'),
            ),
            body_region=('root.generate_report',),
            finalization_region=('root.finally.cleanup.cleanup_step',),
            finalization_entry_node_id='root.finally.cleanup.cleanup_step',
            nodes=MappingProxyType(
                {
                    'root.generate_report': LeafExecutableNode(
                        node_id='root.generate_report',
                        step_id='root.generate_report',
                        presentation_name='GenerateReport',
                        kind=ExecutableNodeKind.COMMAND,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'generate_report'),
                    ),
                    'root.finally.cleanup.cleanup_step': FinalizationStepNode(
                        node_id='root.finally.cleanup.cleanup_step',
                        step_id='root.finally.cleanup.cleanup_step',
                        presentation_name='finally.Cleanup',
                        kind=ExecutableNodeKind.FINALIZATION_STEP,
                        region=WorkflowRegion.FINALIZATION,
                        lexical_scope=('root', 'finally', 'cleanup', 'cleanup_step'),
                    ),
                },
            ),
        ),
        projection=WorkflowStateProjection(
            entries_by_node_id=MappingProxyType(
                {
                    'root.generate_report': CompatibilityNodeProjection(
                        node_id='root.generate_report',
                        step_id='root.generate_report',
                        presentation_key='GenerateReport',
                        display_name='GenerateReport',
                        region=WorkflowRegion.BODY,
                        compatibility_index=0,
                        step_definition=CompatibilityStepDefinition(
                            report_kind='command',
                            command=('bash', '-lc', 'echo report'),
                            consumes=(
                                MappingProxyType(
                                    {
                                        'artifact': 'plan_doc',
                                        'as': 'plan',
                                    },
                                ),
                            ),
                            expected_outputs=(
                                MappingProxyType(
                                    {
                                        'name': 'report_path',
                                        'path': 'state/report_path.txt',
                                        'type': 'string',
                                    },
                                ),
                            ),
                        ),
                    ),
                    'root.finally.cleanup.cleanup_step': CompatibilityNodeProjection(
                        node_id='root.finally.cleanup.cleanup_step',
                        step_id='root.finally.cleanup.cleanup_step',
                        presentation_key='finally.Cleanup',
                        display_name='finally.Cleanup',
                        region=WorkflowRegion.FINALIZATION,
                        finalization_index=0,
                        step_definition=CompatibilityStepDefinition(
                            report_kind='finally',
                            command=('bash', '-lc', 'echo cleanup'),
                        ),
                    ),
                },
            ),
            node_id_by_compatibility_index=MappingProxyType(
                {
                    0: 'root.generate_report',
                },
            ),
            compatibility_index_by_node_id=MappingProxyType(
                {
                    'root.generate_report': 0,
                },
            ),
            presentation_key_by_node_id=MappingProxyType(
                {
                    'root.generate_report': 'GenerateReport',
                    'root.finally.cleanup.cleanup_step': 'finally.Cleanup',
                },
            ),
            node_id_by_step_id=MappingProxyType(
                {
                    'root.generate_report': 'root.generate_report',
                    'root.finally.cleanup.cleanup_step': 'root.finally.cleanup.cleanup_step',
                },
            ),
            finalization_node_id_by_index=MappingProxyType(
                {
                    0: 'root.finally.cleanup.cleanup_step',
                },
            ),
            finalization_index_by_node_id=MappingProxyType(
                {
                    'root.finally.cleanup.cleanup_step': 0,
                },
            ),
        ),
        runtime_plan=None,
        imports=MappingProxyType({}),
        provenance=WorkflowProvenance(
            workflow_path=Path('historical/bundle-projection-metadata.orc'),
            source_root=Path('historical'),
        ),
    ),
    'bundle-report-current-step': LoadedWorkflowBundle(
        surface=SurfaceWorkflow(
            version='2.7',
            name='bundle-report-current-step',
            steps=(),
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/bundle-report-current-step.orc'),
                source_root=Path('historical'),
            ),
        ),
        core_workflow_ast=None,
        semantic_ir=None,
        ir=ExecutableWorkflow(
            schema_version='workflow_executable_ir.v1',
            version='2.7',
            name='bundle-report-current-step',
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/bundle-report-current-step.orc'),
                source_root=Path('historical'),
            ),
            body_region=(
                'root.set_ready',
                'root.route_ready.approve_path',
                'root.route_ready.approve_path.write_approved',
                'root.route_ready.revise_path',
                'root.route_ready.revise_path.write_revision',
                'root.route_ready',
            ),
            finalization_region=(),
            finalization_entry_node_id=None,
            nodes=MappingProxyType(
                {
                    'root.set_ready': LeafExecutableNode(
                        node_id='root.set_ready',
                        step_id='root.set_ready',
                        presentation_name='SetReady',
                        kind=ExecutableNodeKind.SET_SCALAR,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'set_ready'),
                    ),
                    'root.route_ready.approve_path.write_approved': LeafExecutableNode(
                        node_id='root.route_ready.approve_path.write_approved',
                        step_id='root.route_ready.approve_path.write_approved',
                        presentation_name='RouteReady.then.WriteApproved',
                        kind=ExecutableNodeKind.COMMAND,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'route_ready', 'approve_path', 'write_approved'),
                    ),
                    'root.route_ready.approve_path': IfBranchMarkerNode(
                        node_id='root.route_ready.approve_path',
                        step_id='root.route_ready.approve_path',
                        presentation_name='RouteReady.then',
                        kind=ExecutableNodeKind.IF_BRANCH_MARKER,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'route_ready', 'approve_path'),
                    ),
                    'root.route_ready.revise_path.write_revision': LeafExecutableNode(
                        node_id='root.route_ready.revise_path.write_revision',
                        step_id='root.route_ready.revise_path.write_revision',
                        presentation_name='RouteReady.else.WriteRevision',
                        kind=ExecutableNodeKind.COMMAND,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'route_ready', 'revise_path', 'write_revision'),
                    ),
                    'root.route_ready.revise_path': IfBranchMarkerNode(
                        node_id='root.route_ready.revise_path',
                        step_id='root.route_ready.revise_path',
                        presentation_name='RouteReady.else',
                        kind=ExecutableNodeKind.IF_BRANCH_MARKER,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'route_ready', 'revise_path'),
                    ),
                    'root.route_ready': IfJoinNode(
                        node_id='root.route_ready',
                        step_id='root.route_ready',
                        presentation_name='RouteReady',
                        kind=ExecutableNodeKind.IF_JOIN,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'route_ready'),
                    ),
                },
            ),
        ),
        projection=WorkflowStateProjection(
            entries_by_node_id=MappingProxyType(
                {
                    'root.set_ready': CompatibilityNodeProjection(
                        node_id='root.set_ready',
                        step_id='root.set_ready',
                        presentation_key='SetReady',
                        display_name='SetReady',
                        region=WorkflowRegion.BODY,
                        compatibility_index=0,
                        step_definition=CompatibilityStepDefinition(report_kind='set_scalar'),
                    ),
                    'root.route_ready.approve_path.write_approved': CompatibilityNodeProjection(
                        node_id='root.route_ready.approve_path.write_approved',
                        step_id='root.route_ready.approve_path.write_approved',
                        presentation_key='RouteReady.then.WriteApproved',
                        display_name='RouteReady.then.WriteApproved',
                        region=WorkflowRegion.BODY,
                        compatibility_index=2,
                        step_definition=CompatibilityStepDefinition(
                            report_kind='command',
                            command=('bash', '-lc', "printf 'approved\\n'"),
                        ),
                    ),
                    'root.route_ready.approve_path': CompatibilityNodeProjection(
                        node_id='root.route_ready.approve_path',
                        step_id='root.route_ready.approve_path',
                        presentation_key='RouteReady.then',
                        display_name='RouteReady.then',
                        region=WorkflowRegion.BODY,
                        compatibility_index=1,
                        step_definition=CompatibilityStepDefinition(report_kind='structured_if_branch'),
                    ),
                    'root.route_ready.revise_path.write_revision': CompatibilityNodeProjection(
                        node_id='root.route_ready.revise_path.write_revision',
                        step_id='root.route_ready.revise_path.write_revision',
                        presentation_key='RouteReady.else.WriteRevision',
                        display_name='RouteReady.else.WriteRevision',
                        region=WorkflowRegion.BODY,
                        compatibility_index=4,
                        step_definition=CompatibilityStepDefinition(
                            report_kind='command',
                            command=('bash', '-lc', "printf 'revise\\n'"),
                        ),
                    ),
                    'root.route_ready.revise_path': CompatibilityNodeProjection(
                        node_id='root.route_ready.revise_path',
                        step_id='root.route_ready.revise_path',
                        presentation_key='RouteReady.else',
                        display_name='RouteReady.else',
                        region=WorkflowRegion.BODY,
                        compatibility_index=3,
                        step_definition=CompatibilityStepDefinition(report_kind='structured_if_branch'),
                    ),
                    'root.route_ready': CompatibilityNodeProjection(
                        node_id='root.route_ready',
                        step_id='root.route_ready',
                        presentation_key='RouteReady',
                        display_name='RouteReady',
                        region=WorkflowRegion.BODY,
                        compatibility_index=5,
                        step_definition=CompatibilityStepDefinition(report_kind='structured_if_join'),
                    ),
                },
            ),
            node_id_by_compatibility_index=MappingProxyType(
                {
                    0: 'root.set_ready',
                    1: 'root.route_ready.approve_path',
                    2: 'root.route_ready.approve_path.write_approved',
                    3: 'root.route_ready.revise_path',
                    4: 'root.route_ready.revise_path.write_revision',
                    5: 'root.route_ready',
                },
            ),
            compatibility_index_by_node_id=MappingProxyType(
                {
                    'root.set_ready': 0,
                    'root.route_ready.approve_path': 1,
                    'root.route_ready.approve_path.write_approved': 2,
                    'root.route_ready.revise_path': 3,
                    'root.route_ready.revise_path.write_revision': 4,
                    'root.route_ready': 5,
                },
            ),
            presentation_key_by_node_id=MappingProxyType(
                {
                    'root.set_ready': 'SetReady',
                    'root.route_ready.approve_path.write_approved': 'RouteReady.then.WriteApproved',
                    'root.route_ready.approve_path': 'RouteReady.then',
                    'root.route_ready.revise_path.write_revision': 'RouteReady.else.WriteRevision',
                    'root.route_ready.revise_path': 'RouteReady.else',
                    'root.route_ready': 'RouteReady',
                },
            ),
            node_id_by_step_id=MappingProxyType(
                {
                    'root.set_ready': 'root.set_ready',
                    'root.route_ready.approve_path.write_approved': 'root.route_ready.approve_path.write_approved',
                    'root.route_ready.approve_path': 'root.route_ready.approve_path',
                    'root.route_ready.revise_path.write_revision': 'root.route_ready.revise_path.write_revision',
                    'root.route_ready.revise_path': 'root.route_ready.revise_path',
                    'root.route_ready': 'root.route_ready',
                },
            ),
            structured_if_branches=MappingProxyType(
                {
                    'root.route_ready': MappingProxyType(
                        {
                            'then': StructuredSelectionProjection(
                                marker_step_id='root.route_ready.approve_path',
                                marker_presentation_key='RouteReady.then',
                                step_presentation_keys=('RouteReady.then.WriteApproved',),
                            ),
                            'else': StructuredSelectionProjection(
                                marker_step_id='root.route_ready.revise_path',
                                marker_presentation_key='RouteReady.else',
                                step_presentation_keys=('RouteReady.else.WriteRevision',),
                            ),
                        },
                    ),
                },
            ),
        ),
        runtime_plan=None,
        imports=MappingProxyType({}),
        provenance=WorkflowProvenance(
            workflow_path=Path('historical/bundle-report-current-step.orc'),
            source_root=Path('historical'),
        ),
    ),
    'obs-finally': LoadedWorkflowBundle(
        surface=SurfaceWorkflow(
            version='2.3',
            name='obs-finally',
            steps=(),
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/obs-finally.orc'),
                source_root=Path('historical'),
            ),
        ),
        core_workflow_ast=None,
        semantic_ir=None,
        ir=ExecutableWorkflow(
            schema_version='workflow_executable_ir.v1',
            version='2.3',
            name='obs-finally',
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/obs-finally.orc'),
                source_root=Path('historical'),
            ),
            body_region=('root.body',),
            finalization_region=('root.finally.cleanup.release_lock',),
            finalization_entry_node_id='root.finally.cleanup.release_lock',
            nodes=MappingProxyType(
                {
                    'root.body': LeafExecutableNode(
                        node_id='root.body',
                        step_id='root.body',
                        presentation_name='Body',
                        kind=ExecutableNodeKind.COMMAND,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'body'),
                    ),
                    'root.finally.cleanup.release_lock': FinalizationStepNode(
                        node_id='root.finally.cleanup.release_lock',
                        step_id='root.finally.cleanup.release_lock',
                        presentation_name='finally.ReleaseLock',
                        kind=ExecutableNodeKind.FINALIZATION_STEP,
                        region=WorkflowRegion.FINALIZATION,
                        lexical_scope=('root', 'finally', 'cleanup', 'release_lock'),
                    ),
                },
            ),
        ),
        projection=WorkflowStateProjection(
            entries_by_node_id=MappingProxyType(
                {
                    'root.body': CompatibilityNodeProjection(
                        node_id='root.body',
                        step_id='root.body',
                        presentation_key='Body',
                        display_name='Body',
                        region=WorkflowRegion.BODY,
                        compatibility_index=0,
                        step_definition=CompatibilityStepDefinition(
                            report_kind='command',
                            command=('bash', '-lc', 'echo body'),
                        ),
                    ),
                    'root.finally.cleanup.release_lock': CompatibilityNodeProjection(
                        node_id='root.finally.cleanup.release_lock',
                        step_id='root.finally.cleanup.release_lock',
                        presentation_key='finally.ReleaseLock',
                        display_name='finally.ReleaseLock',
                        region=WorkflowRegion.FINALIZATION,
                        finalization_index=0,
                        step_definition=CompatibilityStepDefinition(
                            report_kind='finally',
                            command=('bash', '-lc', 'echo cleanup'),
                        ),
                    ),
                },
            ),
            node_id_by_compatibility_index=MappingProxyType(
                {
                    0: 'root.body',
                },
            ),
            compatibility_index_by_node_id=MappingProxyType(
                {
                    'root.body': 0,
                },
            ),
            presentation_key_by_node_id=MappingProxyType(
                {
                    'root.body': 'Body',
                    'root.finally.cleanup.release_lock': 'finally.ReleaseLock',
                },
            ),
            node_id_by_step_id=MappingProxyType(
                {
                    'root.body': 'root.body',
                    'root.finally.cleanup.release_lock': 'root.finally.cleanup.release_lock',
                },
            ),
            finalization_node_id_by_index=MappingProxyType(
                {
                    0: 'root.finally.cleanup.release_lock',
                },
            ),
            finalization_index_by_node_id=MappingProxyType(
                {
                    'root.finally.cleanup.release_lock': 0,
                },
            ),
        ),
        runtime_plan=None,
        imports=MappingProxyType({}),
        provenance=WorkflowProvenance(
            workflow_path=Path('historical/obs-finally.orc'),
            source_root=Path('historical'),
        ),
    ),
    'obs-structured': LoadedWorkflowBundle(
        surface=SurfaceWorkflow(
            version='2.6',
            name='obs-structured',
            steps=(),
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/obs-structured.orc'),
                source_root=Path('historical'),
            ),
        ),
        core_workflow_ast=None,
        semantic_ir=None,
        ir=ExecutableWorkflow(
            schema_version='workflow_executable_ir.v1',
            version='2.6',
            name='obs-structured',
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/obs-structured.orc'),
                source_root=Path('historical'),
            ),
            body_region=(
                'root.set_ready',
                'root.route_ready.approve_path',
                'root.route_ready.approve_path.write_approved',
                'root.route_ready.revise_path',
                'root.route_ready.revise_path.write_revision',
                'root.route_ready',
                'root.route_decision.approve_path',
                'root.route_decision.approve_path.echo_approved',
                'root.route_decision.revise_path',
                'root.route_decision.revise_path.echo_revision',
                'root.route_decision',
            ),
            finalization_region=(),
            finalization_entry_node_id=None,
            nodes=MappingProxyType(
                {
                    'root.set_ready': LeafExecutableNode(
                        node_id='root.set_ready',
                        step_id='root.set_ready',
                        presentation_name='SetReady',
                        kind=ExecutableNodeKind.SET_SCALAR,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'set_ready'),
                    ),
                    'root.route_ready.approve_path.write_approved': LeafExecutableNode(
                        node_id='root.route_ready.approve_path.write_approved',
                        step_id='root.route_ready.approve_path.write_approved',
                        presentation_name='RouteReady.then.WriteApproved',
                        kind=ExecutableNodeKind.SET_SCALAR,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'route_ready', 'approve_path', 'write_approved'),
                    ),
                    'root.route_ready.approve_path': IfBranchMarkerNode(
                        node_id='root.route_ready.approve_path',
                        step_id='root.route_ready.approve_path',
                        presentation_name='RouteReady.then',
                        kind=ExecutableNodeKind.IF_BRANCH_MARKER,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'route_ready', 'approve_path'),
                    ),
                    'root.route_ready.revise_path.write_revision': LeafExecutableNode(
                        node_id='root.route_ready.revise_path.write_revision',
                        step_id='root.route_ready.revise_path.write_revision',
                        presentation_name='RouteReady.else.WriteRevision',
                        kind=ExecutableNodeKind.SET_SCALAR,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'route_ready', 'revise_path', 'write_revision'),
                    ),
                    'root.route_ready.revise_path': IfBranchMarkerNode(
                        node_id='root.route_ready.revise_path',
                        step_id='root.route_ready.revise_path',
                        presentation_name='RouteReady.else',
                        kind=ExecutableNodeKind.IF_BRANCH_MARKER,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'route_ready', 'revise_path'),
                    ),
                    'root.route_ready': IfJoinNode(
                        node_id='root.route_ready',
                        step_id='root.route_ready',
                        presentation_name='RouteReady',
                        kind=ExecutableNodeKind.IF_JOIN,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'route_ready'),
                    ),
                    'root.route_decision.approve_path.echo_approved': LeafExecutableNode(
                        node_id='root.route_decision.approve_path.echo_approved',
                        step_id='root.route_decision.approve_path.echo_approved',
                        presentation_name='RouteDecision.APPROVE.EchoApproved',
                        kind=ExecutableNodeKind.COMMAND,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'route_decision', 'approve_path', 'echo_approved'),
                    ),
                    'root.route_decision.approve_path': MatchCaseMarkerNode(
                        node_id='root.route_decision.approve_path',
                        step_id='root.route_decision.approve_path',
                        presentation_name='RouteDecision.APPROVE',
                        kind=ExecutableNodeKind.MATCH_CASE_MARKER,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'route_decision', 'approve_path'),
                    ),
                    'root.route_decision.revise_path.echo_revision': LeafExecutableNode(
                        node_id='root.route_decision.revise_path.echo_revision',
                        step_id='root.route_decision.revise_path.echo_revision',
                        presentation_name='RouteDecision.REVISE.EchoRevision',
                        kind=ExecutableNodeKind.COMMAND,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'route_decision', 'revise_path', 'echo_revision'),
                    ),
                    'root.route_decision.revise_path': MatchCaseMarkerNode(
                        node_id='root.route_decision.revise_path',
                        step_id='root.route_decision.revise_path',
                        presentation_name='RouteDecision.REVISE',
                        kind=ExecutableNodeKind.MATCH_CASE_MARKER,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'route_decision', 'revise_path'),
                    ),
                    'root.route_decision': MatchJoinNode(
                        node_id='root.route_decision',
                        step_id='root.route_decision',
                        presentation_name='RouteDecision',
                        kind=ExecutableNodeKind.MATCH_JOIN,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'route_decision'),
                    ),
                },
            ),
        ),
        projection=WorkflowStateProjection(
            entries_by_node_id=MappingProxyType(
                {
                    'root.set_ready': CompatibilityNodeProjection(
                        node_id='root.set_ready',
                        step_id='root.set_ready',
                        presentation_key='SetReady',
                        display_name='SetReady',
                        region=WorkflowRegion.BODY,
                        compatibility_index=0,
                        step_definition=CompatibilityStepDefinition(report_kind='set_scalar'),
                    ),
                    'root.route_ready.approve_path.write_approved': CompatibilityNodeProjection(
                        node_id='root.route_ready.approve_path.write_approved',
                        step_id='root.route_ready.approve_path.write_approved',
                        presentation_key='RouteReady.then.WriteApproved',
                        display_name='RouteReady.then.WriteApproved',
                        region=WorkflowRegion.BODY,
                        compatibility_index=2,
                        step_definition=CompatibilityStepDefinition(report_kind='set_scalar'),
                    ),
                    'root.route_ready.approve_path': CompatibilityNodeProjection(
                        node_id='root.route_ready.approve_path',
                        step_id='root.route_ready.approve_path',
                        presentation_key='RouteReady.then',
                        display_name='RouteReady.then',
                        region=WorkflowRegion.BODY,
                        compatibility_index=1,
                        step_definition=CompatibilityStepDefinition(report_kind='structured_if_branch'),
                    ),
                    'root.route_ready.revise_path.write_revision': CompatibilityNodeProjection(
                        node_id='root.route_ready.revise_path.write_revision',
                        step_id='root.route_ready.revise_path.write_revision',
                        presentation_key='RouteReady.else.WriteRevision',
                        display_name='RouteReady.else.WriteRevision',
                        region=WorkflowRegion.BODY,
                        compatibility_index=4,
                        step_definition=CompatibilityStepDefinition(report_kind='set_scalar'),
                    ),
                    'root.route_ready.revise_path': CompatibilityNodeProjection(
                        node_id='root.route_ready.revise_path',
                        step_id='root.route_ready.revise_path',
                        presentation_key='RouteReady.else',
                        display_name='RouteReady.else',
                        region=WorkflowRegion.BODY,
                        compatibility_index=3,
                        step_definition=CompatibilityStepDefinition(report_kind='structured_if_branch'),
                    ),
                    'root.route_ready': CompatibilityNodeProjection(
                        node_id='root.route_ready',
                        step_id='root.route_ready',
                        presentation_key='RouteReady',
                        display_name='RouteReady',
                        region=WorkflowRegion.BODY,
                        compatibility_index=5,
                        step_definition=CompatibilityStepDefinition(report_kind='structured_if_join'),
                    ),
                    'root.route_decision.approve_path.echo_approved': CompatibilityNodeProjection(
                        node_id='root.route_decision.approve_path.echo_approved',
                        step_id='root.route_decision.approve_path.echo_approved',
                        presentation_key='RouteDecision.APPROVE.EchoApproved',
                        display_name='RouteDecision.APPROVE.EchoApproved',
                        region=WorkflowRegion.BODY,
                        compatibility_index=7,
                        step_definition=CompatibilityStepDefinition(
                            report_kind='command',
                            command=('bash', '-lc', "printf 'approved\\n'"),
                        ),
                    ),
                    'root.route_decision.approve_path': CompatibilityNodeProjection(
                        node_id='root.route_decision.approve_path',
                        step_id='root.route_decision.approve_path',
                        presentation_key='RouteDecision.APPROVE',
                        display_name='RouteDecision.APPROVE',
                        region=WorkflowRegion.BODY,
                        compatibility_index=6,
                        step_definition=CompatibilityStepDefinition(report_kind='structured_match_case'),
                    ),
                    'root.route_decision.revise_path.echo_revision': CompatibilityNodeProjection(
                        node_id='root.route_decision.revise_path.echo_revision',
                        step_id='root.route_decision.revise_path.echo_revision',
                        presentation_key='RouteDecision.REVISE.EchoRevision',
                        display_name='RouteDecision.REVISE.EchoRevision',
                        region=WorkflowRegion.BODY,
                        compatibility_index=9,
                        step_definition=CompatibilityStepDefinition(
                            report_kind='command',
                            command=('bash', '-lc', "printf 'revise\\n'"),
                        ),
                    ),
                    'root.route_decision.revise_path': CompatibilityNodeProjection(
                        node_id='root.route_decision.revise_path',
                        step_id='root.route_decision.revise_path',
                        presentation_key='RouteDecision.REVISE',
                        display_name='RouteDecision.REVISE',
                        region=WorkflowRegion.BODY,
                        compatibility_index=8,
                        step_definition=CompatibilityStepDefinition(report_kind='structured_match_case'),
                    ),
                    'root.route_decision': CompatibilityNodeProjection(
                        node_id='root.route_decision',
                        step_id='root.route_decision',
                        presentation_key='RouteDecision',
                        display_name='RouteDecision',
                        region=WorkflowRegion.BODY,
                        compatibility_index=10,
                        step_definition=CompatibilityStepDefinition(report_kind='structured_match_join'),
                    ),
                },
            ),
            node_id_by_compatibility_index=MappingProxyType(
                {
                    0: 'root.set_ready',
                    1: 'root.route_ready.approve_path',
                    2: 'root.route_ready.approve_path.write_approved',
                    3: 'root.route_ready.revise_path',
                    4: 'root.route_ready.revise_path.write_revision',
                    5: 'root.route_ready',
                    6: 'root.route_decision.approve_path',
                    7: 'root.route_decision.approve_path.echo_approved',
                    8: 'root.route_decision.revise_path',
                    9: 'root.route_decision.revise_path.echo_revision',
                    10: 'root.route_decision',
                },
            ),
            compatibility_index_by_node_id=MappingProxyType(
                {
                    'root.set_ready': 0,
                    'root.route_ready.approve_path': 1,
                    'root.route_ready.approve_path.write_approved': 2,
                    'root.route_ready.revise_path': 3,
                    'root.route_ready.revise_path.write_revision': 4,
                    'root.route_ready': 5,
                    'root.route_decision.approve_path': 6,
                    'root.route_decision.approve_path.echo_approved': 7,
                    'root.route_decision.revise_path': 8,
                    'root.route_decision.revise_path.echo_revision': 9,
                    'root.route_decision': 10,
                },
            ),
            presentation_key_by_node_id=MappingProxyType(
                {
                    'root.set_ready': 'SetReady',
                    'root.route_ready.approve_path.write_approved': 'RouteReady.then.WriteApproved',
                    'root.route_ready.approve_path': 'RouteReady.then',
                    'root.route_ready.revise_path.write_revision': 'RouteReady.else.WriteRevision',
                    'root.route_ready.revise_path': 'RouteReady.else',
                    'root.route_ready': 'RouteReady',
                    'root.route_decision.approve_path.echo_approved': 'RouteDecision.APPROVE.EchoApproved',
                    'root.route_decision.approve_path': 'RouteDecision.APPROVE',
                    'root.route_decision.revise_path.echo_revision': 'RouteDecision.REVISE.EchoRevision',
                    'root.route_decision.revise_path': 'RouteDecision.REVISE',
                    'root.route_decision': 'RouteDecision',
                },
            ),
            node_id_by_step_id=MappingProxyType(
                {
                    'root.set_ready': 'root.set_ready',
                    'root.route_ready.approve_path.write_approved': 'root.route_ready.approve_path.write_approved',
                    'root.route_ready.approve_path': 'root.route_ready.approve_path',
                    'root.route_ready.revise_path.write_revision': 'root.route_ready.revise_path.write_revision',
                    'root.route_ready.revise_path': 'root.route_ready.revise_path',
                    'root.route_ready': 'root.route_ready',
                    'root.route_decision.approve_path.echo_approved': 'root.route_decision.approve_path.echo_approved',
                    'root.route_decision.approve_path': 'root.route_decision.approve_path',
                    'root.route_decision.revise_path.echo_revision': 'root.route_decision.revise_path.echo_revision',
                    'root.route_decision.revise_path': 'root.route_decision.revise_path',
                    'root.route_decision': 'root.route_decision',
                },
            ),
            structured_if_branches=MappingProxyType(
                {
                    'root.route_ready': MappingProxyType(
                        {
                            'then': StructuredSelectionProjection(
                                marker_step_id='root.route_ready.approve_path',
                                marker_presentation_key='RouteReady.then',
                                step_presentation_keys=('RouteReady.then.WriteApproved',),
                            ),
                            'else': StructuredSelectionProjection(
                                marker_step_id='root.route_ready.revise_path',
                                marker_presentation_key='RouteReady.else',
                                step_presentation_keys=('RouteReady.else.WriteRevision',),
                            ),
                        },
                    ),
                },
            ),
            structured_match_cases=MappingProxyType(
                {
                    'root.route_decision': MappingProxyType(
                        {
                            'APPROVE': StructuredSelectionProjection(
                                marker_step_id='root.route_decision.approve_path',
                                marker_presentation_key='RouteDecision.APPROVE',
                                step_presentation_keys=('RouteDecision.APPROVE.EchoApproved',),
                            ),
                            'REVISE': StructuredSelectionProjection(
                                marker_step_id='root.route_decision.revise_path',
                                marker_presentation_key='RouteDecision.REVISE',
                                step_presentation_keys=('RouteDecision.REVISE.EchoRevision',),
                            ),
                        },
                    ),
                },
            ),
        ),
        runtime_plan=None,
        imports=MappingProxyType({}),
        provenance=WorkflowProvenance(
            workflow_path=Path('historical/obs-structured.orc'),
            source_root=Path('historical'),
        ),
    ),
    'prompt-2.20': LoadedWorkflowBundle(
        surface=SurfaceWorkflow(
            version='2.20',
            name='run-review',
            steps=(),
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/prompt-2.20.orc'),
                source_root=Path('historical'),
            ),
        ),
        core_workflow_ast=None,
        semantic_ir=None,
        ir=ExecutableWorkflow(
            schema_version='workflow_executable_ir.v1',
            version='2.20',
            name='run-review',
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/prompt-2.20.orc'),
                source_root=Path('historical'),
            ),
            body_region=('root.run_review__result',),
            finalization_region=(),
            finalization_entry_node_id=None,
            nodes=MappingProxyType(
                {
                    'root.run_review__result': LeafExecutableNode(
                        node_id='root.run_review__result',
                        step_id='root.run_review__result',
                        presentation_name='run-review__result',
                        kind=ExecutableNodeKind.PROVIDER,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'run_review__result'),
                    ),
                },
            ),
        ),
        projection=WorkflowStateProjection(
            entries_by_node_id=MappingProxyType(
                {
                    'root.run_review__result': CompatibilityNodeProjection(
                        node_id='root.run_review__result',
                        step_id='root.run_review__result',
                        presentation_key='run-review__result',
                        display_name='run-review__result',
                        region=WorkflowRegion.BODY,
                        compatibility_index=0,
                        step_definition=CompatibilityStepDefinition(
                            report_kind='provider',
                            provider='capturing-provider',
                        ),
                    ),
                },
            ),
            node_id_by_compatibility_index=MappingProxyType(
                {
                    0: 'root.run_review__result',
                },
            ),
            compatibility_index_by_node_id=MappingProxyType(
                {
                    'root.run_review__result': 0,
                },
            ),
            presentation_key_by_node_id=MappingProxyType(
                {
                    'root.run_review__result': 'run-review__result',
                },
            ),
            node_id_by_step_id=MappingProxyType(
                {
                    'root.run_review__result': 'root.run_review__result',
                },
            ),
        ),
        runtime_plan=None,
        imports=MappingProxyType({}),
        provenance=WorkflowProvenance(
            workflow_path=Path('historical/prompt-2.20.orc'),
            source_root=Path('historical'),
        ),
    ),
    'prompt-2.21': LoadedWorkflowBundle(
        surface=SurfaceWorkflow(
            version='2.21',
            name='run-review',
            steps=(),
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/prompt-2.21.orc'),
                source_root=Path('historical'),
            ),
        ),
        core_workflow_ast=None,
        semantic_ir=None,
        ir=ExecutableWorkflow(
            schema_version='workflow_executable_ir.v1',
            version='2.21',
            name='run-review',
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/prompt-2.21.orc'),
                source_root=Path('historical'),
            ),
            body_region=('root.run_review__result',),
            finalization_region=(),
            finalization_entry_node_id=None,
            nodes=MappingProxyType(
                {
                    'root.run_review__result': LeafExecutableNode(
                        node_id='root.run_review__result',
                        step_id='root.run_review__result',
                        presentation_name='run-review__result',
                        kind=ExecutableNodeKind.PROVIDER,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'run_review__result'),
                    ),
                },
            ),
        ),
        projection=WorkflowStateProjection(
            entries_by_node_id=MappingProxyType(
                {
                    'root.run_review__result': CompatibilityNodeProjection(
                        node_id='root.run_review__result',
                        step_id='root.run_review__result',
                        presentation_key='run-review__result',
                        display_name='run-review__result',
                        region=WorkflowRegion.BODY,
                        compatibility_index=0,
                        step_definition=CompatibilityStepDefinition(
                            report_kind='provider',
                            provider='capturing-provider',
                        ),
                    ),
                },
            ),
            node_id_by_compatibility_index=MappingProxyType(
                {
                    0: 'root.run_review__result',
                },
            ),
            compatibility_index_by_node_id=MappingProxyType(
                {
                    'root.run_review__result': 0,
                },
            ),
            presentation_key_by_node_id=MappingProxyType(
                {
                    'root.run_review__result': 'run-review__result',
                },
            ),
            node_id_by_step_id=MappingProxyType(
                {
                    'root.run_review__result': 'root.run_review__result',
                },
            ),
        ),
        runtime_plan=None,
        imports=MappingProxyType({}),
        provenance=WorkflowProvenance(
            workflow_path=Path('historical/prompt-2.21.orc'),
            source_root=Path('historical'),
        ),
    ),
    'prompt-2.22': LoadedWorkflowBundle(
        surface=SurfaceWorkflow(
            version='2.22',
            name='run-review',
            steps=(),
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/prompt-2.22.orc'),
                source_root=Path('historical'),
            ),
        ),
        core_workflow_ast=None,
        semantic_ir=None,
        ir=ExecutableWorkflow(
            schema_version='workflow_executable_ir.v1',
            version='2.22',
            name='run-review',
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/prompt-2.22.orc'),
                source_root=Path('historical'),
            ),
            body_region=('root.run_review__result',),
            finalization_region=(),
            finalization_entry_node_id=None,
            nodes=MappingProxyType(
                {
                    'root.run_review__result': LeafExecutableNode(
                        node_id='root.run_review__result',
                        step_id='root.run_review__result',
                        presentation_name='run-review__result',
                        kind=ExecutableNodeKind.PROVIDER,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'run_review__result'),
                    ),
                },
            ),
        ),
        projection=WorkflowStateProjection(
            entries_by_node_id=MappingProxyType(
                {
                    'root.run_review__result': CompatibilityNodeProjection(
                        node_id='root.run_review__result',
                        step_id='root.run_review__result',
                        presentation_key='run-review__result',
                        display_name='run-review__result',
                        region=WorkflowRegion.BODY,
                        compatibility_index=0,
                        step_definition=CompatibilityStepDefinition(
                            report_kind='provider',
                            provider='capturing-provider',
                            expected_outputs=(
                                MappingProxyType(
                                    {
                                        'name': 'report_path',
                                        'path': '${inputs.report_path}',
                                        'type': 'string',
                                        'required': True,
                                    },
                                ),
                            ),
                        ),
                    ),
                },
            ),
            node_id_by_compatibility_index=MappingProxyType(
                {
                    0: 'root.run_review__result',
                },
            ),
            compatibility_index_by_node_id=MappingProxyType(
                {
                    'root.run_review__result': 0,
                },
            ),
            presentation_key_by_node_id=MappingProxyType(
                {
                    'root.run_review__result': 'run-review__result',
                },
            ),
            node_id_by_step_id=MappingProxyType(
                {
                    'root.run_review__result': 'root.run_review__result',
                },
            ),
        ),
        runtime_plan=None,
        imports=MappingProxyType({}),
        provenance=WorkflowProvenance(
            workflow_path=Path('historical/prompt-2.22.orc'),
            source_root=Path('historical'),
        ),
    ),
    'prompt-2.23': LoadedWorkflowBundle(
        surface=SurfaceWorkflow(
            version='2.23',
            name='run-review',
            steps=(),
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/prompt-2.23.orc'),
                source_root=Path('historical'),
            ),
        ),
        core_workflow_ast=None,
        semantic_ir=None,
        ir=ExecutableWorkflow(
            schema_version='workflow_executable_ir.v1',
            version='2.23',
            name='run-review',
            provenance=WorkflowProvenance(
                workflow_path=Path('historical/prompt-2.23.orc'),
                source_root=Path('historical'),
            ),
            body_region=('root.run_review__result',),
            finalization_region=(),
            finalization_entry_node_id=None,
            nodes=MappingProxyType(
                {
                    'root.run_review__result': LeafExecutableNode(
                        node_id='root.run_review__result',
                        step_id='root.run_review__result',
                        presentation_name='run-review__result',
                        kind=ExecutableNodeKind.PROVIDER,
                        region=WorkflowRegion.BODY,
                        lexical_scope=('root', 'run_review__result'),
                    ),
                },
            ),
        ),
        projection=WorkflowStateProjection(
            entries_by_node_id=MappingProxyType(
                {
                    'root.run_review__result': CompatibilityNodeProjection(
                        node_id='root.run_review__result',
                        step_id='root.run_review__result',
                        presentation_key='run-review__result',
                        display_name='run-review__result',
                        region=WorkflowRegion.BODY,
                        compatibility_index=0,
                        step_definition=CompatibilityStepDefinition(
                            report_kind='provider',
                            provider='capturing-provider',
                            expected_outputs=(
                                MappingProxyType(
                                    {
                                        'name': 'report_path',
                                        'path': '${inputs.report_path}',
                                        'type': 'string',
                                        'required': True,
                                    },
                                ),
                            ),
                        ),
                    ),
                },
            ),
            node_id_by_compatibility_index=MappingProxyType(
                {
                    0: 'root.run_review__result',
                },
            ),
            compatibility_index_by_node_id=MappingProxyType(
                {
                    'root.run_review__result': 0,
                },
            ),
            presentation_key_by_node_id=MappingProxyType(
                {
                    'root.run_review__result': 'run-review__result',
                },
            ),
            node_id_by_step_id=MappingProxyType(
                {
                    'root.run_review__result': 'root.run_review__result',
                },
            ),
        ),
        runtime_plan=None,
        imports=MappingProxyType({}),
        provenance=WorkflowProvenance(
            workflow_path=Path('historical/prompt-2.23.orc'),
            source_root=Path('historical'),
        ),
    ),
}
