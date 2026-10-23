"""回调审计测试：落盘内容、耗时、脱敏标记、session_id 传播。"""
import json
from types import SimpleNamespace

from app.callbacks import AuditCallbackHandler, _truncate, _extract_output


# ---------- 纯函数 ----------
def test_truncate_short():
    assert _truncate("hello") == "hello"

def test_truncate_long():
    out = _truncate("x" * 600, max_chars=10)
    assert out.startswith("x" * 10)
    assert out.endswith("…(截断)")

def test_extract_output_message_type():
    gen = SimpleNamespace(message=SimpleNamespace(content="答案A"), text=None)
    response = SimpleNamespace(generations=[[gen]])
    assert _extract_output(response) == "答案A"

def test_extract_output_text_type():
    gen = SimpleNamespace(message=None, text="答案B")
    response = SimpleNamespace(generations=[[gen]])
    assert _extract_output(response) == "答案B"


# ---------- 回调落盘 ----------
class TestAuditCallbackHandler:
    def test_llm_lifecycle(self, tmp_path):
        log = tmp_path / "audit.jsonl"
        cb = AuditCallbackHandler(log_path=log)

        cb.on_llm_start({"kwargs": {"model": "deepseek-chat"}}, ["你好"], run_id="r1")
        cb.on_llm_end(
            SimpleNamespace(
                generations=[[SimpleNamespace(message=SimpleNamespace(content="答案"), text=None)]],
                llm_output={"token_usage": {"total_tokens": 42}},
            ),
            run_id="r1",
        )

        start, end = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()]
        assert start["event"] == "llm_start"
        assert start["model"] == "deepseek-chat"
        assert start["prompt"] == "你好"
        assert end["event"] == "llm_end"
        assert end["output"] == "答案"
        assert end["token_usage"] == {"total_tokens": 42}
        assert isinstance(end["duration_ms"], (int, float))

    def test_tool_intercepted_marked(self, tmp_path):
        log = tmp_path / "audit.jsonl"
        cb = AuditCallbackHandler(log_path=log)

        cb.on_tool_start({"name": "execute_sql"}, '{"query": "SELECT 1"}', run_id="t1")
        cb.on_tool_end("[已拦截] 只允许 SELECT", run_id="t1")

        start, end = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()]
        assert start["tool_name"] == "execute_sql"
        assert end["intercepted"] is True
        assert end["output"].startswith("[已拦截]")

    def test_tool_error(self, tmp_path):
        log = tmp_path / "audit.jsonl"
        cb = AuditCallbackHandler(log_path=log)

        cb.on_tool_start({"name": "execute_sql"}, "x", run_id="e1")
        cb.on_tool_error(RuntimeError("boom"), run_id="e1")

        lines = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines()]
        assert lines[-1]["event"] == "tool_error"
        assert "boom" in lines[-1]["error"]

    def test_session_id_recorded(self, tmp_path):
        log = tmp_path / "audit.jsonl"
        cb = AuditCallbackHandler(log_path=log)
        cb.on_llm_start({"kwargs": {}}, ["x"], run_id="s1")

        rec = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
        assert rec["session_id"] == "pytest_session"