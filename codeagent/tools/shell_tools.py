"""
shell_tools —— Shell 命令沙箱执行工具

安全策略：
  - 命令黑名单过滤（rm -rf, dd, mkfs 等危险操作）
  - 执行超时：30 秒
  - 工作目录限制：WORKSPACE_DIR
  - 环境变量隔离：仅传白名单变量，清除 API Key / 密码等
  - 输出截断：最多 10000 字符
"""
import os
import re
import subprocess
from langchain_core.tools import tool

from codeagent.config import settings

_TIMEOUT = 30
_MAX_OUTPUT = 10_000

# 危险命令黑名单（正则）
_BLACKLIST_PATTERNS = [
    r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f",   # rm -rf
    r"\brm\s+-[a-zA-Z]*f[a-zA-Z]*r",   # rm -fr
    r"\bdd\b",                           # dd
    r"\bmkfs\b",                         # mkfs
    r"\bshutdown\b",                     # shutdown
    r"\breboot\b",                       # reboot
    r"\bhalt\b",                         # halt
    r"\bpoweroff\b",                     # poweroff
    r">\s*/dev/sd",                      # 写磁盘设备
    r">\s*/dev/nvme",
    r"\bformat\s+[a-zA-Z]:",            # Windows format
    r"\bdel\s+/[sS]",                   # Windows del /s
    r"\brd\s+/[sS]",                    # Windows rd /s
    r":\(\)\{.*\}",                     # fork bomb
]

_BLACKLIST_RE = [re.compile(p, re.IGNORECASE) for p in _BLACKLIST_PATTERNS]

# 环境变量白名单
_ENV_WHITELIST = {
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE",
    "TEMP", "TMP", "HOME", "USER", "USERNAME",
    "LANG", "LC_ALL", "LC_CTYPE",
    "PYTHONUTF8", "PYTHONIOENCODING",
    "COMSPEC", "WINDIR",
}


def _check_blacklist(cmd: str) -> str | None:
    """若命令命中黑名单，返回匹配的模式描述；否则返回 None"""
    for pattern in _BLACKLIST_RE:
        if pattern.search(cmd):
            return pattern.pattern
    return None


def _safe_env() -> dict:
    """构建隔离的环境变量字典"""
    return {k: v for k, v in os.environ.items() if k in _ENV_WHITELIST}


@tool
def run_shell(command: str) -> str:
    """
    在沙箱环境中执行 Shell 命令（工作目录为 WORKSPACE_DIR）。
    危险命令（rm -rf / dd / mkfs / shutdown 等）将被拒绝。
    超时 30 秒，输出最多返回 10000 字符。
    command: 要执行的 shell 命令字符串
    """
    # 黑名单检查
    hit = _check_blacklist(command)
    if hit:
        return f"拒绝执行：命令命中安全黑名单（匹配模式：{hit}）"

    workspace = os.path.abspath(settings.WORKSPACE_DIR)

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_TIMEOUT,
            cwd=workspace,
            env=_safe_env(),
        )
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        combined = stdout
        if stderr:
            combined += f"\n[stderr]\n{stderr}"

        if len(combined) > _MAX_OUTPUT:
            combined = combined[:_MAX_OUTPUT] + f"\n[输出已截断，原始长度 {len(combined)} 字符]"

        exit_code = result.returncode
        header = f"[退出码: {exit_code}]\n" if exit_code != 0 else ""
        return header + combined if combined.strip() else f"[命令执行成功，无输出，退出码: {exit_code}]"

    except subprocess.TimeoutExpired:
        return f"执行超时（>{_TIMEOUT}s），命令已终止"
    except Exception as e:
        return f"执行失败：{e}"
