"""回调：审计日志。把 Agent 每一步关键操作落盘为 JSONL，作为可追溯的黑匣子。

与 logging 的区别：logging 给开发者排障，审计给行为留痕（谁、调了什么、传了什么、结果如何）。
一条记录一行 JSON，可被 grep / jq / 审计面板直接查询。
"""

import json
import threading
import time

from langchain_core.callbacks import BaseCallbackHandler

from config import settings,session_id_var

# 记录里 input/output 最大字符数，防止把大结果集整个写进审计
OUTPUT_MAX_CHARS = 500

_write_lock = threading.Lock()


def _truncate(s, max_chars=OUTPUT_MAX_CHARS):
    s = str(s)
    return s if len(s) <= max_chars else s[:max_chars] + "…(截断)"


class AuditCallbackHandler(BaseCallbackHandler):
    """把 LLM / 工具调用落盘为 audit.jsonl。"""

    def __init__(self, log_path=None):
        self.log_path = log_path or settings.audit_log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._starts = {}        # run_id -> 起始时刻（秒），用于算耗时
        self._tool_names = {}    # run_id -> 工具名（start 存，end 取）

    # ---- 落盘 ----
    def _write(self, record: dict) -> None:
        line = json.dumps(record, ensure_ascii=False, default=str)
        with _write_lock:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

    def _base(self, event: str, ts=None) -> dict:
        if ts is None:
            ts = time.time()
        return {
            "timestamp": ts,  # 用调用方传入的同一瞬间
            "session_id": session_id_var.get(),
            "event": event,
        }

    def _begin(self, run_id):
        """事件起点：只取一次时间，同时写入 _starts 并返回。"""
        now = time.time()
        self._starts[run_id] = now
        return now

    def _end(self, run_id):
        """事件终点：只取一次时间，并返回 (耗时ms, 终点时刻)。"""
        start = self._starts.pop(run_id, None)
        now = time.time()
        if start is None:
            return None, now
        return round((now - start) * 1000, 1), now

    def on_llm_start(self, serialized, prompts, **kwargs):
        rid = kwargs.get("run_id")
        now = self._begin(rid)  # 取一次，起点唯一
        rec = self._base("llm_start", ts=now)
        rec["run_id"] = rid
        rec["model"] = (serialized.get("kwargs") or {} ).get("model", "unknown")
        rec["prompt"] = _truncate(prompts[0] if prompts else "")
        self._write(rec)

    def on_llm_end(self, response, **kwargs):
        rid = kwargs.get("run_id")
        duration_ms, now = self._end(rid)  # 取一次，终点唯一
        rec = self._base("llm_end", ts=now)
        rec["run_id"] = rid
        rec["duration_ms"] = duration_ms
        self._write(rec)

    def on_llm_error(self, error, **kwargs):
        rid = kwargs.get("run_id")
        duration_ms,now = self._end(rid)  # 取一次，终点唯一
        rec = self._base("llm_error", ts=now)
        rec["error"] = str(error)
        self._write(rec)

    # ---- 工具生命周期 ----
    def on_tool_start(self, serialized, input_str, **kwargs):
        rid = kwargs.get("run_id")
        name = serialized.get("name", "unknown")
        now = self._begin(rid)
        self._tool_names[rid] = name
        rec = self._base("tool_start", ts=now)
        rec["run_id"] = rid
        rec["tool_name"] = name
        rec["tool_input"] = _truncate(input_str)
        self._write(rec)

    def on_tool_end(self, output, **kwargs):
        rid = kwargs.get("run_id")
        duration_ms, now = self._end(rid)  # 取一次，终点唯一
        rec = self._base("tool_end", ts=now)
        rec["run_id"] = rid
        rec["tool_name"] = self._tool_names.pop(rid, "unknown")
        rec["duration_ms"] = duration_ms
        out_str = str(output)
        rec["output"] = _truncate(out_str)
        rec["intercepted"] = out_str.startswith("[已拦截]")
        self._write(rec)

    def on_tool_error(self, error, **kwargs):
        rid = kwargs.get("run_id")
        duration_ms, now = self._end(rid)  # 取一次，终点唯一
        rec = self._base("tool_error", ts=now)
        rec["run_id"] = rid
        rec["tool_name"] = self._tool_names.pop(rid, "unknown")
        rec["duration_ms"] = duration_ms
        rec["error"] = str(error)
        self._write(rec)