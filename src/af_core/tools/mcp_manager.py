from __future__ import annotations

from dataclasses import dataclass, field

from .mcp_models import MCPServerConfig
from .mcp_stdio_client import (
    MCPClientError,
    MCPStdioClient,
)
from .models import (
    ExternalToolRisk,
    ExternalToolTransport,
)
from .registry import (
    ExternalToolRegistry,
    ExternalToolRegistryError,
)


class MCPServerManagerError(RuntimeError):
    """Raised when MCP server lifecycle management fails."""


@dataclass
class ManagedMCPServer:
    config: MCPServerConfig
    client: MCPStdioClient
    registered_tool_ids: set[str] = field(
        default_factory=set
    )


class MCPServerManager:
    def __init__(
        self,
        *,
        registry: ExternalToolRegistry,
    ) -> None:
        self.registry = registry
        self._servers: dict[
            str,
            ManagedMCPServer,
        ] = {}

    def contains(
        self,
        server_id: str,
    ) -> bool:
        return server_id in self._servers

    def list_server_ids(self) -> list[str]:
        return sorted(self._servers)

    def get(
        self,
        server_id: str,
    ) -> ManagedMCPServer:
        try:
            return self._servers[server_id]
        except KeyError as exc:
            raise MCPServerManagerError(
                f"MCP server is not managed: {server_id}"
            ) from exc

    async def connect_stdio(
        self,
        *,
        config: MCPServerConfig,
        default_risk: ExternalToolRisk = (
            ExternalToolRisk.READ_ONLY
        ),
        risk_by_tool: dict[
            str,
            ExternalToolRisk,
        ] | None = None,
    ) -> ManagedMCPServer:
        if (
            config.transport
            is not ExternalToolTransport.MCP_STDIO
        ):
            raise MCPServerManagerError(
                "connect_stdio requires MCP_STDIO transport."
            )

        if config.server_id in self._servers:
            raise MCPServerManagerError(
                f"MCP server already connected: "
                f"{config.server_id}"
            )

        client = MCPStdioClient(config)

        try:
            await client.connect()

            descriptors = await client.tool_descriptors(
                default_risk=default_risk,
                risk_by_tool=risk_by_tool,
            )

            managed = ManagedMCPServer(
                config=config,
                client=client,
            )

            for descriptor in descriptors:
                remote_tool_name = descriptor.name

                self.registry.register(
                    descriptor=descriptor,
                    handler=client.handler(
                        remote_tool_name=remote_tool_name
                    ),
                )

                managed.registered_tool_ids.add(
                    descriptor.tool_id
                )

        except Exception as exc:
            await self._rollback_client(
                client=client,
                registered_tool_ids=locals().get(
                    "managed",
                    ManagedMCPServer(
                        config=config,
                        client=client,
                    ),
                ).registered_tool_ids,
            )

            if isinstance(
                exc,
                (
                    MCPClientError,
                    ExternalToolRegistryError,
                    MCPServerManagerError,
                ),
            ):
                raise

            raise MCPServerManagerError(
                f"Unable to connect MCP server "
                f"{config.server_id}: {exc}"
            ) from exc

        self._servers[config.server_id] = managed
        return managed

    async def refresh_tools(
        self,
        server_id: str,
        *,
        default_risk: ExternalToolRisk = (
            ExternalToolRisk.READ_ONLY
        ),
        risk_by_tool: dict[
            str,
            ExternalToolRisk,
        ] | None = None,
    ) -> ManagedMCPServer:
        managed = self.get(server_id)

        discovered = await managed.client.tool_descriptors(
            default_risk=default_risk,
            risk_by_tool=risk_by_tool,
        )

        discovered_by_id = {
            descriptor.tool_id: descriptor
            for descriptor in discovered
        }

        stale_ids = (
            managed.registered_tool_ids
            - set(discovered_by_id)
        )

        for tool_id in sorted(stale_ids):
            self.registry.unregister(tool_id)
            managed.registered_tool_ids.remove(tool_id)

        new_ids = (
            set(discovered_by_id)
            - managed.registered_tool_ids
        )

        for tool_id in sorted(new_ids):
            descriptor = discovered_by_id[tool_id]

            self.registry.register(
                descriptor=descriptor,
                handler=managed.client.handler(
                    remote_tool_name=descriptor.name
                ),
            )

            managed.registered_tool_ids.add(tool_id)

        return managed

    async def disconnect(
        self,
        server_id: str,
    ) -> None:
        managed = self.get(server_id)

        errors: list[str] = []

        for tool_id in sorted(
            managed.registered_tool_ids
        ):
            try:
                self.registry.unregister(tool_id)
            except Exception as exc:
                errors.append(
                    f"unregister {tool_id}: {exc}"
                )

        try:
            await managed.client.close()
        except Exception as exc:
            errors.append(
                f"close {server_id}: {exc}"
            )

        self._servers.pop(server_id, None)

        if errors:
            raise MCPServerManagerError(
                "; ".join(errors)
            )

    async def close_all(self) -> None:
        errors: list[str] = []

        for server_id in list(
            self.list_server_ids()
        ):
            try:
                await self.disconnect(server_id)
            except Exception as exc:
                errors.append(
                    f"{server_id}: {exc}"
                )

        if errors:
            raise MCPServerManagerError(
                "One or more MCP servers failed to close: "
                + "; ".join(errors)
            )

    async def ping(
        self,
        server_id: str,
    ) -> bool:
        return await self.get(
            server_id
        ).client.ping()

    async def _rollback_client(
        self,
        *,
        client: MCPStdioClient,
        registered_tool_ids: set[str],
    ) -> None:
        for tool_id in sorted(
            registered_tool_ids
        ):
            try:
                self.registry.unregister(tool_id)
            except Exception:
                pass

        try:
            await client.close()
        except Exception:
            pass
