from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from af_core.tools.mcp_manager import MCPServerManager
from af_core.tools.mcp_models import MCPServerConfig
from af_core.tools.models import (
    ExternalToolCall,
    ExternalToolRisk,
    ExternalToolTransport,
    ToolContentType,
    ToolExecutionStatus,
)
from af_core.tools.policy import ExternalToolPolicy
from af_core.tools.registry import (
    ExternalToolRegistry,
    ExternalToolRegistryError,
)


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "tests" / "fixtures" / "mcp_test_server.py"


def config() -> MCPServerConfig:
    return MCPServerConfig(
        server_id="test-server",
        transport=ExternalToolTransport.MCP_STDIO,
        command=sys.executable,
        arguments=[str(SERVER)],
        timeout_seconds=10,
    )


def test_real_mcp_stdio_discovery_call_and_disconnect() -> None:
    async def run() -> None:
        registry = ExternalToolRegistry(
            policy=ExternalToolPolicy(
                maximum_risk=(
                    ExternalToolRisk.WORKSPACE_WRITE
                ),
            )
        )

        manager = MCPServerManager(
            registry=registry
        )

        managed = await manager.connect_stdio(
            config=config(),
            risk_by_tool={
                "echo_text": ExternalToolRisk.READ_ONLY,
                "add_numbers": ExternalToolRisk.READ_ONLY,
                "fail_tool": ExternalToolRisk.READ_ONLY,
            },
        )

        try:
            assert managed.client.connected is True
            assert await manager.ping(
                "test-server"
            ) is True

            tool_ids = {
                item.tool_id
                for item in registry.list()
            }

            assert tool_ids == {
                "mcp:test-server:echo_text",
                "mcp:test-server:add_numbers",
                "mcp:test-server:fail_tool",
            }

            echo = await registry.execute(
                ExternalToolCall(
                    call_id="call-echo",
                    tool_id=(
                        "mcp:test-server:echo_text"
                    ),
                    arguments={
                        "message": "AF-CORE-MCP-OK",
                    },
                )
            )

            assert (
                echo.status
                is ToolExecutionStatus.SUCCEEDED
            )
            assert echo.is_error is False
            assert any(
                item.type is ToolContentType.TEXT
                and item.text == "AF-CORE-MCP-OK"
                for item in echo.content
            )

            addition = await registry.execute(
                ExternalToolCall(
                    call_id="call-add",
                    tool_id=(
                        "mcp:test-server:add_numbers"
                    ),
                    arguments={
                        "left": 7,
                        "right": 8,
                    },
                )
            )

            assert (
                addition.status
                is ToolExecutionStatus.SUCCEEDED
            )
            assert addition.is_error is False

            structured = [
                item.json_value
                for item in addition.content
                if item.type is ToolContentType.JSON
            ]

            assert structured
            assert structured[0] == {
                "left": 7,
                "right": 8,
                "total": 15,
            }

            failed = await registry.execute(
                ExternalToolCall(
                    call_id="call-fail",
                    tool_id=(
                        "mcp:test-server:fail_tool"
                    ),
                    arguments={
                        "message": "expected failure",
                    },
                )
            )

            assert (
                failed.status
                is ToolExecutionStatus.FAILED
            )
            assert failed.is_error is True
            assert "expected failure" in (
                failed.error or ""
            )

            audit = registry.audit_records()

            assert len(audit) == 3
            assert {
                item.call.call_id
                for item in audit
            } == {
                "call-echo",
                "call-add",
                "call-fail",
            }

        finally:
            await manager.disconnect(
                "test-server"
            )

        assert manager.list_server_ids() == []
        assert registry.list() == []

        with pytest.raises(
            ExternalToolRegistryError,
            match="Unknown external tool",
        ):
            registry.get(
                "mcp:test-server:echo_text"
            )

    asyncio.run(run())


def test_real_mcp_stdio_argument_validation_before_remote_call() -> None:
    async def run() -> None:
        registry = ExternalToolRegistry()
        manager = MCPServerManager(
            registry=registry
        )

        await manager.connect_stdio(
            config=config()
        )

        try:
            result = await registry.execute(
                ExternalToolCall(
                    call_id="call-invalid",
                    tool_id=(
                        "mcp:test-server:add_numbers"
                    ),
                    arguments={
                        "left": "seven",
                        "right": 8,
                    },
                )
            )

            assert (
                result.status
                is ToolExecutionStatus.FAILED
            )
            assert result.is_error is True
            assert "must be integer" in (
                result.error or ""
            )

        finally:
            await manager.close_all()

    asyncio.run(run())


def test_real_mcp_stdio_duplicate_server_connection_blocked() -> None:
    async def run() -> None:
        registry = ExternalToolRegistry()
        manager = MCPServerManager(
            registry=registry
        )

        await manager.connect_stdio(
            config=config()
        )

        try:
            from af_core.tools.mcp_manager import (
                MCPServerManagerError,
            )

            with pytest.raises(
                MCPServerManagerError,
                match="already connected",
            ):
                await manager.connect_stdio(
                    config=config()
                )

        finally:
            await manager.close_all()

    asyncio.run(run())
