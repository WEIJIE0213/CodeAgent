"""
AgentState —— LangGraph 全局状态（Phase 3 扩展版）

新增字段：
  task_plan          : 任务拆解子任务列表
  reflection_feedback: Reflection 节点的审查意见
  needs_revision     : 是否需要重试
  revision_count     : 已反思次数（最多 1 次）
"""
from typing import TypedDict


class AgentState(TypedDict):
    # ── 输入 ──────────────────────────────────────
    user_input: str

    # ── 路由 ──────────────────────────────────────
    intent: str                  # code | decompose | qa | memory

    # ── 记忆（Phase 2）────────────────────────────
    short_term: list             # [{"role": str, "content": str}, ...]
    long_term_summary: str       # 历史摘要（SQLite）
    retrieved_memory: str        # Qdrant 语义检索片段
    needs_compression: bool      # memory_writer 写入，供 CLI 提示

    # ── 任务拆解（Phase 3）────────────────────────
    task_plan: list              # [{"id": int, "title": str, "status": str}]

    # ── Reflection（Phase 3）──────────────────────
    reflection_feedback: str     # 审查意见（空字符串 = 通过）
    needs_revision: bool         # 是否需要重新生成
    revision_count: int          # 已反思次数（最多 1）

    # ── 输出 ──────────────────────────────────────
    final_response: str
    response_type: str
