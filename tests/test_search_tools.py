"""tests/test_search_tools.py — search_files 多策略搜索测试"""
import pytest
from pathlib import Path
from unittest.mock import patch


@pytest.fixture(autouse=True)
def patch_workspace(tmp_path, monkeypatch):
    import codeagent.tools.search_tools as st
    monkeypatch.setattr(st.settings, "WORKSPACE_DIR", str(tmp_path))
    return tmp_path


def write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


class TestSearchFilesPythonFallback:
    """强制禁用 git/rg，只测试 Python fallback"""

    def _search(self, query, file_pattern="*", case_sensitive=False):
        from codeagent.tools.search_tools import search_files
        # 用 patch 让 git 和 rg 不可用
        with patch("codeagent.tools.search_tools._git_grep", return_value=None), \
             patch("codeagent.tools.search_tools._rg_search", return_value=None):
            return search_files.invoke({
                "query": query,
                "file_pattern": file_pattern,
                "case_sensitive": case_sensitive,
            })

    def test_finds_match(self, tmp_path):
        write(tmp_path, "a.py", "def hello_world():\n    pass\n")
        result = self._search("hello_world", "*.py")
        assert "hello_world" in result
        assert "a.py" in result

    def test_no_match(self, tmp_path):
        write(tmp_path, "a.py", "def foo():\n    pass\n")
        result = self._search("zzznomatch", "*.py")
        assert "未找到" in result

    def test_case_insensitive(self, tmp_path):
        write(tmp_path, "a.py", "HELLO WORLD\n")
        result = self._search("hello world", "*.py", case_sensitive=False)
        assert "a.py" in result

    def test_case_sensitive_miss(self, tmp_path):
        write(tmp_path, "a.py", "HELLO WORLD\n")
        result = self._search("hello world", "*.py", case_sensitive=True)
        assert "未找到" in result

    def test_file_pattern_filter(self, tmp_path):
        write(tmp_path, "a.py", "needle\n")
        write(tmp_path, "b.txt", "needle\n")
        result = self._search("needle", "*.py")
        assert "a.py" in result
        assert "b.txt" not in result

    def test_multifile(self, tmp_path):
        write(tmp_path, "a.py", "match here\n")
        write(tmp_path, "b.py", "match here too\n")
        result = self._search("match here")
        assert "a.py" in result
        assert "b.py" in result


class TestSearchFilesEngineLabel:
    def test_python_label(self, tmp_path):
        write(tmp_path, "a.py", "hello\n")
        from codeagent.tools.search_tools import search_files
        with patch("codeagent.tools.search_tools._git_grep", return_value=None), \
             patch("codeagent.tools.search_tools._rg_search", return_value=None):
            result = search_files.invoke({"query": "hello"})
        assert "Python" in result
