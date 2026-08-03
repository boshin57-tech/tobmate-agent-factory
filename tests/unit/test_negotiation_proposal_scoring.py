from __future__ import annotations

from af_core.organization import (
    NegotiationProposal,
    ProposalScoringEngine,
    ProposalScoringPolicy,
    ProposalScoringWeights,
)


def proposal(
    *,
    proposal_id: str,
    cost: float,
    duration: int,
    quality: float,
    risk: float,
    confidence: float,
    security: float = 80.0,
    reliability: float = 80.0,
    maintainability: float = 80.0,
) -> NegotiationProposal:
    return NegotiationProposal(
        proposal_id=proposal_id,
        session_id="session-001",
        proposer_agent_id=(
            f"{proposal_id}-agent"
        ),
        title=f"Proposal {proposal_id}",
        summary="Implementation proposal",
        estimated_cost=cost,
        estimated_duration_minutes=duration,
        expected_quality=quality,
        risk_score=risk,
        confidence_score=confidence,
        metadata={
            "security_score":
                str(security),
            "reliability_score":
                str(reliability),
            "maintainability_score":
                str(maintainability),
        },
    )


def test_proposal_score_is_normalized():

    engine = ProposalScoringEngine()

    result = engine.score(
        proposal(
            proposal_id="proposal-a",
            cost=20,
            duration=120,
            quality=90,
            risk=15,
            confidence=95,
        )
    )

    assert (
        0.0
        <= result.weighted_score
        <= 100.0
    )

    assert result.acceptable
    assert result.strengths


def test_lower_cost_receives_better_cost_score():

    engine = ProposalScoringEngine()

    low_cost = engine.score(
        proposal(
            proposal_id="low-cost",
            cost=10,
            duration=120,
            quality=80,
            risk=20,
            confidence=80,
        )
    )

    high_cost = engine.score(
        proposal(
            proposal_id="high-cost",
            cost=90,
            duration=120,
            quality=80,
            risk=20,
            confidence=80,
        )
    )

    assert (
        low_cost.cost_score
        > high_cost.cost_score
    )


def test_lower_risk_receives_better_score():

    engine = ProposalScoringEngine()

    low_risk = engine.score(
        proposal(
            proposal_id="low-risk",
            cost=30,
            duration=120,
            quality=85,
            risk=10,
            confidence=85,
        )
    )

    high_risk = engine.score(
        proposal(
            proposal_id="high-risk",
            cost=30,
            duration=120,
            quality=85,
            risk=90,
            confidence=85,
        )
    )

    assert (
        low_risk.risk_score
        > high_risk.risk_score
    )

    assert (
        low_risk.weighted_score
        > high_risk.weighted_score
    )


def test_rank_returns_best_proposal_first():

    engine = ProposalScoringEngine()

    proposals = [
        proposal(
            proposal_id="weak",
            cost=90,
            duration=1200,
            quality=55,
            risk=80,
            confidence=50,
            security=50,
            reliability=50,
            maintainability=50,
        ),
        proposal(
            proposal_id="strong",
            cost=20,
            duration=120,
            quality=95,
            risk=10,
            confidence=95,
            security=95,
            reliability=95,
            maintainability=95,
        ),
    ]

    result = engine.rank(
        session_id="session-001",
        proposals=proposals,
    )

    assert (
        result.best_proposal_id
        == "strong"
    )

    assert (
        result.ranked_proposal_ids
        == ["strong", "weak"]
    )


def test_custom_weights_change_ranking():

    engine = ProposalScoringEngine(
        policy=ProposalScoringPolicy(
            weights=ProposalScoringWeights(
                quality=10.0,
                cost=0.1,
                speed=0.1,
                risk=0.1,
                security=0.1,
                reliability=0.1,
                maintainability=0.1,
                confidence=0.1,
            )
        )
    )

    quality_first = proposal(
        proposal_id="quality-first",
        cost=90,
        duration=1000,
        quality=100,
        risk=60,
        confidence=90,
    )

    cheap_fast = proposal(
        proposal_id="cheap-fast",
        cost=5,
        duration=30,
        quality=60,
        risk=20,
        confidence=90,
    )

    result = engine.rank(
        session_id="session-001",
        proposals=[
            cheap_fast,
            quality_first,
        ],
    )

    assert (
        result.best_proposal_id
        == "quality-first"
    )


def test_invalid_metadata_uses_default_score():

    engine = ProposalScoringEngine()

    item = proposal(
        proposal_id="invalid-metadata",
        cost=20,
        duration=120,
        quality=85,
        risk=20,
        confidence=90,
    ).model_copy(
        update={
            "metadata": {
                "security_score":
                    "not-a-number",
            }
        }
    )

    result = engine.score(item)

    assert (
        result.security_score
        == engine.policy
        .default_security_score
    )
