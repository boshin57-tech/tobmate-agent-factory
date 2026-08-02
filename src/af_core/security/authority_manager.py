from __future__ import annotations

from .authority_registry import (
    AuthorityRegistry,
)

from .permission_policy import (
    PermissionPolicy,
)


class AuthorityManager:
    """
    Validates agent execution permission.
    """


    def __init__(
        self,
        registry:
        AuthorityRegistry | None = None,

        policy:
        PermissionPolicy | None = None,
    ) -> None:

        self.registry = (
            registry
            or AuthorityRegistry()
        )

        self.policy = (
            policy
            or PermissionPolicy()
        )



    def authorize(
        self,
        agent_id: str,
        permission: str,
        environment: str,
    ) -> bool:


        authorities = (
            self.registry.find(
                agent_id,
                permission,
                environment,
            )
        )


        if not authorities:
            return False


        if self.policy.requires_approval(
            permission,
            environment,
        ):

            return False


        return True
