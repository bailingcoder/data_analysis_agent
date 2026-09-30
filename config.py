"""全局配置。

所有可调参数集中在这里，避免散落各处。
"""
from __future__ import annotations

import os
import yaml
import logging

from dataclasses import dataclass, field
from pathlib import Path
from logging.config import dictConfig

from dotenv import load_dotenv

# 请求级上下文：Agent 入口 set，回调里 get（跨函数透传 session_id，不污染签名）
import contextvars
session_id_var = contextvars.ContextVar("session_id", default="default")

# 项目根目录 = 本文件所在目录
PROJECT_ROOT = Path(__file__).resolve().parent
SESSION_DIR = PROJECT_ROOT / "sessions"


load_dotenv(PROJECT_ROOT / ".env")


_configured = False


@dataclass(frozen=True)
class Settings:
    # ---- LLM ----
    deepseek_api_key: str = field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", ""))
    deepseek_base_url: str = field(default_factory=lambda: os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
    deepseek_model: str = field(default_factory=lambda: os.getenv("DEEPSEEK_MODEL", "deepseek-chat"))
    temperature: float = 0.0

    # ---- MySQL 业务库（OLTP，规范化）----
    mysql_host: str = field(default_factory=lambda: os.getenv("MYSQL_HOST", "127.0.0.1"))
    mysql_port: int = field(default_factory=lambda: int(os.getenv("MYSQL_PORT", "3306")))
    mysql_user: str = field(default_factory=lambda: os.getenv("MYSQL_USER", "root"))
    mysql_password: str = field(default_factory=lambda: os.getenv("MYSQL_PASSWORD", ""))
    mysql_database: str = field(default_factory=lambda: os.getenv("MYSQL_DATABASE", "ecommerce"))

    # ---- ClickHouse 数据仓库（OLAP，分层）----
    clickhouse_host: str = field(default_factory=lambda: os.getenv("CLICKHOUSE_HOST", "127.0.0.1"))
    clickhouse_http_port: int = field(default_factory=lambda: int(os.getenv("CLICKHOUSE_HTTP_PORT", "8123")))
    clickhouse_native_port: int = field(default_factory=lambda: int(os.getenv("CLICKHOUSE_NATIVE_PORT", "9000")))
    clickhouse_user: str = field(default_factory=lambda: os.getenv("CLICKHOUSE_USER", "default"))
    clickhouse_password: str = field(default_factory=lambda: os.getenv("CLICKHOUSE_PASSWORD", "clickhouse123"))
    clickhouse_database: str = field(default_factory=lambda: os.getenv("CLICKHOUSE_DATABASE", "analytics"))

    # ---- 中间件参数 ----
    # execute_sql 结果集最大行数，超过会被截断
    max_result_rows: int = 100
    # execute_python 沙箱最大执行时间（秒）
    python_timeout_seconds: int = 10
    # 单个会话允许的最大 SQL 查询次数
    max_queries_per_session: int = 10
    # 脱敏时保留的字符数（如邮箱 username 前 2 位）
    mask_keep_prefix: int = 2

    # ---- 审计 ----
    audit_log_path: Path = field(default_factory=lambda: PROJECT_ROOT / "logs" / "audit.jsonl")

    def setup_logging(self,name:str="data_analysis_agent"):
        """从 logging.yaml 加载日志配置（幂等：重复调用只初始化一次）。"""
        global _configured

        if not _configured:
            with open(PROJECT_ROOT / "logging.yaml", "r") as f:
                logging_config = yaml.safe_load(f).get("logging", {})

            for handler in logging_config.get("handlers", {}).values():
                if "filename" in handler:
                    file_path = PROJECT_ROOT / handler["filename"]
                    file_path.parent.mkdir(parents=True, exist_ok=True)  # 关键：自动建 logs/ 目录
                    handler["filename"] = str(file_path)
            dictConfig(logging_config)
            _configured = True
        return logging.getLogger(name)

settings = Settings()