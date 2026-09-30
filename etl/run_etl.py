"""ETL 编排入口：python -m etl.run_etl"""
import logging

from config import settings
from etl.extract import extract_mysql_to_ods
from etl.transform import build_dwd, build_dws, build_ads
from etl.metadata import load_metadata

logger = logging.getLogger("data_analysis_agent.etl")


def main() -> None:
    settings.setup_logging()          # 只初始化一次（幂等）
    logger.info("ETL 开始")
    extract_mysql_to_ods()
    build_dwd()
    build_dws()
    build_ads()
    load_metadata()
    logger.info("ETL 完成")


if __name__ == "__main__":
    main()