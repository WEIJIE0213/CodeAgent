"""
reflection.py —— Reflection 节点（Phase 3）

触发条件：intent 为 code 或 decompose，且 revision_count < 1。
判断逻辑：
  - 调用 LLM 审查 final_response
  - 响应以 PASS 开头 → 通过，needs_revision=False
  - 响应以 NEEDS_REVISION 开头 → 设置反馈，needs_revision=True

路由函数 route_after_reflection：
  - needs_revision=True  → 回到 code_agent 或 task_decomposer（仅一次）
  - needs_revision=False → 前往 memory_writer
"""
from langchain_core.prompts import ChatPromptTemplate
from codeagent.graph.state import AgentState
from codeagent.config import get_llm

_REFLECTION_SYSTEM = """\
你是一名严格的代码审查员，负责快速审查编程助手的输出质量。

审查维度（仅关注明显问题，不要过度挑剔）：
1. 代码是否有语法错误或明显的逻辑缺陷？
2. 是否遗漏了用户明确要求的关键功能？
3. 回答是否与用户问题严重不符？

输出格式（严格遵守，只能选其一）：

若输出质量合格：
PASS

若存在明显问题（不超过 3 条）：
NEEDS_REVISION
- 问题 1
- 问题 2
"""

_PROMPT = ChatPromptTemplate.from_messages([
    ("system", _REFLECTION_SYSTEM),
    ("human", "用户需求：{user_input}\n\n助手输出：\n{response}"),
])

_REVIEWED_INTENTS = {"code", "decompose"}


def reflection_node(state: AgentState) -> dict:
    intent = state.get("intent", "qa")
    revision_count = state.get("revision_count", 0)

    # 不需要 reflection 的情况：直接通过
    if intent not in _REVIEWED_INTENTS or revision_count >= 1:
        return {"needs_revision": False, "reflection_feedback": ""}

    llm = get_llm()
    chain = _PROMPT | llm

    try:
        result = chain.invoke({
            "user_input": state.get("user_input", ""),
            "response": state.get("final_response", "")[:2000],  # 截断防 token 超出
        })
        content = result.content.strip()
    except Exception:
        # reflection 失败，不阻断主流程
        return {"needs_revision": False, "reflection_feedback": ""}

    if content.upper().startswith("PASS"):
        return {"needs_revision": False, "reflection_feedback": ""}

    # 提取 NEEDS_REVISION 后面的具体反馈
    feedback = content.replace("NEEDS_REVISION", "").strip()
    return {
        "needs_revision": True,
        "reflection_feedback": feedback,
        "revision_count": revision_count + 1,
    }


def route_after_reflection(state: AgentState) -> str:
    """Reflection 后的路由：需要修正 → 回原节点；否则 → memory_writer"""
    if state.get("needs_revision"):
        return "task_decomposer" if state.get("intent") == "decompose" else "code_agent"
    return "memory_writer"
