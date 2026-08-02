from __future__ import annotations

import time

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from pydantic import BaseModel, Field

from af_core.tools.models import (
    ExternalToolCall,
    ExternalToolResult,
    ToolExecutionStatus,
)
from af_core.tools.tool_telemetry import (
    ToolTelemetryCollector,
)

from af_core.tools.registry import (
    ExternalToolRegistry,
    ExternalToolRegistryError,
)

from .tool_call_batch import (
    ToolBatchAudit,
    ToolBatchGovernor,
    ToolBatchLimitError,
)

from .tool_call_budget import (
    ToolBudgetEvaluationResult,
    ToolCallBudgetGovernor,
)

from .tool_call_resilience import (
    ResilientToolExecutionResult,
    ToolCallResilienceExecutor,
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
        resilience_executor: (
            ToolCallResilienceExecutor | None
        ) = None,
        budget_governor: (
            ToolCallBudgetGovernor | None
        ) = None,
        batch_governor: (
            ToolBatchGovernor | None
        ) = None,
        telemetry_collector: (
            ToolTelemetryCollector | None
        ) = None,
    ) -> None:
        self.registry = registry
        self.normalizer = (
            normalizer or ProviderToolCallNormalizer()
        )
        self.policy = policy or ToolCallRuntimePolicy()
        self.approval_resolver = approval_resolver
        self.resilience_executor = (
            resilience_executor
        )
        self.budget_governor = budget_governor
        self.batch_governor = batch_governor
        self.telemetry_collector = telemetry_collector
        self._batch_audits: list[
            ToolBatchAudit
        ] = []
        self._budget_by_call_id: dict[
            str,
            ToolBudgetEvaluationResult,
        ] = {}
        self._resilience_by_call_id: dict[
            str,
            ResilientToolExecutionResult,
        ] = {}

        self._tool_name_map: dict[str, str] = {}

        for mapping in mappings or []:
            self.add_mapping(mapping)

    async def _emit_telemetry(
        self,
        method: str,
        **kwargs,
    ) -> None:
        collector = self.telemetry_collector

        if collector is None:
            return

        emitter = getattr(
            collector,
            method,
        )

        await emitter(**kwargs)

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
        started_at = time.perf_counter()

        try:
            tool_id = self.resolve_tool_id(
                call.tool_name
            )
        except Exception as exc:
            await self._emit_telemetry(
                "call_failed",
                tool_id=None,
                call_id=call.call_id,
                error=exc,
                project_id=project_id,
                run_id=run_id,
                task_id=task_id,
                agent_id=agent_name,
                metadata={
                    "provider_tool_name": (
                        call.tool_name
                    ),
                    "phase": "tool_resolution",
                },
            )
            raise

        await self._emit_telemetry(
            "call_requested",
            tool_id=tool_id,
            call_id=call.call_id,
            project_id=project_id,
            run_id=run_id,
            task_id=task_id,
            agent_id=agent_name,
            metadata={
                "provider_tool_name": (
                    call.tool_name
                ),
            },
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

        await self._emit_telemetry(
            "call_started",
            tool_id=tool_id,
            call_id=external_call.call_id,
            project_id=project_id,
            run_id=run_id,
            task_id=task_id,
            agent_id=agent_name,
        )

        budget_evaluation = None

        if self.budget_governor is not None:
            descriptor = self.registry.get(tool_id)

            budget_evaluation = (
                self.budget_governor.evaluate(
                    call=external_call,
                    descriptor=descriptor,
                    attempt_count=1,
                    scopes=(
                        self.budget_governor
                        .scope_bindings(
                            project_id=project_id,
                            run_id=run_id,
                            task_id=task_id,
                            agent_name=agent_name,
                        )
                    ),
                )
            )

            self._budget_by_call_id[
                external_call.call_id
            ] = budget_evaluation

            if not budget_evaluation.allowed:
                reasons = (
                    budget_evaluation.reasons
                    or [
                        "Tool execution blocked by "
                        "budget governance."
                    ]
                )

                blocked_result = ExternalToolResult(
                    call_id=external_call.call_id,
                    tool_id=external_call.tool_id,
                    status=ToolExecutionStatus.BLOCKED,
                    is_error=True,
                    error="; ".join(reasons),
                    metadata={
                        "budget": (
                            budget_evaluation.model_dump(
                                mode="json"
                            )
                        ),
                    },
                )

                await self._emit_telemetry(
                    "call_blocked",
                    tool_id=tool_id,
                    call_id=external_call.call_id,
                    reason=blocked_result.error or (
                        "Tool Call blocked."
                    ),
                    project_id=project_id,
                    run_id=run_id,
                    task_id=task_id,
                    agent_id=agent_name,
                )

                return ToolCallExecutionRecord(
                    call=call,
                    external_call=external_call,
                    result=blocked_result,
                    approved=approved,
                )

        try:
            if self.resilience_executor is None:
                result = await self.registry.execute(
                    external_call,
                    approved=approved,
                )
            else:
                resilient = await (
                    self.resilience_executor.execute(
                        lambda attempt: (
                            self.registry.execute(
                                external_call,
                                approved=approved,
                            )
                        )
                    )
                )

                result = resilient.result.model_copy(
                    update={
                        "call_id": external_call.call_id,
                        "tool_id": external_call.tool_id,
                        "metadata": {
                            **resilient.result.metadata,
                            "resilience": {
                                "attempt_count": (
                                    resilient.attempt_count
                                ),
                                "retried": (
                                    resilient.retried
                                ),
                                "retry_history": (
                                    resilient.retry_history
                                    .model_dump(
                                        mode="json"
                                    )
                                ),
                                "attempts": [
                                    item.model_dump(
                                        mode="json"
                                    )
                                    for item in (
                                        resilient.attempts
                                    )
                                ],
                            },
                        },
                    }
                )

                self._resilience_by_call_id[
                    external_call.call_id
                ] = resilient

        except Exception as exc:
            duration_ms = (
                time.perf_counter() - started_at
            ) * 1000

            await self._emit_telemetry(
                "call_failed",
                tool_id=tool_id,
                call_id=external_call.call_id,
                error=exc,
                duration_ms=duration_ms,
                project_id=project_id,
                run_id=run_id,
                task_id=task_id,
                agent_id=agent_name,
            )
            raise

        if (
            self.budget_governor is not None
            and budget_evaluation is not None
        ):
            actual_attempt_count = 1

            resilience = self._resilience_by_call_id.get(
                external_call.call_id
            )

            if resilience is not None:
                actual_attempt_count = max(
                    resilience.attempt_count,
                    1,
                )

            if actual_attempt_count != 1:
                descriptor = self.registry.get(tool_id)

                budget_evaluation = (
                    self.budget_governor.evaluate(
                        call=external_call,
                        descriptor=descriptor,
                        attempt_count=(
                            actual_attempt_count
                        ),
                        scopes=(
                            self.budget_governor
                            .scope_bindings(
                                project_id=project_id,
                                run_id=run_id,
                                task_id=task_id,
                                agent_name=agent_name,
                            )
                        ),
                    )
                )

                self._budget_by_call_id[
                    external_call.call_id
                ] = budget_evaluation

            if budget_evaluation.allowed:
                committed_usage = (
                    self.budget_governor.commit(
                        call_id=external_call.call_id
                    )
                )

                result = result.model_copy(
                    update={
                        "metadata": {
                            **result.metadata,
                            "budget": {
                                "evaluation": (
                                    budget_evaluation
                                    .model_dump(
                                        mode="json"
                                    )
                                ),
                                "committed_usage": (
                                    committed_usage
                                    .model_dump(
                                        mode="json"
                                    )
                                ),
                            },
                        },
                    }
                )

        duration_ms = (
            time.perf_counter() - started_at
        ) * 1000

        resilience = self._resilience_by_call_id.get(
            external_call.call_id
        )
        retry_count = (
            max(resilience.attempt_count - 1, 0)
            if resilience is not None
            else 0
        )

        if result.status is (
            ToolExecutionStatus.SUCCEEDED
        ):
            await self._emit_telemetry(
                "call_succeeded",
                tool_id=tool_id,
                call_id=external_call.call_id,
                duration_ms=duration_ms,
                project_id=project_id,
                run_id=run_id,
                task_id=task_id,
                agent_id=agent_name,
                retry_count=retry_count,
                metadata={
                    "approved": approved,
                },
            )

        elif result.status is (
            ToolExecutionStatus.TIMED_OUT
        ):
            await self._emit_telemetry(
                "call_timed_out",
                tool_id=tool_id,
                call_id=external_call.call_id,
                duration_ms=duration_ms,
                project_id=project_id,
                run_id=run_id,
                task_id=task_id,
                agent_id=agent_name,
                retry_count=retry_count,
            )

        elif result.status is (
            ToolExecutionStatus.BLOCKED
        ):
            await self._emit_telemetry(
                "call_blocked",
                tool_id=tool_id,
                call_id=external_call.call_id,
                reason=result.error or (
                    "Tool Call blocked."
                ),
                project_id=project_id,
                run_id=run_id,
                task_id=task_id,
                agent_id=agent_name,
            )

        else:
            await self._emit_telemetry(
                "call_failed",
                tool_id=tool_id,
                call_id=external_call.call_id,
                error=result.error or (
                    f"Tool Call ended with "
                    f"{result.status.value}."
                ),
                duration_ms=duration_ms,
                project_id=project_id,
                run_id=run_id,
                task_id=task_id,
                agent_id=agent_name,
                retry_count=retry_count,
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

        batch_audit = None

        if self.batch_governor is not None:
            batch_id = (
                f"{run_id or 'run'}:"
                f"{task_id or 'task'}:"
                f"{len(self._batch_audits) + 1}"
            )

            batch_audit = self.batch_governor.begin(
                batch_id=batch_id,
                calls=list(calls),
                run_id=run_id,
            )

            self._batch_audits.append(
                batch_audit
            )

        if (
            not self.policy.allow_parallel_execution
            or self.policy.maximum_parallelism == 1
        ):
            records: list[
                ToolCallExecutionRecord
            ] = []

            for call in calls:
                if (
                    batch_audit is not None
                    and self.batch_governor
                    is not None
                ):
                    self.batch_governor.mark_running(
                        batch_audit,
                        call.call_id,
                    )

                record = await self.execute_one(
                    call,
                    project_id=project_id,
                    run_id=run_id,
                    task_id=task_id,
                    agent_name=agent_name,
                )
                records.append(record)

                if (
                    batch_audit is not None
                    and self.batch_governor
                    is not None
                ):
                    budget_result = (
                        self.budget_result(
                            call.call_id
                        )
                    )

                    post_budget_violation = (
                        budget_result is not None
                        and not budget_result.allowed
                        and record.result.status.value
                        != "BLOCKED"
                    )

                    self.batch_governor.mark_completed(
                        batch_audit,
                        record,
                        post_budget_violation=(
                            post_budget_violation
                        ),
                    )

                if (
                    self.policy.stop_on_failure
                    and not record.successful
                ):
                    if (
                        batch_audit is not None
                        and self.batch_governor
                        is not None
                        and (
                            self.batch_governor
                            .policy
                            .cancel_pending_on_failure
                        )
                    ):
                        current_index = list(
                            calls
                        ).index(call)

                        for pending_call in list(
                            calls
                        )[current_index + 1:]:
                            self.batch_governor.mark_cancelled(
                                batch_audit,
                                pending_call.call_id,
                                reason=(
                                    "Cancelled after an earlier "
                                    "Tool Call failed."
                                ),
                            )

                        if (
                            current_index + 1
                            < len(calls)
                        ):
                            batch_audit.cancellation_requested = (
                                True
                            )

                    break

            if (
                batch_audit is not None
                and self.batch_governor
                is not None
            ):
                self.batch_governor.finalize(
                    batch_audit
                )

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
                if (
                    batch_audit is not None
                    and self.batch_governor
                    is not None
                ):
                    self.batch_governor.mark_running(
                        batch_audit,
                        call.call_id,
                    )

                record = await self.execute_one(
                    call,
                    project_id=project_id,
                    run_id=run_id,
                    task_id=task_id,
                    agent_name=agent_name,
                )

                if (
                    batch_audit is not None
                    and self.batch_governor
                    is not None
                ):
                    budget_result = (
                        self.budget_result(
                            call.call_id
                        )
                    )

                    post_budget_violation = (
                        budget_result is not None
                        and not budget_result.allowed
                        and record.result.status.value
                        != "BLOCKED"
                    )

                    self.batch_governor.mark_completed(
                        batch_audit,
                        record,
                        post_budget_violation=(
                            post_budget_violation
                        ),
                    )

                return record

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

            if (
                batch_audit is not None
                and self.batch_governor
                is not None
            ):
                self.batch_governor.finalize(
                    batch_audit
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
                for index, pending in enumerate(
                    tasks
                ):
                    if not pending.done():
                        pending.cancel()

                        if (
                            batch_audit is not None
                            and self.batch_governor
                            is not None
                        ):
                            cancelled_call = calls[index]

                            self.batch_governor.mark_cancelled(
                                batch_audit,
                                cancelled_call.call_id,
                            )

                if (
                    batch_audit is not None
                    and self.batch_governor
                    is not None
                ):
                    batch_audit.cancellation_requested = True

                await asyncio.gather(
                    *tasks,
                    return_exceptions=True,
                )
                break

        if (
            batch_audit is not None
            and self.batch_governor
            is not None
        ):
            self.batch_governor.finalize(
                batch_audit
            )

        return ToolCallBatchResult(
            records=records
        )

    def batch_audits(
        self,
    ) -> list[ToolBatchAudit]:
        return [
            item.model_copy(deep=True)
            for item in self._batch_audits
        ]

    def latest_batch_audit(
        self,
    ) -> ToolBatchAudit | None:
        if not self._batch_audits:
            return None

        return self._batch_audits[-1].model_copy(
            deep=True
        )

    def budget_result(
        self,
        call_id: str,
    ) -> ToolBudgetEvaluationResult | None:
        return self._budget_by_call_id.get(
            call_id
        )

    def budget_results(
        self,
    ) -> dict[
        str,
        ToolBudgetEvaluationResult,
    ]:
        return dict(self._budget_by_call_id)

    def resilience_result(
        self,
        call_id: str,
    ) -> ResilientToolExecutionResult | None:
        return self._resilience_by_call_id.get(
            call_id
        )

    def resilience_results(
        self,
    ) -> dict[
        str,
        ResilientToolExecutionResult,
    ]:
        return dict(
            self._resilience_by_call_id
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
