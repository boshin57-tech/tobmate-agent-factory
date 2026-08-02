from af_core.security.authority_models import (
    AgentAuthority,
)

from af_core.security.authority_manager import (
    AuthorityManager,
)



def test_agent_testnet_permission():

    manager = (
        AuthorityManager()
    )


    manager.registry.register(
        AgentAuthority(
            agent_id="blockchain-agent",

            permission=
            "contract_deploy",

            environment=
            "testnet",

            scope=
            "smart-contract",
        )
    )


    assert (
        manager.authorize(
            "blockchain-agent",
            "contract_deploy",
            "testnet",
        )
    )



def test_mainnet_requires_approval():

    manager = (
        AuthorityManager()
    )


    manager.registry.register(
        AgentAuthority(
            agent_id="blockchain-agent",

            permission=
            "contract_deploy",

            environment=
            "mainnet",

            scope=
            "smart-contract",
        )
    )


    assert not (
        manager.authorize(
            "blockchain-agent",
            "contract_deploy",
            "mainnet",
        )
    )
