from __future__ import annotations

from af_core.factory_runtime import (
    AgentFactoryRuntime,
    FactoryRequest,
)


def test_factory_runtime_full_lifecycle():

    runtime = AgentFactoryRuntime(
        planner=None,
        optimizer=None,
        decision_loop=None,
    )

    result = runtime.run(
        FactoryRequest(
            project_name=
            "D5 Virtual Go Dojo",

            requirements=[
                "GSOS",
                "Spatial",
                "AI",
                "Tournament",
            ],
        )
    )

    assert result.status == "completed"

    assert (
        "planning"
        in result.stages
    )

    assert (
        "knowledge_selection"
        in result.stages
    )

    assert (
        "adr_analysis"
        in result.stages
    )

    assert (
        "optimization"
        in result.stages
    )

    assert (
        "agent_execution"
        in result.stages
    )

    assert (
        "audit_validation"
        in result.stages
    )

    assert (
        "learning_feedback"
        in result.stages
    )

    assert (
        "self_improvement"
        in result.stages
    )


def test_factory_supports_web3_project_flow():

    runtime = AgentFactoryRuntime(
        planner=None,
        optimizer=None,
        decision_loop=None,
    )


    result = runtime.run(
        FactoryRequest(
            project_name=
            "TOBMATE Web3 Platform",

            requirements=[
                "Blockchain",
                "GSOS",
                "Agent",
            ],
        )
    )


    assert result.project_name == (
        "TOBMATE Web3 Platform"
    )

    assert len(
        result.stages
    ) > 5
