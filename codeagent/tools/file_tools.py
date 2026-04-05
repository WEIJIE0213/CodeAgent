"""
file_tools —— 文件读写工具（路径限制在 WORKSPACE_DIR 内）
"""
import os
from pathlib import Path
from langchain_core.tools import tool

from codeagent.config import settings

_MAX_READ_CHARS = 20_000  # 单次最多读取字符数


def _safe_path(path: str) -> Path:
    """将相对路径解析为绝对路径，并确保在 WORKSPACE_DIR 内"""
    workspace = Path(settings.WORKSPACE_DIR).resolve()
    target = (workspace / path).resolve()
    if not str(target).startswith(str(workspace)):
        raise PermissionError(f"路径 '{path}' 超出工作目录 '{workspace}'，拒绝访问")
    return target


@tool
def read_file(path: str) -> str:
    """读取工作目录内的文件内容。path 为相对路径，如 'src/main.py'"""
    try:
        target = _safe_path(path)
        if not target.exists():
            return f"错误：文件不存在 '{path}'"
        if not target.is_file():
            return f"错误：'{path}' 不是文件"
        content = target.read_text(encoding="utf-8", errors="replace")
        if len(content) > _MAX_READ_CHARS:
            content = content[:_MAX_READ_CHARS] + f"\n\n[已截断，原始长度 {len(content)} 字符]"
        return content
    except PermissionError as e:
        return f"权限错误：{e}"
    except Exception as e:
        return f"读取失败：{e}"


@tool
def write_file(path: str, content: str) -> str:
    """将内容写入工作目录内的文件（自动创建父目录）。path 为相对路径"""
    try:
        target = _safe_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"已写入 '{path}'（{len(content)} 字符）"
    except PermissionError as e:
        return f"权限错误：{e}"
    except Exception as e:
        return f"写入失败：{e}"


@tool
def list_dir(path: str = ".") -> str:
    """列出工作目录内某个目录的文件和子目录。path 为相对路径，默认为工作目录根"""
    try:
        target = _safe_path(path)
        if not target.exists():
            return f"错误：目录不存在 '{path}'"
        if not target.is_dir():
            return f"错误：'{path}' 不是目录"
        entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name))
        lines = []
        for entry in entries[:200]:  # 最多列出 200 个条目
            prefix = "📁 " if entry.is_dir() else "📄 "
            lines.append(f"{prefix}{entry.name}")
        if len(list(target.iterdir())) > 200:
            lines.append("...(超过 200 条目，已截断)")
        return "\n".join(lines) if lines else "（空目录）"
    except PermissionError as e:
        return f"权限错误：{e}"
    except Exception as e:
        return f"列目录失败：{e}"
