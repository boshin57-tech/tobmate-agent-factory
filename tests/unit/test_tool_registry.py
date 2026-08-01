import pytest

from af_core.runtime.tool_registry import (
    ToolDefinition,
    ToolRegistry,
    ToolRegistryError,
    ToolRiskLevel,
)


def handler(**kwargs):
    return kwargs


def test_tool_registry_authorizes_expected_role() -> None:
    registry = ToolRegistry()

    registry.register(
        ToolDefinition(
            name="read_file",
            description="Read a workspace file",
            risk_level=ToolRiskLevel.READ_ONLY,
            handler=handler,
            allowed_roles=frozenset(
                {"planner", "implementer", "tester", "reviewer"}
            ),
        )
    )

    tool = registry.authorize(
        tool_name="read_file",
        agent_role="implementer",
        allowed_tools={"read_file"},
        maximum_risk=ToolRiskLevel.WORKSPACE_MUTATION,
    )

    assert tool.name == "read_file"


def test_tool_registry_blocks_unlisted_tool() -> None:
    registry = ToolRegistry()

    registry.register(
        ToolDefinition(
            name="write_file",
            description="Write a workspace file",
            risk_level=ToolRiskLevel.WORKSPACE_MUTATION,
            handler=handler,
            allowed_roles=frozenset({"implementer"}),
        )
    )

    with pytest.raises(ToolRegistryError):
        registry.authorize(
            tool_name="write_file",
            agent_role="implementer",
            allowed_tools={"read_file"},
            maximum_risk=ToolRiskLevel.WORKSPACE_MUTATION,
        )


def test_tool_registry_blocks_role_and_risk() -> None:
    registry = ToolRegistry()

    registry.register(
        ToolDefinition(
            name="write_file",
            description="Write a workspace file",
            risk_level=ToolRiskLevel.WORKSPACE_MUTATION,
            handler=handler,
            allowed_roles=frozenset({"implementer"}),
        )
    )

    with pytest.raises(ToolRegistryError):
        registry.authorize(
            tool_name="write_file",
            agent_role="reviewer",
            allowed_tools={"write_file"},
            maximum_risk=ToolRiskLevel.WORKSPACE_MUTATION,
        )

    with pytest.raises(ToolRegistryError):
        registry.authorize(
            tool_name="write_file",
            agent_role="implementer",
            allowed_tools={"write_file"},
            maximum_risk=ToolRiskLevel.READ_ONLY,
        )


def test_duplicate_tool_registration_is_rejected() -> None:
    registry = ToolRegistry()
    definition = ToolDefinition(
        name="read_file",
        description="Read file",
        risk_level=ToolRiskLevel.READ_ONLY,
        handler=handler,
        allowed_roles=frozenset({"planner"}),
    )

    registry.register(definition)

    with pytest.raises(ToolRegistryError):
        registry.register(definition)
