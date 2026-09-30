"""数据分析 Agent 前端：聊天界面 + 审计面板（流式版）。"""
import json
import uuid


import pandas as pd
import streamlit as st
from datetime import datetime

from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings,SESSION_DIR
from app.agent import stream_agent
from langchain_core.messages import HumanMessage, AIMessage



logger = settings.setup_logging()


st.set_page_config(
    page_title="数据分析 Agent",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={}
)
st.title("📚 数据分析 Agent")


def to_messages(history_dict: list[dict]):
    """把 st.session_state.messages 的 dict 列表转成 LangChain 消息列表"""
    msgs = []
    for m in history_dict:
        if m["role"] == "user":
            msgs.append(HumanMessage(content=m["content"]))
        else:
            msgs.append(AIMessage(content=m["content"]))
    return msgs


def generate_session_name():
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

def save_session():
    """保存会话记录"""
    if st.session_state.session_name:
        session_data = {
            "session_name": st.session_state.session_name,
            "session_id": st.session_state.session_id,
            "messages": st.session_state.messages,
        }
        if not Path(SESSION_DIR).exists():
            Path(SESSION_DIR).mkdir()

        with open(SESSION_DIR / f"{st.session_state.session_name}.json","w" ,encoding="utf-8") as f:
            json.dump(session_data, f, ensure_ascii=False, indent=4)

def load_sessions():
    """加载所有会话列表"""
    sessions_list = []
    if Path(SESSION_DIR).exists():
        for file in Path(SESSION_DIR).glob("*.json"):
            sessions_list.append(file.name[:-5])

    sessions_list.reverse()
    logger.info(f"加载会话列表：{sessions_list}")
    return sessions_list

def load_session(session_name: str):
    """加载指定会话记录"""
    try:
        if Path(SESSION_DIR / f"{session_name}.json").exists():
            with open(SESSION_DIR / f"{session_name}.json", "r", encoding="utf-8") as f:
                session_data = json.load(f)
                st.session_state.messages = session_data["messages"]
                st.session_state.session_name = session_data["session_name"]
                st.session_state.session_id = session_data["session_id"]
        logger.info(f"加载会话：{session_name}")
    except Exception as e:
        logger.error(f"加载会话出错：{e}")

def delete_session(session_name):
    try:
        if Path(SESSION_DIR / f"{session_name}.json").exists():
            Path(SESSION_DIR / f"{session_name}.json").unlink()
            logger.info(f"删除会话：{session_name}")
            if st.session_state.session_name == session_name:
                st.session_state.messages = []
                st.session_state.session_name = generate_session_name()
                st.session_state.session_id = uuid.uuid4().hex
                logger.info(f"新建会话：{st.session_state.session_name}")

    except Exception as e:
        logger.error(f"删除会话出错：{e}")


# 初始化

if "messages" not in st.session_state:
    st.session_state.messages = []

if "session_name"  not in st.session_state:
    st.session_state.session_name = generate_session_name()

if "session_id" not in st.session_state:
    st.session_state.session_id = uuid.uuid4().hex

# 加载会话信息
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

with st.sidebar:
    st.header("数据分析 Agent")
    #创建一个新会话
    if st.button("新建会话", width="stretch", icon="✒️"):
        if st.session_state.messages:
            st.session_state.session_name = generate_session_name()
            st.session_state.messages = []
            st.session_state.session_id = uuid.uuid4().hex
            save_session()
            logger.info(f"新建会话：{st.session_state.session_name}")
            st.rerun()

    st.text("会话历史")
    #加载会话列表信息
    session_list = load_sessions()

    for session in session_list:
        col1, col2 = st.columns([4, 1])
        with col1:
            # 加载会话信息
            if st.button(session, width="stretch", icon="📄", key=f"load_{session}",
                         type="primary" if session == st.session_state.session_name else "secondary"):
                load_session(session)
                st.rerun()
        with col2:
            # 删除会话信息
            if st.button("", width="stretch", icon="❌", key=f"delete_{session}"):
                delete_session(session)
                st.rerun()

question = st.chat_input("问一个数据分析问题…")

if question:
    history = to_messages(st.session_state.messages)
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    answer = ""
    for chunk in stream_agent(history, question, session_id=st.session_state.session_id):
        for node, update in chunk.items():
            if node == "agent":
                msg = update["messages"][-1]
                if getattr(msg, "tool_calls", None):
                    # LLM 决定调用工具：展示工具名 + 参数
                    for tc in msg.tool_calls:
                        with st.chat_message("assistant"):
                            st.caption(
                                f"调用工具 {tc['name']}："
                                f"{json.dumps(tc['args'], ensure_ascii=False)}"
                            )
                elif msg.content:
                    # 最终回答
                    answer = msg.content
                    with st.chat_message("assistant"):
                        st.markdown(answer)
            elif node == "tools":
                # 工具执行结果（SQL 结果等），折叠起来避免刷屏
                for msg in update.get("messages", []):
                    with st.expander("查看工具返回", expanded=False):
                        st.code(msg.content)

    if not answer:
        st.warning("未获得有效回答。")
    else:
        st.session_state.messages.append({"role": "assistant", "content": answer})
    save_session()

