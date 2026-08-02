from __future__ import annotations

from .capability_models import (
    AgentCapability,
)

from .capability_registry import (
    CapabilityRegistry,
)



class CapabilitySelector:
    """
    Selects agents based on
    required capabilities.
    """


    def __init__(
        self,
        registry:
        CapabilityRegistry,
    ) -> None:

        self.registry = registry



    def find(
        self,
        required:
        list[str],
    ) -> tuple[
        AgentCapability,
        ...
    ]:


        result = []


        for agent in (
            self.registry.all()
        ):

            if all(
                capability
                in agent.capabilities
                for capability
                in required
            ):

                result.append(
                    agent
                )


        return tuple(result)
