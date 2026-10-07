"""
日志入口
"""
from logging import Logger
from logging.handlers import RotatingFileHandler


def get_logger(name: str, filename: str) -> Logger:
    logger = Logger(name)
    handler = RotatingFileHandler(filename, maxBytes=64*1024*1024) # 64KB
    logger.addHandler(handler)

    return logger
