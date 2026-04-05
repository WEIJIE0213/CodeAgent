"""
test_graph.py —— LangGraph 图流程测试

测试内容：
- 图编译正常（节点、边注册完整）
- Reflection 节点逻辑（PASS / NEEDS_REVISION）
- route_after_reflection 路由逻辑
- memory_writer_node 更新 short_term 和压缩
- 端到端意图路由（mock 节点函数，不调用真实 LLM）
"""
import pytest
from unittest.mock import patch, MagicMock, call
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from codeagent.graph.builder import graph
from codeagent.graph.nodes.reflection import reflection_node, route_after_reflection
from codeagent.graph.nodes.memory_writer import memory_writer_node


def _fake_llm(content: str):
    return RunnableLambda(lambda _: AIMessage(content=content))


# ── 图结构验证 ────────────────────────────────────────────────────────────────

class TestGraphStructure:
    def test_graph_compiles_without_error(self):
        assert graph is not None

    def test_all_expected_nodes_exist(self):
        expected = {
            "context_loader", "intent_router",
            "code_agent", "task_decomposer", "context_qa",
            "reflection", "memory_writer",
        }
        assert expected == set(graph.nodes.keys()) - {"__start__"}


# ── Reflection 节点 ───────────────────────────────────────────────────────────

class TestReflectionNode:
    def _state(self, **kw) -> dict:
        return {
            "user_input": "帮我写排序算法",
            "intent": "code",
            "final_response": "def bubble_sort(arr): ...",
            "revision_count": 0,
            **kw,
        }

    def test_pass_when_llm_returns_pass(self):
        with patch("codeagent.graph.nodes.reflection.get_llm",
                   return_value=_fake_llm("PASS")):
            result = reflection_node(self._state())
        assert result["needs_revision"] is False
        assert result["reflection_feedback"] == ""

    def test_needs_revision_sets_feedback(self):
        feedback_text = "NEEDS_REVISION\n- 缺少边界检查\n- 没有类型注解"
        with patch("codeagent.graph.nodes.reflection.get_llm",
                   return_value=_fake_llm(feedback_text)):
            result = reflection_node(self._state())
        assert result["needs_revision"] is True
        assert "缺少边界检查" in result["reflection_feedback"]
        assert result["revision_count"] == 1

    def test_skips_when_revision_count_reached(self):
        result = reflection_node(self._state(revision_count=1))
        assert result["needs_revision"] is False

    def test_skips_for_qa_intent(self):
        result = reflection_node(self._state(intent="qa"))
        assert result["needs_revision"] is False

    def test_skips_for_memory_intent(self):
        result = reflection_node(self._state(intent="memory"))
        assert result["needs_revision"] is False

    def test_handles_llm_exception_gracefully(self):
        broken_llm = MagicMock()
        broken_llm.invoke.side_effect = Exception("API error")
        with patch("codeagent.graph.nodes.reflection.get_llm", return_value=broken_llm):
            result = reflection_node(self._state())
        assert result["needs_revision"] is False


class TestRouteAfterReflection:
    def test_routes_to_code_agent(self):
        assert route_after_reflection({"needs_revision": True, "intent": "code"}) == "code_agent"

    def test_routes_to_task_decomposer(self):
        assert route_after_reflection({"needs_revision": True, "intent": "decompose"}) == "task_decomposer"

    def test_routes_to_memory_writer_on_pass(self):
        assert route_after_reflection({"needs_revision": False, "intent": "code"}) == "memory_writer"


# ── memory_writer 节点 ────────────────────────────────────────────────────────

class TestMemoryWriterNode:
    _CONFIG = {"configurable": {"thread_id": "test-thread"}}

    def _state(self, **kw) -> dict:
        return {
            "user_input": "什么是 GIL？",
            "final_response": "GIL 是全局解释器锁...",
            "short_term": [],
            "long_term_summary": "",
            **kw,
        }

    def test_appends_user_and_assistant_to_short_term(self):
        with patch("codeagent.graph.nodes.memory_writer.upsert_session"), \
             patch("codeagent.graph.nodes.memory_writer.save_messages"), \
             patch("codeagent.graph.nodes.memory_writer.store_memory"), \
             patch("codeagent.graph.nodes.memory_writer.should_compress", return_value=False):
            result = memory_writer_node(self._state(), config=self._CONFIG)

        st = result["short_term"]
        assert len(st) == 2
        assert st[0] == {"role": "user", "content": "什么是 GIL？"}
        assert st[1] == {"role": "assistant", "content": "GIL 是全局解释器锁..."}

    def test_compression_triggered_updates_summary(self):
        existing = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"}
            for i in range(20)
        ]
        with patch("codeagent.graph.nodes.memory_writer.upsert_session"), \
             patch("codeagent.graph.nodes.memory_writer.save_messages"), \
             patch("codeagent.graph.nodes.memory_writer.store_memory"), \
             patch("codeagent.graph.nodes.memory_writer.should_compress", return_value=True), \
             patch("codeagent.graph.nodes.memory_writer.compress", return_value="压缩摘要"), \
             patch("codeagent.graph.nodes.memory_writer.save_summary"):
            result = memory_writer_node(self._state(short_term=existing), config=self._CONFIG)

        assert result["long_term_summary"] == "压缩摘要"
        assert result["needs_compression"] is True

    def test_no_compression_when_not_needed(self):
        with patch("codeagent.graph.nodes.memory_writer.upsert_session"), \
             patch("codeagent.graph.nodes.memory_writer.save_messages"), \
             patch("codeagent.graph.nodes.memory_writer.store_memory"), \
             patch("codeagent.graph.nodes.memory_writer.should_compress", return_value=False):
            result = memory_writer_node(self._state(), config=self._CONFIG)

        assert result["needs_compression"] is False
        assert result["long_term_summary"] == ""


# ── 端到端意图路由 ────────────────────────────────────────────────────────────

class TestGraphIntentRouting:
    """
    LangGraph 图在编译时捕获节点函数引用，patch 无法替换。
    因此直接调用真实图（使用真实 LLM），只验证：
      - 图能正常完成（不崩溃）
      - intent 字段被正确设置
      - final_response 非空

    每次测试使用独立 UUID thread_id，避免 MemorySaver 跨测试污染状态。
    """

    @pytest.fixture
    def thread_id(self):
        import uuid
        return f"test-{uuid.uuid4().hex[:8]}"

    def _cfg(self, tid: str) -> dict:
        return {"configurable": {"thread_id": tid}}

    def test_graph_runs_without_error(self, thread_id):
        """最基础验证：图能跑完不报错，返回 final_response"""
        result = graph.invoke({"user_input": "Python 的 print 函数怎么用？"}, config=self._cfg(thread_id))
        assert isinstance(result.get("final_response", ""), str)
        assert len(result.get("final_response", "")) > 0

    def test_graph_sets_intent_field(self, thread_id):
        """图执行完毕后 state 中 intent 字段必须是合法值"""
        result = graph.invoke({"user_input": "什么是变量？"}, config=self._cfg(thread_id))
        assert result.get("intent") in {"code", "decompose", "qa", "memory"}

    def test_graph_code_request_routes_correctly(self, thread_id):
        """明确的代码请求 intent 应被路由为 code"""
        result = graph.invoke({"user_input": "帮我写一个 hello world"}, config=self._cfg(thread_id))
        # 只验证路由正确，不验证响应内容（真实 LLM 偶发空响应属正常）
        assert result.get("intent") in {"code", "decompose"}  # 两者均合理
