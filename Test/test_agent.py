"""Agent 编排：图结构、节点、消息构建（单测，mock LLM 与图）。"""
import pytest
from unittest.mock import MagicMock

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from app import agent
from app.agent import AgentState, _build_messages, build_agent


def test_build_messages_order():
    history = [HumanMessage(content="hi"), AIMessage(content="hello")]
    msgs = _build_messages(history, "问题")

    assert isinstance(msgs[0], SystemMessage)
    assert msgs[1] is history[0]
    assert msgs[2] is history[1]
    assert msgs[-1] == HumanMessage(content="问题")


def test_agent_node_returns_llm_result(monkeypatch):
    fake_resp = AIMessage(content="回答")
    fake_llm = MagicMock(invoke=MagicMock(return_value=fake_resp))
    monkeypatch.setattr(agent, "_llm", fake_llm)

    result = agent._agent_node(AgentState(messages=[]))

    assert result == {"messages": [fake_resp]}
    fake_llm.invoke.assert_called_once_with([])


def test_build_agent_has_expected_nodes():
    graph = build_agent()
    nodes = set(graph.get_graph().nodes)
    assert {"agent", "tools"} <= nodes


def test_run_agent(monkeypatch):
    fake_graph = MagicMock()
    fake_graph.invoke.return_value = {"messages": [AIMessage(content="最终答案")]}
    monkeypatch.setattr(agent, "build_agent", lambda: fake_graph)
    monkeypatch.setattr(agent, "AuditCallbackHandler", MagicMock)

    answer = agent.run_agent([], "哪个城市最高", session_id="s1")

    assert answer == "最终答案"
    _, kwargs = fake_graph.invoke.call_args
    assert kwargs["config"]["callbacks"]              # 传入了审计回调


def test_stream_agent_yields_chunks(monkeypatch):
    fake_graph = MagicMock()
    fake_graph.stream.return_value = iter(
        [{"agent": {"messages": [AIMessage(content="流式")]}}]
    )
    monkeypatch.setattr(agent, "build_agent", lambda: fake_graph)
    monkeypatch.setattr(agent, "AuditCallbackHandler", MagicMock)

    chunks = list(agent.stream_agent([], "问题", session_id="s2"))

    assert chunks
    fake_graph.stream.assert_called_once()


# ---------- 端到端（真实 LLM + DB，默认跳过） ----------
@pytest.mark.integration
def test_run_agent_end_to_end():
    answer = agent.run_agent([], "哪个城市的销售额最高？", session_id="test_agent_session")
    assert isinstance(answer, str)
    assert answer.strip()