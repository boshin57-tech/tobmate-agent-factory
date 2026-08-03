from __future__ import annotations

from .task_workload_models import (
    TaskAgentAvailability,
    TaskAgentRuntimeProfile,
)


class TaskRuntimeProfileRepository:
    """
    Stores current Agent runtime profiles used by task coordination.

    The repository is the runtime source of truth for:
    - availability
    - workload and capacity
    - task counts
    - success, quality, and reliability
    - supported capabilities and task types
    """

    def __init__(self) -> None:
        self._profiles: dict[
            str,
            TaskAgentRuntimeProfile,
        ] = {}

    def register(
        self,
        profile: TaskAgentRuntimeProfile,
    ) -> TaskAgentRuntimeProfile:
        if profile.agent_id in self._profiles:
            raise ValueError(
                "Agent runtime profile already exists"
            )

        self._profiles[
            profile.agent_id
        ] = profile

        return profile

    def upsert(
        self,
        profile: TaskAgentRuntimeProfile,
    ) -> TaskAgentRuntimeProfile:
        self._profiles[
            profile.agent_id
        ] = profile

        return profile

    def replace(
        self,
        profile: TaskAgentRuntimeProfile,
    ) -> TaskAgentRuntimeProfile:
        if profile.agent_id not in self._profiles:
            raise ValueError(
                "Agent runtime profile does not exist"
            )

        self._profiles[
            profile.agent_id
        ] = profile

        return profile

    def get(
        self,
        agent_id: str,
    ) -> TaskAgentRuntimeProfile | None:
        return self._profiles.get(
            agent_id
        )

    def remove(
        self,
        agent_id: str,
    ) -> TaskAgentRuntimeProfile:
        profile = self._profiles.pop(
            agent_id,
            None,
        )

        if profile is None:
            raise ValueError(
                "Agent runtime profile does not exist"
            )

        return profile

    def update_availability(
        self,
        *,
        agent_id: str,
        availability: TaskAgentAvailability,
    ) -> TaskAgentRuntimeProfile:
        profile = self._require(
            agent_id
        )

        updated = profile.model_copy(
            update={
                "availability":
                    availability,
            }
        )

        return self.replace(
            updated
        )

    def update_workload(
        self,
        *,
        agent_id: str,
        current_task_count: int,
        workload_ratio: float | None = None,
    ) -> TaskAgentRuntimeProfile:
        profile = self._require(
            agent_id
        )

        if current_task_count < 0:
            raise ValueError(
                "current_task_count must not be negative"
            )

        if workload_ratio is None:
            workload_ratio = min(
                1.0,
                (
                    current_task_count
                    / profile.maximum_task_count
                ),
            )

        if not 0.0 <= workload_ratio <= 1.0:
            raise ValueError(
                "workload_ratio must be between 0 and 1"
            )

        updated = profile.model_copy(
            update={
                "current_task_count":
                    current_task_count,
                "workload_ratio":
                    workload_ratio,
            }
        )

        return self.replace(
            updated
        )

    def increment_task_count(
        self,
        agent_id: str,
    ) -> TaskAgentRuntimeProfile:
        profile = self._require(
            agent_id
        )

        return self.update_workload(
            agent_id=agent_id,
            current_task_count=(
                profile.current_task_count
                + 1
            ),
        )

    def decrement_task_count(
        self,
        agent_id: str,
    ) -> TaskAgentRuntimeProfile:
        profile = self._require(
            agent_id
        )

        return self.update_workload(
            agent_id=agent_id,
            current_task_count=max(
                0,
                profile.current_task_count
                - 1,
            ),
        )

    def available(
        self,
    ) -> tuple[
        TaskAgentRuntimeProfile,
        ...
    ]:
        return tuple(
            profile
            for profile
            in self._profiles.values()
            if (
                profile.availability
                is TaskAgentAvailability
                .AVAILABLE
                and profile.has_capacity
            )
        )

    def all(
        self,
    ) -> tuple[
        TaskAgentRuntimeProfile,
        ...
    ]:
        return tuple(
            self._profiles.values()
        )

    def _require(
        self,
        agent_id: str,
    ) -> TaskAgentRuntimeProfile:
        profile = self.get(
            agent_id
        )

        if profile is None:
            raise ValueError(
                "Agent runtime profile not found"
            )

        return profile

    @property
    def count(self) -> int:
        return len(
            self._profiles
        )
