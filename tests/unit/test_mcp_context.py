import asyncio

from af_core.tools.mcp_context import MCPContextOperations


class FakeSession:
    async def list_resources(self, cursor=None):
        class R:
            resources = [
                {
                    "uri": "file:///README.md",
                    "name": "README",
                }
            ]
            next_cursor = None
        return R()

    async def list_resource_templates(self, cursor=None):
        class R:
            resource_templates = [
                {
                    "uri_template": "file:///{path}",
                    "name": "file",
                }
            ]
            next_cursor = None
        return R()

    async def list_prompts(self, cursor=None):
        class R:
            prompts = [
                {
                    "name": "review_code",
                }
            ]
            next_cursor = None
        return R()

    async def read_resource(self, uri):
        class R:
            contents = [
                {
                    "uri": str(uri),
                    "text": "hello",
                }
            ]
        return R()

    async def get_prompt(
        self,
        name,
        arguments=None,
    ):
        class R:
            description = "prompt"
            messages = [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": "hello",
                    },
                }
            ]
        return R()


def test_discovery():
    ctx = MCPContextOperations(
        session=FakeSession()
    )

    result = asyncio.run(
        ctx.discover()
    )

    assert len(result.resources) == 1
    assert len(result.resource_templates) == 1
    assert len(result.prompts) == 1


def test_read_resource():
    ctx = MCPContextOperations(
        session=FakeSession()
    )

    result = asyncio.run(
        ctx.read_resource(
            "file:///README.md"
        )
    )

    assert result.uri == "file:///README.md"
    assert result.contents[0].text == "hello"


def test_get_prompt():
    ctx = MCPContextOperations(
        session=FakeSession()
    )

    prompt = asyncio.run(
        ctx.get_prompt(
            name="review_code"
        )
    )

    assert prompt.name == "review_code"
    assert prompt.messages[0].content.text == "hello"
