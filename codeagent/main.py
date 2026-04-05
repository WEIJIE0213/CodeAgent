"""
main.py —— CLI 入口（Phase 4 升级版）

新增：
- /compress  手动触发上下文压缩
- /reflect   手动触发 Reflection 审查
- /config    查看当前配置
- 优雅 Ctrl+C 处理
"""
import uuid
import typer
from rich.prompt import Prompt
from rich.table import Table

from codeagent.graph.builder import graph
from codeagent.memory.short_term import format_history
from codeagent.memory.long_term import init_db, get_latest_summary
from codeagent.memory.compressor import compress, should_compress, split_for_compression
from codeagent.memory.vector_store import store_memory
from codeagent.config import settings
from codeagent.ui.renderer import (
    console,
    print_banner,
    print_response,
    print_error,
    print_system,
    print_history,
    print_task_plan,
    print_task_chain,
    print_thinking_step,
    print_tool_call,
    print_help,
    stream_response_header,
    stream_token,
    stream_done,
)


app = typer.Typer(
    name="codeagent",
    help="LangGraph 多 Agent 编程助手",
    add_completion=False,
)

_DEFAULT_THREAD = "default"


# context_qa：纯文字问答，实时逐字流式
# code_agent / task_decomposer：带工具调用，缓冲后按"推理步骤 + 最终答案"分层渲染
_STREAM_NODES = {"context_qa"}
_TOOL_NODES   = {"code_agent", "task_decomposer"}


# ── 内部工具 ──────────────────────────────────────────────────────────────────

