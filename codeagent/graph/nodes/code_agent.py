"""
code_agent —— 代码生成节点（Phase 4 升级版）

变更：
- 集成工具调用（bind_tools + ToolMessage 循环，最多 3 轮）
- revision 模式保留
"""
import json
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from codeagent.graph.state import AgentState
from codeagent.config import get_llm
from codeagent.tools import all_tools

_TOOL_MAP = {t.name: t for t in all_tools}
_MAX_TOOL_ROUNDS = 3

# ── 正常生成 ──────────────────────────────────────────────────────────────────

_CODE_SYSTEM = """\
你是一个专业的编程助手。根据用户请求生成高质量的代码。

你可以调用以下工具来辅助完成任务：
文件读写：
- read_file(path): 读取工作目录内的文件
- write_file(path, content): 写入文件（整体覆盖）
- list_dir(path): 列出目录内容
精确编辑（优先用这些替代 write_file）：
- apply_diff(path, diff_content): 应用 unified diff 补丁，精确修改文件局部
- search_and_replace(path, old_text, new_text, use_regex): 搜索并替换文本
- insert_content(path, insert_after_line, content): 在指定行号后插入内容
搜索：
- search_files(query, file_pattern, case_sensitive): 多策略搜索（git grep/rg/Python）
- search_code(pattern, file_glob): 正则搜索代码文件
执行与追踪：
- run_shell(command): 在沙箱内执行命令（危险命令会被拦截）
- update_todos(action, content, todo_id): 管理任务列表（add/list/complete/remove/clear）
- use_mcp_tool(server_name, tool_name, arguments): 调用外部 MCP 工具服务器

要求：
1. 代码完整、可直接运行
2. 使用正确的代码块标记（```python / ```javascript 等）
3. 代码前后用一两句话说明思路或注意事项
4. 需要时先调用工具了解项目结构，再生成代码

── 历史摘要 ──────────────────────
{long_term_summary}

── 相关记忆 ──────────────────────
{retrieved_memory}

── 近期对话 ──────────────────────
{context}
"""

# ── Revision 模式 ─────────────────────────────────────────────────────────────

_REVISION_SYSTEM = """\
你是一个专业的编程助手。你的上一次代码输出收到了审查反馈，请根据反馈进行修正。

审查反馈（请重点修正这些问题）：
{reflection_feedback}

你的原始输出：
{previous_response}

请修正上述问题并输出完整的最终版本。
你可以调用工具（read_file / run_shell 等）来验证修正结果。
"""


def _fmt_context(short_term: list) -> str:
    if not short_term:
        return "（无）"
    return "\n".join(
        f"{m['role'].upper()}: {m['content'][:300]}"
        for m in short_term[-6:]
    )


def _run_tool(tool_call: dict) -> str:
    """执行单个工具调用，返回结果字符串"""
    name = tool_call.get("name", "")
    args = tool_call.get("args", {})
    tool_fn = _TOOL_MAP.get(name)
    if tool_fn is None:
        return f"未知工具：{name}"
    try:
        return str(tool_fn.invoke(args))
    except Exception as e:
        return f"工具执行失败：{e}"


def _tool_loop(llm_with_tools, messages: list) -> str:
    """执行 LLM + 工具调用循环，最多 _MAX_TOOL_ROUNDS 轮，返回最终文本响应"""
    for _ in range(_MAX_TOOL_ROUNDS):
        response = llm_with_tools.invoke(messages)
        tool_calls = getattr(response, "tool_calls", None)

        if not tool_calls:
            # 无工具调用，直接返回文本
            return response.content

        # 追加 AI 消息（包含 tool_calls）
        messages.append(response)

        # 执行所有工具调用，追加 ToolMessage
        for tc in tool_calls:
            result = _run_tool(tc)
            messages.append(ToolMessage(content=result, tool_call_id=tc["id"]))

    # 超过最大轮次：用不绑定工具的 LLM 强制生成文字总结，避免返回空内容
    messages.append({
        "role": "user",
        "content": "请根据以上工具调用的结果，给出完整的分析和回答。",
    })
    final = get_llm().invoke(messages)
    return final.content or "（工具调用已达到最大轮次，无法生成完整回答，请尝试更具体的问题）"


def code_agent_node(state: AgentState) -> dict:
    llm = get_llm()
    llm_with_tools = llm.bind_tools(all_tools)
    is_revision = bool(state.get("reflection_feedback"))

    if is_revision:
        system_content = _REVISION_SYSTEM.format(
            reflection_feedback=state.get("reflection_feedback", ""),
            previous_response=state.get("final_response", ""),
        )
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": f"原始需求：{state['user_input']}"},
        ]
    else:
        system_content = _CODE_SYSTEM.format(
            long_term_summary=state.get("long_term_summary") or "（无）",
            retrieved_memory=state.get("retrieved_memory") or "（无）",
            context=_fmt_context(state.get("short_term", [])),
        )
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": state["user_input"]},
        ]

    final_text = _tool_loop(llm_with_tools, messages)

    return {
        "final_response": final_text,
        "response_type": "markdown",
        "reflection_feedback": "",  # 清空，避免下轮误用
    }
