from __future__ import annotations

from af_core.communication import (
    AgentCommunicationBus,
    AgentMessage,
    MessageType,
)

from .readiness_models import (
    TeamReadinessResult,
)
from .team_communication_models import (
    TeamEventPayload,
    TeamEventType,
)
from .team_models import (
    AgentTeam,
)
from .team_validation_models import (
    TeamValidationReport,
)


class TeamEventPublisher:
    """
    Publishes team lifecycle events through the
    Agent Communication Bus.
    """

    def __init__(
        self,
        bus: AgentCommunicationBus,
        *,
        sender_agent_id: str = (
            "team-builder-engine"
        ),
    ) -> None:
        self._bus = bus
        self._sender_agent_id = (
            sender_agent_id
        )

    def publish_created(
        self,
        team: AgentTeam,
    ):
        payload = self._base_payload(
            team=team,
            event_type=(
                TeamEventType.CREATED
            ),
        )

        return self._publish(
            team=team,
            topic="team.created",
            payload=payload,
        )

    def publish_validation(
        self,
        *,
        team: AgentTeam,
        validation: TeamValidationReport,
    ):
        payload = self._base_payload(
            team=team,
            event_type=(
                TeamEventType
                .VALIDATION_COMPLETED
            ),
        )

        payload.validation_valid = (
            validation.valid
        )

        payload.reasons = [
            issue.message
            for issue in validation.issues
        ]

        payload.metadata.update(
            {
                "error_count":
                    validation.error_count,

                "warning_count":
                    validation.warning_count,
            }
        )

        return self._publish(
            team=team,
            topic=(
                "team.validation.completed"
            ),
            payload=payload,
        )

    def publish_readiness(
        self,
        *,
        team: AgentTeam,
        readiness: TeamReadinessResult,
    ):
        event_type, topic = (
            self._readiness_event(
                readiness
            )
        )

        payload = self._base_payload(
            team=team,
            event_type=event_type,
        )

        payload.readiness_decision = (
            readiness.decision.value
        )

        payload.reasons = list(
            readiness.reasons
        )

        if readiness.required_approver:
            payload.metadata[
                "required_approver"
            ] = (
                readiness
                .required_approver
            )

        return self._publish(
            team=team,
            topic=topic,
            payload=payload,
        )

    def publish_activated(
        self,
        team: AgentTeam,
    ):
        payload = self._base_payload(
            team=team,
            event_type=(
                TeamEventType.ACTIVATED
            ),
        )

        return self._publish(
            team=team,
            topic="team.activated",
            payload=payload,
        )

    def _publish(
        self,
        *,
        team: AgentTeam,
        topic: str,
        payload: TeamEventPayload,
    ):
        message = AgentMessage(
            topic=topic,
            message_type=(
                MessageType.EVENT_PUBLISHED
            ),
            sender_agent_id=(
                self._sender_agent_id
            ),
            workspace_id=(
                team.workspace_id
            ),
            correlation_id=(
                team.request_id
            ),
            payload=(
                payload.model_dump(
                    mode="json"
                )
            ),
            metadata={
                "team_id":
                    team.team_id,

                "team_status":
                    team.status.value,
            },
        )

        return self._bus.publish(
            message
        )

    @staticmethod
    def _base_payload(
        *,
        team: AgentTeam,
        event_type: TeamEventType,
    ) -> TeamEventPayload:
        return TeamEventPayload(
            team_id=team.team_id,
            request_id=team.request_id,
            team_name=team.team_name,
            workspace_id=(
                team.workspace_id
            ),
            event_type=event_type,
            status=team.status.value,
            member_count=(
                team.member_count
            ),
            member_agent_ids=[
                member.agent_id
                for member in team.members
            ],
            unfilled_roles=[
                role.role_name
                for role
                in team.unfilled_roles
            ],
        )

    @staticmethod
    def _readiness_event(
        readiness: TeamReadinessResult,
    ) -> tuple[
        TeamEventType,
        str,
    ]:
        decision = (
            readiness.decision.value
        )

        if decision == "ready":
            return (
                TeamEventType.READY,
                "team.ready",
            )

        if (
            decision
            == "approval_required"
        ):
            return (
                TeamEventType
                .APPROVAL_REQUIRED,
                "team.approval.required",
            )

        if decision == "rejected":
            return (
                TeamEventType.REJECTED,
                "team.rejected",
            )

        return (
            TeamEventType.BLOCKED,
            "team.blocked",
        )
