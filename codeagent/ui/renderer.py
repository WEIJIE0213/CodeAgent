"""
renderer —— rich 输出渲染工具

提供统一的 CLI 输出格式：
- 欢迎横幅
- Agent 响应（Markdown + 代码高亮）
- 流式输出（逐字打印）
- 状态提示（思考中、错误、系统信息）
- 对话历史
"""
import sys
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from rich.rule import Rule
from rich import box

# force_terminal=True：强制启用 ANSI 渲染（避免 Windows legacy 路径崩溃）
# highlight=False：关闭自动高亮（防止误识别）
console = Console(force_terminal=True, legacy_windows=False, highlight=False)


def print_banner() -> None:
    """打印欢迎横幅"""
    banner = Text()
    banner.append("CodeAgent", style="bold cyan")
    banner.append("  v0.1.0", style="dim")
    banner.append("\nLangGraph 多 Agent 编程助手", style="italic")

    console.print(Panel(
        banner,
        subtitle="输入 [bold]/help[/bold] 查看命令，[bold]/exit[/bold] 退出",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(0, 2),
    ))


def print_response(content: str, intent: str = "qa") -> None:
    """渲染 Agent 响应"""
    intent_labels = {
        "code": ("[CODE]", "green"),
        "decompose": ("[TASK]", "yellow"),
        "qa": ("[QA]", "blue"),
        "memory": ("[MEM]", "magenta"),
    }
    label, color = intent_labels.get(intent, ("[AGENT]", "cyan"))

    console.print(
        Panel(
            Markdown(content),
            title=f"[bold {color}]{label}[/bold {color}] Agent",
            border_style=color,
            box=box.ROUNDED,
            padding=(0, 1),
        )
    )


def print_error(msg: str) -> None:
    console.print(f"[bold red]错误：[/bold red]{msg}")


def print_system(msg: str) -> None:
    console.print(f"[dim cyan]→ {msg}[/dim cyan]")


def print_history(history_text: str) -> None:
    console.print(Panel(
        history_text,
        title="[bold]对话历史[/bold]",
        border_style="dim",
        box=box.SIMPLE,
    ))


def print_task_plan(task_plan: list) -> None:
    """展示任务拆解计划"""
    if not task_plan:
        console.print("[dim]（当前无任务拆解记录，发送复杂任务后自动生成）[/dim]")
        return
    lines = []
    for t in task_plan:
        status_icon = "✓" if t.get("status") == "completed" else "○"
        lines.append(f"  [{status_icon}] {t['id']}. {t['title']}")
    console.print(Panel(
        "\n".join(lines),
        title="[bold yellow]任务拆解计划[/bold yellow]",
        border_style="yellow",
        box=box.ROUNDED,
    ))


def print_thinking_step(text: str) -> None:
    """打印推理过程（暗色，与最终回答区分）"""
    for line in text.strip().splitlines():
        line = line.strip()
        if line:
            console.print(f"  [dim]💭 {line}[/dim]")


def print_tool_call(tool_name: str) -> None:
    """打印工具调用提示"""
    console.print(f"  [dim yellow]→ 调用 [bold]{tool_name}[/bold][/dim yellow]")


def print_task_chain(task_plan: list) -> None:
    """展示任务链进度（带 ✓ 标记）"""
    if not task_plan:
        return
    lines = []
    for t in task_plan:
        icon = "[green]✓[/green]" if t.get("status") == "completed" else "[dim]○[/dim]"
        lines.append(f"  {icon}  {t['title']}")
    console.print(Panel(
        "\n".join(lines),
        title="[bold yellow]任务进度[/bold yellow]",
        border_style="yellow",
        box=box.ROUNDED,
        padding=(0, 1),
    ))


def stream_response_header(intent: str) -> None:
    """流式输出前打印 Agent 标签头"""
    intent_labels = {
        "code": ("[CODE]", "green"),
        "decompose": ("[TASK]", "yellow"),
        "qa": ("[QA]", "blue"),
        "memory": ("[MEM]", "magenta"),
    }
    label, color = intent_labels.get(intent, ("[AGENT]", "cyan"))
    console.print(f"\n[bold {color}]{label}[/bold {color}] Agent", end="  ")
    console.print(Rule(style=color), end="")
    console.print()


def stream_token(token: str) -> None:
    """打印单个流式 token（不换行）"""
    console.print(token, end="", markup=False)


def stream_done() -> None:
    """流式输出结束后打印分隔线"""
    console.print()
    console.print(Rule(style="dim"))



def print_help() -> None:
    help_text = """\
**内置命令**

| 命令 | 说明 |
|------|------|
| `/help` | 显示此帮助 |
| `/history` | 查看本次会话对话历史 |
| `/memory` | 查看当前长期记忆摘要 |
| `/tasks` | 查看最近一次任务拆解计划 |
| `/compress` | 手动触发上下文压缩 |
| `/config` | 查看当前配置 |
| `/clear` | 开启新会话（旧记录保留在 SQLite）|
| `/exit` / `/quit` | 退出 |

**支持的意图类型**

| 意图 | 示例 |
|------|------|
| 代码生成 | "帮我写一个快速排序" |
| 任务拆解 | "帮我从零搭建 FastAPI 项目" |
| 概念问答 | "什么是 Python 的 GIL？" |
| 记忆查询 | "你之前帮我写过什么？" |

**可用工具（Agent 自动调用）**

| 工具 | 说明 |
|------|------|
| `read_file` | 读取工作目录内的文件 |
| `write_file` | 写入文件（整体覆盖） |
| `list_dir` | 列出目录内容 |
| `apply_diff` | 应用 unified diff 补丁精确修改文件 |
| `search_and_replace` | 在文件中搜索并替换文本 |
| `insert_content` | 在指定行号后插入内容 |
| `search_files` | 多策略搜索（git grep / rg / Python） |
| `search_code` | 正则表达式搜索代码文件 |
| `run_shell` | 沙箱执行 Shell 命令 |
| `update_todos` | Agent 任务列表管理 |
| `use_mcp_tool` | 调用外部 MCP 工具服务器 |
"""
    console.print(Markdown(help_text))
