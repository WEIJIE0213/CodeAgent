"""tests/test_task_tools.py — update_todos 任务追踪测试"""
import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def patch_workspace(tmp_path, monkeypatch):
    import codeagent.tools.task_tools as tt
    monkeypatch.setattr(tt.settings, "WORKSPACE_DIR", str(tmp_path))
    return tmp_path


class TestUpdateTodos:
    def test_add_and_list(self, tmp_path):
        from codeagent.tools.task_tools import update_todos
        update_todos.invoke({"action": "add", "content": "实现登录功能"})
        result = update_todos.invoke({"action": "list"})
        assert "实现登录功能" in result

    def test_add_multiple(self, tmp_path):
        from codeagent.tools.task_tools import update_todos
        update_todos.invoke({"action": "add", "content": "任务一"})
        update_todos.invoke({"action": "add", "content": "任务二"})
        result = update_todos.invoke({"action": "list"})
        assert "任务一" in result
        assert "任务二" in result

    def test_complete(self, tmp_path):
        from codeagent.tools.task_tools import update_todos
        add_result = update_todos.invoke({"action": "add", "content": "测试任务"})
        # 从返回值中提取 ID
        import re
        m = re.search(r"\[([0-9a-f]+)\]", add_result)
        assert m, f"未找到 ID，返回：{add_result}"
        todo_id = m.group(1)
        result = update_todos.invoke({"action": "complete", "todo_id": todo_id})
        assert "完成" in result
        list_result = update_todos.invoke({"action": "list"})
        assert "✓" in list_result

    def test_remove(self, tmp_path):
        from codeagent.tools.task_tools import update_todos
        add_result = update_todos.invoke({"action": "add", "content": "待删除任务"})
        import re
        todo_id = re.search(r"\[([0-9a-f]+)\]", add_result).group(1)
        remove_result = update_todos.invoke({"action": "remove", "todo_id": todo_id})
        assert "删除" in remove_result
        list_result = update_todos.invoke({"action": "list"})
        assert "待删除任务" not in list_result

    def test_clear(self, tmp_path):
        from codeagent.tools.task_tools import update_todos
        update_todos.invoke({"action": "add", "content": "任务A"})
        update_todos.invoke({"action": "add", "content": "任务B"})
        update_todos.invoke({"action": "clear"})
        result = update_todos.invoke({"action": "list"})
        assert "为空" in result

    def test_add_without_content(self, tmp_path):
        from codeagent.tools.task_tools import update_todos
        result = update_todos.invoke({"action": "add", "content": ""})
        assert "错误" in result

    def test_complete_unknown_id(self, tmp_path):
        from codeagent.tools.task_tools import update_todos
        result = update_todos.invoke({"action": "complete", "todo_id": "nonexistent"})
        assert "未找到" in result

    def test_unknown_action(self, tmp_path):
        from codeagent.tools.task_tools import update_todos
        result = update_todos.invoke({"action": "foobar"})
        assert "未知" in result

    def test_persistence(self, tmp_path):
        """重新导入模块后数据仍然存在（持久化到 JSON）"""
        from codeagent.tools.task_tools import update_todos
        update_todos.invoke({"action": "add", "content": "持久化测试"})
        # 直接读 JSON 验证
        import json
        todos_file = tmp_path / ".codeagent_todos.json"
        assert todos_file.exists()
        data = json.loads(todos_file.read_text(encoding="utf-8"))
        assert any(t["content"] == "持久化测试" for t in data)
