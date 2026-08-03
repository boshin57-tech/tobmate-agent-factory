from __future__ import annotations

from .dynamic_role_models import (
    DynamicRoleAssignment,
    RoleAssignmentStatus,
)


class RoleAssignmentRepository:
    """
    In-memory runtime role assignment repository.
    """

    def __init__(self) -> None:
        self._assignments: dict[
            str,
            DynamicRoleAssignment,
        ] = {}

    def save(
        self,
        assignment: DynamicRoleAssignment,
    ) -> DynamicRoleAssignment:
        if (
            assignment.assignment_id
            in self._assignments
        ):
            raise ValueError(
                "role assignment "
                "already exists"
            )

        self._assignments[
            assignment.assignment_id
        ] = assignment

        return assignment

    def replace(
        self,
        assignment: DynamicRoleAssignment,
    ) -> DynamicRoleAssignment:
        if (
            assignment.assignment_id
            not in self._assignments
        ):
            raise ValueError(
                "role assignment "
                "does not exist"
            )

        self._assignments[
            assignment.assignment_id
        ] = assignment

        return assignment

    def get(
        self,
        assignment_id: str,
    ) -> DynamicRoleAssignment | None:
        return self._assignments.get(
            assignment_id
        )

    def active_for_team(
        self,
        team_id: str,
    ) -> tuple[
        DynamicRoleAssignment,
        ...
    ]:
        return tuple(
            assignment
            for assignment
            in self._assignments.values()
            if (
                assignment.team_id
                == team_id
                and assignment.status
                is RoleAssignmentStatus.ACTIVE
            )
        )

    def active_for_role(
        self,
        *,
        team_id: str,
        role_name: str,
    ) -> tuple[
        DynamicRoleAssignment,
        ...
    ]:
        return tuple(
            assignment
            for assignment
            in self.active_for_team(
                team_id
            )
            if (
                assignment.role_name
                == role_name
            )
        )

    def active_for_agent(
        self,
        agent_id: str,
    ) -> tuple[
        DynamicRoleAssignment,
        ...
    ]:
        return tuple(
            assignment
            for assignment
            in self._assignments.values()
            if (
                assignment.agent_id
                == agent_id
                and assignment.status
                is RoleAssignmentStatus.ACTIVE
            )
        )

    def by_request(
        self,
        request_id: str,
    ) -> tuple[
        DynamicRoleAssignment,
        ...
    ]:
        return tuple(
            assignment
            for assignment
            in self._assignments.values()
            if (
                assignment.request_id
                == request_id
            )
        )

    def all(
        self,
    ) -> tuple[
        DynamicRoleAssignment,
        ...
    ]:
        return tuple(
            self._assignments.values()
        )

    @property
    def count(self) -> int:
        return len(
            self._assignments
        )
