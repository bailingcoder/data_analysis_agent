import pytest

from app.agent import run_agent

pytestmark = pytest.mark.integration


def test_run_agent_returns_answer():
    answer = run_agent([], "哪个城市的销售额最高？", session_id="test_agent_session")
    assert isinstance(answer, str)
    assert answer.strip(), "回答不应为空"