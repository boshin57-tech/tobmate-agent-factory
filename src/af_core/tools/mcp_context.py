from __future__ import annotations

import asyncio
from typing import Any, Protocol
from urllib.parse import urlparse

from .mcp_context_models import (
    MCPContextDiscoveryResult,
    MCPPromptArgumentDescriptor,
    MCPPromptContent,
    MCPPromptContentType,
    MCPPromptDescriptor,
    MCPPromptMessage,
    MCPPromptResult,
    MCPResourceContent,
    MCPResourceContentType,
    MCPResourceDescriptor,
    MCPResourceReadResult,
    MCPResourceTemplateDescriptor,
)


class MCPContextError(RuntimeError):
    """Raised when MCP context operations fail."""


class MCPContextSession(Protocol):
    async def list_resources(
        self,
        *,
        cursor: str | None = None,
    ) -> Any:
        ...

    async def list_resource_templates(
        self,
        *,
        cursor: str | None = None,
    ) -> Any:
        ...

    async def read_resource(
        self,
        uri: Any,
    ) -> Any:
        ...

    async def list_prompts(
        self,
        *,
        cursor: str | None = None,
    ) -> Any:
        ...

    async def get_prompt(
        self,
        name: str,
        *,
        arguments: dict[str, str] | None = None,
    ) -> Any:
        ...


