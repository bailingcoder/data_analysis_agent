"""Agent 编排：LangGraph 状态图，把 llm + tools + middleware + callbacks 拼成完整 Agent。

图结构（ReAct 循环）：
  START -> agent -> (有 tool_calls? -> tools -> agent | 无 -> END)
"""

from __future__ import annotations

from typing import Annotated
from langchain_core.messages import AnyMessage,HumanMessage,SystemMessage
from langgraph.graph.state import StateGraph,START,END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from pydantic import BaseModel, Field

from app.callbacks import AuditCallbackHandler
from config import session_id_var
from app.llm import create_agent_llm,AGENT_TOOLS
from app.prompts import SYSTEM_PROMPT

class AgentState(BaseModel):
    messages:Annotated[list[AnyMessage],add_messages] = Field(default_factory=list)

_llm = create_agent_llm()

def _agent_node(state:AgentState):
    """agent 节点：把对话历史喂给 LLM，返回它的决策（可能带 tool_calls）。"""
    resp = _llm.invoke(state.messages)
    return {"messages":[resp]}

def _build_messages(history, question):
    return [SystemMessage(content=SYSTEM_PROMPT)] + history + [HumanMessage(content=question)]

_tool_node = ToolNode(AGENT_TOOLS)

def build_agent():
    graph = StateGraph(AgentState)
    graph.add_node("agent",_agent_node)
    graph.add_node("tools",_tool_node)

    graph.add_edge(START,"agent")
    graph.add_conditional_edges(
        "agent",
        tools_condition,
        {
            "tools":"tools",
            END:END
        }
    )
    graph.add_edge("tools","agent")

    return graph.compile()

def run_agent(history:list[AnyMessage], question:str, session_id:str):
    session_id_var.set(session_id)          # 钩子1：给回调设置 session_id

    callbacks = AuditCallbackHandler()
    agent = build_agent()

    messages = _build_messages(history, question)
    result = agent.invoke(
        {"messages":messages},
        config = {"callbacks":[callbacks]}
    )
    return result["messages"][-1].content

def stream_agent(history, question:str, session_id:str):
    """流式版：按节点逐段产出，前端可实时展示中间过程。"""
    session_id_var.set(session_id)

    callbacks = AuditCallbackHandler()
    agent = build_agent()

    messages = _build_messages(history, question)
    return agent.stream(
        {"messages": messages},
        config={"callbacks": [callbacks]},
        stream_mode="updates",
    )