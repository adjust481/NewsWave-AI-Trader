# infra/logging_utils.py
import logging
import sys

def setup_logger(name: str = "AI_Router"):
    """
    配置并返回一个标准的 Logger。
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # 避免重复打印日志 (如果 logger 已经有 handler 了，就不加了)
    if not logger.handlers:
        # 创建控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)

        # 设置日志格式：时间 - 级别 - 消息
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        console_handler.setFormatter(formatter)

        # 给 logger 装上处理器
        logger.addHandler(console_handler)

    return logger

# 直接初始化一个单例 logger 供外部使用
logger = setup_logger()
