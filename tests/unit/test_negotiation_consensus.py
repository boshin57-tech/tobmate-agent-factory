from __future__ import annotations

from af_core.organization import (
    ConsensusFailureReason,
    ConsensusPolicy,
    NegotiationDecisionType,
    NegotiationParticipant,
    NegotiationParticipantRole,
    NegotiationProposal,
    NegotiationSession,
    NegotiationVote,
    ProposalStatus,
    SessionConsensusEngine,
    WeightedConsensusEngine,
)


def make_session(
    *,
    consensus_ratio: float = 0.67,
) -> NegotiationSession:
    return NegotiationSession(
        workspace_id="workspace-001",
        team_id="team-001",
        subject="Implementation choice",
        objective="Choose the best plan",
        created_by="manager-agent",
        required_consensus_ratio=(
            consensus_ratio
        ),
        participants=[
            NegotiationParticipant(
                agent_id="architect-agent",
                role=(
                    NegotiationParticipantRole
                    .PROPOSER
                ),
                voting_weight=1.0,
            ),
            NegotiationParticipant(
                agent_id="security-agent",
                role=(
                    NegotiationParticipantRole
                    .REVIEWER
                ),
                voting_weight=1.0,
            ),
            NegotiationParticipant(
                agent_id="manager-agent",
                role=(
                    NegotiationParticipantRole
                    .DECISION_MAKER
                ),
                voting_weight=2.0,
                can_veto=True,
            ),
        ],
    )


def proposal(
    *,
    session_id: str,
    proposal_id: str = "proposal-a",
    quality: float = 90,
    cost: float = 20,
) -> NegotiationProposal:
    return NegotiationProposal(
        proposal_id=proposal_id,
        session_id=session_id,
        proposer_agent_id=(
            "architect-agent"
        ),
        title=proposal_id,
        summary="Implementation proposal",
        expected_quality=quality,
        estimated_cost=cost,
        estimated_duration_minutes=120,
        risk_score=15,
        confidence_score=90,
        metadata={
            "security_score": "90",
            "reliability_score": "90",
            "maintainability_score": "90",
        },
    )


def test_weighted_vote_reaches_consensus():

    session = make_session()

    item = proposal(
        session_id=session.session_id
    )

    session = session.model_copy(
        update={
            "proposals": [item],
            "votes": [
                NegotiationVote(
                    session_id=(
                        session.session_id
                    ),
                    proposal_id=(
                        item.proposal_id
                    ),
                    voter_agent_id=(
                        "architect-agent"
                    ),
                    approve=True,
                    score=90,
                ),
                NegotiationVote(
                    session_id=(
                        session.session_id
                    ),
                    proposal_id=(
                        item.proposal_id
                    ),
                    voter_agent_id=(
                        "manager-agent"
                    ),
                    approve=True,
                    score=95,
                ),
            ],
        }
    )

    result = (
        WeightedConsensusEngine()
        .evaluate_proposal(
            session=session,
            proposal=item,
        )
    )

    assert result.consensus_reached

    assert (
        result.cast_voting_weight
        == 3.0
    )

    assert (
        result.approval_ratio
        == 1.0
    )

    assert result.quorum_reached


def test_low_weight_votes_can_fail_approval_ratio():

    session = make_session(
        consensus_ratio=0.67
    )

    item = proposal(
        session_id=session.session_id
    )

    session = session.model_copy(
        update={
            "proposals": [item],
            "votes": [
                NegotiationVote(
                    session_id=(
                        session.session_id
                    ),
                    proposal_id=(
                        item.proposal_id
                    ),
                    voter_agent_id=(
                        "architect-agent"
                    ),
                    approve=True,
                    score=90,
                ),
                NegotiationVote(
                    session_id=(
                        session.session_id
                    ),
                    proposal_id=(
                        item.proposal_id
                    ),
                    voter_agent_id=(
                        "manager-agent"
                    ),
                    approve=False,
                    score=30,
                ),
            ],
        }
    )

    result = (
        WeightedConsensusEngine()
        .evaluate_proposal(
            session=session,
            proposal=item,
        )
    )

    assert not result.consensus_reached

    assert (
        result.approval_ratio
        < 0.67
    )

    assert (
        ConsensusFailureReason
        .APPROVAL_RATIO_NOT_REACHED
        in result.failure_reasons
    )


