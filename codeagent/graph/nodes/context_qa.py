"""
context_qa —— 上下文问答节点（Phase 2 升级版）

system prompt 新增三层记忆注入（同 code_agent）。
memory 意图直接返回当前 long_term_summary 内容，让用户查看历史。
"""
from langchain_core.prompts import ChatPromptTemplate
from codeagent.graph.state import AgentState
from codeagent.config import get_llm

_QA_SYSTEM = """\
你是一个专业的编程助手，擅长解释概念、回答技术问题、提供建议。

回答要求：
1. 准确清晰，避免冗余
2. 必要时给出代码示例
3. 复杂概念分点说明

── 历史摘要 ──────────────────────
{long_term_summary}

── 相关记忆 ──────────────────────
{retrieved_memory}

── 近期对话 ──────────────────────
{context}
"""

_PROMPT = ChatPromptTemplate.from_messages([
    ("system", _QA_SYSTEM),
    ("human", "{user_input}"),
])


def _fmt_context(short_term: list) -> str:
    if not short_term:
        return "（无）"
    return "\n".join(
        f"{m['role'].upper()}: {m['content'][:300]}"
        for m in short_term[-6:]
    )


def context_qa_node(state: AgentState) -> dict:
    # memory 意图：展示当前长期摘要 + 相关检索片段
    if state.get("intent") == "memory":
        parts = []
        summary = state.get("long_term_summary")
        if summary:
            parts.append(f"**长期记忆摘要：**\n\n{summary}")
        else:
            parts.append("**长期记忆摘要：** 暂无（对话超过 10 轮后自动生成）")

        retrieved = state.get("retrieved_memory")
        if retrieved:
            parts.append(f"**语义检索到的相关历史：**\n\n{retrieved[:600]}")

        return {
            "final_response": "\n\n---\n\n".join(parts),
            "response_type": "markdown",
        }

    llm = get_llm(streaming=True)
    chain = _PROMPT | llm
    result = chain.invoke({
        "user_input": state["user_input"],
        "long_term_summary": state.get("long_term_summary") or "（无）",
        "retrieved_memory": state.get("retrieved_memory") or "（无）",
        "context": _fmt_context(state.get("short_term", [])),
    })

    return {"final_response": result.content, "response_type": "markdown"}
