"""LLM 封装：验证 bind_tools 绑定 + 单例缓存。"""
from unittest.mock import MagicMock

from app import llm


def test_create_agent_llm_cached(monkeypatch):
    fake_bound = MagicMock()
    fake_chat = MagicMock()
    fake_chat.return_value.bind_tools.return_value = fake_bound

    monkeypatch.setattr(llm, "ChatOpenAI", fake_chat)
    monkeypatch.setattr(llm, "_llm", None)          # 清缓存，从零测

    a = llm.create_agent_llm()
    b = llm.create_agent_llm()

    assert a is b is fake_bound                     # 第二次走缓存，返回同一对象
    assert fake_chat.call_count == 1                # ChatOpenAI 只构造一次
    fake_chat.return_value.bind_tools.assert_called_once_with(llm.AGENT_TOOLS)