from __future__ import annotations

import asyncio

import pytest

from af_core.runtime.tool_call_models import (
    NormalizedToolCall,
)
from af_core.runtime.tool_call_runtime import (
    ToolCallRuntime,
    ToolCallRuntimeError,
)
from af_core.tools.ecosystem_models import (
    AgentToolRequirement,
    CapabilityKind,
    CompatibilityStatus,
    ProjectToolBundle,
    ToolCapability,
    ToolCompatibility,
    ToolHealthRecord,
    ToolHealthState,
    ToolInstallationRecord,
    ToolInstallationState,
    ToolManifest,
    ToolTrustLevel,
)
from af_core.tools.ecosystem_registry import (
    ToolEcosystemRegistry,
)
from af_core.tools.models import (
    ExternalToolCall,
    ExternalToolDescriptor,
    ExternalToolResult,
    ExternalToolRisk,
    ToolContent,
    ToolContentType,
    ToolExecutionStatus,
)
from af_core.tools.registry import (
    ExternalToolRegistry,
    ExternalToolRegistryError,
)
from af_core.tools.tool_provisioning import (
    AgentToolProvisionRequest,
    AgentToolProvisioner,
    ProjectToolBundleActivationRegistry,
    RuntimeToolRegistryBridge,
    ToolProvisionStatus,
)


async def echo_handler(
    call: ExternalToolCall,
) -> ExternalToolResult:
    return ExternalToolResult(
        call_id=call.call_id,
        tool_id=call.tool_id,
        status=ToolExecutionStatus.SUCCEEDED,
        content=[
            ToolContent(
                type=ToolContentType.JSON,
                json_value={
                    "message": call.arguments[
                        "message"
                    ],
                    "project_id": call.project_id,
                    "agent_name": call.agent_name,
                },
            )
        ],
    )


def external_descriptor() -> ExternalToolDescriptor:
    return ExternalToolDescriptor(
        tool_id="tool.echo",
        name="echo",
        description="Echo message",
        input_schema={
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                }
            },
            "required": ["message"],
            "additionalProperties": False,
        },
        risk=ExternalToolRisk.READ_ONLY,
    )


def ecosystem_manifest() -> ToolManifest:
    return ToolManifest(
        tool_id="tool.echo",
        name="Echo",
        version="1.0.0",
        risk=ExternalToolRisk.READ_ONLY,
        trust_level=ToolTrustLevel.FIRST_PARTY,
        allowed_roles={"reviewer"},
        capabilities=[
            ToolCapability(
                capability_id="communication.echo",
                kind=CapabilityKind.CUSTOM,
                name="Echo",
                operations={"echo"},
            )
        ],
        compatibility=ToolCompatibility(
            status=CompatibilityStatus.COMPATIBLE
        ),
    )


def setup_runtime():
    source = ExternalToolRegistry()

    source.register(
        descriptor=external_descriptor(),
        handler=echo_handler,
    )

    ecosystem = ToolEcosystemRegistry()

    ecosystem.register_tool(
        ecosystem_manifest(),
        installation=ToolInstallationRecord(
            ecosystem_id="tool.echo",
            state=ToolInstallationState.INSTALLED,
            installed_version="1.0.0",
        ),
        health=ToolHealthRecord(
            ecosystem_id="tool.echo",
            state=ToolHealthState.HEALTHY,
        ),
    )

    ecosystem.register_bundle(
        ProjectToolBundle(
            bundle_id="bundle-review",
            project_id="project-1",
            name="Review Tools",
            tool_ids=["tool.echo"],
        )
    )

    activations = (
        ProjectToolBundleActivationRegistry()
    )

    activations.activate(
        project_id="project-1",
        bundle_id="bundle-review",
    )

    provisioner = AgentToolProvisioner(
        ecosystem=ecosystem,
        activations=activations,
    )

    bridge = RuntimeToolRegistryBridge(
        source_registry=source
    )

    return (
        source,
        ecosystem,
        activations,
        provisioner,
        bridge,
    )


def provision_request(
    *,
    role: str = "reviewer",
    capability: str = "communication.echo",
) -> AgentToolProvisionRequest:
    return AgentToolProvisionRequest(
        project_id="project-1",
        agent_id=f"agent-{role}",
        role=role,
        requirement=AgentToolRequirement(
            role=role,
            required_capabilities={
                capability,
            },
            minimum_trust_level=(
                ToolTrustLevel.VERIFIED
            ),
            maximum_risk=(
                ExternalToolRisk.READ_ONLY
            ),
        ),
    )


def test_provision_succeeds_for_matching_role() -> None:
    (
        source,
        ecosystem,
        activations,
        provisioner,
        bridge,
    ) = setup_runtime()

    del source, ecosystem, activations, bridge

    result = provisioner.provision(
        provision_request()
    )

    assert result.status is (
        ToolProvisionStatus.SUCCEEDED
    )
    assert result.successful is True
    assert result.selected_tool_ids == [
        "tool.echo",
    ]
    assert result.runtime_tool_ids == [
        "tool.echo",
    ]
    assert (
        result.missing_required_capabilities
        == set()
    )
    assert result.warnings == []


