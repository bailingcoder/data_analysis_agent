import pytest

from config import  session_id_var
from app.logger import get_logger

@pytest.fixture(scope="session", autouse=True)
def _setup_logging():
    get_logger()          # 幂等，整个测试会话只初始化一次
    yield


@pytest.fixture(scope="session", autouse=True)
def isolated_session():
    """给测试一个独立 session_id，避免污染限流计数。"""
    token = session_id_var.set("pytest_session")
    yield
    session_id_var.reset(token)