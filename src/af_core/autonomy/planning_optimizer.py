from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, Field

from .autonomous_models import (
    AutonomousPlan,
)


class OptimizationIssue(BaseModel):

    issue_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    category: str

    description: str

    severity: str



class OptimizationImprovement(BaseModel):

    improvement_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    action: str

    expected_effect: str



class OptimizationResult(BaseModel):

    optimization_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    plan_id: str

    issues: list[
        OptimizationIssue
    ]

    improvements: list[
        OptimizationImprovement
    ]

    optimized: bool



class PlanningOptimizationEngine:
    """
    Optimizes autonomous plans by
    detecting execution inefficiencies.
    """


    def optimize(
        self,
        plan: AutonomousPlan,
    ) -> OptimizationResult:


        issues = []

        improvements = []


        if len(plan.objectives) > 5:

            issues.append(
                OptimizationIssue(
                    category="complexity",

                    description=(
                        "Too many objectives "
                        "may increase execution risk."
                    ),

                    severity="medium",
                )
            )


            improvements.append(
                OptimizationImprovement(
                    action=(
                        "Split objectives "
                        "into staged execution phases."
                    ),

                    expected_effect=(
                        "Improved planning stability."
                    ),
                )
            )


        if len(plan.improvements) > 3:

            issues.append(
                OptimizationIssue(
                    category="scope",

                    description=(
                        "Large improvement scope "
                        "requires prioritization."
                    ),

                    severity="medium",
                )
            )


            improvements.append(
                OptimizationImprovement(
                    action=(
                        "Prioritize critical "
                        "improvement targets."
                    ),

                    expected_effect=(
                        "Reduced execution overhead."
                    ),
                )
            )


        return OptimizationResult(

            plan_id=plan.plan_id,

            issues=issues,

            improvements=improvements,

            optimized=
                len(issues) == 0,
        )
