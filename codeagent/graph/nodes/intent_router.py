"""
intent_router —— 意图路由节点

将用户输入分类为：code | decompose | qa | memory
使用 few-shot prompt 提高分类准确性。
"""
from langchain_core.prompts import ChatPromptTemplate
from codeagent.graph.state import AgentState
from codeagent.config import get_llm

_INTENT_SYSTEM = """\
你是一个编程助手的意图分类器。将用户输入分类为以下四类之一，只输出类别名称，不要其他内容。

类别定义：
- code      ：用户想生成、解释、调试、重构具体代码片段，或需要读取/操作文件
- decompose ：用户有复杂的编程任务（需要多步骤才能完成的项目/功能）
- qa        ：用户在问编程概念、原理、工具用法、项目分析或寻求技术建议
- memory    ：用户明确询问"你之前帮我做过什么"、"我们之前聊了什么"等对话历史，或要求清空记忆

重要规则：
- "查看项目/分析项目/项目功能" → code（需要读取文件）
- "分析/解释/介绍某个概念" → qa
- 只有用户明确问历史对话记录时才选 memory

示例：
用户：帮我写一个二分查找 → code
用户：查看一下我的项目，分析功能 → code
用户：帮我从零搭建一个 FastAPI + SQLAlchemy 的用户管理系统 → decompose
用户：什么是装饰器？Python 的 GIL 是什么？ → qa
用户：你之前帮我写过什么？上次我们聊了什么？ → memory
用户：解释一下这段代码 → code
用户：帮我实现一个完整的博客系统 → decompose
"""

_PROMPT = ChatPromptTemplate.from_messages([
    ("system", _INTENT_SYSTEM),
    ("human", "{user_input}"),
])

_VALID_INTENTS = {"code", "decompose", "qa", "memory"}


def intent_router_node(state: AgentState) -> dict:
    llm = get_llm()
    chain = _PROMPT | llm
    result = chain.invoke({"user_input": state["user_input"]})
    content = result.content.strip().lower()

    # 健壮解析：从响应中找到第一个合法意图词
    intent = "qa"  # 默认兜底
    for token in content.split():
        if token in _VALID_INTENTS:
            intent = token
            break

    return {"intent": intent}


def route_by_intent(state: AgentState) -> str:
    """条件边路由函数，返回下一个节点名称"""
    intent = state.get("intent", "qa")
    if intent == "code":
        return "code_agent"
    if intent == "decompose":
        return "task_decomposer"
    return "context_qa"
