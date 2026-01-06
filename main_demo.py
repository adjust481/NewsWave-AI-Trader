# main_demo.py
import sys
import os

# ---------------------------------------------------------
# 💡 路径黑魔法：
# 这一步是为了确保 Python 能找到 'infra' 文件夹。
# 它把当前脚本所在的目录加入到了 Python 的搜索路径中。
# ---------------------------------------------------------
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from infra.logging_utils import logger

def main():
    logger.info("🚀 AI Quant Router project initialized successfully!")
    logger.info("✅ 阶段 0 目标达成：骨架已建立，日志系统正常。")
    logger.info("等待加载策略引擎...")

if __name__ == "__main__":
    main()
