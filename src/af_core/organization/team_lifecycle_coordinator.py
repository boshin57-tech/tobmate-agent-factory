from __future__ import annotations

from pydantic import BaseModel

from .readiness_models import (
    TeamReadinessResult,
)
from .team_builder import (
    TeamBuilderEngine,
)
from .team_event_publisher import (
    TeamEventPublisher,
)
from .team_models import (
    AgentTeam,
    TeamBuildRequest,
)
from .team_readiness_governance import (
    TeamReadinessGovernance,
)
from .team_validation_models import (
    TeamValidationReport,
)


class TeamLifecycleResult(BaseModel):
    team: AgentTeam

    validation: TeamValidationReport

    readiness: TeamReadinessResult

    activated_team: AgentTeam | None = None

    @property
    def activated(
        self,
    ) -> bool:
        return (
            self.activated_team
            is not None
        )


class TeamLifecycleCoordinator:
    """
    Coordinates the complete team lifecycle:

    Build
    → Validate
    → Evaluate readiness
    → Publish lifecycle events
    → Activate when approved
    """

    def __init__(
        self,
        *,
        builder: TeamBuilderEngine,
        governance: TeamReadinessGovernance,
        publisher: TeamEventPublisher,
    ) -> None:
        self._builder = builder
        self._governance = governance
        self._publisher = publisher

    def create_team(
        self,
        *,
        request: TeamBuildRequest,
        environment: str = "runtime",
        human_approved: bool = False,
        approver_id: str | None = None,
        activate_when_ready: bool = True,
    ) -> TeamLifecycleResult:
        team = self._builder.build(
            request
        )

        self._publisher.publish_created(
            team
        )

        validation = (
            self._builder
            .validation_report(
                team.team_id
            )
        )

        if validation is None:
            raise RuntimeError(
                "team validation report "
                "was not generated"
            )

        self._publisher.publish_validation(
            team=team,
            validation=validation,
        )

        readiness = (
            self._governance.evaluate(
                team=team,
                validation=validation,
                environment=environment,
                human_approved=(
                    human_approved
                ),
                approver_id=approver_id,
            )
        )

        self._publisher.publish_readiness(
            team=team,
            readiness=readiness,
        )

        activated_team = None

        if (
            activate_when_ready
            and readiness.approved
            and readiness.decision.value
            == "ready"
        ):
            activated_team = (
                self._governance
                .activate(
                    team=team,
                    readiness=readiness,
                )
            )

            self._publisher.publish_activated(
                activated_team
            )

        return TeamLifecycleResult(
            team=team,
            validation=validation,
            readiness=readiness,
            activated_team=(
                activated_team
            ),
        )
