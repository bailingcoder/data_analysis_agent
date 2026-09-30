"""LLM 封装：把 DeepSeek 包装成 LangGraph 认识的 chat model，并绑定工具。

本质两件事：
  ① 用 ChatOpenAI 指向 DeepSeek 的 OpenAI 兼容地址（复用成熟工具调用协议，只改地址和 key）
  ② bind_tools 把三个工具的签名 + docstring 交给模型，让它具备「自主决定调哪个工具」的能力
"""
from langchain_openai import ChatOpenAI

from config import settings
from app.tools import get_schema, execute_sql, execute_python

# Agent 可用的全部工具（后面 agent.py 也会引用这份清单）
AGENT_TOOLS = [get_schema, execute_sql, execute_python]

_llm = None

def create_agent_llm():
    """创建绑定了工具的 DeepSeek 模型。

    返回的是 bind_tools 的结果（一个 Runnable），可直接交给 LangGraph 当节点用。
    温度读 settings.temperature（0.0）：数据分析要确定性，不要即兴。
    """
    global _llm

    if _llm is  None:
        _llm = ChatOpenAI(
            model=settings.deepseek_model,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            temperature=settings.temperature,
            timeout=60,        # 网络抖动时别无限挂起
            max_retries=2,
        ).bind_tools(AGENT_TOOLS)
    return _llm