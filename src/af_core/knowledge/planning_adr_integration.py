from __future__ import annotations

from pydantic import BaseModel, Field

from .planning_intelligence import (
    PlanningRequest,
    PlanningResult,
)

from .adr_reasoning import (
    ADRReasoningEngine,
    ADRReasoningRequest,
)

from .decision_recommendation import (
    DecisionRecommendationEngine,
    DecisionRecommendationRequest,
    DecisionOption,
)


class ArchitectureAwarePlan(BaseModel):

    plan_id: str = Field(
        default_factory=lambda:
            "architecture-plan"
    )

    project_name: str

    base_plan: PlanningResult

    adr_decision: str

    adr_explanation: str


class PlanningADRIntegrationEngine:
    """
    Integrates ADR intelligence
    into planning decisions.
    """


    def __init__(
        self,
        planner,
        adr_reasoner:
            ADRReasoningEngine,
        recommender:
            DecisionRecommendationEngine,
    ) -> None:

        self._planner = planner

        self._reasoner = adr_reasoner

        self._recommender = recommender



    def create_architecture_plan(
        self,
        request: PlanningRequest,
    ) -> ArchitectureAwarePlan:


        base_plan = (
            self._planner.create_plan(
                request
            )
        )


        topic = request.project_name


        reasoning = (
            self._reasoner.reason(
                ADRReasoningRequest(
                    topic=topic,
                    description=
                    "Architecture planning request",
                )
            )
        )


        recommendation = (
            self._recommender.recommend(
                DecisionRecommendationRequest(
                    topic=topic,
                    options=[
                        DecisionOption(
                            name=
                            "Reuse Existing Architecture",
                            description=
                            "Apply existing ADR decisions",
                            score=0.9,
                        ),
                        DecisionOption(
                            name=
                            "Create New Architecture",
                            description=
                            "Introduce new design",
                            score=0.5,
                        ),
                    ],
                )
            )
        )


        return ArchitectureAwarePlan(
            project_name=
                request.project_name,

            base_plan=
                base_plan,

            adr_decision=
                recommendation
                .selected_option_name,

            adr_explanation=
                reasoning
                .explanation,
        )
