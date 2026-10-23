import os
from unittest.mock import MagicMock, patch
import pytest

from config import session_id_var
from app.logger import get_logger


# —— ① 模块级 start：抢在 test 模块 import（收集阶段）之前生效 ——
_started = []                                     # 记录已启动的 patcher
if os.getenv("USE_REAL_DB") != "1":
    for target in ("clickhouse_connect.get_client", "redis.Redis"):
        p = patch(target, return_value=MagicMock())
        p.start()
        _started.append(p)


# —— ② session 结束 stop：和 isolated_session 的 reset 保持对称 ——
@pytest.fixture(scope="session", autouse=True)
def _cleanup_connection_mocks():
    yield
    for p in _started:
        p.stop()


@pytest.fixture(scope="session", autouse=True)
def _setup_logging():
    get_logger()
    yield


@pytest.fixture(scope="session", autouse=True)
def isolated_session():
    token = session_id_var.set("pytest_session")
    yield
    session_id_var.reset(token)


@pytest.fixture
def fake_ch():
    return MagicMock()