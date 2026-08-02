from __future__ import annotations

from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


class DecisionState(str, Enum):

    OBSERVE = "observe"

    ANALYZE = "analyze"

    DECIDE = "decide"

    EXECUTE = "execute"

    LEARN = "learn"

    IMPROVE = "improve"



class DecisionContext(BaseModel):

    execution_id: str

    current_state: str

    metrics: dict[str, str] = Field(
        default_factory=dict
    )



class DecisionAction(BaseModel):

    action_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    state: DecisionState

    action: str

    reason: str



class AutonomousDecisionResult(BaseModel):

    execution_id: str

    actions: list[
        DecisionAction
    ]



class AutonomousDecisionLoop:
    """
    Closed-loop autonomous decision
    controller for Agent Factory.
    """


    def run(
        self,
        context: DecisionContext,
    ) -> AutonomousDecisionResult:


        actions = []


        # OBSERVE

        actions.append(
            DecisionAction(
                state=
                DecisionState.OBSERVE,

                action=
                "Collect execution state",

                reason=
                "Understand current system status",
            )
        )


        # ANALYZE

        actions.append(
            DecisionAction(
                state=
                DecisionState.ANALYZE,

                action=
                "Analyze execution result",

                reason=
                "Detect risks and improvements",
            )
        )


        # DECIDE

        if (
            context.current_state
            == "failed"
        ):

            actions.append(
                DecisionAction(
                    state=
                    DecisionState.DECIDE,

                    action=
                    "Trigger recovery workflow",

                    reason=
                    "Execution failure detected",
                )
            )

        else:

            actions.append(
                DecisionAction(
                    state=
                    DecisionState.DECIDE,

                    action=
                    "Continue execution",

                    reason=
                    "Execution is healthy",
                )
            )


        # LEARN

        actions.append(
            DecisionAction(
                state=
                DecisionState.LEARN,

                action=
                "Update knowledge base",

                reason=
                "Store execution experience",
            )
        )


        # IMPROVE

        actions.append(
            DecisionAction(
                state=
                DecisionState.IMPROVE,

                action=
                "Generate improvement feedback",

                reason=
                "Improve future planning",
            )
        )


        return AutonomousDecisionResult(
            execution_id=
            context.execution_id,

            actions=actions,
        )
