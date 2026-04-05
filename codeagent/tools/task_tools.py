"""
task_tools —— Agent 内部任务追踪工具

将任务列表持久化到 WORKSPACE_DIR/.codeagent_todos.json。
Agent 可用此工具自我管理子任务进度，不依赖外部数据库。
"""
import json
import uuid
from datetime import datetime
from pathlib import Path
from langchain_core.tools import tool

from codeagent.config import settings

_TODOS_FILE = ".codeagent_todos.json"


def _todos_path() -> Path:
    return Path(settings.WORKSPACE_DIR).resolve() / _TODOS_FILE


def _load() -> list[dict]:
    p = _todos_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save(todos: list[dict]) -> None:
    _todos_path().write_text(
        json.dumps(todos, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


@tool
def update_todos(action: str, content: str = "", todo_id: str = "") -> str:
    """
    管理 Agent 任务列表（存储在工作目录的 .codeagent_todos.json）。
    action 支持：
      add      — 新增任务，需提供 content（任务描述）
      list     — 列出所有任务及状态
      complete — 标记任务为已完成，需提供 todo_id
      remove   — 删除任务，需提供 todo_id
      clear    — 清空所有任务
    content: 任务描述（action=add 时必填）
    todo_id: 任务 ID（action=complete/remove 时必填）
    """
    action = action.strip().lower()

    if action == "add":
        if not content.strip():
            return "错误：action=add 时必须提供 content（任务描述）"
        todos = _load()
        new_todo = {
            "id": str(uuid.uuid4())[:8],
            "content": content.strip(),
            "status": "pending",
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
        todos.append(new_todo)
        _save(todos)
        return f"已添加任务 [{new_todo['id']}]：{new_todo['content']}"

    elif action == "list":
        todos = _load()
        if not todos:
            return "任务列表为空（使用 action=add 添加任务）"
        lines = []
        for t in todos:
            icon = "✓" if t["status"] == "completed" else "○"
            lines.append(f"[{icon}] {t['id']}  {t['content']}")
        return "\n".join(lines)

    elif action == "complete":
        if not todo_id.strip():
            return "错误：action=complete 时必须提供 todo_id"
        todos = _load()
        for t in todos:
            if t["id"] == todo_id.strip():
                t["status"] = "completed"
                t["completed_at"] = datetime.now().isoformat(timespec="seconds")
                _save(todos)
                return f"已标记完成：[{t['id']}] {t['content']}"
        return f"未找到 ID 为 '{todo_id}' 的任务"

    elif action == "remove":
        if not todo_id.strip():
            return "错误：action=remove 时必须提供 todo_id"
        todos = _load()
        before = len(todos)
        todos = [t for t in todos if t["id"] != todo_id.strip()]
        if len(todos) == before:
            return f"未找到 ID 为 '{todo_id}' 的任务"
        _save(todos)
        return f"已删除任务 '{todo_id}'"

    elif action == "clear":
        _save([])
        return "已清空所有任务"

    else:
        return f"未知 action '{action}'，支持：add / list / complete / remove / clear"
