"""pytest 全局配置。

惰性化之后，import 被测模块不再有连库 / 构造 LLM 的副作用，
因此这里不需要再 patch 连接入口——各测试按需显式 mock。
"""
import pytest
from unittest.mock import MagicMock

from config import session_id_var
from app.logger import get_logger


@pytest.fixture(scope="session", autouse=True)
def _setup_logging():
    get_logger()          # 幂等：初始化一次 logging
    yield


@pytest.fixture(scope="session", autouse=True)
def isolated_session():
    """给整个测试会话一个独立 session_id，避免污染限流计数。"""
    token = session_id_var.set("pytest_session")
    yield
    session_id_var.reset(token)


@pytest.fixture
def fake_ch():
    """一个假的 ClickHouse 连接：query()/command() 都返回 MagicMock。

    测试里按需覆盖返回值，例如：
        fake_ch.query.return_value.result_rows = [...]
    """
    return MagicMock()