class MCPContextOperations:
    def __init__(
        self,
        *,
        session: MCPContextSession,
        timeout_seconds: float = 60.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError(
                "timeout_seconds must be positive."
            )

        self.session = session
        self.timeout_seconds = timeout_seconds

    async def discover(
        self,
    ) -> MCPContextDiscoveryResult:
        resources, templates, prompts = await asyncio.gather(
            self.list_resources(),
            self.list_resource_templates(),
            self.list_prompts(),
        )

        return MCPContextDiscoveryResult(
            resources=resources,
            resource_templates=templates,
            prompts=prompts,
        )

    async def list_resources(
        self,
    ) -> list[MCPResourceDescriptor]:
        descriptors: list[MCPResourceDescriptor] = []
        cursor: str | None = None

        while True:
            try:
                response = await asyncio.wait_for(
                    self.session.list_resources(
                        cursor=cursor
                    ),
                    timeout=self.timeout_seconds,
                )
            except Exception as exc:
                raise MCPContextError(
                    f"MCP resource discovery failed: {exc}"
                ) from exc

            for resource in getattr(
                response,
                "resources",
                [],
            ):
                payload = self._model_dump(resource)

                descriptors.append(
                    MCPResourceDescriptor(
                        uri=str(payload.get("uri")),
                        name=str(payload.get("name") or ""),
                        title=payload.get("title"),
                        description=payload.get(
                            "description"
                        ),
                        mime_type=payload.get(
                            "mimeType"
                        ),
                        size=payload.get("size"),
                        annotations=payload.get(
                            "annotations"
                        ),
                        meta=payload.get("_meta"),
                    )
                )

            cursor = self._next_cursor(response)

            if cursor is None:
                break

        return descriptors

    async def list_resource_templates(
        self,
    ) -> list[MCPResourceTemplateDescriptor]:
        descriptors: list[
            MCPResourceTemplateDescriptor
        ] = []
        cursor: str | None = None

        while True:
            try:
                response = await asyncio.wait_for(
                    self.session.list_resource_templates(
                        cursor=cursor
                    ),
                    timeout=self.timeout_seconds,
                )
            except Exception as exc:
                raise MCPContextError(
                    "MCP resource template discovery "
                    f"failed: {exc}"
                ) from exc

            for template in getattr(
                response,
                "resourceTemplates",
                getattr(
                    response,
                    "resource_templates",
                    [],
                ),
            ):
                payload = self._model_dump(template)

                descriptors.append(
                    MCPResourceTemplateDescriptor(
                        uri_template=str(
                            payload.get("uriTemplate")
                            or payload.get(
                                "uri_template"
                            )
                            or ""
                        ),
                        name=str(
                            payload.get("name") or ""
                        ),
                        title=payload.get("title"),
                        description=payload.get(
                            "description"
                        ),
                        mime_type=payload.get(
                            "mimeType"
                        ),
                        annotations=payload.get(
                            "annotations"
                        ),
                        meta=payload.get("_meta"),
                    )
                )

            cursor = self._next_cursor(response)

            if cursor is None:
                break

        return descriptors

    async def read_resource(
        self,
        uri: str,
    ) -> MCPResourceReadResult:
        self._validate_uri(uri)

        try:
            from pydantic import AnyUrl

            parsed_uri: Any = AnyUrl(uri)
        except Exception:
            parsed_uri = uri

        try:
            response = await asyncio.wait_for(
                self.session.read_resource(
                    parsed_uri
                ),
                timeout=self.timeout_seconds,
            )
        except Exception as exc:
            raise MCPContextError(
                f"MCP resource read failed for {uri}: {exc}"
            ) from exc

        contents: list[MCPResourceContent] = []

        for content in getattr(
            response,
            "contents",
            [],
        ):
            payload = self._model_dump(content)

            content_uri = str(
                payload.get("uri") or uri
            )
            mime_type = payload.get("mimeType")

            if "text" in payload:
                contents.append(
                    MCPResourceContent(
                        uri=content_uri,
                        type=MCPResourceContentType.TEXT,
                        mime_type=mime_type,
                        text=payload.get("text"),
                        meta=payload.get("_meta"),
                    )
                )
            elif "blob" in payload:
                contents.append(
                    MCPResourceContent(
                        uri=content_uri,
                        type=MCPResourceContentType.BLOB,
                        mime_type=mime_type,
                        blob=payload.get("blob"),
                        meta=payload.get("_meta"),
                    )
                )

        return MCPResourceReadResult(
            uri=uri,
            contents=contents,
            meta=self._response_meta(response),
        )

    async def list_prompts(
        self,
    ) -> list[MCPPromptDescriptor]:
        descriptors: list[MCPPromptDescriptor] = []
        cursor: str | None = None

        while True:
            try:
                response = await asyncio.wait_for(
                    self.session.list_prompts(
                        cursor=cursor
                    ),
                    timeout=self.timeout_seconds,
                )
            except Exception as exc:
                raise MCPContextError(
                    f"MCP prompt discovery failed: {exc}"
                ) from exc

            for prompt in getattr(
                response,
                "prompts",
                [],
            ):
                payload = self._model_dump(prompt)

                arguments = [
                    MCPPromptArgumentDescriptor(
                        name=str(
                            argument.get("name") or ""
                        ),
                        description=argument.get(
                            "description"
                        ),
                        required=bool(
                            argument.get(
                                "required",
                                False,
                            )
                        ),
                    )
                    for argument in (
                        payload.get("arguments") or []
                    )
                    if isinstance(argument, dict)
                ]

                descriptors.append(
                    MCPPromptDescriptor(
                        name=str(
                            payload.get("name") or ""
                        ),
                        title=payload.get("title"),
                        description=payload.get(
                            "description"
                        ),
                        arguments=arguments,
                        meta=payload.get("_meta"),
                    )
                )

            cursor = self._next_cursor(response)

            if cursor is None:
                break

        return descriptors

    async def get_prompt(
        self,
        *,
        name: str,
        arguments: dict[str, str] | None = None,
    ) -> MCPPromptResult:
        if not name.strip():
            raise ValueError(
                "Prompt name is required."
            )

        try:
            response = await asyncio.wait_for(
                self.session.get_prompt(
                    name,
                    arguments=arguments or {},
                ),
                timeout=self.timeout_seconds,
            )
        except Exception as exc:
            raise MCPContextError(
                f"MCP prompt retrieval failed for "
                f"{name}: {exc}"
            ) from exc

        messages: list[MCPPromptMessage] = []

        for message in getattr(
            response,
            "messages",
            [],
        ):
            payload = self._model_dump(message)

            content_payload = payload.get(
                "content"
            )

            if not isinstance(
                content_payload,
                dict,
            ):
                continue

            messages.append(
                MCPPromptMessage(
                    role=str(
                        payload.get("role") or ""
                    ),
                    content=self._normalize_prompt_content(
                        content_payload
                    ),
                )
            )

        return MCPPromptResult(
            name=name,
            description=getattr(
                response,
                "description",
                None,
            ),
            messages=messages,
            meta=self._response_meta(response),
        )

    def _normalize_prompt_content(
        self,
        payload: dict[str, Any],
    ) -> MCPPromptContent:
        content_type = payload.get("type")

        mapped = {
            "text": MCPPromptContentType.TEXT,
            "image": MCPPromptContentType.IMAGE,
            "audio": MCPPromptContentType.AUDIO,
            "resource": (
                MCPPromptContentType.EMBEDDED_RESOURCE
            ),
            "resource_link": (
                MCPPromptContentType.RESOURCE_LINK
            ),
        }.get(
            content_type,
            MCPPromptContentType.UNKNOWN,
        )

        resource = payload.get("resource")

        if not isinstance(resource, dict):
            resource = {}

        return MCPPromptContent(
            type=mapped,
            text=payload.get("text")
            or resource.get("text"),
            data=payload.get("data")
            or resource.get("blob"),
            mime_type=payload.get("mimeType")
            or resource.get("mimeType"),
            uri=payload.get("uri")
            or resource.get("uri"),
            name=payload.get("name"),
            raw=payload,
        )

    def _next_cursor(
        self,
        response: Any,
    ) -> str | None:
        value = getattr(
            response,
            "nextCursor",
            getattr(
                response,
                "next_cursor",
                None,
            ),
        )

        if value is None:
            return None

        return str(value)

    def _response_meta(
        self,
        response: Any,
    ) -> dict[str, Any] | None:
        payload = self._model_dump(response)
        meta = payload.get("_meta")

        return (
            meta
            if isinstance(meta, dict)
            else None
        )

    def _model_dump(
        self,
        value: Any,
    ) -> dict[str, Any]:
        if hasattr(value, "model_dump"):
            payload = value.model_dump(
                mode="json",
                by_alias=True,
            )
        elif isinstance(value, dict):
            payload = value
        elif hasattr(value, "__dict__"):
            payload = {
                key: item
                for key, item in vars(value).items()
                if not key.startswith("_")
            }

            for attribute in (
                "contents",
                "resources",
                "resource_templates",
                "resourceTemplates",
                "prompts",
                "messages",
                "description",
                "next_cursor",
                "nextCursor",
            ):
                if (
                    attribute not in payload
                    and hasattr(value, attribute)
                ):
                    payload[attribute] = getattr(
                        value,
                        attribute,
                    )
        else:
            raise MCPContextError(
                "MCP SDK returned unsupported "
                f"context type: {type(value)!r}"
            )

        if not isinstance(payload, dict):
            raise MCPContextError(
                "MCP context response must be an object."
            )

        return payload

    def _validate_uri(
        self,
        uri: str,
    ) -> None:
        parsed = urlparse(uri)

        if not parsed.scheme:
            raise ValueError(
                "Resource URI must include a scheme."
            )
