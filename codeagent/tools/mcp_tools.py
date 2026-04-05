"""
mcp_tools —— MCP（Model Context Protocol）协议工具调用

通过 MCP 协议调用外部工具服务器。
服务器配置文件：~/.codeagent/mcp_servers.json

配置格式（与 Claude Desktop 兼容）：
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"]
    },
    "my-server": {
      "command": "python",
      "args": ["-m", "my_mcp_server"]
    }
  }
}

依赖：pip install mcp
"""
import asyncio
import json
from pathlib import Path
from langchain_core.tools import tool

_CONFIG_PATH = Path.home() / ".codeagent" / "mcp_servers.json"
_TIMEOUT = 30


def _load_servers() -> dict:
    if not _CONFIG_PATH.exists():
        return {}
    try:
        data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        return data.get("mcpServers", {})
    except Exception as e:
        raise RuntimeError(f"读取 MCP 配置失败：{e}")


async def _call_mcp_async(server_config: dict, tool_name: str, arguments: dict) -> str:
    """异步调用 MCP 工具"""
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError:
        raise ImportError("mcp")

    params = StdioServerParameters(
        command=server_config["command"],
        args=server_config.get("args", []),
        env=server_config.get("env") or None,
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            # 提取文本内容
            parts = []
            for item in result.content:
                if hasattr(item, "text"):
                    parts.append(item.text)
                else:
                    parts.append(str(item))
            return "\n".join(parts) if parts else "（工具返回空结果）"


@tool
def use_mcp_tool(server_name: str, tool_name: str, arguments: str = "{}") -> str:
    """
    通过 MCP 协议调用外部工具服务器上的工具。
    需要先在 ~/.codeagent/mcp_servers.json 中配置服务器（与 Claude Desktop 格式兼容）。
    server_name: 配置文件中的服务器名称，如 'filesystem'
    tool_name: 要调用的工具名称，如 'read_file'
    arguments: 工具参数，JSON 字符串格式，如 '{"path": "/tmp/test.txt"}'
    """
    # 检查依赖
    try:
        import mcp  # noqa: F401
    except ImportError:
        return (
            "错误：未安装 mcp 包。请运行：pip install mcp\n"
            "安装后即可通过 MCP 协议调用外部工具服务器。"
        )

    # 解析 arguments
    try:
        args_dict = json.loads(arguments) if arguments.strip() else {}
    except json.JSONDecodeError as e:
        return f"错误：arguments 不是有效的 JSON：{e}"

    # 加载服务器配置
    try:
        servers = _load_servers()
    except RuntimeError as e:
        return str(e)

    if not servers:
        return (
            f"错误：未找到 MCP 服务器配置（{_CONFIG_PATH}）\n"
            "请创建配置文件，格式：\n"
            '{\n  "mcpServers": {\n    "my-server": {"command": "npx", "args": [...]}\n  }\n}'
        )

    if server_name not in servers:
        available = ", ".join(servers.keys())
        return f"错误：未找到服务器 '{server_name}'，可用服务器：{available}"

    server_config = servers[server_name]
    if "command" not in server_config:
        return f"错误：服务器 '{server_name}' 配置缺少 'command' 字段"

    # 执行调用
    try:
        result = asyncio.run(
            asyncio.wait_for(
                _call_mcp_async(server_config, tool_name, args_dict),
                timeout=_TIMEOUT,
            )
        )
        return result
    except asyncio.TimeoutError:
        return f"错误：调用超时（>{_TIMEOUT}s），服务器 '{server_name}' 未响应"
    except ImportError:
        return "错误：mcp 包导入失败，请运行：pip install mcp"
    except Exception as e:
        return f"MCP 调用失败：{e}"
