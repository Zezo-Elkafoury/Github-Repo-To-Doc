"""LangGraph workflow assembly."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from github_to_docs.graph.nodes import (
    acquire_repository,
    finalize_output,
    generate_documentation,
    inspect_repository,
    plan_documentation,
    prepare_evidence,
    select_revision_target,
    should_revise,
    validate_request,
    verify_documentation,
)
from github_to_docs.graph.state import GraphState


def build_graph(
    planner,
    generator,
    verifier,
) -> StateGraph:
    """Build the LangGraph workflow.

    Structure:
        Validate → Acquire → Inspect → Plan → Prepare Evidence → Generate → Verify
            → (revise: targeted section → Generate) | finalize → END
    """
    workflow = StateGraph(GraphState)

    # Nodes with injected dependencies.
    workflow.add_node("validate_request", validate_request)
    workflow.add_node("acquire_repository", acquire_repository)
    workflow.add_node("inspect_repository", inspect_repository)
    workflow.add_node(
        "plan_documentation",
        lambda state: plan_documentation(state, planner),
    )
    workflow.add_node("prepare_evidence", prepare_evidence)
    workflow.add_node(
        "generate_documentation",
        lambda state: generate_documentation(state, generator),
    )
    workflow.add_node(
        "verify_documentation",
        lambda state: verify_documentation(state, verifier),
    )
    workflow.add_node("select_revision_target", select_revision_target)
    workflow.add_node("finalize_output", finalize_output)

    # Edges.
    workflow.add_edge("validate_request", "acquire_repository")
    workflow.add_edge("acquire_repository", "inspect_repository")
    workflow.add_edge("inspect_repository", "plan_documentation")
    workflow.add_edge("plan_documentation", "prepare_evidence")
    workflow.add_edge("prepare_evidence", "generate_documentation")
    workflow.add_edge("generate_documentation", "verify_documentation")

    # Conditional: revise targeted section or finalize.
    workflow.add_conditional_edges(
        "verify_documentation",
        should_revise,
        {
            "revise": "select_revision_target",
            "finalize": "finalize_output",
        },
    )

    # After targeted revision, loop back to generate (only that section).
    workflow.add_edge("select_revision_target", "generate_documentation")
    workflow.add_edge("finalize_output", END)

    workflow.set_entry_point("validate_request")
    return workflow


__all__ = ["build_graph"]
