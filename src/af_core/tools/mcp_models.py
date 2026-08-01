from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .models import (
    ExternalToolDescriptor,
    ExternalToolRisk,
    ExternalToolTransport,
    ToolContent,
    ToolContentType,
)


class MCPServerConfig(BaseModel):
    server_id: str
    transport: ExternalToolTransport
    command: str | None = None
    arguments: list[str] = Field(
        default_factory=list
    )
    environment: dict[str, str] = Field(
        default_factory=dict
    )
    url: str | None = None
    headers: dict[str, str] = Field(
        default_factory=dict
    )
    timeout_seconds: float = Field(
        default=60.0,
        gt=0,
        le=3600,
    )
    enabled: bool = True
    metadata: dict[str, Any] = Field(
        default_factory=dict
    )


class MCPToolDefinition(BaseModel):
    name: str
    title: str | None = None
    description: str = ""

    inputSchema: dict[str, Any] = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {},
        }
    )

    outputSchema: dict[str, Any] | None = None
    annotations: dict[str, Any] | None = None

    meta: dict[str, Any] | None = Field(
        default=None,
        alias="_meta",
    )

    def to_external_descriptor(
        self,
        *,
        server_id: str,
        risk: ExternalToolRisk = (
            ExternalToolRisk.READ_ONLY
        ),
        transport: ExternalToolTransport,
    ) -> ExternalToolDescriptor:
        return ExternalToolDescriptor(
            tool_id=(
                f"mcp:{server_id}:{self.name}"
            ),
            name=self.name,
            description=self.description,
            input_schema=self.inputSchema,
            output_schema=self.outputSchema,
            risk=risk,
            transport=transport,
            server_id=server_id,
            tags={
                "mcp",
                server_id,
            },
            metadata={
                "title": self.title,
                "annotations": self.annotations,
                "_meta": self.meta,
            },
        )


class MCPToolCallResult(BaseModel):
    content: list[
        dict[str, Any]
    ] = Field(
        default_factory=list
    )

    structuredContent: dict[
        str,
        Any,
    ] | None = None

    isError: bool = False

    meta: dict[str, Any] | None = Field(
        default=None,
        alias="_meta",
    )

    def normalized_content(
        self,
    ) -> list[ToolContent]:
        normalized: list[
            ToolContent
        ] = []

        for item in self.content:
            item_type = item.get("type")

            if item_type == "text":
                normalized.append(
                    ToolContent(
                        type=ToolContentType.TEXT,
                        text=item.get("text"),
                    )
                )

            elif item_type == "resource_link":
                normalized.append(
                    ToolContent(
                        type=(
                            ToolContentType.RESOURCE
                        ),
                        uri=item.get("uri"),
                        mime_type=item.get(
                            "mimeType"
                        ),
                        metadata={
                            "name": item.get(
                                "name"
                            ),
                        },
                    )
                )

            elif item_type == "image":
                normalized.append(
                    ToolContent(
                        type=ToolContentType.IMAGE,
                        mime_type=item.get(
                            "mimeType"
                        ),
                        metadata={
                            "data": item.get(
                                "data"
                            ),
                        },
                    )
                )

        if self.structuredContent is not None:
            normalized.append(
                ToolContent(
                    type=ToolContentType.JSON,
                    json_value=(
                        self.structuredContent
                    ),
                )
            )

        return normalized
