from af_core.capability.capability_models import (
    AgentCapability,
)

from af_core.capability.capability_registry import (
    CapabilityRegistry,
)

from af_core.capability.capability_selector import (
    CapabilitySelector,
)



def test_register_agent_capability():

    registry = (
        CapabilityRegistry()
    )


    agent = (
        AgentCapability(
            agent_id="blockchain-001",

            agent_name=
            "Blockchain Agent",

            capabilities=[
                "Sui Move",
                "Security Audit",
            ],

            supported_tasks=[
                "contract_test",
            ],
        )
    )


    registry.register(agent)


    assert (
        registry.count
        == 1
    )



def test_capability_selection():

    registry = (
        CapabilityRegistry()
    )


    registry.register(
        AgentCapability(
            agent_id="ai-001",

            agent_name="AI Agent",

            capabilities=[
                "LLM",
                "Planning",
            ],
        )
    )


    selector = (
        CapabilitySelector(
            registry
        )
    )


    result = selector.find(
        [
            "LLM",
        ]
    )


    assert len(result) == 1

    assert (
        result[0].agent_name
        ==
        "AI Agent"
    )
