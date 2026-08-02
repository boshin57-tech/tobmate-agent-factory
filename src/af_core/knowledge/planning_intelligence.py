from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, Field

from .knowledge_selector import (
    KnowledgeSelectorEngine,
    SelectionRequest,
    KnowledgeSelection,
)


class PlanningRequest(BaseModel):

    project_name: str

    requirements: list[str]


class PlanningResult(BaseModel):

    plan_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    project_name: str

    selected_knowledge: KnowledgeSelection

    execution_steps: list[str]


class PlanningIntelligenceEngine:
    """
    Creates project plans using
    accumulated knowledge intelligence.
    """


    def __init__(
        self,
        selector:
            KnowledgeSelectorEngine,
    ) -> None:

        self._selector = selector


    def create_plan(
        self,
        request: PlanningRequest,
    ) -> PlanningResult:


        keyword = " ".join(
            request.requirements
        )


        knowledge = (
            self._selector.select(
                SelectionRequest(
                    keyword=keyword,
                    limit=10,
                )
            )
        )


        steps = [
            "Analyze requirements",
            "Select architecture pattern",
            "Assign reusable components",
            "Generate agent workflow",
            "Execute validation",
        ]


        return PlanningResult(
            project_name=
                request.project_name,

            selected_knowledge=
                knowledge,

            execution_steps=
                steps,
        )
