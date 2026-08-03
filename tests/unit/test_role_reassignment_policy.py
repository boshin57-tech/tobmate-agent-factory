from __future__ import annotations

from datetime import datetime, timedelta, timezone

from af_core.organization import (
    AgentAvailabilityStatus,
    AgentRuntimeMetrics,
    DynamicRoleAssignment,
    ReassignmentPolicy,
    RoleAssignmentAction,
    RoleAssignmentReason,
    RoleAssignmentStatus,
    RoleHealthDecision,
    RoleHealthTrigger,
    RoleReassignmentPolicyEngine,
)


def assignment() -> DynamicRoleAssignment:
    return DynamicRoleAssignment(
        request_id="request-001",
        team_id="team-001",
        workspace_id="workspace-001",
        role_name="Move Developer",
        agent_id="move-agent-1",
        agent_name="Move Agent 1",
        action=RoleAssignmentAction.ASSIGN,
        reason=(
            RoleAssignmentReason
            .INITIAL_ASSIGNMENT
        ),
        status=RoleAssignmentStatus.ACTIVE,
    )


def healthy_metrics() -> AgentRuntimeMetrics:
    return AgentRuntimeMetrics(
        agent_id="move-agent-1",
        availability=(
            AgentAvailabilityStatus.AVAILABLE
        ),
        current_assignments=1,
        maximum_assignments=4,
        workload_ratio=0.40,
        success_rate=0.98,
        quality_score=95,
        reliability_score=97,
        consecutive_failures=0,
    )


def test_healthy_assignment_is_kept():

    engine = (
        RoleReassignmentPolicyEngine()
    )

    result = engine.evaluate(
        assignment=assignment(),
        metrics=healthy_metrics(),
    )

    assert (
        result.decision
        is RoleHealthDecision.KEEP
    )

    assert not result.action_required


def test_offline_agent_requires_failover():

    engine = (
        RoleReassignmentPolicyEngine()
    )

    metrics = healthy_metrics().model_copy(
        update={
            "availability":
                AgentAvailabilityStatus
                .OFFLINE,
        }
    )

    result = engine.evaluate(
        assignment=assignment(),
        metrics=metrics,
    )

    assert (
        result.decision
        is RoleHealthDecision.FAILOVER
    )

    assert (
        RoleHealthTrigger.AGENT_OFFLINE
        in result.triggers
    )


def test_overloaded_agent_requires_reassignment():

    engine = (
        RoleReassignmentPolicyEngine()
    )

    metrics = healthy_metrics().model_copy(
        update={
            "workload_ratio": 0.95,
        }
    )

    result = engine.evaluate(
        assignment=assignment(),
        metrics=metrics,
    )

    assert (
        result.decision
        is RoleHealthDecision.REASSIGN
    )

    assert (
        RoleHealthTrigger
        .WORKLOAD_EXCEEDED
        in result.triggers
    )


def test_performance_degradation_requires_reassignment():

    engine = (
        RoleReassignmentPolicyEngine()
    )

    metrics = healthy_metrics().model_copy(
        update={
            "success_rate": 0.60,
            "quality_score": 55,
            "reliability_score": 60,
        }
    )

    result = engine.evaluate(
        assignment=assignment(),
        metrics=metrics,
    )

    assert (
        result.decision
        is RoleHealthDecision.REASSIGN
    )

    assert (
        RoleHealthTrigger
        .SUCCESS_RATE_DEGRADED
        in result.triggers
    )


def test_stale_heartbeat_requires_failover():

    now = datetime.now(timezone.utc)

    engine = RoleReassignmentPolicyEngine(
        policy=ReassignmentPolicy(
            maximum_heartbeat_age_seconds=60
        )
    )

    metrics = healthy_metrics().model_copy(
        update={
            "last_heartbeat_at":
                now - timedelta(
                    minutes=5
                ),
        }
    )

    result = engine.evaluate(
        assignment=assignment(),
        metrics=metrics,
        evaluated_at=now,
    )

    assert (
        result.decision
        is RoleHealthDecision.FAILOVER
    )

    assert (
        RoleHealthTrigger.HEARTBEAT_STALE
        in result.triggers
    )


def test_missing_metrics_blocks_evaluation():

    engine = (
        RoleReassignmentPolicyEngine()
    )

    result = engine.evaluate(
        assignment=assignment(),
        metrics=None,
    )

    assert (
        result.decision
        is RoleHealthDecision.BLOCKED
    )

    assert not result.metrics_available
