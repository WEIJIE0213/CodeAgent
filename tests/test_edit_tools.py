"""tests/test_edit_tools.py — 精确文件编辑工具测试"""
import pytest
from pathlib import Path


# ── Fixture ────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def patch_workspace(tmp_path, monkeypatch):
    import codeagent.tools.edit_tools as et
    monkeypatch.setattr(et.settings, "WORKSPACE_DIR", str(tmp_path))
    return tmp_path


def write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# ── search_and_replace ─────────────────────────────────────────────────────────

class TestSearchAndReplace:
    def test_literal_replace(self, tmp_path):
        write(tmp_path, "f.py", "hello world\nhello again\n")
        from codeagent.tools.edit_tools import search_and_replace
        result = search_and_replace.invoke({"path": "f.py", "old_text": "hello", "new_text": "hi"})
        assert "2 处替换" in result
        assert (tmp_path / "f.py").read_text() == "hi world\nhi again\n"

    def test_no_match(self, tmp_path):
        write(tmp_path, "f.py", "hello world\n")
        from codeagent.tools.edit_tools import search_and_replace
        result = search_and_replace.invoke({"path": "f.py", "old_text": "xyz", "new_text": "abc"})
        assert "未找到" in result

    def test_regex_replace(self, tmp_path):
        write(tmp_path, "f.py", "foo123bar\nfoo456bar\n")
        from codeagent.tools.edit_tools import search_and_replace
        result = search_and_replace.invoke({
            "path": "f.py", "old_text": r"foo\d+bar", "new_text": "replaced", "use_regex": True
        })
        assert "2 处替换" in result

    def test_file_not_exist(self, tmp_path):
        from codeagent.tools.edit_tools import search_and_replace
        result = search_and_replace.invoke({"path": "no.py", "old_text": "x", "new_text": "y"})
        assert "不存在" in result

    def test_path_escape(self, tmp_path):
        from codeagent.tools.edit_tools import search_and_replace
        result = search_and_replace.invoke({"path": "../../etc/passwd", "old_text": "x", "new_text": "y"})
        assert "权限错误" in result or "超出工作目录" in result


# ── insert_content ─────────────────────────────────────────────────────────────

class TestInsertContent:
    def test_insert_after_line(self, tmp_path):
        write(tmp_path, "f.py", "line1\nline2\nline3\n")
        from codeagent.tools.edit_tools import insert_content
        result = insert_content.invoke({"path": "f.py", "insert_after_line": 1, "content": "inserted"})
        assert "插入" in result
        lines = (tmp_path / "f.py").read_text().splitlines()
        assert lines == ["line1", "inserted", "line2", "line3"]

    def test_insert_at_beginning(self, tmp_path):
        write(tmp_path, "f.py", "line1\nline2\n")
        from codeagent.tools.edit_tools import insert_content
        insert_content.invoke({"path": "f.py", "insert_after_line": 0, "content": "header"})
        lines = (tmp_path / "f.py").read_text().splitlines()
        assert lines[0] == "header"

    def test_insert_at_end(self, tmp_path):
        write(tmp_path, "f.py", "line1\nline2\n")
        from codeagent.tools.edit_tools import insert_content
        insert_content.invoke({"path": "f.py", "insert_after_line": 2, "content": "footer"})
        lines = (tmp_path / "f.py").read_text().splitlines()
        assert lines[-1] == "footer"

    def test_line_out_of_range(self, tmp_path):
        write(tmp_path, "f.py", "line1\n")
        from codeagent.tools.edit_tools import insert_content
        result = insert_content.invoke({"path": "f.py", "insert_after_line": 99, "content": "x"})
        assert "错误" in result


# ── apply_diff ─────────────────────────────────────────────────────────────────

class TestApplyDiff:
    def test_simple_replace(self, tmp_path):
        write(tmp_path, "f.py", "line1\nold line\nline3\n")
        diff = (
            "@@ -1,3 +1,3 @@\n"
            " line1\n"
            "-old line\n"
            "+new line\n"
            " line3\n"
        )
        from codeagent.tools.edit_tools import apply_diff
        result = apply_diff.invoke({"path": "f.py", "diff_content": diff})
        assert "成功" in result
        assert (tmp_path / "f.py").read_text(encoding="utf-8").split("\n")[1] == "new line"

    def test_add_lines(self, tmp_path):
        write(tmp_path, "f.py", "line1\nline2\n")
        diff = (
            "@@ -1,2 +1,3 @@\n"
            " line1\n"
            "+inserted\n"
            " line2\n"
        )
        from codeagent.tools.edit_tools import apply_diff
        apply_diff.invoke({"path": "f.py", "diff_content": diff})
        lines = (tmp_path / "f.py").read_text().splitlines()
        assert "inserted" in lines

    def test_invalid_diff_no_hunks(self, tmp_path):
        write(tmp_path, "f.py", "content\n")
        from codeagent.tools.edit_tools import apply_diff
        result = apply_diff.invoke({"path": "f.py", "diff_content": "not a diff"})
        assert "错误" in result

    def test_file_not_exist(self, tmp_path):
        from codeagent.tools.edit_tools import apply_diff
        result = apply_diff.invoke({"path": "no.py", "diff_content": "@@ -1 +1 @@\n-x\n+y\n"})
        assert "不存在" in result
