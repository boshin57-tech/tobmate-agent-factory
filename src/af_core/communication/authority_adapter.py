from __future__ import annotations

from af_core.security.authority_manager import (
    AuthorityManager,
)


class AuthorityManagerAdapter:
    """
    Adapts the Checkpoint 15 AuthorityManager to the
    CommunicationAuthorityGate checker contract.
    """

    def __init__(
        self,
        manager: AuthorityManager,
    ) -> None:
        self._manager = manager

    def __call__(
        self,
        agent_id: str,
        permission: str,
        environment: str,
        resource_scope: str,
    ) -> bool:
        # resource_scope is retained in the communication
        # decision and audit trail. The existing authority
        # manager currently authorizes by agent, permission,
        # and environment.
        del resource_scope

        return self._manager.authorize(
            agent_id,
            permission,
            environment,
        )
