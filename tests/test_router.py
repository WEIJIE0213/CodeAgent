"""
test_router.py —— 意图路由节点测试

测试内容：
- route_by_intent() 条件边路由函数
- intent_router_node() 节点（用 RunnableLambda 模拟 LLM，不调用真实 API）
"""
import pytest
from unittest.mock import patch
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from codeagent.graph.nodes.intent_router import route_by_intent, intent_router_node


def _fake_llm(content: str):
    """返回固定内容的 fake LLM（RunnableLambda，可正确接入 LangChain 链）"""
    return RunnableLambda(lambda _: AIMessage(content=content))


# ── route_by_intent ───────────────────────────────────────────────────────────

class TestRouteByIntent:
    def test_code_routes_to_code_agent(self):
        assert route_by_intent({"intent": "code"}) == "code_agent"

    def test_decompose_routes_to_task_decomposer(self):
        assert route_by_intent({"intent": "decompose"}) == "task_decomposer"

    def test_qa_routes_to_context_qa(self):
        assert route_by_intent({"intent": "qa"}) == "context_qa"

    def test_memory_routes_to_context_qa(self):
        assert route_by_intent({"intent": "memory"}) == "context_qa"

    def test_unknown_intent_defaults_to_context_qa(self):
        assert route_by_intent({"intent": "unknown"}) == "context_qa"

    def test_missing_intent_defaults_to_context_qa(self):
        assert route_by_intent({}) == "context_qa"


# ── intent_router_node ────────────────────────────────────────────────────────

class TestIntentRouterNode:
    def _run(self, llm_response: str, user_input: str = "test") -> dict:
        with patch("codeagent.graph.nodes.intent_router.get_llm",
                   return_value=_fake_llm(llm_response)):
            return intent_router_node({"user_input": user_input})

    def test_returns_code_intent(self):
        assert self._run("code")["intent"] == "code"

    def test_returns_decompose_intent(self):
        assert self._run("decompose")["intent"] == "decompose"

    def test_returns_qa_intent(self):
        assert self._run("qa")["intent"] == "qa"

    def test_returns_memory_intent(self):
        assert self._run("memory")["intent"] == "memory"

    def test_extracts_intent_from_noisy_response(self):
        # LLM 可能返回带多余文字的响应
        assert self._run("根据分析，这是一个 code 类型的请求")["intent"] == "code"

    def test_unknown_response_falls_back_to_qa(self):
        assert self._run("我不确定")["intent"] == "qa"

    def test_case_insensitive(self):
        assert self._run("CODE")["intent"] == "code"
