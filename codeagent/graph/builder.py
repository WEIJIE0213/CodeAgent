"""
builder.py —— LangGraph 图构建（Phase 3 版）

图结构：
  START
    → context_loader
    → intent_router
    →(条件) code_agent | task_decomposer | context_qa
    → (code/decompose 后) reflection
    →(条件) code_agent | task_decomposer | memory_writer  ← revision 或直接结束
    → (context_qa 后) memory_writer
    → END
"""
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from codeagent.graph.state import AgentState
from codeagent.graph.nodes.context_loader import context_loader_node
from codeagent.graph.nodes.intent_router import intent_router_node, route_by_intent
from codeagent.graph.nodes.code_agent import code_agent_node
from codeagent.graph.nodes.task_decomposer import task_decomposer_node
from codeagent.graph.nodes.context_qa import context_qa_node
from codeagent.graph.nodes.reflection import reflection_node, route_after_reflection
from codeagent.graph.nodes.memory_writer import memory_writer_node


def build_graph():
    builder = StateGraph(AgentState)

    # ── 注册节点 ──────────────────────────────────
    builder.add_node("context_loader",   context_loader_node)
    builder.add_node("intent_router",    intent_router_node)
    builder.add_node("code_agent",       code_agent_node)
    builder.add_node("task_decomposer",  task_decomposer_node)
    builder.add_node("context_qa",       context_qa_node)
    builder.add_node("reflection",       reflection_node)
    builder.add_node("memory_writer",    memory_writer_node)

    # ── 固定边 ────────────────────────────────────
    builder.add_edge(START, "context_loader")
    builder.add_edge("context_loader", "intent_router")

    # code / decompose → reflection（Reflection 节点内部决定是否真正执行）
    builder.add_edge("code_agent",      "reflection")
    builder.add_edge("task_decomposer", "reflection")

    # context_qa 直接跳过 reflection
    builder.add_edge("context_qa", "memory_writer")
    builder.add_edge("memory_writer", END)

    # ── 意图路由：intent_router → 各 Agent ─────────
    builder.add_conditional_edges(
        "intent_router",
        route_by_intent,
        {
            "code_agent":      "code_agent",
            "task_decomposer": "task_decomposer",
            "context_qa":      "context_qa",
        },
    )

    # ── Reflection 后路由：通过/重试/结束 ───────────
    builder.add_conditional_edges(
        "reflection",
        route_after_reflection,
        {
            "code_agent":      "code_agent",
            "task_decomposer": "task_decomposer",
            "memory_writer":   "memory_writer",
        },
    )

    checkpointer = MemorySaver()
    return builder.compile(checkpointer=checkpointer)


graph = build_graph()
