"""Multi-team coordination for autonomous project execution."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from uuid import uuid4


class ProjectTeamCoordinationError(ValueError):
    """Raised when a team coordination invariant is violated."""


class ProjectTeamRole(str, Enum):
    """Responsibility held by a team for one project task."""

    OWNER = "owner"
    PRODUCER = "producer"
    REVIEWER = "reviewer"
    VALIDATOR = "validator"
    APPROVER = "approver"


class ProjectHandoffStatus(str, Enum):
    """Lifecycle state of an inter-team artifact handoff."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ProjectBlockerSeverity(str, Enum):
    """Operational severity of a project blocker."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ProjectConflictKind(str, Enum):
    """Conflict categories detected across project teams."""

    TASK_OWNERSHIP = "task_ownership"
    AUTHORITY = "authority"
    DEPENDENCY = "dependency"
    ARTIFACT = "artifact"
    HANDOFF = "handoff"


@dataclass(frozen=True, slots=True)
class ProjectTeamAssignment:
    """Team responsibility for one task in one project run."""

    run_id: str
    task_id: str
    team_id: str
    role: ProjectTeamRole
    capabilities: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        for name, value in (
            ("run_id", self.run_id),
            ("task_id", self.task_id),
            ("team_id", self.team_id),
        ):
            if not value.strip():
                raise ProjectTeamCoordinationError(
                    f"{name} must not be empty"
                )


@dataclass(frozen=True, slots=True)
class ProjectArtifactHandoff:
    """Artifact transfer between project execution teams."""

    handoff_id: str
    run_id: str
    source_task_id: str
    target_task_id: str
    source_team_id: str
    target_team_id: str
    artifact_reference: str
    status: ProjectHandoffStatus
    created_at: float
    updated_at: float
    reason: str = ""

    def __post_init__(self) -> None:
        required = (
            self.handoff_id,
            self.run_id,
            self.source_task_id,
            self.target_task_id,
            self.source_team_id,
            self.target_team_id,
            self.artifact_reference,
        )

        if any(not value.strip() for value in required):
            raise ProjectTeamCoordinationError(
                "handoff fields must not be empty"
            )

        if self.source_team_id == self.target_team_id:
            raise ProjectTeamCoordinationError(
                "handoff requires different source and target teams"
            )


@dataclass(frozen=True, slots=True)
class ProjectExecutionBlocker:
    """Blocking condition affecting a project task or team."""

    blocker_id: str
    run_id: str
    task_id: str
    team_id: str
    severity: ProjectBlockerSeverity
    reason: str
    created_at: float
    resolved_at: float | None = None
    resolution: str = ""

    @property
    def resolved(self) -> bool:
        return self.resolved_at is not None


@dataclass(frozen=True, slots=True)
class ProjectTeamConflict:
    """Recorded conflict requiring coordination resolution."""

    conflict_id: str
    run_id: str
    kind: ProjectConflictKind
    task_id: str
    teams: tuple[str, ...]
    reason: str
    created_at: float
    resolved_at: float | None = None
    resolution: str = ""

    @property
    def resolved(self) -> bool:
        return self.resolved_at is not None


@dataclass(frozen=True, slots=True)
class ProjectCoordinationSnapshot:
    """Current coordination state for one project run."""

    run_id: str
    assignments: tuple[ProjectTeamAssignment, ...]
    handoffs: tuple[ProjectArtifactHandoff, ...]
    blockers: tuple[ProjectExecutionBlocker, ...]
    conflicts: tuple[ProjectTeamConflict, ...]


class ProjectTeamCoordinationRegistry:
    """In-memory deterministic multi-team coordination registry."""

    def __init__(self) -> None:
        self._assignments: dict[
            tuple[str, str],
            ProjectTeamAssignment,
        ] = {}
        self._handoffs: dict[
            str,
            ProjectArtifactHandoff,
        ] = {}
        self._blockers: dict[
            str,
            ProjectExecutionBlocker,
        ] = {}
        self._conflicts: dict[
            str,
            ProjectTeamConflict,
        ] = {}

    def assign(
        self,
        *,
        run_id: str,
        task_id: str,
        team_id: str,
        role: ProjectTeamRole = ProjectTeamRole.OWNER,
        capabilities: frozenset[str] = frozenset(),
    ) -> ProjectTeamAssignment:
        """Assign one task to exactly one responsible team."""

        key = run_id, task_id

        if key in self._assignments:
            current = self._assignments[key]

            if current.team_id != team_id:
                self.record_conflict(
                    run_id=run_id,
                    task_id=task_id,
                    kind=ProjectConflictKind.TASK_OWNERSHIP,
                    teams=(current.team_id, team_id),
                    reason="multiple teams claimed task ownership",
                    now=0,
                )

            raise ProjectTeamCoordinationError(
                f"task already assigned: {run_id}/{task_id}"
            )

        assignment = ProjectTeamAssignment(
            run_id=run_id,
            task_id=task_id,
            team_id=team_id,
            role=role,
            capabilities=frozenset(capabilities),
        )

        self._assignments[key] = assignment
        return assignment

    def assignment(
        self,
        run_id: str,
        task_id: str,
    ) -> ProjectTeamAssignment:
        try:
            return self._assignments[
                (run_id, task_id)
            ]
        except KeyError as exc:
            raise ProjectTeamCoordinationError(
                f"task assignment not found: {run_id}/{task_id}"
            ) from exc

    def create_handoff(
        self,
        *,
        run_id: str,
        source_task_id: str,
        target_task_id: str,
        artifact_reference: str,
        now: float,
    ) -> ProjectArtifactHandoff:
        """Create a pending artifact handoff between assigned teams."""

        source = self.assignment(
            run_id,
            source_task_id,
        )
        target = self.assignment(
            run_id,
            target_task_id,
        )

        handoff = ProjectArtifactHandoff(
            handoff_id=f"handoff-{uuid4().hex}",
            run_id=run_id,
            source_task_id=source_task_id,
            target_task_id=target_task_id,
            source_team_id=source.team_id,
            target_team_id=target.team_id,
            artifact_reference=artifact_reference,
            status=ProjectHandoffStatus.PENDING,
            created_at=now,
            updated_at=now,
        )

        self._handoffs[handoff.handoff_id] = handoff
        return handoff

    def accept_handoff(
        self,
        handoff_id: str,
        *,
        team_id: str,
        now: float,
    ) -> ProjectArtifactHandoff:
        handoff = self._handoff(handoff_id)

        if handoff.status is not ProjectHandoffStatus.PENDING:
            raise ProjectTeamCoordinationError(
                "only pending handoffs may be accepted"
            )

        if handoff.target_team_id != team_id:
            raise ProjectTeamCoordinationError(
                "only the target team may accept a handoff"
            )

        updated = replace(
            handoff,
            status=ProjectHandoffStatus.ACCEPTED,
            updated_at=now,
        )

        self._handoffs[handoff_id] = updated
        return updated

    def complete_handoff(
        self,
        handoff_id: str,
        *,
        now: float,
    ) -> ProjectArtifactHandoff:
        handoff = self._handoff(handoff_id)

        if handoff.status is not ProjectHandoffStatus.ACCEPTED:
            raise ProjectTeamCoordinationError(
                "handoff must be accepted before completion"
            )

        updated = replace(
            handoff,
            status=ProjectHandoffStatus.COMPLETED,
            updated_at=now,
        )

        self._handoffs[handoff_id] = updated
        return updated

    def raise_blocker(
        self,
        *,
        run_id: str,
        task_id: str,
        team_id: str,
        severity: ProjectBlockerSeverity,
        reason: str,
        now: float,
    ) -> ProjectExecutionBlocker:
        self.assignment(run_id, task_id)

        blocker = ProjectExecutionBlocker(
            blocker_id=f"blocker-{uuid4().hex}",
            run_id=run_id,
            task_id=task_id,
            team_id=team_id,
            severity=severity,
            reason=reason,
            created_at=now,
        )

        self._blockers[blocker.blocker_id] = blocker
        return blocker

    def resolve_blocker(
        self,
        blocker_id: str,
        *,
        resolution: str,
        now: float,
    ) -> ProjectExecutionBlocker:
        blocker = self._blocker(blocker_id)

        if blocker.resolved:
            raise ProjectTeamCoordinationError(
                "blocker is already resolved"
            )

        updated = replace(
            blocker,
            resolved_at=now,
            resolution=resolution,
        )

        self._blockers[blocker_id] = updated
        return updated

    def record_conflict(
        self,
        *,
        run_id: str,
        task_id: str,
        kind: ProjectConflictKind,
        teams: tuple[str, ...],
        reason: str,
        now: float,
    ) -> ProjectTeamConflict:
        conflict = ProjectTeamConflict(
            conflict_id=f"conflict-{uuid4().hex}",
            run_id=run_id,
            kind=kind,
            task_id=task_id,
            teams=tuple(sorted(set(teams))),
            reason=reason,
            created_at=now,
        )

        self._conflicts[conflict.conflict_id] = conflict
        return conflict

    def resolve_conflict(
        self,
        conflict_id: str,
        *,
        resolution: str,
        now: float,
    ) -> ProjectTeamConflict:
        conflict = self._conflict(conflict_id)

        if conflict.resolved:
            raise ProjectTeamCoordinationError(
                "conflict is already resolved"
            )

        updated = replace(
            conflict,
            resolved_at=now,
            resolution=resolution,
        )

        self._conflicts[conflict_id] = updated
        return updated

    def snapshot(
        self,
        run_id: str,
    ) -> ProjectCoordinationSnapshot:
        return ProjectCoordinationSnapshot(
            run_id=run_id,
            assignments=tuple(
                sorted(
                    (
                        item
                        for item in self._assignments.values()
                        if item.run_id == run_id
                    ),
                    key=lambda item: item.task_id,
                )
            ),
            handoffs=tuple(
                sorted(
                    (
                        item
                        for item in self._handoffs.values()
                        if item.run_id == run_id
                    ),
                    key=lambda item: item.created_at,
                )
            ),
            blockers=tuple(
                sorted(
                    (
                        item
                        for item in self._blockers.values()
                        if item.run_id == run_id
                    ),
                    key=lambda item: item.created_at,
                )
            ),
            conflicts=tuple(
                sorted(
                    (
                        item
                        for item in self._conflicts.values()
                        if item.run_id == run_id
                    ),
                    key=lambda item: item.created_at,
                )
            ),
        )

    def _handoff(
        self,
        handoff_id: str,
    ) -> ProjectArtifactHandoff:
        try:
            return self._handoffs[handoff_id]
        except KeyError as exc:
            raise ProjectTeamCoordinationError(
                f"handoff not found: {handoff_id}"
            ) from exc

    def _blocker(
        self,
        blocker_id: str,
    ) -> ProjectExecutionBlocker:
        try:
            return self._blockers[blocker_id]
        except KeyError as exc:
            raise ProjectTeamCoordinationError(
                f"blocker not found: {blocker_id}"
            ) from exc

    def _conflict(
        self,
        conflict_id: str,
    ) -> ProjectTeamConflict:
        try:
            return self._conflicts[conflict_id]
        except KeyError as exc:
            raise ProjectTeamCoordinationError(
                f"conflict not found: {conflict_id}"
            ) from exc