def _cfg(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def _snapshot(thread_id: str) -> dict:
    snap = graph.get_state(_cfg(thread_id))
    return snap.values if snap else {}


_NODE_TO_INTENT = {
    "code_agent": "code",
    "task_decomposer": "decompose",
    "context_qa": "qa",
}


def _get_tool_name(tool_call_chunks) -> str:
    """从 tool_call_chunks 提取工具名（兼容 dict 和 ToolCallChunk 对象）"""
    if not tool_call_chunks:
        return ""
    tc = tool_call_chunks[0]
    return tc.get("name", "") if isinstance(tc, dict) else (getattr(tc, "name", "") or "")


def _stream_invoke(user_input: str, thread_id: str) -> dict:
    """
    流式执行图：
    - context_qa：实时逐字流式
    - code_agent / task_decomposer：分层渲染
        推理文字  → 暗色 💭 步骤
        工具调用  → 黄色 → 调用 xxx
        最终回答  → Panel 整块渲染
    返回最终 state dict。
    """
    intent_detected = None
    has_output = False

    # ── context_qa 实时流式状态 ───────────────────
    qa_header_printed = False
    qa_streamed = False

    # ── tool_nodes 缓冲状态 ───────────────────────
    tool_header_printed = False
    tool_active = False
    tool_call_count = 0
    pending_text: list[str] = []   # 当前文字批次（可能是推理 or 最终答案）

    with console.status("[bold green]思考中...[/bold green]", spinner="dots") as status:
        for chunk in graph.stream(
            {"user_input": user_input},
            config=_cfg(thread_id),
            stream_mode="messages",
        ):
            msg, metadata = chunk
            node = metadata.get("langgraph_node", "")

            # ── context_qa：实时流式 ───────────────
            if node in _STREAM_NODES:
                if getattr(msg, "tool_call_chunks", []):
                    continue
                content = getattr(msg, "content", "")
                if not content:
                    continue
                if not qa_header_printed:
                    status.stop()
                    intent_detected = "qa"
                    stream_response_header("qa")
                    qa_header_printed = True
                stream_token(content)
                qa_streamed = True
                continue

            # ── code_agent / task_decomposer：缓冲渲染 ──
            if node not in _TOOL_NODES:
                continue

            # 先提取文字内容（同一条消息可能同时携带 content 和工具调用）
            content = getattr(msg, "content", "")
            if content:
                pending_text.append(content)

            # 兼容两种格式：
            #   tool_call_chunks — 流式 LLM（streaming=True）的工具调用
            #   tool_calls       — 非流式 LLM（streaming=False）的工具调用
            tcc = getattr(msg, "tool_call_chunks", [])
            tc  = getattr(msg, "tool_calls", [])
            has_tool_call = bool(tcc or tc)

            if has_tool_call:
                # 把当前 pending_text 刷出为"推理步骤"
                thinking = "".join(pending_text).strip()
                if thinking:
                    if not tool_header_printed:
                        status.stop()
                        intent_detected = _NODE_TO_INTENT.get(node, "code")
                        stream_response_header(intent_detected)
                        tool_header_printed = True
                    print_thinking_step(thinking)
                pending_text = []

                # 显示工具调用（优先从 tool_calls 取名称，更可靠）
                tool_name = ""
                if tc:
                    tool_name = tc[0].get("name", "") if isinstance(tc[0], dict) else getattr(tc[0], "name", "")
                if not tool_name:
                    tool_name = _get_tool_name(tcc)

                if tool_header_printed:
                    print_tool_call(tool_name or "工具")
                else:
                    status.update(f"[bold yellow]→ {tool_name or '工具'}...[/bold yellow]")

                tool_active = True
                tool_call_count += 1

            elif tool_active:
                tool_active = False

    # ── 收尾：渲染最终答案 ─────────────────────────
    if qa_streamed:
        stream_done()
        has_output = True

    if pending_text:
        final_text = "".join(pending_text).strip()
        if final_text:
            intent = intent_detected or "code"
            if tool_header_printed:
                console.print()   # 与最后一个工具调用间隔一行
            else:
                # 无工具调用，直接打 header
                stream_response_header(intent)
            print_response(final_text, intent=intent)
            has_output = True

    # 获取最终 state
    state = _snapshot(thread_id)

    # 兜底：以上都没输出时，从 state 取 final_response
    if not has_output:
        final_response = state.get("final_response", "")
        if final_response:
            intent = state.get("intent", "qa")
            print_response(final_response, intent=intent)

    return state


# ── 斜杠命令 ─────────────────────────────────────────────────────────────────

def _handle_slash(cmd: str, thread_id: str) -> bool:
    """返回 True = 已处理；False = 未识别"""
    cmd_lower = cmd.strip().lower()

    if cmd_lower in ("/exit", "/quit"):
        print_system("再见！")
        raise typer.Exit()

    if cmd_lower == "/help":
        print_help()
        return True

    if cmd_lower == "/history":
        state = _snapshot(thread_id)
        print_history(format_history(state.get("short_term", [])))
        return True

    if cmd_lower == "/memory":
        state = _snapshot(thread_id)
        summary = state.get("long_term_summary") or get_latest_summary(thread_id)
        if summary:
            print_response(f"**长期记忆摘要**\n\n{summary}", intent="memory")
        else:
            print_system("暂无长期记忆（对话超过窗口限制后自动生成）")
        return True

    if cmd_lower == "/tasks":
        state = _snapshot(thread_id)
        print_task_plan(state.get("task_plan", []))
        return True

    if cmd_lower == "/compress":
        state = _snapshot(thread_id)
        short_term = state.get("short_term", [])
        if len(short_term) < 4:
            print_system("对话历史太短，无需压缩")
            return True
        with console.status("[bold green]压缩中...[/bold green]", spinner="dots"):
            old_msgs, _ = split_for_compression(short_term)
            new_summary = compress(old_msgs, state.get("long_term_summary", ""))
        store_memory(thread_id, new_summary, doc_type="summary")
        print_system(f"压缩完成，摘要已更新（{len(new_summary)} 字符）")
        return True

    if cmd_lower == "/config":
        _print_config()
        return True

    return False  # /clear 由 chat() 特殊处理，未知命令也走这里


def _print_config() -> None:
    table = Table(title="当前配置", show_header=True, header_style="bold cyan")
    table.add_column("配置项", style="cyan")
    table.add_column("值")
    table.add_row("LLM 模型", settings.LLM_MODEL)
    table.add_row("LLM BaseURL", settings.LLM_BASE_URL)
    table.add_row("Embedding 模型", settings.EMBEDDING_MODEL)
    table.add_row("向量后端", settings.VECTOR_BACKEND)
    table.add_row("Qdrant URL", settings.QDRANT_URL)
    table.add_row("工作目录", settings.WORKSPACE_DIR)
    table.add_row("记忆窗口", str(settings.WINDOW_SIZE))
    table.add_row("Shell 沙箱", settings.SHELL_SANDBOX)
    table.add_row("LLM 最大重试", str(settings.LLM_MAX_RETRIES))
    console.print(table)


# ── chat 命令 ─────────────────────────────────────────────────────────────────

@app.command()
def chat(
    thread: str = typer.Option(
        _DEFAULT_THREAD, "--thread", "-t",
        help="会话 ID（默认 'default'，跨会话保持上下文）"
    ),
):
    """进入交互式多轮对话模式"""
    init_db()
    print_banner()
    thread_id = thread
    print_system(f"会话 ID：{thread_id}  (使用 --thread <id> 切换会话)")

    while True:
        try:
            user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]")
        except (KeyboardInterrupt, EOFError):
            print_system("\n已退出，再见！")
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        # 斜杠命令处理
        if user_input.startswith("/"):
            if user_input.lower() == "/clear":
                thread_id = str(uuid.uuid4())
                print_system(f"已开启新会话：{thread_id[:8]}...（旧记录保留在 SQLite）")
                continue

            handled = _handle_slash(user_input, thread_id)
            if handled:
                continue
            print_system(f"未知命令 '{user_input}'，作为普通输入发送...")

        # 调用 Agent（流式）
        try:
            result = _stream_invoke(user_input, thread_id)

            if result.get("revision_count", 0) > 0:
                print_system("Reflection 已审查并修正了输出")

            if result.get("task_plan"):
                print_task_chain(result["task_plan"])

            if result.get("needs_compression"):
                print_system("上下文已压缩并写入长期记忆")

        except KeyboardInterrupt:
            print_system("\n已中断当前请求（可继续输入）")
        except Exception as e:
            print_error(str(e))


# ── run 命令 ──────────────────────────────────────────────────────────────────

@app.command()
def run(
    prompt: str = typer.Argument(..., help="发送给 Agent 的指令"),
    thread: str = typer.Option(
        _DEFAULT_THREAD, "--thread", "-t",
        help="会话 ID，使用相同 ID 可延续上下文"
    ),
):
    """单次执行，非交互模式"""
    init_db()

    try:
        result = _stream_invoke(prompt, thread)

        if result.get("needs_compression"):
            print_system("上下文已压缩并写入长期记忆")

    except KeyboardInterrupt:
        print_system("\n已中断")
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)


# ── config 命令 ───────────────────────────────────────────────────────────────

@app.command(name="config")
def show_config():
    """查看当前配置"""
    _print_config()


if __name__ == "__main__":
    app()
