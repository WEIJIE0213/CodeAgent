"""
test_tools.py —— 工具安全策略测试

测试内容：
- shell_tools: 黑名单拦截、超时、输出截断
- file_tools: 路径安全限制
- code_tools: 基础搜索功能
"""
import pytest
import os
from pathlib import Path
from unittest.mock import patch, MagicMock


# ── shell_tools ───────────────────────────────────────────────────────────────

class TestShellBlacklist:
    """测试危险命令黑名单拦截"""

    def _run(self, cmd: str) -> str:
        from codeagent.tools.shell_tools import run_shell
        return run_shell.invoke({"command": cmd})

    def test_rm_rf_blocked(self):
        result = self._run("rm -rf /tmp/test")
        assert "拒绝" in result or "黑名单" in result

    def test_rm_fr_blocked(self):
        result = self._run("rm -fr /tmp/test")
        assert "拒绝" in result or "黑名单" in result

    def test_dd_blocked(self):
        result = self._run("dd if=/dev/zero of=/dev/sda")
        assert "拒绝" in result or "黑名单" in result

    def test_mkfs_blocked(self):
        result = self._run("mkfs.ext4 /dev/sdb")
        assert "拒绝" in result or "黑名单" in result

    def test_shutdown_blocked(self):
        result = self._run("shutdown -h now")
        assert "拒绝" in result or "黑名单" in result

    def test_reboot_blocked(self):
        result = self._run("reboot")
        assert "拒绝" in result or "黑名单" in result

    def test_safe_echo_allowed(self):
        with patch("codeagent.tools.shell_tools.settings") as mock_s:
            mock_s.WORKSPACE_DIR = "."
            result = self._run("echo hello")
        assert "hello" in result

    def test_safe_python_version_allowed(self):
        with patch("codeagent.tools.shell_tools.settings") as mock_s:
            mock_s.WORKSPACE_DIR = "."
            result = self._run("python --version")
        assert "Python" in result or "退出码" in result  # 有些环境可能路径不同


class TestShellOutput:
    def test_output_not_exceed_max(self):
        """输出超长时应被截断"""
        with patch("codeagent.tools.shell_tools.settings") as mock_s, \
             patch("codeagent.tools.shell_tools._MAX_OUTPUT", 100):
            mock_s.WORKSPACE_DIR = "."
            from codeagent.tools.shell_tools import run_shell
            result = run_shell.invoke({"command": "python -c \"print('x' * 500)\""})
        assert len(result) <= 300  # 截断 + header 不超过合理范围


# ── file_tools ────────────────────────────────────────────────────────────────

class TestFileTools:
    @pytest.fixture(autouse=True)
    def _setup_workspace(self, tmp_path, monkeypatch):
        """每个测试使用独立的临时工作目录"""
        self.workspace = str(tmp_path)
        monkeypatch.setattr("codeagent.tools.file_tools.settings",
                            _fake_settings(workspace=self.workspace))

    def test_write_and_read_file(self):
        from codeagent.tools.file_tools import write_file, read_file
        write_result = write_file.invoke({"path": "hello.txt", "content": "Hello, World!"})
        assert "已写入" in write_result

        read_result = read_file.invoke({"path": "hello.txt"})
        assert read_result == "Hello, World!"

    def test_read_nonexistent_file(self):
        from codeagent.tools.file_tools import read_file
        result = read_file.invoke({"path": "not_exist.txt"})
        assert "不存在" in result or "错误" in result

    def test_path_traversal_blocked(self):
        from codeagent.tools.file_tools import read_file
        result = read_file.invoke({"path": "../../etc/passwd"})
        assert "权限错误" in result or "超出工作目录" in result

    def test_write_creates_parent_dirs(self):
        from codeagent.tools.file_tools import write_file, read_file
        write_file.invoke({"path": "subdir/nested/file.txt", "content": "deep"})
        result = read_file.invoke({"path": "subdir/nested/file.txt"})
        assert result == "deep"

    def test_list_dir_shows_files(self, tmp_path):
        from codeagent.tools.file_tools import write_file, list_dir
        write_file.invoke({"path": "a.py", "content": "# a"})
        write_file.invoke({"path": "b.py", "content": "# b"})
        result = list_dir.invoke({"path": "."})
        assert "a.py" in result
        assert "b.py" in result

    def test_list_nonexistent_dir(self):
        from codeagent.tools.file_tools import list_dir
        result = list_dir.invoke({"path": "nonexistent_dir"})
        assert "不存在" in result or "错误" in result

    def test_read_file_truncation(self, tmp_path):
        from codeagent.tools.file_tools import write_file, read_file
        import codeagent.tools.file_tools as ft
        big_content = "x" * 25_000
        write_file.invoke({"path": "big.txt", "content": big_content})

        with patch.object(ft, "_MAX_READ_CHARS", 100):
            result = read_file.invoke({"path": "big.txt"})
        assert "截断" in result


# ── code_tools ────────────────────────────────────────────────────────────────

class TestCodeTools:
    @pytest.fixture(autouse=True)
    def _setup_workspace(self, tmp_path, monkeypatch):
        self.workspace = str(tmp_path)
        monkeypatch.setattr("codeagent.tools.code_tools.settings",
                            _fake_settings(workspace=self.workspace))
        # 写一个示例 Python 文件
        (tmp_path / "example.py").write_text(
            "def hello():\n    return 'world'\n\nclass Foo:\n    pass\n",
            encoding="utf-8",
        )

    def test_search_finds_match(self):
        from codeagent.tools.code_tools import search_code
        result = search_code.invoke({"pattern": "def hello"})
        assert "example.py" in result
        assert "def hello" in result

    def test_search_no_match(self):
        from codeagent.tools.code_tools import search_code
        result = search_code.invoke({"pattern": "nonexistent_function_xyz"})
        assert "未找到" in result

    def test_search_class(self):
        from codeagent.tools.code_tools import search_code
        result = search_code.invoke({"pattern": "class Foo"})
        assert "Foo" in result

    def test_invalid_regex(self):
        from codeagent.tools.code_tools import search_code
        result = search_code.invoke({"pattern": "[invalid"})
        assert "正则表达式错误" in result


# ── helpers ───────────────────────────────────────────────────────────────────

def _fake_settings(workspace: str = "."):
    s = MagicMock()
    s.WORKSPACE_DIR = workspace
    s.SHELL_SANDBOX = "subprocess"
    return s
