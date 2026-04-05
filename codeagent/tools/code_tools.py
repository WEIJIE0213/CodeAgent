"""
code_tools —— 代码搜索工具（在 WORKSPACE_DIR 内 grep）
"""
import os
import re
from pathlib import Path
from langchain_core.tools import tool

from codeagent.config import settings

_MAX_RESULTS = 50
_MAX_LINE_LEN = 200


@tool
def search_code(pattern: str, file_glob: str = "**/*.py") -> str:
    """
    在工作目录内搜索匹配正则表达式的代码行。
    pattern: 正则表达式搜索模式
    file_glob: 文件匹配模式（默认 '**/*.py'，也可用 '**/*.js' 等）
    返回匹配的文件名、行号和内容。
    """
    workspace = Path(settings.WORKSPACE_DIR).resolve()
    results = []

    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return f"正则表达式错误：{e}"

    try:
        files = list(workspace.glob(file_glob))
    except Exception as e:
        return f"文件匹配失败：{e}"

    for file_path in files:
        if not file_path.is_file():
            continue
        try:
            lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue

        for lineno, line in enumerate(lines, 1):
            if regex.search(line):
                rel = file_path.relative_to(workspace)
                truncated = line.strip()[:_MAX_LINE_LEN]
                results.append(f"{rel}:{lineno}: {truncated}")
                if len(results) >= _MAX_RESULTS:
                    results.append(f"[已达到最大结果数 {_MAX_RESULTS}，搜索终止]")
                    break
        if len(results) >= _MAX_RESULTS:
            break

    if not results:
        return f"未找到匹配 '{pattern}' 的内容（范围：{file_glob}）"
    return "\n".join(results)
