from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator

from .negotiation_models import (
    NegotiationDecisionType,
)


class ConsensusFailureReason(str, Enum):
    NONE = "none"

    NO_PROPOSALS = "no_proposals"
    NO_VOTERS = "no_voters"

    QUORUM_NOT_REACHED = (
        "quorum_not_reached"
    )

    APPROVAL_RATIO_NOT_REACHED = (
        "approval_ratio_not_reached"
    )

    MINIMUM_SCORE_NOT_REACHED = (
        "minimum_score_not_reached"
    )

    VETO_APPLIED = "veto_applied"

    TIED_PROPOSALS = "tied_proposals"

    DECISION_MAKER_VOTE_MISSING = (
        "decision_maker_vote_missing"
    )


class ConflictResolutionStrategy(str, Enum):
    NONE = "none"

    SELECT_HIGHEST_CONSENSUS = (
        "select_highest_consensus"
    )

    SELECT_HIGHEST_PROPOSAL_SCORE = (
        "select_highest_proposal_score"
    )

    REQUEST_REVISION = (
        "request_revision"
    )

    REJECT_ALL = "reject_all"

    ESCALATE = "escalate"


class ConsensusPolicy(BaseModel):
    """
    Governance policy for weighted Agent voting.

    `required_approval_ratio=None` means that the session's own
    required_consensus_ratio is used.
    """

    minimum_quorum_ratio: float = 0.50

    required_approval_ratio: (
        float | None
    ) = None

    minimum_average_vote_score: float = 0.0

    veto_blocks_consensus: bool = True

    require_decision_maker_vote: bool = False

    allow_scoring_tie_break: bool = True

    reject_all_when_no_acceptable_proposal: bool = True

    score_tie_tolerance: float = 0.0001

    @field_validator(
        "minimum_quorum_ratio",
        "required_approval_ratio",
    )
    @classmethod
    def validate_ratio(
        cls,
        value: float | None,
    ) -> float | None:
        if value is None:
            return value

        if not 0.0 < value <= 1.0:
            raise ValueError(
                "ratio must be greater than 0 and at most 1"
            )

        return value

    @field_validator(
        "minimum_average_vote_score"
    )
    @classmethod
    def validate_vote_score(
        cls,
        value: float,
    ) -> float:
        if not 0.0 <= value <= 100.0:
            raise ValueError(
                "minimum_average_vote_score "
                "must be between 0 and 100"
            )

        return value

    @field_validator(
        "score_tie_tolerance"
    )
    @classmethod
    def validate_tolerance(
        cls,
        value: float,
    ) -> float:
        if value < 0:
            raise ValueError(
                "score_tie_tolerance "
                "must not be negative"
            )

        return value


class ProposalConsensusResult(BaseModel):
    proposal_id: str

    eligible_voter_count: int = 0
    cast_vote_count: int = 0

    eligible_voting_weight: float = 0.0
    cast_voting_weight: float = 0.0

    approval_weight: float = 0.0
    rejection_weight: float = 0.0

    quorum_ratio: float = 0.0
    approval_ratio: float = 0.0

    average_vote_score: float = 0.0

    vetoed: bool = False

    quorum_reached: bool = False
    approval_reached: bool = False
    score_reached: bool = False

    consensus_reached: bool = False

    approving_agent_ids: list[str] = Field(
        default_factory=list
    )

    rejecting_agent_ids: list[str] = Field(
        default_factory=list
    )

    veto_agent_ids: list[str] = Field(
        default_factory=list
    )

    missing_voter_agent_ids: list[str] = Field(
        default_factory=list
    )

    failure_reasons: list[
        ConsensusFailureReason
    ] = Field(
        default_factory=list
    )


class ConflictResolutionResult(BaseModel):
    strategy: ConflictResolutionStrategy

    decision_type: NegotiationDecisionType

    selected_proposal_id: str | None = None

    conflicting_proposal_ids: list[str] = Field(
        default_factory=list
    )

    reasons: list[str] = Field(
        default_factory=list
    )

    escalated: bool = False


class SessionConsensusResult(BaseModel):
    session_id: str

    proposal_results: list[
        ProposalConsensusResult
    ] = Field(
        default_factory=list
    )

    consensus_proposal_ids: list[str] = Field(
        default_factory=list
    )

    selected_proposal_id: str | None = None

    decision_type: NegotiationDecisionType = (
        NegotiationDecisionType
        .NO_DECISION
    )

    resolution: (
        ConflictResolutionResult
        | None
    ) = None

    consensus_reached: bool = False

    reasons: list[str] = Field(
        default_factory=list
    )
