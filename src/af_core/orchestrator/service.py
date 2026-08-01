from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from af_core.assurance.completion import (
    CompletionAuditor,
    CompletionInput,
)
from af_core.assurance.reviewer import (
    ReviewEngine,
    ReviewInput,
)
from af_core.assurance.validator import (
    ValidationCheck,
    ValidationEngine,
    ValidationPlan,
)
from af_core.delivery.service import DeliveryService
from af_core.knowledge.promoter import (
    KnowledgePromoter,
    PromotionInput,
    PromotionStatus,
)
from af_core.knowledge.store import FileKnowledgeStore
from af_core.repository.analyzer import RepositoryAnalyzer
from af_core.repository.context_builder import ContextBuilder
from af_core.workspace.manager import (
    WorkspaceManager,
    WorkspaceRecord,
)

from .planner import DeterministicPlanner, PlanningRequest
from .run_models import (
    FactoryExecutionResult,
    FactoryRunEvent,
    FactoryRunPhase,
    FactoryRunRequest,
    FactoryRunResult,
)


ExecutionHandler = Callable[
    [
        FactoryRunRequest,
        WorkspaceRecord,
        object,
    ],
    Awaitable[FactoryExecutionResult],
]


class ProjectOrchestrator:
    def __init__(
        self,
        execution_handler: ExecutionHandler,
    ) -> None:
        self.execution_handler = execution_handler
        self.analyzer = RepositoryAnalyzer()
        self.context_builder = ContextBuilder()
        self.planner = DeterministicPlanner()
        self.reviewer = ReviewEngine()
        self.completion_auditor = CompletionAuditor()
        self.knowledge_promoter = KnowledgePromoter()

    async def run(
        self,
        request: FactoryRunRequest,
    ) -> FactoryRunResult:
        result = FactoryRunResult(
            project_id=request.project_id,
            run_id=request.run_id,
            phase=FactoryRunPhase.CREATED,
        )

        workspace_record: WorkspaceRecord | None = None

        try:
            self._event(
                result,
                FactoryRunPhase.ANALYZING,
                "Analyzing source repository.",
            )
            analysis = self.analyzer.analyze(
                request.repository_path
            )
            result.analysis = analysis

            self._event(
                result,
                FactoryRunPhase.CONTEXT_BUILDING,
                "Building focused repository context.",
            )
            context = self.context_builder.build(
                analysis=analysis,
                objective=request.objective,
                constraints=request.constraints,
                explicit_files=request.explicit_context_files,
            )
            result.context = context

            self._event(
                result,
                FactoryRunPhase.PLANNING,
                "Creating structured project plan.",
            )
            plan = self.planner.create_plan(
                PlanningRequest(
                    objective=request.objective,
                    context=context,
                )
            )
            result.plan = plan

            self._event(
                result,
                FactoryRunPhase.WORKSPACE_CREATING,
                "Creating isolated Git worktree.",
            )
            workspace_manager = WorkspaceManager(
                request.workspace_root
            )
            workspace_record = workspace_manager.create(
                source_repository=request.repository_path,
                project_id=request.project_id,
                run_id=request.run_id,
                base_revision=request.base_revision,
            )
            result.workspace_path = (
                workspace_record.workspace_path
            )

            self._event(
                result,
                FactoryRunPhase.EXECUTING,
                "Executing planned work in isolated workspace.",
            )
            execution = await self.execution_handler(
                request,
                workspace_record,
                plan,
            )

            self._event(
                result,
                FactoryRunPhase.VALIDATING,
                "Running validation checks.",
            )
            validation = await self._validate(
                request=request,
                workspace_path=workspace_record.workspace_path,
            )
            result.validation = validation

            self._event(
                result,
                FactoryRunPhase.REVIEWING,
                "Reviewing the generated change set.",
            )
            review = self.reviewer.review(
                ReviewInput(
                    diff_text=execution.diff_text,
                    changed_files=execution.changed_files,
                    allowed_paths=request.allowed_change_paths,
                    validation_passed=validation.passed,
                    acceptance_criteria=request.acceptance_criteria,
                )
            )
            result.review = review

            self._event(
                result,
                FactoryRunPhase.COMPLETING,
                "Auditing completion evidence.",
            )
            required_task_ids = [
                task.id
                for task in plan.tasks
            ]

            completion = self.completion_auditor.audit(
                CompletionInput(
                    required_task_ids=required_task_ids,
                    completed_task_ids=(
                        execution.completed_task_ids
                    ),
                    required_evidence=[
                        "diff",
                        "validation",
                        "review",
                    ],
                    available_evidence=(
                        execution.evidence_refs
                    ),
                    validation=validation,
                    review=review,
                    acceptance_criteria=(
                        request.acceptance_criteria
                    ),
                    satisfied_criteria=(
                        request.acceptance_criteria
                        if validation.passed
                        else []
                    ),
                )
            )
            result.completion = completion

            self._event(
                result,
                FactoryRunPhase.DELIVERING,
                "Generating delivery artifacts.",
            )
            delivery_service = DeliveryService(
                request.report_root
            )
            delivery = delivery_service.create(
                project_id=request.project_id,
                run_id=request.run_id,
                repository_path=request.repository_path,
                base_revision=(
                    workspace_record.base_revision
                ),
                branch=workspace_record.branch,
                changed_files=execution.changed_files,
                diff_text=execution.diff_text,
                validation=validation,
                review=review,
                completion=completion,
                change_summary=(
                    request.change_summary
                    or request.objective
                ),
                known_risks=completion.risks,
                recommended_commit_message=(
                    request.recommended_commit_message
                ),
            )
            result.delivery = delivery

            self._event(
                result,
                FactoryRunPhase.PROMOTING_KNOWLEDGE,
                "Evaluating reusable knowledge promotion.",
            )
            promotion = self.knowledge_promoter.promote(
                PromotionInput(
                    category="projects",
                    title=request.objective,
                    summary=(
                        request.change_summary
                        or request.objective
                    ),
                    repository_fingerprint=(
                        analysis.head_commit
                    ),
                    tags=[
                        "af-core",
                        "completed-run",
                    ],
                    evidence_refs=[
                        artifact.relative_path
                        for artifact in delivery.artifacts
                    ],
                    validation=validation,
                    review=review,
                    completion=completion,
                )
            )

            if (
                promotion.status
                is PromotionStatus.PROMOTED
                and promotion.record is not None
            ):
                store = FileKnowledgeStore(
                    request.knowledge_root
                )
                store.save(promotion.record)
                result.knowledge = promotion.record

            self._event(
                result,
                FactoryRunPhase.COMPLETED,
                "Factory run completed.",
            )

            return result

        except Exception as exc:
            result.failure_reason = str(exc)

            self._event(
                result,
                FactoryRunPhase.FAILED,
                "Factory run failed.",
                {"error": str(exc)},
            )

            return result

    async def _validate(
        self,
        *,
        request: FactoryRunRequest,
        workspace_path: str,
    ):
        commands = request.validation_commands or [
            ["git", "diff", "--check"]
        ]

        plan = ValidationPlan(
            checks=[
                ValidationCheck(
                    name=f"validation-{index}",
                    command=command,
                )
                for index, command in enumerate(
                    commands,
                    start=1,
                )
            ]
        )

        engine = ValidationEngine(
            workspace_path
        )
        return await engine.validate(plan)

    def _event(
        self,
        result: FactoryRunResult,
        phase: FactoryRunPhase,
        message: str,
        data: dict | None = None,
    ) -> None:
        result.phase = phase
        result.events.append(
            FactoryRunEvent(
                sequence=len(result.events) + 1,
                phase=phase,
                message=message,
                data=data or {},
            )
        )
