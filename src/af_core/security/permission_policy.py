from __future__ import annotations


class PermissionPolicy:
    """
    Defines execution approval rules.
    """


    def requires_approval(
        self,
        permission: str,
        environment: str,
    ) -> bool:


        if (
            environment
            == "mainnet"
            and
            permission
            in [
                "contract_deploy",
                "asset_mint",
            ]
        ):
            return True


        return False
