from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from af_core.orchestrator.planner import PlannedTask
from af_core.runtime.agent import (
    AgentAction,
    AgentExecutionState,
    AgentProfile,
)
from af_core.runtime.command_runner import (
    RestrictedCommandRunner,
)
from af_core.runtime.file_tools import WorkspaceFileTools
from af_core.runtime.llm_provider import (
    LLMMessage,
    LLMProvider,
)
from af_core.runtime.provider_protocol import (
    ProviderAdapter,
    ProviderMessage,
)
from af_core.runtime.tool_call_models import (
    NormalizedToolCall,
    ToolCallExecutionRecord,
)
from af_core.runtime.tool_call_runtime import (
    ToolCallRuntime,
)
from af_core.runtime.tool_registry import (
    ToolDefinition,
    ToolRegistry,
    ToolRiskLevel,
)


class ToolExecutionRecord(BaseModel):
    step: int
    tool_name: str
    arguments: dict[str, Any]
    success: bool
    output: str
    error: str | None = None


class AgentExecutorResult(BaseModel):
    successful: bool
    summary: str
    state: AgentExecutionState
    tool_records: list[ToolExecutionRecord] = Field(
        default_factory=list
    )
    provider_tool_records: list[
        ToolCallExecutionRecord
    ] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    diff_text: str = ""
    error: str | None = None


