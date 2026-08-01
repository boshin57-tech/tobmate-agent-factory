from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from pydantic import BaseModel, Field

from af_core.tools.models import (
    ExternalToolCall,
)
from af_core.tools.registry import (
    ExternalToolRegistry,
    ExternalToolRegistryError,
)

from .tool_call_models import (
    NormalizedToolCall,
    ProviderToolResultMessage,
    ToolCallBatchResult,
    ToolCallExecutionRecord,
)
from .tool_call_normalizer import (
    ProviderToolCallNormalizer,
)


class ToolCallRuntimeError(RuntimeError):
    """Raised when tool-call execution cannot proceed."""


class ToolNameMapping(BaseModel):
    provider_tool_name: str
    external_tool_id: str


ApprovalResolver = Callable[
    [NormalizedToolCall, str],
    bool | Awaitable[bool],
]


class ToolCallRuntimePolicy(BaseModel):
    maximum_parallelism: int = Field(
        default=4,
        ge=1,
        le=64,
    )
    stop_on_failure: bool = False
    allow_parallel_execution: bool = True


class ToolCallRuntime:
    def __init__(
        self,
        *,
        registry: ExternalToolRegistry,
        normalizer: ProviderToolCallNormalizer | None = None,
        mappings: Sequence[ToolNameMapping] | None = None,
        policy: ToolCallRuntimePolicy | None = None,
        approval_resolver: ApprovalResolver | None = None,
    ) -> None:
        self.registry = registry
        self.normalizer = (
            normalizer or ProviderToolCallNormalizer()
        )
        self.policy = policy or ToolCallRuntimePolicy()
        self.approval_resolver = approval_resolver

        self._tool_name_map: dict[str, str] = {}

        for mapping in mappings or []:
            self.add_mapping(mapping)

    def add_mapping(
        self,
        mapping: ToolNameMapping,
    ) -> None:
        provider_name = (
            mapping.provider_tool_name.strip()
        )
        external_id = (
            mapping.external_tool_id.strip()
        )

        if not provider_name:
            raise ValueError(
                "Provider tool name is required."
            )

        if not external_id:
            raise ValueError(
                "External tool ID is required."
            )

        existing = self._tool_name_map.get(
            provider_name
        )

        if (
            existing is not None
            and existing != external_id
        ):
            raise ToolCallRuntimeError(
                "Provider tool name is already mapped "
                f"to another tool: {provider_name}"
            )

        self._tool_name_map[provider_name] = external_id

    def remove_mapping(
        self,
        provider_tool_name: str,
    ) -> None:
        self._tool_name_map.pop(
            provider_tool_name,
            None,
        )

    def resolve_tool_id(
        self,
        tool_name: str,
    ) -> str:
        mapped = self._tool_name_map.get(tool_name)

        if mapped is not None:
            return mapped

        try:
            self.registry.get(tool_name)
        except ExternalToolRegistryError:
            matches = [
                descriptor.tool_id
                for descriptor in self.registry.list()
                if descriptor.name == tool_name
            ]

            if len(matches) == 1:
                return matches[0]

            if len(matches) > 1:
                raise ToolCallRuntimeError(
                    "Multiple external tools share the "
                    f"provider tool name {tool_name!r}; "
                    "an explicit mapping is required."
                )

            raise ToolCallRuntimeError(
                "No external tool is registered for "
                f"provider tool name {tool_name!r}."
            )

        return tool_name

    async def execute_one(
        self,
        call: NormalizedToolCall,
        *,
        project_id: str | None = None,
        run_id: str | None = None,
        task_id: str | None = None,
        agent_name: str | None = None,
    ) -> ToolCallExecutionRecord:
        tool_id = self.resolve_tool_id(
            call.tool_name
        )

        approved = await self._resolve_approval(
            call,
            tool_id,
        )

        external_call = call.to_external_call(
            tool_id=tool_id,
            project_id=project_id,
            run_id=run_id,
            task_id=task_id,
            agent_name=agent_name,
        )

        result = await self.registry.execute(
            external_call,
            approved=approved,
        )

        return ToolCallExecutionRecord(
            call=call,
            external_call=external_call,
            result=result,
            approved=approved,
        )

    async def execute_many(
        self,
        calls: Sequence[NormalizedToolCall],
        *,
        project_id: str | None = None,
        run_id: str | None = None,
        task_id: str | None = None,
        agent_name: str | None = None,
    ) -> ToolCallBatchResult:
        if not calls:
            return ToolCallBatchResult()

        if (
            not self.policy.allow_parallel_execution
            or self.policy.maximum_parallelism == 1
        ):
            records: list[
                ToolCallExecutionRecord
            ] = []

            for call in calls:
                record = await self.execute_one(
                    call,
                    project_id=project_id,
                    run_id=run_id,
                    task_id=task_id,
                    agent_name=agent_name,
                )
                records.append(record)

                if (
                    self.policy.stop_on_failure
                    and not record.successful
                ):
                    break

            return ToolCallBatchResult(
                records=records
            )

        semaphore = asyncio.Semaphore(
            self.policy.maximum_parallelism
        )

        async def run_call(
            call: NormalizedToolCall,
        ) -> ToolCallExecutionRecord:
            async with semaphore:
                return await self.execute_one(
                    call,
                    project_id=project_id,
                    run_id=run_id,
                    task_id=task_id,
                    agent_name=agent_name,
                )

        tasks = [
            asyncio.create_task(
                run_call(call)
            )
            for call in calls
        ]

        if not self.policy.stop_on_failure:
            records = await asyncio.gather(
                *tasks
            )

            return ToolCallBatchResult(
                records=list(records)
            )

        records: list[
            ToolCallExecutionRecord
        ] = []

        for task in tasks:
            record = await task
            records.append(record)

            if not record.successful:
                for pending in tasks:
                    if not pending.done():
                        pending.cancel()

                await asyncio.gather(
                    *tasks,
                    return_exceptions=True,
                )
                break

        return ToolCallBatchResult(
            records=records
        )

    def result_messages(
        self,
        batch: ToolCallBatchResult,
    ) -> list[ProviderToolResultMessage]:
        return [
            self.normalizer.result_message(
                tool_call=record.call,
                result=record.result,
            )
            for record in batch.records
        ]

    async def _resolve_approval(
        self,
        call: NormalizedToolCall,
        tool_id: str,
    ) -> bool:
        if self.approval_resolver is None:
            return False

        value = self.approval_resolver(
            call,
            tool_id,
        )

        if isinstance(value, bool):
            return value

        return bool(await value)
