from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, Field


class ImprovementType:

    SUCCESS = "success"

    FAILURE = "failure"

    CAPABILITY = "capability"

    PATTERN = "pattern"



class ExecutionFeedback(BaseModel):

    execution_id: str

    success: bool

    summary: str

    metrics: dict[str, str] = Field(
        default_factory=dict
    )



class ImprovementAction(BaseModel):

    action_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    improvement_type: str

    description: str

    target: str



class SelfImprovementResult(BaseModel):

    improvement_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    execution_id: str

    actions: list[
        ImprovementAction
    ]

    learning_generated: bool



class SelfImprovementEngine:
    """
    Learns from execution results and
    generates improvement actions.
    """


    def improve(
        self,
        feedback: ExecutionFeedback,
    ) -> SelfImprovementResult:


        actions = []


        if feedback.success:

            actions.append(
                ImprovementAction(
                    improvement_type=
                    ImprovementType.SUCCESS,

                    description=(
                        "Promote successful "
                        "execution pattern."
                    ),

                    target="pattern_library",
                )
            )


        else:

            actions.append(
                ImprovementAction(
                    improvement_type=
                    ImprovementType.FAILURE,

                    description=(
                        "Analyze failure and "
                        "create recovery improvement."
                    ),

                    target="recovery_policy",
                )
            )


        return SelfImprovementResult(

            execution_id=
            feedback.execution_id,

            actions=actions,

            learning_generated=
            True,
        )
