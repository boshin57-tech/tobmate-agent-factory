from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[2]


def test_mcp_runtime_dependencies_are_declared():
    data = tomllib.loads(
        (ROOT / "pyproject.toml").read_text(
            encoding="utf-8"
        )
    )

    dependencies = set(
        data["project"]["dependencies"]
    )

    assert "httpx>=0.27.1,<1" in dependencies
    assert "mcp>=1.29,<2" in dependencies


def test_mcp_runtime_modules_import():
    from af_core.tools.mcp_http_client import (
        MCPHTTPClient,
    )
    from af_core.tools.mcp_manager import (
        MCPServerManager,
    )
    from af_core.tools.mcp_stdio_client import (
        MCPStdioClient,
    )

    assert MCPHTTPClient
    assert MCPServerManager
    assert MCPStdioClient
