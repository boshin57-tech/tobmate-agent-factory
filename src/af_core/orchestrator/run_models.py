from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from af_core.assurance.completion import CompletionDecision
from af_core.assurance.reviewer import ReviewResult
from af_core.assurance.validator import ValidationResult
from af_core.delivery.manifest import DeliveryManifest
from af_core.knowledge.store import KnowledgeRecord
from af_core.repository.analyzer import RepositoryAnalysis
from af_core.repository.context_builder import ContextPackage

from .planner import ProjectPlan


class FactoryRunPhase(StrEnum):
    CREATED = "CREATED"
    ANALYZING = "ANALYZING"
    CONTEXT_BUILDING = "CONTEXT_BUILDING"
    PLANNING = "PLANNING"
    WORKSPACE_CREATING = "WORKSPACE_CREATING"
    EXECUTING = "EXECUTING"
    VALIDATING = "VALIDATING"
    REVIEWING = "REVIEWING"
    COMPLETING = "COMPLETING"
    DELIVERING = "DELIVERING"
    PROMOTING_KNOWLEDGE = "PROMOTING_KNOWLEDGE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class FactoryRunEvent(BaseModel):
    sequence: int
    phase: FactoryRunPhase
    message: str
    data: dict = Field(default_factory=dict)


class FactoryRunRequest(BaseModel):
    project_id: str
    run_id: str
    repository_path: str
    objective: str
    workspace_root: str
    report_root: str
    knowledge_root: str
    base_revision: str = "HEAD"
    constraints: list[str] = Field(default_factory=list)
    explicit_context_files: list[str] = Field(default_factory=list)
    allowed_change_paths: list[str] = Field(default_factory=list)
    validation_commands: list[list[str]] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    change_summary: str = ""
    recommended_commit_message: str | None = None


class FactoryExecutionResult(BaseModel):
    changed_files: list[str] = Field(default_factory=list)
    diff_text: str = ""
    completed_task_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class FactoryRunResult(BaseModel):
    project_id: str
    run_id: str
    phase: FactoryRunPhase
    events: list[FactoryRunEvent] = Field(default_factory=list)
    analysis: RepositoryAnalysis | None = None
    context: ContextPackage | None = None
    plan: ProjectPlan | None = None
    validation: ValidationResult | None = None
    review: ReviewResult | None = None
    completion: CompletionDecision | None = None
    delivery: DeliveryManifest | None = None
    knowledge: KnowledgeRecord | None = None
    workspace_path: str | None = None
    failure_reason: str | None = None
