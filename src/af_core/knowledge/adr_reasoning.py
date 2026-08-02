from __future__ import annotations

from pydantic import BaseModel, Field
from uuid import uuid4

from .adr_graph import (
    ADRKnowledgeGraphEngine,
)


class ReasoningDecision:

    ACCEPT = "accept"

    EXTEND = "extend"

    REVISE = "revise"

    CONFLICT = "conflict"



class ADRReasoningRequest(BaseModel):

    topic: str

    description: str



class ADRReasoningResult(BaseModel):

    reasoning_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    topic: str

    related_adr_count: int

    decision: str

    explanation: str

    related_adr_ids: list[str] = Field(
        default_factory=list
    )



class ADRReasoningEngine:
    """
    Evaluates new architecture requests
    against existing ADR knowledge.
    """


    def __init__(
        self,
        graph:
        ADRKnowledgeGraphEngine,
    ) -> None:

        self._graph = graph



    def reason(
        self,
        request: ADRReasoningRequest,
    ) -> ADRReasoningResult:


        related = []

        keyword = (
            request.topic.lower()
        )


        for adr in self._graph.nodes():

            text = (
                adr.title
                +
                adr.context
                +
                adr.decision
            ).lower()


            if keyword in text:

                related.append(
                    adr
                )


        if not related:

            decision = (
                ReasoningDecision.EXTEND
            )

            explanation = (
                "No conflicting ADR found. "
                "New decision can extend architecture."
            )


        else:

            decision = (
                ReasoningDecision.ACCEPT
            )

            explanation = (
                "Existing architecture decisions "
                "are compatible."
            )


        return ADRReasoningResult(
            topic=request.topic,

            related_adr_count=len(
                related
            ),

            decision=decision,

            explanation=explanation,

            related_adr_ids=[
                adr.adr_id
                for adr
                in related
            ],
        )