def test_authorized_veto_blocks_consensus():

    session = make_session()

    item = proposal(
        session_id=session.session_id
    )

    session = session.model_copy(
        update={
            "proposals": [item],
            "votes": [
                NegotiationVote(
                    session_id=(
                        session.session_id
                    ),
                    proposal_id=(
                        item.proposal_id
                    ),
                    voter_agent_id=(
                        "architect-agent"
                    ),
                    approve=True,
                    score=95,
                ),
                NegotiationVote(
                    session_id=(
                        session.session_id
                    ),
                    proposal_id=(
                        item.proposal_id
                    ),
                    voter_agent_id=(
                        "security-agent"
                    ),
                    approve=True,
                    score=95,
                ),
                NegotiationVote(
                    session_id=(
                        session.session_id
                    ),
                    proposal_id=(
                        item.proposal_id
                    ),
                    voter_agent_id=(
                        "manager-agent"
                    ),
                    approve=False,
                    score=20,
                    veto=True,
                ),
            ],
        }
    )

    result = (
        SessionConsensusEngine()
        .evaluate(session)
    )

    assert not result.consensus_reached

    assert (
        result.decision_type
        is NegotiationDecisionType
        .ESCALATE
    )

    assert result.resolution is not None
    assert result.resolution.escalated


def test_quorum_failure_requests_revision():

    session = make_session()

    item = proposal(
        session_id=session.session_id
    )

    session = session.model_copy(
        update={
            "proposals": [item],
            "votes": [
                NegotiationVote(
                    session_id=(
                        session.session_id
                    ),
                    proposal_id=(
                        item.proposal_id
                    ),
                    voter_agent_id=(
                        "architect-agent"
                    ),
                    approve=True,
                    score=90,
                )
            ],
        }
    )

    result = SessionConsensusEngine(
        policy=ConsensusPolicy(
            minimum_quorum_ratio=0.75
        )
    ).evaluate(session)

    assert not result.consensus_reached

    assert (
        result.decision_type
        is NegotiationDecisionType
        .REQUEST_REVISION
    )


def test_multiple_consensus_proposals_use_scoring_tie_break():

    session = make_session(
        consensus_ratio=0.50
    )

    weak = proposal(
        session_id=session.session_id,
        proposal_id="weak",
        quality=65,
        cost=80,
    )

    strong = proposal(
        session_id=session.session_id,
        proposal_id="strong",
        quality=95,
        cost=15,
    )

    votes = []

    for item in (weak, strong):
        votes.extend(
            [
                NegotiationVote(
                    session_id=(
                        session.session_id
                    ),
                    proposal_id=(
                        item.proposal_id
                    ),
                    voter_agent_id=(
                        "architect-agent"
                    ),
                    approve=True,
                    score=90,
                ),
                NegotiationVote(
                    session_id=(
                        session.session_id
                    ),
                    proposal_id=(
                        item.proposal_id
                    ),
                    voter_agent_id=(
                        "manager-agent"
                    ),
                    approve=True,
                    score=90,
                ),
            ]
        )

    session = session.model_copy(
        update={
            "proposals": [weak, strong],
            "votes": votes,
        }
    )

    result = (
        SessionConsensusEngine()
        .evaluate(session)
    )

    assert result.consensus_reached

    assert (
        result.selected_proposal_id
        == "strong"
    )

    assert result.resolution is not None

    assert (
        result.resolution
        .strategy.value
        == "select_highest_proposal_score"
    )


def test_no_acceptable_proposal_rejects_all():

    session = make_session()

    weak = NegotiationProposal(
        proposal_id="very-weak",
        session_id=session.session_id,
        proposer_agent_id=(
            "architect-agent"
        ),
        title="Very Weak",
        summary="Weak proposal",
        estimated_cost=100,
        estimated_duration_minutes=1440,
        expected_quality=0,
        risk_score=100,
        confidence_score=0,
        metadata={
            "security_score": "0",
            "reliability_score": "0",
            "maintainability_score": "0",
        },
    )

    session = session.model_copy(
        update={
            "proposals": [weak],
            "votes": [],
        }
    )

    result = (
        SessionConsensusEngine()
        .evaluate(session)
    )

    assert (
        result.decision_type
        is NegotiationDecisionType
        .REJECT_ALL
    )
