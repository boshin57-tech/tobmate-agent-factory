from __future__ import annotations

from mcp.server.fastmcp import FastMCP


server = FastMCP(
    "AF-Core Test MCP Server",
)


@server.tool()
def echo_text(
    message: str,
) -> str:
    """Return the supplied message unchanged."""
    return message


@server.tool()
def add_numbers(
    left: int,
    right: int,
) -> dict[str, int]:
    """Add two integers and return structured output."""
    return {
        "left": left,
        "right": right,
        "total": left + right,
    }


@server.tool()
def fail_tool(
    message: str = "intentional failure",
) -> str:
    """Raise an intentional error for failure testing."""
    raise RuntimeError(message)


def main() -> None:
    server.run(
        transport="stdio",
    )


if __name__ == "__main__":
    main()
