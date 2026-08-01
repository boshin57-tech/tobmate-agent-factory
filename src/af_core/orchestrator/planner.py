from __future__ import annotations

from collections import Counter
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from af_core.repository.context_builder import ContextPackage


AgentRole = Literal[
    "planner",
    "implementer",
    "tester",
    "reviewer",
    "completion_auditor",
]


class PlannedTask(BaseModel):
    id: str
    title: str
    description: str
    task_type: str
    dependencies: list[str] = Field(default_factory=list)
    agent_role: AgentRole
    acceptance_criteria: list[str] = Field(default_factory=list)
    risk_level: Literal["LOW", "MODERATE", "HIGH"] = "LOW"

    @model_validator(mode="after")
    def validate_self_dependency(self) -> "PlannedTask":
        if self.id in self.dependencies:
            raise ValueError(
                f"Task cannot depend on itself: {self.id}"
            )

        if len(self.dependencies) != len(set(self.dependencies)):
            raise ValueError(
                f"Task has duplicate dependencies: {self.id}"
            )

        return self


class ProjectPlan(BaseModel):
    goal: str
    assumptions: list[str] = Field(default_factory=list)
    tasks: list[PlannedTask]
    validation_strategy: list[str] = Field(default_factory=list)
    completion_criteria: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_task_identifiers(self) -> "ProjectPlan":
        identifiers = [task.id for task in self.tasks]
        duplicates = [
            task_id
            for task_id, count in Counter(identifiers).items()
            if count > 1
        ]

        if duplicates:
            raise ValueError(
                f"Duplicate task IDs: {', '.join(sorted(duplicates))}"
            )

        known = set(identifiers)

        for task in self.tasks:
            unknown = set(task.dependencies) - known

            if unknown:
                raise ValueError(
                    f"Task {task.id} has unknown dependencies: "
                    f"{', '.join(sorted(unknown))}"
                )

        return self


class PlanningRequest(BaseModel):
    objective: str
    context: ContextPackage
    maximum_tasks: int = Field(default=12, ge=1, le=50)


class DeterministicPlanner:
    """
    Minimal non-LLM planner used for the MVP foundation and tests.

    A provider-backed planner can later implement the same create_plan
    interface while returning the same ProjectPlan contract.
    """

    def create_plan(self, request: PlanningRequest) -> ProjectPlan:
        build_commands = self._extract_commands(
            request.context.repository_summary,
            "Build commands:",
        )
        test_commands = self._extract_commands(
            request.context.repository_summary,
            "Test commands:",
        )

        tasks = [
            PlannedTask(
                id="task-1",
                title="Inspect selected context",
                description=(
                    "Review the selected repository files, constraints, "
                    "and current repository state."
                ),
                task_type="analysis",
                agent_role="planner",
                acceptance_criteria=[
                    "Relevant files are identified.",
                    "Existing changes and constraints are preserved.",
                ],
            ),
            PlannedTask(
                id="task-2",
                title="Implement requested change",
                description=request.objective,
                task_type="implementation",
                dependencies=["task-1"],
                agent_role="implementer",
                acceptance_criteria=[
                    "Requested behavior is implemented.",
                    "Changes remain inside the isolated workspace.",
                ],
                risk_level="MODERATE",
            ),
            PlannedTask(
                id="task-3",
                title="Validate implementation",
                description=(
                    "Run applicable syntax, build, and test checks."
                ),
                task_type="validation",
                dependencies=["task-2"],
                agent_role="tester",
                acceptance_criteria=[
                    "Applicable validation commands pass.",
                    "Failures are recorded as evidence.",
                ],
            ),
            PlannedTask(
                id="task-4",
                title="Review change set",
                description=(
                    "Review the diff for correctness, safety, scope, "
                    "and test coverage."
                ),
                task_type="review",
                dependencies=["task-3"],
                agent_role="reviewer",
                acceptance_criteria=[
                    "Unexpected file changes are absent.",
                    "Acceptance criteria are satisfied.",
                ],
            ),
            PlannedTask(
                id="task-5",
                title="Audit completion",
                description=(
                    "Evaluate all evidence and issue the final "
                    "completion decision."
                ),
                task_type="completion",
                dependencies=["task-4"],
                agent_role="completion_auditor",
                acceptance_criteria=[
                    "All required tasks are complete.",
                    "Validation and review evidence exists.",
                ],
            ),
        ]

        tasks = tasks[: request.maximum_tasks]

        validation_strategy = [
            "Run git diff --check.",
            *[f"Run build command: {item}" for item in build_commands],
            *[f"Run test command: {item}" for item in test_commands],
        ]

        if not build_commands and not test_commands:
            validation_strategy.append(
                "Determine repository-specific validation commands."
            )

        return ProjectPlan(
            goal=request.objective,
            assumptions=[
                "The source repository remains unchanged.",
                "All modifications occur in an isolated Git worktree.",
                "Existing uncommitted changes must not be overwritten.",
            ],
            tasks=tasks,
            validation_strategy=validation_strategy,
            completion_criteria=[
                "All planned tasks are complete.",
                "Required validation checks pass.",
                "Review approves the final diff.",
                "Completion evidence is available.",
            ],
        )

    def _extract_commands(
        self,
        summary: str,
        prefix: str,
    ) -> list[str]:
        for line in summary.splitlines():
            if line.startswith(prefix):
                value = line[len(prefix):].strip()

                if not value or value == "none":
                    return []

                return [
                    command.strip()
                    for command in value.split(",")
                    if command.strip()
                ]

        return []