def test_provision_blocks_when_capability_missing() -> None:
    (
        source,
        ecosystem,
        activations,
        provisioner,
        bridge,
    ) = setup_runtime()

    del source, ecosystem, activations, bridge

    result = provisioner.provision(
        provision_request(
            capability="filesystem.write",
        )
    )

    assert result.status is (
        ToolProvisionStatus.BLOCKED
    )
    assert result.successful is False
    assert result.selected_tool_ids == []
    assert result.runtime_tool_ids == []
    assert (
        result.missing_required_capabilities
        == {
            "filesystem.write",
        }
    )
    assert result.warnings


def test_provision_blocks_when_role_not_allowed() -> None:
    (
        source,
        ecosystem,
        activations,
        provisioner,
        bridge,
    ) = setup_runtime()

    del source, ecosystem, activations, bridge

    result = provisioner.provision(
        provision_request(
            role="tester",
        )
    )

    assert result.status is (
        ToolProvisionStatus.BLOCKED
    )
    assert result.successful is False
    assert result.selected_tool_ids == []
    assert (
        result.missing_required_capabilities
        == {
            "communication.echo",
        }
    )


def test_runtime_view_executes_only_provisioned_tool() -> None:
    (
        source,
        ecosystem,
        activations,
        provisioner,
        bridge,
    ) = setup_runtime()

    del ecosystem, activations

    result = provisioner.provision(
        provision_request()
    )

    view = bridge.provision(result)

    assert view.allowed_tool_ids() == [
        "tool.echo",
    ]
    assert view.contains("tool.echo") is True
    assert view.get("tool.echo").name == "echo"

    response = asyncio.run(
        view.execute(
            ExternalToolCall(
                call_id="call-1",
                tool_id="tool.echo",
                arguments={
                    "message": "hello",
                },
            )
        )
    )

    assert response.status is (
        ToolExecutionStatus.SUCCEEDED
    )

    content = response.content[0].json_value

    assert content == {
        "message": "hello",
        "project_id": "project-1",
        "agent_name": "agent-reviewer",
    }

    assert source.get("tool.echo").name == "echo"


def test_runtime_view_blocks_unprovisioned_tool() -> None:
    (
        source,
        ecosystem,
        activations,
        provisioner,
        bridge,
    ) = setup_runtime()

    del ecosystem, activations

    source.register(
        descriptor=ExternalToolDescriptor(
            tool_id="tool.hidden",
            name="hidden",
            description="Hidden Tool",
            input_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            risk=ExternalToolRisk.READ_ONLY,
        ),
        handler=echo_handler,
    )

    result = provisioner.provision(
        provision_request()
    )

    view = bridge.provision(result)

    assert view.contains("tool.hidden") is False

    with pytest.raises(
        ExternalToolRegistryError,
        match="not provisioned",
    ):
        view.get("tool.hidden")


def test_runtime_bridge_release_removes_agent_view() -> None:
    (
        source,
        ecosystem,
        activations,
        provisioner,
        bridge,
    ) = setup_runtime()

    del source, ecosystem, activations

    result = provisioner.provision(
        provision_request()
    )

    bridge.provision(result)

    assert bridge.contains_view(
        project_id="project-1",
        agent_id="agent-reviewer",
    )
    assert bridge.list_agent_ids(
        "project-1"
    ) == [
        "agent-reviewer",
    ]

    removed = bridge.release(
        project_id="project-1",
        agent_id="agent-reviewer",
    )

    assert removed == ["tool.echo"]
    assert bridge.contains_view(
        project_id="project-1",
        agent_id="agent-reviewer",
    ) is False


def test_runtime_view_executes_through_tool_call_runtime() -> None:
    (
        source,
        ecosystem,
        activations,
        provisioner,
        bridge,
    ) = setup_runtime()

    del source, ecosystem, activations

    provision = provisioner.provision(
        provision_request()
    )

    view = bridge.provision(provision)

    runtime = ToolCallRuntime(
        registry=view,
    )

    record = asyncio.run(
        runtime.execute_one(
            NormalizedToolCall(
                call_id="provider-call-1",
                tool_name="echo",
                arguments={
                    "message": (
                        "provider tool runtime"
                    ),
                },
            ),
            project_id="project-override",
            agent_name="agent-override",
        )
    )

    assert record.successful is True
    assert record.external_call.tool_id == (
        "tool.echo"
    )
    assert record.result.status is (
        ToolExecutionStatus.SUCCEEDED
    )

    payload = (
        record.result
        .content[0]
        .json_value
    )

    assert payload == {
        "message": "provider tool runtime",
        "project_id": "project-override",
        "agent_name": "agent-override",
    }


def test_runtime_view_blocks_unprovisioned_tool_call_runtime() -> None:
    (
        source,
        ecosystem,
        activations,
        provisioner,
        bridge,
    ) = setup_runtime()

    del ecosystem, activations

    source.register(
        descriptor=ExternalToolDescriptor(
            tool_id="tool.hidden",
            name="hidden",
            description="Hidden Tool",
            input_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            risk=ExternalToolRisk.READ_ONLY,
        ),
        handler=echo_handler,
    )

    provision = provisioner.provision(
        provision_request()
    )

    view = bridge.provision(provision)

    runtime = ToolCallRuntime(
        registry=view,
    )

    with pytest.raises(
        ToolCallRuntimeError,
        match="No external tool is registered",
    ):
        asyncio.run(
            runtime.execute_one(
                NormalizedToolCall(
                    call_id="provider-call-hidden",
                    tool_name="hidden",
                    arguments={},
                )
            )
        )
