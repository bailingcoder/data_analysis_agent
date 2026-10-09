import logging
import yaml
from logging.config import dictConfig
from config import PROJECT_ROOT

with open(PROJECT_ROOT / "logging.yaml", "r",encoding="utf-8") as f:
    logging_config = yaml.safe_load(f).get("logging",{})

for handler in logging_config.get("handlers",{}).values():
    if "filename" in handler:
        file_path = PROJECT_ROOT / handler["filename"]
        file_path.parent.mkdir(parents=True, exist_ok=True)  # 关键：自动建 logs/ 目录
        handler["filename"] = str(file_path)
dictConfig(logging_config)

def get_logger(name: str = "data_analysis_agent")->logging.Logger:
    return logging.getLogger(name)