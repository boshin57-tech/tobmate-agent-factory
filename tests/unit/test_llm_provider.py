from af_core.llm.llm_models import (
    LLMRequest,
)

from af_core.llm.providers.openai_provider import (
    OpenAIProvider,
)

from af_core.llm.providers.local_provider import (
    LocalLLMProvider,
)

from af_core.llm.llm_registry import (
    LLMProviderRegistry,
)



def test_openai_adapter():

    provider = (
        OpenAIProvider()
    )


    result = provider.generate(
        LLMRequest(
            prompt="hello"
        )
    )


    assert (
        result.provider
        ==
        "openai"
    )



def test_provider_registry():

    registry = (
        LLMProviderRegistry()
    )


    registry.register(
        "local",
        LocalLLMProvider(),
    )


    assert (
        registry.get("local")
        is not None
    )
