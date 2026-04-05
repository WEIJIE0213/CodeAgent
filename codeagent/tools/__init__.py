"""tools — LangChain 工具集，供 code_agent / task_decomposer 调用"""
from codeagent.tools.file_tools import read_file, write_file, list_dir
from codeagent.tools.shell_tools import run_shell
from codeagent.tools.code_tools import search_code
from codeagent.tools.edit_tools import apply_diff, search_and_replace, insert_content
from codeagent.tools.search_tools import search_files
from codeagent.tools.task_tools import update_todos
from codeagent.tools.mcp_tools import use_mcp_tool

all_tools = [
    # 文件读写
    read_file, write_file, list_dir,
    # 精确编辑
    apply_diff, search_and_replace, insert_content,
    # 搜索
    search_code, search_files,
    # Shell
    run_shell,
    # 任务追踪
    update_todos,
    # MCP 协议
    use_mcp_tool,
]

__all__ = [
    "all_tools",
    "read_file", "write_file", "list_dir",
    "apply_diff", "search_and_replace", "insert_content",
    "search_code", "search_files",
    "run_shell",
    "update_todos",
    "use_mcp_tool",
]
