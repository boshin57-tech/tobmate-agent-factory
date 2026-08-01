from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class MCPResourceContentType(StrEnum):
    TEXT = "TEXT"
    BLOB = "BLOB"


class MCPResourceDescriptor(BaseModel):
    uri: str
    name: str
    title: str | None = None
    description: str | None = None
    mime_type: str | None = None
    size: int | None = Field(
        default=None,
        ge=0,
    )
    annotations: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None


class MCPResourceTemplateDescriptor(BaseModel):
    uri_template: str
    name: str
    title: str | None = None
    description: str | None = None
    mime_type: str | None = None
    annotations: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None


class MCPResourceContent(BaseModel):
    uri: str
    type: MCPResourceContentType
    mime_type: str | None = None
    text: str | None = None
    blob: str | None = None
    meta: dict[str, Any] | None = None


class MCPResourceReadResult(BaseModel):
    uri: str
    contents: list[MCPResourceContent] = Field(
        default_factory=list
    )
    meta: dict[str, Any] | None = None


class MCPPromptArgumentDescriptor(BaseModel):
    name: str
    description: str | None = None
    required: bool = False


class MCPPromptDescriptor(BaseModel):
    name: str
    title: str | None = None
    description: str | None = None
    arguments: list[
        MCPPromptArgumentDescriptor
    ] = Field(default_factory=list)
    meta: dict[str, Any] | None = None


class MCPPromptContentType(StrEnum):
    TEXT = "TEXT"
    IMAGE = "IMAGE"
    AUDIO = "AUDIO"
    EMBEDDED_RESOURCE = "EMBEDDED_RESOURCE"
    RESOURCE_LINK = "RESOURCE_LINK"
    UNKNOWN = "UNKNOWN"


class MCPPromptContent(BaseModel):
    type: MCPPromptContentType
    text: str | None = None
    data: str | None = None
    mime_type: str | None = None
    uri: str | None = None
    name: str | None = None
    raw: dict[str, Any] = Field(
        default_factory=dict
    )


class MCPPromptMessage(BaseModel):
    role: str
    content: MCPPromptContent


class MCPPromptResult(BaseModel):
    name: str
    description: str | None = None
    messages: list[MCPPromptMessage] = Field(
        default_factory=list
    )
    meta: dict[str, Any] | None = None


class MCPContextDiscoveryResult(BaseModel):
    resources: list[
        MCPResourceDescriptor
    ] = Field(default_factory=list)
    resource_templates: list[
        MCPResourceTemplateDescriptor
    ] = Field(default_factory=list)
    prompts: list[
        MCPPromptDescriptor
    ] = Field(default_factory=list)
