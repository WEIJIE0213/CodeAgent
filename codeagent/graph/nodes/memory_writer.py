"""
memory_writer —— 记忆写入节点（Phase 2 升级版）

每轮对话结束后执行：
  1. 更新 short_term 滑动窗口
  2. 将本轮消息持久化到 SQLite
  3. 将摘要对存入 ChromaDB（用于语义检索）
  4. 判断是否需要压缩：若 short_term 超出阈值，执行压缩
     - 压缩结果存入 SQLite summaries 表
     - 压缩摘要存入 ChromaDB
     - short_term 截断到最近 3 轮（6 条）
"""
from langchain_core.runnables import RunnableConfig

from codeagent.graph.state import AgentState
from codeagent.config import settings
from codeagent.memory.long_term import save_messages, save_summary, upsert_session
from codeagent.memory.compressor import should_compress, split_for_compression, compress
from codeagent.memory.vector_store import store_memory


def memory_writer_node(state: AgentState, config: RunnableConfig) -> dict:
    thread_id: str = config.get("configurable", {}).get("thread_id", "default")
    user_input = state.get("user_input", "")
    final_response = state.get("final_response", "")

    # ── 1. 更新 short_term ────────────────────────
    short_term = list(state.get("short_term", []))
    short_term.append({"role": "user", "content": user_input})
    short_term.append({"role": "assistant", "content": final_response})

    # ── 2. 持久化到 SQLite ────────────────────────
    try:
        upsert_session(thread_id)
        save_messages(thread_id, user_input, final_response)
    except Exception:
        pass

    # ── 3. 存入向量库（本轮摘要对）─────────────
    # 跳过 memory 意图的回复，避免把记忆摘要本身再存入向量库造成"套娃"
    intent = state.get("intent", "")
    if intent != "memory":
        try:
            turn_text = f"Q: {user_input[:300]}\nA: {final_response[:300]}"
            store_memory(thread_id, turn_text, doc_type="turn")
        except Exception:
            pass

    # ── 4. 判断是否压缩 ────────────────────────────
    long_term_summary = state.get("long_term_summary", "")
    needs_compression = False

    if should_compress(short_term):
        old_messages, short_term = split_for_compression(short_term)
        new_summary = compress(old_messages, long_term_summary)

        long_term_summary = new_summary
        needs_compression = True

        # 持久化摘要
        try:
            save_summary(thread_id, new_summary)
            store_memory(thread_id, new_summary, doc_type="summary")
        except Exception:
            pass

    return {
        "short_term": short_term,
        "long_term_summary": long_term_summary,
        "needs_compression": needs_compression,
    }