class AgentExecutor:
    def __init__(
        self,
        *,
        provider: LLMProvider,
        profile: AgentProfile,
        workspace_path: str | Path,
        model: str | None = None,
        maximum_risk: ToolRiskLevel = (
            ToolRiskLevel.WORKSPACE_MUTATION
        ),
    ) -> None:
        self.provider = provider
        self.profile = profile
        self.workspace = Path(
            workspace_path
        ).expanduser().resolve()
        self.model = model
        self.maximum_risk = maximum_risk

        self.file_tools = WorkspaceFileTools(
            self.workspace
        )
        self.command_runner = RestrictedCommandRunner(
            self.workspace
        )
        self.registry = self._build_registry()

    async def execute(
        self,
        *,
        task: PlannedTask,
        context_summary: str = "",
    ) -> AgentExecutorResult:
        state = AgentExecutionState(
            agent_name=self.profile.name,
            role=self.profile.role,
        )
        state.begin()

        records: list[ToolExecutionRecord] = []

        messages = [
            LLMMessage(
                role="system",
                content=self._system_prompt(),
            ),
            LLMMessage(
                role="user",
                content=self._task_prompt(
                    task=task,
                    context_summary=context_summary,
                ),
            ),
        ]

        try:
            while state.step < self.profile.maximum_steps:
                action = await self.provider.generate(
                    messages=messages,
                    response_model=AgentAction,
                    model=self.model,
                )

                if action.action_type == "complete":
                    summary = (
                        action.summary
                        or "Task completed."
                    )
                    state.complete(summary)

                    return await self._build_result(
                        successful=True,
                        summary=summary,
                        state=state,
                        records=records,
                    )

                if action.action_type == "fail":
                    error = (
                        action.error
                        or "Agent reported failure."
                    )
                    state.fail(error)

                    return await self._build_result(
                        successful=False,
                        summary="Agent failed.",
                        state=state,
                        records=records,
                        error=error,
                    )

                if action.action_type == "request_review":
                    summary = (
                        action.summary
                        or "Agent requested review."
                    )
                    state.complete(summary)

                    return await self._build_result(
                        successful=True,
                        summary=summary,
                        state=state,
                        records=records,
                    )

                if action.tool_call is None:
                    raise RuntimeError(
                        "Tool action omitted tool_call."
                    )

                call = action.tool_call
                state.record_tool_call(call)

                record = await self._execute_tool(
                    step=state.step,
                    tool_name=call.tool_name,
                    arguments=call.arguments,
                )
                records.append(record)

                messages.append(
                    LLMMessage(
                        role="assistant",
                        content=action.model_dump_json(),
                    )
                )
                messages.append(
                    LLMMessage(
                        role="tool",
                        content=json.dumps(
                            {
                                "tool_name": record.tool_name,
                                "success": record.success,
                                "output": record.output,
                                "error": record.error,
                            },
                            ensure_ascii=False,
                        ),
                    )
                )

            error = (
                "Agent exceeded maximum execution steps: "
                f"{self.profile.maximum_steps}"
            )
            state.fail(error)

            return await self._build_result(
                successful=False,
                summary="Maximum steps exceeded.",
                state=state,
                records=records,
                error=error,
            )

        except Exception as exc:
            state.fail(str(exc))

            return await self._build_result(
                successful=False,
                summary="Agent execution failed.",
                state=state,
                records=records,
                error=str(exc),
            )

    async def execute_provider_tool_loop(
        self,
        *,
        task: PlannedTask,
        provider_adapter: ProviderAdapter,
        tool_runtime: ToolCallRuntime,
        model_id: str,
        context_summary: str = "",
        parameters: dict[str, Any] | None = None,
        project_id: str | None = None,
        run_id: str | None = None,
    ) -> AgentExecutorResult:
        """Execute a provider-native Tool Calling loop.

        This path preserves the legacy AgentAction loop and uses
        ProviderResponse.tool_calls as the source of tool requests.
        """

        state = AgentExecutionState(
            agent_name=self.profile.name,
            role=self.profile.role,
        )
        state.begin()

        provider_records: list[
            ToolCallExecutionRecord
        ] = []

        messages = [
            ProviderMessage(
                role="system",
                content=self._system_prompt(),
            ),
            ProviderMessage(
                role="user",
                content=self._task_prompt(
                    task=task,
                    context_summary=context_summary,
                ),
            ),
        ]

        try:
            for step in range(
                1,
                self.profile.maximum_steps + 1,
            ):
                response = await provider_adapter.complete(
                    messages=messages,
                    model_id=model_id,
                    parameters=parameters,
                )

                if not response.has_tool_calls:
                    summary = (
                        response.content
                        or "Task completed."
                    )
                    state.complete(summary)

                    return await self._build_result(
                        successful=True,
                        summary=summary,
                        state=state,
                        records=[],
                        provider_records=provider_records,
                    )

                normalized_calls = [
                    NormalizedToolCall
                    .from_provider_tool_call(
                        item,
                        provider_id=response.provider_id,
                        model_id=response.model_id,
                    )
                    for item in response.tool_calls
                ]

                batch = await tool_runtime.execute_many(
                    normalized_calls,
                    project_id=project_id,
                    run_id=run_id,
                    task_id=task.id,
                    agent_name=self.profile.name,
                )

                provider_records.extend(
                    batch.records
                )

                assistant_payload = {
                    "content": response.content,
                    "tool_calls": [
                        item.model_dump(
                            mode="json"
                        )
                        for item in response.tool_calls
                    ],
                    "step": step,
                }

                messages.append(
                    ProviderMessage(
                        role="assistant",
                        content=json.dumps(
                            assistant_payload,
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                    )
                )

                for tool_message in (
                    tool_runtime.result_messages(
                        batch
                    )
                ):
                    messages.append(
                        ProviderMessage(
                            role="tool",
                            content=json.dumps(
                                {
                                    "call_id": (
                                        tool_message.call_id
                                    ),
                                    "tool_name": (
                                        tool_message.tool_name
                                    ),
                                    "content": (
                                        tool_message.content
                                    ),
                                    "is_error": (
                                        tool_message.is_error
                                    ),
                                    "metadata": (
                                        tool_message.metadata
                                    ),
                                },
                                ensure_ascii=False,
                                sort_keys=True,
                            ),
                        )
                    )

            error = (
                "Agent exceeded maximum provider tool "
                "execution steps: "
                f"{self.profile.maximum_steps}"
            )
            state.fail(error)

            return await self._build_result(
                successful=False,
                summary="Maximum steps exceeded.",
                state=state,
                records=[],
                provider_records=provider_records,
                error=error,
            )

        except Exception as exc:
            state.fail(str(exc))

            return await self._build_result(
                successful=False,
                summary=(
                    "Provider tool-loop execution failed."
                ),
                state=state,
                records=[],
                provider_records=provider_records,
                error=str(exc),
            )

    async def _execute_tool(
        self,
        *,
        step: int,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolExecutionRecord:
        definition = self.registry.authorize(
            tool_name=tool_name,
            agent_role=self.profile.role.value,
            allowed_tools=self.profile.allowed_tools,
            maximum_risk=self.maximum_risk,
        )

        try:
            if tool_name == "run_command":
                command = arguments.get("command")

                if not isinstance(command, list):
                    raise ValueError(
                        "run_command requires a command list."
                    )

                result = await self.command_runner.run(
                    command,
                    timeout=(
                        self.profile.command_timeout_seconds
                    ),
                )
                output = result.model_dump_json()

                if result.returncode != 0:
                    return ToolExecutionRecord(
                        step=step,
                        tool_name=tool_name,
                        arguments=arguments,
                        success=False,
                        output=output,
                        error=(
                            result.stderr.strip()
                            or (
                                "Command returned "
                                f"{result.returncode}"
                            )
                        ),
                    )
            else:
                result = definition.handler(**arguments)

                if isinstance(result, BaseModel):
                    output = result.model_dump_json()
                else:
                    output = json.dumps(
                        result,
                        ensure_ascii=False,
                    )

            return ToolExecutionRecord(
                step=step,
                tool_name=tool_name,
                arguments=arguments,
                success=True,
                output=output,
            )

        except Exception as exc:
            return ToolExecutionRecord(
                step=step,
                tool_name=tool_name,
                arguments=arguments,
                success=False,
                output="",
                error=str(exc),
            )

    async def _build_result(
        self,
        *,
        successful: bool,
        summary: str,
        state: AgentExecutionState,
        records: list[ToolExecutionRecord],
        provider_records: list[
            ToolCallExecutionRecord
        ] | None = None,
        error: str | None = None,
    ) -> AgentExecutorResult:
        status_result = await self.command_runner.run(
            [
                "git",
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ]
        )

        changed_files = []

        for line in status_result.stdout.splitlines():
            if len(line) < 4:
                continue

            value = line[3:].strip()

            if " -> " in value:
                value = value.split(" -> ", 1)[1]

            if value:
                candidate = (
                    self.workspace / value
                ).resolve()

                if self.file_tools._ignored(candidate):
                    continue

                changed_files.append(value)

        diff_result = await self.command_runner.run(
            [
                "git",
                "diff",
                "--binary",
            ]
        )

        return AgentExecutorResult(
            successful=successful,
            summary=summary,
            state=state,
            tool_records=records,
            provider_tool_records=(
                provider_records or []
            ),
            changed_files=sorted(set(changed_files)),
            diff_text=diff_result.stdout,
            error=error,
        )

    def _build_registry(self) -> ToolRegistry:
        registry = ToolRegistry()

        registry.register(
            ToolDefinition(
                name="read_file",
                description="Read one workspace file.",
                risk_level=ToolRiskLevel.READ_ONLY,
                handler=self.file_tools.read_file,
                allowed_roles=frozenset(
                    {
                        "planner",
                        "implementer",
                        "tester",
                        "reviewer",
                        "completion_auditor",
                    }
                ),
            )
        )

        registry.register(
            ToolDefinition(
                name="list_files",
                description="List workspace files.",
                risk_level=ToolRiskLevel.READ_ONLY,
                handler=self.file_tools.list_files,
                allowed_roles=frozenset(
                    {
                        "planner",
                        "implementer",
                        "tester",
                        "reviewer",
                    }
                ),
            )
        )

        registry.register(
            ToolDefinition(
                name="search_text",
                description="Search literal workspace text.",
                risk_level=ToolRiskLevel.READ_ONLY,
                handler=self.file_tools.search_text,
                allowed_roles=frozenset(
                    {
                        "planner",
                        "implementer",
                        "tester",
                        "reviewer",
                    }
                ),
            )
        )

        registry.register(
            ToolDefinition(
                name="write_file",
                description="Create or replace a file.",
                risk_level=(
                    ToolRiskLevel.WORKSPACE_MUTATION
                ),
                handler=self.file_tools.write_file,
                allowed_roles=frozenset(
                    {
                        "implementer",
                        "tester",
                    }
                ),
            )
        )

        registry.register(
            ToolDefinition(
                name="run_command",
                description="Run an allowlisted command.",
                risk_level=(
                    ToolRiskLevel.WORKSPACE_MUTATION
                ),
                handler=lambda **kwargs: kwargs,
                allowed_roles=frozenset(
                    {
                        "implementer",
                        "tester",
                        "reviewer",
                    }
                ),
            )
        )

        return registry

    def _system_prompt(self) -> str:
        return (
            "You are an AF-Core software engineering Agent. "
            "Operate only inside the assigned Git worktree. "
            "Use only the allowed tools. "
            "Inspect existing files before modifying them. "
            "Do not access secrets, external networks, production "
            "systems, or the original source repository. "
            "Return one structured AgentAction per step."
        )

    def _task_prompt(
        self,
        *,
        task: PlannedTask,
        context_summary: str,
    ) -> str:
        return (
            f"Task ID: {task.id}\n"
            f"Title: {task.title}\n"
            f"Description: {task.description}\n"
            "Acceptance criteria: "
            f"{json.dumps(task.acceptance_criteria)}\n"
            f"Risk: {task.risk_level}\n"
            f"Context:\n{context_summary}"
        )
