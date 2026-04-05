"""
search_tools —— 多策略文件搜索工具

搜索优先级：
  1. git grep（最快，仅在 .git 目录存在时可用）
  2. ripgrep（rg，若系统已安装）
  3. Python glob + re（兜底，始终可用）
"""
import re
import subprocess
from pathlib import Path
from langchain_core.tools import tool

from codeagent.config import settings

_MAX_RESULTS = 50
_MAX_LINE_LEN = 200
_TIMEOUT = 15


def _truncate_line(line: str) -> str:
    line = line.rstrip("\n")
    return line[:_MAX_LINE_LEN] + ("…" if len(line) > _MAX_LINE_LEN else "")


def _git_grep(workspace: Path, query: str, file_pattern: str, case_sensitive: bool) -> str | None:
    """使用 git grep 搜索，返回结果字符串；不可用时返回 None"""
    if not (workspace / ".git").exists():
        return None
    flags = ["-n"]
    if not case_sensitive:
        flags.append("-i")
    cmd = ["git", "grep"] + flags + ["--", query]
    if file_pattern and file_pattern != "*":
        cmd += [f"*{file_pattern}" if not file_pattern.startswith("*") else file_pattern]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_TIMEOUT,
            cwd=workspace,
        )
        if result.returncode not in (0, 1):  # 1 = 无匹配（正常）
            return None
        lines = result.stdout.strip().splitlines()
        if not lines:
            return ""
        truncated = [_truncate_line(l) for l in lines[:_MAX_RESULTS]]
        suffix = f"\n[已截断，仅显示前 {_MAX_RESULTS} 条]" if len(lines) > _MAX_RESULTS else ""
        return "\n".join(truncated) + suffix
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def _rg_search(workspace: Path, query: str, file_pattern: str, case_sensitive: bool) -> str | None:
    """使用 ripgrep 搜索，返回结果字符串；不可用时返回 None"""
    cmd = ["rg", "-n", "--no-heading"]
    if not case_sensitive:
        cmd.append("-i")
    if file_pattern and file_pattern != "*":
        cmd += ["--glob", file_pattern]
    cmd += [query, str(workspace)]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_TIMEOUT,
        )
        if result.returncode not in (0, 1):
            return None
        lines = result.stdout.strip().splitlines()
        if not lines:
            return ""
        # 转为相对路径
        rel_lines = []
        for l in lines[:_MAX_RESULTS]:
            try:
                parts = l.split(":", 2)
                if len(parts) >= 3:
                    rel = Path(parts[0]).relative_to(workspace)
                    rel_lines.append(f"{rel}:{parts[1]}: {_truncate_line(parts[2])}")
                else:
                    rel_lines.append(_truncate_line(l))
            except ValueError:
                rel_lines.append(_truncate_line(l))
        suffix = f"\n[已截断，仅显示前 {_MAX_RESULTS} 条]" if len(lines) > _MAX_RESULTS else ""
        return "\n".join(rel_lines) + suffix
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def _python_search(workspace: Path, query: str, file_pattern: str, case_sensitive: bool) -> str:
    """Python glob + re 兜底搜索"""
    glob_pattern = file_pattern if file_pattern else "*"
    if "**" not in glob_pattern and not glob_pattern.startswith("*"):
        glob_pattern = f"**/{glob_pattern}"
    elif "**" not in glob_pattern:
        glob_pattern = f"**/{glob_pattern}"

    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        regex = re.compile(re.escape(query), flags)
    except re.error:
        regex = re.compile(query, flags)

    results = []
    try:
        files = list(workspace.glob(glob_pattern))
    except Exception as e:
        return f"文件匹配失败：{e}"

    for file_path in files:
        if not file_path.is_file():
            continue
        try:
            for lineno, line in enumerate(
                file_path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if regex.search(line):
                    rel = file_path.relative_to(workspace)
                    results.append(f"{rel}:{lineno}: {_truncate_line(line)}")
                    if len(results) >= _MAX_RESULTS:
                        results.append(f"[已达到最大结果数 {_MAX_RESULTS}]")
                        return "\n".join(results)
        except Exception:
            continue

    return "\n".join(results) if results else ""


@tool
def search_files(query: str, file_pattern: str = "*", case_sensitive: bool = False) -> str:
    """
    在工作目录内多策略搜索文件内容（git grep → ripgrep → Python fallback）。
    比 search_code 更快、支持所有文件类型、自动选择最优搜索引擎。
    query: 搜索关键词（字面量字符串）
    file_pattern: 文件名匹配模式，如 '*.py'、'*.ts'、'*'（默认全部文件）
    case_sensitive: 是否区分大小写（默认 False）
    """
    workspace = Path(settings.WORKSPACE_DIR).resolve()

    # 依次尝试各策略
    for strategy_fn, name in [
        (lambda: _git_grep(workspace, query, file_pattern, case_sensitive), "git grep"),
        (lambda: _rg_search(workspace, query, file_pattern, case_sensitive), "ripgrep"),
    ]:
        result = strategy_fn()
        if result is not None:
            if result == "":
                return f"未找到匹配 '{query}' 的内容（范围：{file_pattern}，引擎：{name}）"
            return f"[搜索引擎：{name}]\n{result}"

    # Python fallback
    result = _python_search(workspace, query, file_pattern, case_sensitive)
    if not result:
        return f"未找到匹配 '{query}' 的内容（范围：{file_pattern}）"
    return f"[搜索引擎：Python]\n{result}"
