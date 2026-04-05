"""
context_loader —— 上下文加载节点（Phase 2 升级版）

每次对话开始时执行：
  1. 确保 SQLite 已初始化
  2. 加载该 thread_id 的最新 long_term_summary
  3. 语义检索 ChromaDB，获取 retrieved_memory（Top-3）
  4. 若 short_term 为空，从 SQLite 恢复最近 N 条消息
"""
from langchain_core.runnables import RunnableConfig

from codeagent.graph.state import AgentState
from codeagent.memory.long_term import init_db, upsert_session, get_latest_summary, get_recent_messages
from codeagent.memory.vector_store import retrieve_memories
from codeagent.config import settings


def context_loader_node(state: AgentState, config: RunnableConfig) -> dict:
    thread_id: str = config.get("configurable", {}).get("thread_id", "default")

    # 确保数据库表存在
    init_db()
    upsert_session(thread_id)

    updates: dict = {}

    # ── 1. 加载长期摘要 ────────────────────────────
    if not state.get("long_term_summary"):
        summary = get_latest_summary(thread_id)
        if summary:
            updates["long_term_summary"] = summary

    # ── 2. 语义检索相关记忆 ────────────────────────
    user_input = state.get("user_input", "")
    if user_input:
        retrieved = retrieve_memories(user_input, top_k=3)
        updates["retrieved_memory"] = retrieved

    # ── 3. 恢复 short_term（会话重启时） ──────────
    if not state.get("short_term"):
        recent = get_recent_messages(thread_id, limit=settings.WINDOW_SIZE * 2)
        if recent:
            updates["short_term"] = recent

    return updates
