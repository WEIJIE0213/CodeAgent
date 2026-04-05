"""
test_memory.py —— 记忆系统测试

测试内容：
- short_term: format_history(), count_rounds()
- compressor: should_compress(), split_for_compression()
- long_term: SQLite CRUD（使用临时数据库）
"""
import pytest
from unittest.mock import patch

from codeagent.memory.short_term import format_history, count_rounds
from codeagent.memory.compressor import should_compress, split_for_compression


# ── short_term ────────────────────────────────────────────────────────────────

class TestFormatHistory:
    def test_empty_history(self):
        result = format_history([])
        assert "无历史记录" in result

    def test_single_round(self):
        history = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！有什么可以帮你的？"},
        ]
        result = format_history(history)
        assert "轮 1" in result
        assert "你好" in result

    def test_truncates_long_messages(self):
        long_msg = "x" * 200
        history = [
            {"role": "user", "content": long_msg},
            {"role": "assistant", "content": long_msg},
        ]
        result = format_history(history)
        assert "..." in result

    def test_multiple_rounds(self):
        history = []
        for i in range(3):
            history.append({"role": "user", "content": f"问题{i}"})
            history.append({"role": "assistant", "content": f"答案{i}"})
        result = format_history(history)
        assert "轮 1" in result
        assert "轮 2" in result
        assert "轮 3" in result

    def test_odd_length_history_does_not_crash(self):
        # 奇数条消息（只有用户问题，没有助手回答），不应崩溃
        history = [{"role": "user", "content": "只有问题"}]
        result = format_history(history)  # 不崩溃即可，返回空字符串属于正常行为
        assert isinstance(result, str)


class TestCountRounds:
    def test_empty(self):
        assert count_rounds([]) == 0

    def test_one_round(self):
        assert count_rounds([
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "a"},
        ]) == 1

    def test_three_rounds(self):
        msgs = []
        for _ in range(3):
            msgs += [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
        assert count_rounds(msgs) == 3


# ── compressor ────────────────────────────────────────────────────────────────

class TestShouldCompress:
    def _make_msgs(self, n_rounds: int) -> list:
        msgs = []
        for _ in range(n_rounds):
            msgs += [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
        return msgs

    def test_below_threshold(self):
        msgs = self._make_msgs(9)  # 18 条，WINDOW_SIZE=10 阈值 20
        with patch("codeagent.memory.compressor.settings") as s:
            s.WINDOW_SIZE = 10
            assert should_compress(msgs) is False

    def test_above_threshold(self):
        msgs = self._make_msgs(11)  # 22 条
        with patch("codeagent.memory.compressor.settings") as s:
            s.WINDOW_SIZE = 10
            assert should_compress(msgs) is True

    def test_exactly_at_threshold_not_triggered(self):
        msgs = self._make_msgs(10)  # 20 条，不超过
        with patch("codeagent.memory.compressor.settings") as s:
            s.WINDOW_SIZE = 10
            assert should_compress(msgs) is False


class TestSplitForCompression:
    def _make_msgs(self, n: int) -> list:
        return [{"role": "user" if i % 2 == 0 else "assistant", "content": f"msg{i}"}
                for i in range(n)]

    def test_short_history_not_split(self):
        msgs = self._make_msgs(4)  # <= 6（_ANCHOR_MESSAGES）
        old, recent = split_for_compression(msgs)
        assert old == []
        assert recent == msgs

    def test_long_history_split_correctly(self):
        msgs = self._make_msgs(10)
        old, recent = split_for_compression(msgs)
        assert len(recent) == 6
        assert len(old) == 4
        assert old + recent == msgs

    def test_exact_anchor_size_not_split(self):
        msgs = self._make_msgs(6)
        old, recent = split_for_compression(msgs)
        assert old == []
        assert recent == msgs


# ── long_term SQLite ──────────────────────────────────────────────────────────

class TestLongTermSQLite:
    """使用临时数据库，monkeypatch settings.DB_URL 后再 init_db"""

    @pytest.fixture(autouse=True)
    def _setup_db(self, tmp_path, monkeypatch):
        db_file = tmp_path / "test.db"
        db_url = f"sqlite:///{db_file}"
        import codeagent.memory.long_term as lt
        monkeypatch.setattr(lt.settings, "DB_URL", db_url)
        lt.init_db()

    def test_init_db_idempotent(self):
        from codeagent.memory.long_term import init_db
        init_db()
        init_db()  # 多次调用不应报错

    def test_upsert_session_twice_no_error(self):
        from codeagent.memory.long_term import upsert_session
        upsert_session("thread-001")
        upsert_session("thread-001")

    def test_save_and_retrieve_messages(self):
        from codeagent.memory.long_term import upsert_session, save_messages, get_recent_messages
        upsert_session("thread-002")
        save_messages("thread-002", "用户问题", "助手回答")

        msgs = get_recent_messages("thread-002")
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "用户问题"
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["content"] == "助手回答"

    def test_get_messages_empty_thread(self):
        from codeagent.memory.long_term import get_recent_messages
        assert get_recent_messages("nonexistent-thread") == []

    def test_save_and_get_latest_summary(self):
        from codeagent.memory.long_term import upsert_session, save_summary, get_latest_summary
        upsert_session("thread-003")
        save_summary("thread-003", "第一条摘要")
        save_summary("thread-003", "最新摘要")
        assert get_latest_summary("thread-003") == "最新摘要"

    def test_get_summary_nonexistent_returns_none(self):
        from codeagent.memory.long_term import get_latest_summary
        assert get_latest_summary("no-such-thread") is None

    def test_get_messages_respects_limit(self):
        from codeagent.memory.long_term import upsert_session, save_messages, get_recent_messages
        upsert_session("thread-004")
        for i in range(15):
            save_messages("thread-004", f"q{i}", f"a{i}")
        msgs = get_recent_messages("thread-004", limit=10)
        assert len(msgs) == 10
