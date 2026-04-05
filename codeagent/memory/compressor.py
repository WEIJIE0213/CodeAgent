"""
compressor.py —— 上下文压缩

触发时机：short_term 轮数超过 WINDOW_SIZE 时，
  1. 取最旧的 (total - 6) 条消息（保留最近 3 轮作为锚点）
  2. 用 LLM 摘要，合并到 long_term_summary
  3. short_term 截断到最近 6 条

压缩后数据存入：SQLite summaries 表 + ChromaDB（由 memory_writer 调用）
"""
from langchain_core.prompts import ChatPromptTemplate
from codeagent.config import get_llm, settings

_ANCHOR_MESSAGES = 6   # 压缩后保留的最近消息数（3 轮）

_COMPRESS_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """\
你是编程对话摘要助手。将提供的编程对话历史压缩为结构化摘要，保留：
1. 用户提出的核心问题或任务
2. 关键代码的函数签名/核心逻辑（删除冗余细节）
3. 达成的结论、约定或未完成的事项

输出为流畅的中文段落，不超过 300 字。
若已有历史摘要，将新内容合并进去（不要丢失历史摘要的内容）。"""),
    ("human", "已有历史摘要：\n{existing}\n\n新增对话：\n{new_messages}"),
])


def should_compress(short_term: list) -> bool:
    """判断是否需要触发压缩"""
    return len(short_term) > settings.WINDOW_SIZE * 2


def split_for_compression(short_term: list) -> tuple[list, list]:
    """
    拆分 short_term：
    返回 (待压缩的旧消息, 保留的近期消息)
    """
    if len(short_term) <= _ANCHOR_MESSAGES:
        return [], short_term
    return short_term[:-_ANCHOR_MESSAGES], short_term[-_ANCHOR_MESSAGES:]


def compress(messages_to_compress: list, existing_summary: str = "") -> str:
    """
    将消息列表压缩为摘要，合并到已有摘要。
    失败时回退到拼接截断，不阻断主流程。
    """
    if not messages_to_compress:
        return existing_summary

    try:
        llm = get_llm()
        chain = _COMPRESS_PROMPT | llm

        new_text = "\n".join(
            f"{m['role'].upper()}: {m['content'][:600]}"
            for m in messages_to_compress
        )

        result = chain.invoke({
            "existing": existing_summary or "（无）",
            "new_messages": new_text,
        })
        return result.content.strip()

    except Exception:
        # 降级：直接拼接截断
        existing = existing_summary or ""
        new_chunk = " | ".join(
            m["content"][:80] for m in messages_to_compress if m["role"] == "user"
        )
        merged = f"{existing} {new_chunk}".strip()
        return merged[:800]
