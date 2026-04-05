"""
short_term —— 短期记忆工具函数

管理滑动窗口，为 CLI 的 /history 命令提供格式化输出。
"""
from typing import List


def format_history(short_term: List[dict]) -> str:
    """将 short_term 格式化为可读的对话历史字符串"""
    if not short_term:
        return "（本次会话无历史记录）"

    lines = []
    round_num = 1
    for i in range(0, len(short_term) - 1, 2):
        user_msg = short_term[i].get("content", "")
        assistant_msg = short_term[i + 1].get("content", "") if i + 1 < len(short_term) else ""
        lines.append(f"[轮 {round_num}]")
        lines.append(f"  You     : {user_msg[:100]}{'...' if len(user_msg) > 100 else ''}")
        lines.append(f"  Agent   : {assistant_msg[:100]}{'...' if len(assistant_msg) > 100 else ''}")
        round_num += 1

    return "\n".join(lines)


def count_rounds(short_term: List[dict]) -> int:
    return len(short_term) // 2
