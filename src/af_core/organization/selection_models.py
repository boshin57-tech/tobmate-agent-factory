from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class AgentRankingWeights(BaseModel):
    """
    Configurable weights used when ranking eligible Agent candidates.
    """

    capability_match: float = 10.0
    task_match: float = 5.0
    skill_level: float = 2.0
    exact_capability_fit: float = 4.0
    exact_task_fit: float = 2.0
    specialization_bonus: float = 3.0
    excess_capability_penalty: float = 0.25
    diversity_bonus: float = 2.0

    @field_validator("*")
    @classmethod
    def validate_non_negative(
        cls,
        value: float,
    ) -> float:
        if value < 0:
            raise ValueError(
                "ranking weights must not be negative"
            )

        return value


class DiversityPolicy(BaseModel):
    """
    Controls how the selector balances quality and team diversity.

    Capability profile:
        Sorted complete capability set of an Agent.

    `max_same_capability_profile` prevents a multi-member role from
    selecting too many Agents with an identical capability profile.
    """

    enabled: bool = True

    prefer_distinct_agents: bool = True
    prefer_distinct_capability_profiles: bool = True

    max_same_capability_profile: int = 1

    allow_profile_limit_fallback: bool = True

    @field_validator(
        "max_same_capability_profile"
    )
    @classmethod
    def validate_profile_limit(
        cls,
        value: int,
    ) -> int:
        if value < 1:
            raise ValueError(
                "max_same_capability_profile "
                "must be at least 1"
            )

        return value


class CandidateScore(BaseModel):
    """
    Explainable ranking result for one eligible Agent.
    """

    agent_id: str
    agent_name: str

    matched_capabilities: set[str] = Field(
        default_factory=set
    )

    matched_tasks: set[str] = Field(
        default_factory=set
    )

    capability_profile: tuple[str, ...] = ()

    skill_level: int

    capability_score: float = 0.0
    task_score: float = 0.0
    skill_score: float = 0.0
    exact_fit_score: float = 0.0
    specialization_score: float = 0.0
    diversity_score: float = 0.0
    penalty_score: float = 0.0

    total_score: float = 0.0

    reasons: list[str] = Field(
        default_factory=list
    )


class SelectionResult(BaseModel):
    """
    Complete selection result for one team role.
    """

    role_name: str

    selected_agent_ids: list[str] = Field(
        default_factory=list
    )

    ranked_candidates: list[
        CandidateScore
    ] = Field(
        default_factory=list
    )

    eligible_count: int = 0
    selected_count: int = 0

    diversity_fallback_used: bool = False

    rejection_reasons: dict[
        str,
        list[str],
    ] = Field(
        default_factory=dict
    )
