from __future__ import annotations

from .capability_models import (
    AgentCapability,
)


class CapabilityRegistry:
    """
    Registry for agent skills
    and execution capabilities.
    """


    def __init__(self) -> None:

        self._agents: dict[
            str,
            AgentCapability
        ] = {}



    def register(
        self,
        agent:
        AgentCapability,
    ) -> AgentCapability:


        if (
            agent.agent_id
            in self._agents
        ):
            raise ValueError(
                "Agent already registered"
            )


        self._agents[
            agent.agent_id
        ] = agent


        return agent



    def get(
        self,
        agent_id: str,
    ) -> AgentCapability | None:

        return self._agents.get(
            agent_id
        )



    def all(
        self,
    ) -> tuple[
        AgentCapability,
        ...
    ]:

        return tuple(
            self._agents.values()
        )



    @property
    def count(
        self,
    ) -> int:

        return len(
            self._agents
        )
