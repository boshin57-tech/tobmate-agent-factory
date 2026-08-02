from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, Field


class DecisionOption(BaseModel):

    option_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    name: str

    description: str

    score: float = 0.0


class DecisionRecommendationRequest(BaseModel):

    topic: str

    options: list[
        DecisionOption
    ]


class DecisionRecommendationResult(BaseModel):

    recommendation_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    topic: str

    selected_option_id: str

    selected_option_name: str

    reasoning: str

    alternatives: list[str] = Field(
        default_factory=list
    )


class DecisionRecommendationEngine:
    """
    Recommends architecture decisions
    using available decision options.
    """


    def recommend(
        self,
        request:
        DecisionRecommendationRequest,
    ) -> DecisionRecommendationResult:


        if not request.options:

            raise ValueError(
                "No decision options provided"
            )


        ranked = sorted(
            request.options,
            key=lambda option:
                option.score,
            reverse=True,
        )


        selected = ranked[0]


        return DecisionRecommendationResult(

            topic=request.topic,

            selected_option_id=
                selected.option_id,

            selected_option_name=
                selected.name,

            reasoning=(
                "Selected highest ranked "
                "architecture option."
            ),

            alternatives=[
                option.name
                for option
                in ranked[1:]
            ],
        )
