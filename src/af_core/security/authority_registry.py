from __future__ import annotations

from .authority_models import (
    AgentAuthority,
)


class AuthorityRegistry:
    """
    Stores agent execution authorities.
    """


    def __init__(self) -> None:

        self._authorities: list[
            AgentAuthority
        ] = []



    def register(
        self,
        authority:
        AgentAuthority,
    ) -> AgentAuthority:

        self._authorities.append(
            authority
        )

        return authority



    def find(
        self,
        agent_id: str,
        permission: str,
        environment: str,
    ) -> tuple[
        AgentAuthority,
        ...
    ]:

        return tuple(
            authority
            for authority
            in self._authorities
            if (
                authority.agent_id
                == agent_id
                and
                authority.permission
                == permission
                and
                authority.environment
                == environment
                and
                authority.status
                == "active"
            )
        )
