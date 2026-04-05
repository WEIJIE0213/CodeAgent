"""
task_decomposer —— 任务拆解节点（Phase 4 升级版）

变更：集成工具调用（bind_tools + ToolMessage 循环，最多 3 轮）

两步执行：
  Step 1：调用 LLM 生成结构化计划（带编号列表）
  Step 2：根据计划生成完整实现（可使用工具读取项目结构）

支持 revision 模式：若 reflection_feedback 非空，则使用修正 prompt。
解析响应中的编号列表，写入 task_plan 供 /tasks 命令显示。
"""
import re
from langchain_core.messages import ToolMessage
from codeagent.graph.state import AgentState
from codeagent.config import get_llm
from codeagent.tools import all_tools

_TOOL_MAP = {t.name: t for t in all_tools}
_MAX_TOOL_ROUNDS = 3

# ── Prompt：首次拆解 ──────────────────────────────────────────────────────────

_DECOMPOSE_SYSTEM = """\
你是一个专业的编程助手，擅长将复杂任务拆解为可执行步骤并逐步实现。

输出格式要求（严格遵守）：

## 任务拆解
1. 第一步标题
2. 第二步标题
3. 第三步标题
（最多 5 步）

## 实现

### 步骤 1：第一步标题
[代码或说明]

### 步骤 2：第二步标题
[代码或说明]

（以此类推）

可用工具（需要时调用）：
- read_file / list_dir: 读取项目结构和文件内容
- apply_diff / search_and_replace / insert_content: 精确修改文件
- search_files / search_code: 搜索代码和内容
- run_shell: 执行命令（如安装依赖、运行测试）
- update_todos: 记录子任务进度

── 历史摘要 ──────────────────────
{long_term_summary}

── 相关记忆 ──────────────────────
{retrieved_memory}

── 近期对话 ──────────────────────
{context}
"""

# ── Prompt：修正模式 ──────────────────────────────────────────────────────────

_REVISION_SYSTEM = """\
你是一个专业的编程助手。你的上一次任务拆解输出收到了审查反馈，请根据反馈进行修正。

审查反馈：
{reflection_feedback}

原始输出（请在此基础上修正，保留格式）：
{previous_response}

修正后仍需保持原有的输出格式（## 任务拆解 + ## 实现）。
你可以调用工具（read_file / list_dir 等）来了解项目结构。
"""


# ── 解析工具 ──────────────────────────────────────────────────────────────────

def _parse_task_plan(text: str) -> list:
    """从响应中解析 '## 任务拆解' 下的编号列表"""
    # 找到任务拆解部分
    section = re.search(
        r'##\s*任务拆解\s*\n((?:\d+\..+\n?)+)',
        text,
        re.MULTILINE,
    )
    if not section:
        return []

    tasks = []
    for i, line in enumerate(section.group(1).strip().splitlines(), start=1):
        line = line.strip()
        if re.match(r'^\d+\.', line):
            title = re.sub(r'^\d+\.\s*', '', line).strip()
            if title:
                tasks.append({"id": i, "title": title, "status": "completed"})
    return tasks


def _fmt_context(short_term: list) -> str:
    if not short_term:
        return "（无）"
    return "\n".join(
        f"{m['role'].upper()}: {m['content'][:300]}"
        for m in short_term[-6:]
    )


def _run_tool(tool_call: dict) -> str:
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
    for _ in range(_MAX_TOOL_ROUNDS):
        response = llm_with_tools.invoke(messages)
        tool_calls = getattr(response, "tool_calls", None)
        if not tool_calls:
            return response.content
        messages.append(response)
        for tc in tool_calls:
            result = _run_tool(tc)
            messages.append(ToolMessage(content=result, tool_call_id=tc["id"]))
    # 超过最大轮次：强制文字总结
    from codeagent.config import get_llm as _get_llm
    messages.append({
        "role": "user",
        "content": "请根据以上工具调用的结果，给出完整的任务拆解和实现方案。",
    })
    final = _get_llm().invoke(messages)
    return final.content or "（工具调用已达到最大轮次，请尝试更具体的任务描述）"


# ── 节点函数 ──────────────────────────────────────────────────────────────────

def task_decomposer_node(state: AgentState) -> dict:
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
        system_content = _DECOMPOSE_SYSTEM.format(
            long_term_summary=state.get("long_term_summary") or "（无）",
            retrieved_memory=state.get("retrieved_memory") or "（无）",
            context=_fmt_context(state.get("short_term", [])),
        )
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": state["user_input"]},
        ]

    response_text = _tool_loop(llm_with_tools, messages)
    task_plan = _parse_task_plan(response_text)

    return {
        "final_response": response_text,
        "response_type": "markdown",
        "task_plan": task_plan,
        "reflection_feedback": "",   # 清空，避免下轮误用
    }
