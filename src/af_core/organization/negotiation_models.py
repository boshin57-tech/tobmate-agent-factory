from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class NegotiationStatus(str, Enum):
    CREATED = "created"
    OPEN = "open"
    EVALUATING = "evaluating"
    CONSENSUS_REACHED = "consensus_reached"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    CLOSED = "closed"


class ProposalStatus(str, Enum):
    SUBMITTED = "submitted"
    COUNTERED = "countered"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    SUPERSEDED = "superseded"


class NegotiationDecisionType(str, Enum):
    ACCEPT_PROPOSAL = "accept_proposal"
    REJECT_ALL = "reject_all"
    REQUEST_REVISION = "request_revision"
    ESCALATE = "escalate"
    NO_DECISION = "no_decision"


class NegotiationParticipantRole(str, Enum):
    PROPOSER = "proposer"
    REVIEWER = "reviewer"
    DECISION_MAKER = "decision_maker"
    OBSERVER = "observer"
    MEDIATOR = "mediator"


class NegotiationCriterion(str, Enum):
    QUALITY = "quality"
    COST = "cost"
    SPEED = "speed"
    RISK = "risk"
    SECURITY = "security"
    RELIABILITY = "reliability"
    MAINTAINABILITY = "maintainability"


class NegotiationParticipant(BaseModel):
    agent_id: str
    role: NegotiationParticipantRole

    voting_weight: float = 1.0

    capabilities: set[str] = Field(
        default_factory=set
    )

    can_submit_proposal: bool = True
    can_vote: bool = True
    can_veto: bool = False

    metadata: dict[str, str] = Field(
        default_factory=dict
    )

    @field_validator("agent_id")
    @classmethod
    def validate_agent_id(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "agent_id must not be empty"
            )

        return normalized

    @field_validator("voting_weight")
    @classmethod
    def validate_voting_weight(
        cls,
        value: float,
    ) -> float:
        if value <= 0:
            raise ValueError(
                "voting_weight must be positive"
            )

        return value


class NegotiationProposal(BaseModel):
    proposal_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    session_id: str

    proposer_agent_id: str

    title: str
    summary: str

    implementation_plan: list[str] = Field(
        default_factory=list
    )

    estimated_cost: float = 0.0
    estimated_duration_minutes: int = 0

    expected_quality: float = 0.0
    risk_score: float = 0.0
    confidence_score: float = 0.0

    required_capabilities: set[str] = Field(
        default_factory=set
    )

    dependencies: list[str] = Field(
        default_factory=list
    )

    status: ProposalStatus = (
        ProposalStatus.SUBMITTED
    )

    parent_proposal_id: str | None = None

    created_at: datetime = Field(
        default_factory=lambda:
            datetime.now(timezone.utc)
    )

    metadata: dict[str, str] = Field(
        default_factory=dict
    )

    @field_validator(
        "session_id",
        "proposer_agent_id",
        "title",
        "summary",
    )
    @classmethod
    def validate_required_text(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "value must not be empty"
            )

        return normalized

    @field_validator(
        "expected_quality",
        "risk_score",
        "confidence_score",
    )
    @classmethod
    def validate_score(
        cls,
        value: float,
    ) -> float:
        if not 0.0 <= value <= 100.0:
            raise ValueError(
                "score must be between 0 and 100"
            )

        return value

    @field_validator("estimated_cost")
    @classmethod
    def validate_cost(
        cls,
        value: float,
    ) -> float:
        if value < 0:
            raise ValueError(
                "estimated_cost must not be negative"
            )

        return value

    @field_validator(
        "estimated_duration_minutes"
    )
    @classmethod
    def validate_duration(
        cls,
        value: int,
    ) -> int:
        if value < 0:
            raise ValueError(
                "duration must not be negative"
            )

        return value


class NegotiationVote(BaseModel):
    vote_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    session_id: str
    proposal_id: str
    voter_agent_id: str

    approve: bool

    score: float = 0.0

    rationale: str = ""

    veto: bool = False

    created_at: datetime = Field(
        default_factory=lambda:
            datetime.now(timezone.utc)
    )

    @field_validator("score")
    @classmethod
    def validate_score(
        cls,
        value: float,
    ) -> float:
        if not 0.0 <= value <= 100.0:
            raise ValueError(
                "score must be between 0 and 100"
            )

        return value


class NegotiationDecision(BaseModel):
    decision_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    session_id: str

    decision_type: NegotiationDecisionType

    selected_proposal_id: str | None = None

    decided_by: str

    reasons: list[str] = Field(
        default_factory=list
    )

    approval_score: float = 0.0

    decided_at: datetime = Field(
        default_factory=lambda:
            datetime.now(timezone.utc)
    )


class NegotiationSession(BaseModel):
    session_id: str = Field(
        default_factory=lambda:
            str(uuid4())
    )

    workspace_id: str
    team_id: str | None = None

    subject: str
    objective: str

    status: NegotiationStatus = (
        NegotiationStatus.CREATED
    )

    participants: list[
        NegotiationParticipant
    ] = Field(
        default_factory=list
    )

    proposals: list[
        NegotiationProposal
    ] = Field(
        default_factory=list
    )

    votes: list[
        NegotiationVote
    ] = Field(
        default_factory=list
    )

    decision: NegotiationDecision | None = None

    required_consensus_ratio: float = 0.67

    maximum_proposals: int = 10

    created_by: str

    created_at: datetime = Field(
        default_factory=lambda:
            datetime.now(timezone.utc)
    )

    opened_at: datetime | None = None
    closed_at: datetime | None = None

    metadata: dict[str, str] = Field(
        default_factory=dict
    )

    @field_validator(
        "workspace_id",
        "subject",
        "objective",
        "created_by",
    )
    @classmethod
    def validate_required_text(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "value must not be empty"
            )

        return normalized

    @field_validator(
        "required_consensus_ratio"
    )
    @classmethod
    def validate_consensus_ratio(
        cls,
        value: float,
    ) -> float:
        if not 0.0 < value <= 1.0:
            raise ValueError(
                "required_consensus_ratio must "
                "be greater than 0 and at most 1"
            )

        return value

    @field_validator("maximum_proposals")
    @classmethod
    def validate_maximum_proposals(
        cls,
        value: int,
    ) -> int:
        if value < 1:
            raise ValueError(
                "maximum_proposals must be at least 1"
            )

        return value
