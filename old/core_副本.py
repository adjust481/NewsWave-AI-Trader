import asyncio
import random
import time
import logging
import os
import json
import csv
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from enum import Enum
from web3 import Web3
from web3.exceptions import Web3Exception


# ========== 网络请求工具 ==========
def create_robust_session(
    retries: int = 3,
    backoff_factor: float = 1.0,
    status_forcelist: tuple = (500, 502, 503, 504),
    timeout: int = 15
) -> requests.Session:
    """
    创建带有自动重试机制的 requests Session

    Args:
        retries: 最大重试次数
        backoff_factor: 重试间隔因子 (1s, 2s, 4s...)
        status_forcelist: 需要重试的 HTTP 状态码
        timeout: 默认超时时间

    Returns:
        配置好的 Session 对象
    """
    session = requests.Session()

    retry_strategy = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=["GET", "POST"],  # 允许重试的方法
        raise_on_status=False  # 不抛出状态码异常，让调用者处理
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    session.headers.update({
        'User-Agent': 'ArbitrageBot/6.0',
        'Accept': 'application/json'
    })

    return session

# ========== 导入基础设施模块 ==========
from infra.logging import logger
from infra.risk import RiskManager
from infra.math_utils import SmartTrader, FeeCalculator


# ========== 风险管理器 ==========
# RiskManager 已移至 infra/risk.py

# ========== Web3 钱包管理器 ==========
class WalletManager:
    """
    Web3 钱包管理器 - 连接 Polygon 网络并查询余额

    支持:
    - MATIC (原生代币) 余额查询
    - USDC.e (Bridged USDC) 余额查询
    """

    # Polygon USDC.e 合约地址 (Bridged USDC from Ethereum)
    USDC_CONTRACT_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"

    # 最小 ABI - 仅包含 balanceOf 和 decimals 函数
    MINIMAL_ERC20_ABI = [
        {
            "constant": True,
            "inputs": [{"name": "_owner", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"name": "balance", "type": "uint256"}],
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [],
            "name": "decimals",
            "outputs": [{"name": "", "type": "uint8"}],
            "type": "function"
        }
    ]

    # 默认 Polygon RPC
    DEFAULT_RPC = "https://polygon-rpc.com"

    def __init__(self, rpc_url: str = None):
        """
        初始化 WalletManager

        Args:
            rpc_url: Polygon RPC URL, 默认使用 https://polygon-rpc.com
        """
        # 支持多种环境变量名称
        self.rpc_url = rpc_url or os.getenv("POLYGON_RPC") or os.getenv("POLYGON_RPC_URL", self.DEFAULT_RPC)
        self.w3: Optional[Web3] = None
        self.usdc_contract = None
        self._connected = False

    def connect(self) -> bool:
        """
        连接到 Polygon 网络

        Returns:
            bool: 连接是否成功
        """
        try:
            self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))

            if self.w3.is_connected():
                # 初始化 USDC 合约实例
                checksum_address = Web3.to_checksum_address(self.USDC_CONTRACT_ADDRESS)
                self.usdc_contract = self.w3.eth.contract(
                    address=checksum_address,
                    abi=self.MINIMAL_ERC20_ABI
                )
                self._connected = True
                logger.info(f"✅ 已连接到 Polygon 网络: {self.rpc_url}")
                return True
            else:
                logger.error("❌ 无法连接到 Polygon 网络")
                return False

        except Web3Exception as e:
            logger.error(f"❌ Web3 连接错误: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ 连接失败: {e}")
            return False

    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._connected and self.w3 is not None and self.w3.is_connected()

    def get_current_block(self) -> Optional[int]:
        """
        获取当前区块号

        Returns:
            int: 当前区块号, 失败返回 None
        """
        if not self.is_connected():
            logger.warning("未连接到网络")
            return None

        try:
            return self.w3.eth.block_number
        except Exception as e:
            logger.error(f"获取区块号失败: {e}")
            return None

    def get_balance(self, address: str) -> Dict[str, float]:
        """
        获取指定地址的 MATIC 和 USDC 余额

        Args:
            address: 钱包地址

        Returns:
            Dict: {"matic": float, "usdc": float} - 转换为可读数字
        """
        result = {"matic": 0.0, "usdc": 0.0}

        if not self.is_connected():
            logger.warning("未连接到网络")
            return result

        try:
            # 转换为 checksum 地址
            checksum_address = Web3.to_checksum_address(address)

            # 获取 MATIC 余额 (18 位小数)
            matic_wei = self.w3.eth.get_balance(checksum_address)
            result["matic"] = float(Web3.from_wei(matic_wei, 'ether'))

            # 获取 USDC 余额
            if self.usdc_contract:
                # 获取 USDC decimals (通常是 6)
                decimals = self.usdc_contract.functions.decimals().call()

                # 获取原始余额
                usdc_raw = self.usdc_contract.functions.balanceOf(checksum_address).call()

                # 转换为可读数字
                result["usdc"] = usdc_raw / (10 ** decimals)

            return result

        except Exception as e:
            logger.error(f"获取余额失败: {e}")
            return result

    def get_chain_id(self) -> Optional[int]:
        """获取链 ID (Polygon = 137)"""
        if not self.is_connected():
            return None
        try:
            return self.w3.eth.chain_id
        except Exception:
            return None


# ========== 市场扫描器 ==========
@dataclass
class MarketInfo:
    """单个市场的信息"""
    market_id: str
    condition_id: str
    question: str
    volume: float
    liquidity: float
    best_bid: float
    best_ask: float
    spread: float
    outcome: str  # Yes/No
    end_date: Optional[str] = None


class MarketScanner:
    """
    Polymarket Gamma API 市场扫描器

    功能:
    - 获取高流动性市场
    - 过滤死市场 (零流动性/宽价差)
    - 输出美观的表格
    """

    # Gamma API 端点
    GAMMA_API_BASE = "https://gamma-api.polymarket.com"
    EVENTS_ENDPOINT = f"{GAMMA_API_BASE}/events"
    MARKETS_ENDPOINT = f"{GAMMA_API_BASE}/markets"

    # 过滤参数
    DEFAULT_MAX_SPREAD = 0.05      # 最大价差 5%
    DEFAULT_MIN_VOLUME = 1000     # 最小成交量 $1000
    DEFAULT_LIMIT = 20             # 获取数量
    DEFAULT_MIN_PRICE = 0.20       # 最低价格 (过滤极端低价)
    DEFAULT_MAX_PRICE = 0.80       # 最高价格 (过滤极端高价)

    def __init__(
        self,
        max_spread: float = DEFAULT_MAX_SPREAD,
        min_volume: float = DEFAULT_MIN_VOLUME,
        min_price: float = DEFAULT_MIN_PRICE,
        max_price: float = DEFAULT_MAX_PRICE,
        timeout: int = 30
    ):
        """
        初始化 MarketScanner

        Args:
            max_spread: 最大允许价差 (默认 0.05 = 5%)
            min_volume: 最小成交量 (默认 $1000)
            min_price: 最低价格门槛 (默认 0.20，过滤冷门市场)
            max_price: 最高价格门槛 (默认 0.80，过滤已确定市场)
            timeout: API 请求超时时间
        """
        self.max_spread = max_spread
        self.min_volume = min_volume
        self.min_price = min_price
        self.max_price = max_price
        self.timeout = timeout
        # 使用带重试机制的 Session
        self.session = create_robust_session(retries=3, backoff_factor=1.0)

    def fetch_top_events(self, limit: int = DEFAULT_LIMIT) -> List[Dict]:
        """
        从 Gamma API 获取热门事件

        Args:
            limit: 获取数量

        Returns:
            List[Dict]: 事件列表
        """
        try:
            params = {
                'limit': limit,
                'active': 'true',
                'closed': 'false',
                'order': 'volume',
                'ascending': 'false'
            }

            response = self.session.get(
                self.EVENTS_ENDPOINT,
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"获取事件失败: {e}")
            return []

    def fetch_markets_for_event(self, event_id: str) -> List[Dict]:
        """
        获取特定事件下的所有市场

        Args:
            event_id: 事件 ID

        Returns:
            List[Dict]: 市场列表
        """
        try:
            # 直接使用 markets 端点过滤
            params = {
                'event_id': event_id,
                'active': 'true',
                'closed': 'false'
            }

            response = self.session.get(
                self.MARKETS_ENDPOINT,
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"获取市场失败 (event_id={event_id}): {e}")
            return []

    def scan_top_markets(self, limit: int = DEFAULT_LIMIT) -> List[MarketInfo]:
        """
        扫描并返回顶级流动性市场

        过滤条件:
        - spread <= max_spread
        - best_bid > 0 AND best_ask > 0
        - volume >= min_volume
        - min_price <= mid_price <= max_price (活跃博弈区间)

        Args:
            limit: 最大返回数量

        Returns:
            List[MarketInfo]: 过滤后的市场列表
        """
        logger.info(f"📡 扫描 Polymarket 热门市场 (价格区间: {self.min_price:.0%}-{self.max_price:.0%})...")

        # 获取热门事件
        events = self.fetch_top_events(limit=limit * 3)  # 多获取一些，因为价格过滤会排除很多

        if not events:
            logger.warning("未获取到任何事件")
            return []

        valid_markets = []
        filtered_by_price = 0  # 统计被价格过滤的数量

        for event in events:
            # 从事件中提取市场
            markets = event.get('markets', [])

            for market in markets:
                try:
                    # 提取关键字段
                    market_id = market.get('id', '')
                    condition_id = market.get('conditionId', market.get('condition_id', ''))
                    question = market.get('question', event.get('title', 'Unknown'))

                    # 截断过长的问题
                    if len(question) > 50:
                        question = question[:47] + "..."

                    # 价格数据
                    best_bid = float(market.get('bestBid', 0) or 0)
                    best_ask = float(market.get('bestAsk', 0) or 0)

                    # 如果没有 bestBid/bestAsk，尝试从 outcomePrices 解析
                    if best_bid == 0 and best_ask == 0:
                        outcome_prices = market.get('outcomePrices', '[]')
                        if isinstance(outcome_prices, str):
                            try:
                                prices = json.loads(outcome_prices)
                                if prices and len(prices) >= 1:
                                    # 第一个是 Yes 价格
                                    mid_price = float(prices[0])
                                    # 估算 bid/ask
                                    best_bid = mid_price * 0.98
                                    best_ask = mid_price * 1.02
                            except (json.JSONDecodeError, ValueError):
                                pass

                    # 成交量和流动性
                    volume = float(market.get('volume', 0) or 0)
                    liquidity = float(market.get('liquidity', 0) or 0)

                    # outcome
                    outcome = market.get('outcome', 'Yes')

                    # 结束日期
                    end_date = market.get('endDate', market.get('end_date_iso', None))

                    # 计算价差和中间价
                    if best_ask > 0 and best_bid > 0:
                        spread = best_ask - best_bid
                        mid_price = (best_bid + best_ask) / 2
                    else:
                        spread = 1.0  # 无效市场
                        mid_price = 0

                    # === 过滤条件 ===
                    # 1. 必须有有效的 bid/ask
                    if best_bid <= 0 or best_ask <= 0:
                        continue

                    # 2. 价差不能太大
                    if spread > self.max_spread:
                        continue

                    # 3. 成交量门槛
                    if volume < self.min_volume:
                        continue

                    # 4. 【新增】价格区间过滤 - 只保留活跃博弈的市场
                    #    排除 0.001 (几乎不可能) 和 0.99 (几乎确定) 的市场
                    if not (self.min_price <= mid_price <= self.max_price):
                        filtered_by_price += 1
                        continue

                    # 通过过滤，加入结果
                    market_info = MarketInfo(
                        market_id=market_id,
                        condition_id=condition_id,
                        question=question,
                        volume=volume,
                        liquidity=liquidity,
                        best_bid=best_bid,
                        best_ask=best_ask,
                        spread=spread,
                        outcome=outcome,
                        end_date=end_date
                    )
                    valid_markets.append(market_info)

                except (KeyError, ValueError, TypeError) as e:
                    # 跳过解析失败的市场
                    continue

            # 如果已经收集够了，提前退出
            if len(valid_markets) >= limit:
                break

        # 按成交量排序
        valid_markets.sort(key=lambda x: x.volume, reverse=True)

        if filtered_by_price > 0:
            logger.info(f"   已过滤 {filtered_by_price} 个极端价格市场 (价格 < {self.min_price:.0%} 或 > {self.max_price:.0%})")

        # 截取指定数量
        return valid_markets[:limit]

    def print_market_table(self, markets: List[MarketInfo]) -> None:
        """
        打印美观的市场表格

        Args:
            markets: 市场列表
        """
        if not markets:
            print("\n❌ No valid markets found matching your criteria.")
            print("   Try relaxing the filters (increase max_spread or decrease min_volume)")
            return

        print("\n" + "=" * 110)
        print("📊 TOP LIQUIDITY MARKETS - Polymarket (Active Markets Only)")
        print("=" * 110)

        # 表头 - 增加 Price 列
        header = f"{'#':<3} {'Title':<45} {'Price':>8} {'Volume':>12} {'Bid':>8} {'Ask':>8} {'Spread':>8}"
        print(header)
        print("-" * 110)

        for idx, m in enumerate(markets, 1):
            # 计算中间价
            mid_price = (m.best_bid + m.best_ask) / 2

            # 格式化数字
            price_str = f"{mid_price:.1%}"
            volume_str = f"${m.volume:,.0f}"
            bid_str = f"{m.best_bid:.3f}"
            ask_str = f"{m.best_ask:.3f}"
            spread_str = f"{m.spread:.3f}"

            # 截断问题到45字符
            question = m.question[:42] + "..." if len(m.question) > 45 else m.question

            row = f"{idx:<3} {question:<45} {price_str:>8} {volume_str:>12} {bid_str:>8} {ask_str:>8} {spread_str:>8}"
            print(row)

        print("-" * 110)
        print(f"Total: {len(markets)} markets | Price Range: {self.min_price:.0%}-{self.max_price:.0%} | Max Spread: {self.max_spread:.1%} | Min Volume: ${self.min_volume:,.0f}")
        print("=" * 110 + "\n")

    def get_market_ids(self, markets: List[MarketInfo]) -> List[str]:
        """
        提取市场 ID 列表

        Args:
            markets: 市场列表

        Returns:
            List[str]: 市场 ID 列表
        """
        return [m.market_id for m in markets]

    def get_condition_ids(self, markets: List[MarketInfo]) -> List[str]:
        """
        提取 Condition ID 列表 (用于链上交易)

        Args:
            markets: 市场列表

        Returns:
            List[str]: Condition ID 列表
        """
        return [m.condition_id for m in markets if m.condition_id]

    def scan_and_display(self, limit: int = DEFAULT_LIMIT) -> List[MarketInfo]:
        """
        扫描并显示市场 (便捷方法)

        Args:
            limit: 最大数量

        Returns:
            List[MarketInfo]: 市场列表
        """
        markets = self.scan_top_markets(limit=limit)
        self.print_market_table(markets)
        return markets


# ========== 数据录制器 ==========
class DataRecorder:
    """
    实时市场数据录制器

    功能:
    - 持续监控指定市场
    - 将 bid/ask/spread 数据写入 CSV
    - 支持 Ctrl+C 安全退出
    """

    GAMMA_API_BASE = "https://gamma-api.polymarket.com"
    MARKETS_ENDPOINT = f"{GAMMA_API_BASE}/markets"

    def __init__(self, output_dir: str = "data"):
        """
        初始化 DataRecorder

        Args:
            output_dir: 输出目录，默认 "data"
        """
        self.output_dir = output_dir
        # 使用带重试机制的 Session
        self.session = create_robust_session(retries=3, backoff_factor=1.0)

        # 确保输出目录存在
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
            logger.info(f"📁 创建数据目录: {self.output_dir}")

        # 录制统计
        self.records_count = 0
        self.errors_count = 0
        self.start_time = None
        self.csv_path = None

    def _fetch_market_data(self, market_id: str) -> Optional[Dict]:
        """
        获取单个市场的最新数据

        Args:
            market_id: 市场 ID (支持字符串或数字)

        Returns:
            Dict: 市场数据，失败返回 None
        """
        try:
            # 确保 market_id 是字符串
            market_id_str = str(market_id)

            url = f"{self.MARKETS_ENDPOINT}/{market_id_str}"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            self.errors_count += 1
            return None

    def _parse_market_data(self, data: Dict) -> Dict:
        """
        解析市场数据

        Args:
            data: API 返回的原始数据

        Returns:
            Dict: 解析后的数据
        """
        # 提取 bid/ask
        best_bid = float(data.get('bestBid', 0) or 0)
        best_ask = float(data.get('bestAsk', 0) or 0)

        # 如果没有 bestBid/bestAsk，尝试从 outcomePrices 解析
        if best_bid == 0 and best_ask == 0:
            outcome_prices = data.get('outcomePrices', '[]')
            if isinstance(outcome_prices, str):
                try:
                    prices = json.loads(outcome_prices)
                    if prices and len(prices) >= 1:
                        mid_price = float(prices[0])
                        best_bid = mid_price * 0.98
                        best_ask = mid_price * 1.02
                except (json.JSONDecodeError, ValueError):
                    pass

        # 计算 spread
        spread = best_ask - best_bid if best_ask > 0 and best_bid > 0 else 0

        # last trade price (用中间价代替)
        last_trade_price = (best_bid + best_ask) / 2 if best_bid > 0 and best_ask > 0 else 0

        # volume
        volume = float(data.get('volume', 0) or 0)

        return {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'best_bid': best_bid,
            'best_ask': best_ask,
            'spread': spread,
            'last_trade_price': last_trade_price,
            'volume': volume
        }

    def record(self, market_id, duration_minutes: int = 60, interval_seconds: int = 3) -> str:
        """
        开始录制市场数据

        Args:
            market_id: 市场 ID (支持字符串或数字)
            duration_minutes: 录制时长 (分钟)
            interval_seconds: 采样间隔 (秒)

        Returns:
            str: CSV 文件路径
        """
        # 确保 market_id 是字符串
        market_id_str = str(market_id)

        # 生成文件名
        timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        # 截取 market_id 前16位作为文件名一部分
        safe_id = market_id_str[:16].replace('/', '_').replace('\\', '_')
        self.csv_path = os.path.join(self.output_dir, f"market_{safe_id}_{timestamp_str}.csv")

        # 重置统计
        self.records_count = 0
        self.errors_count = 0
        self.start_time = datetime.now()

        # 计算结束时间
        end_time = time.time() + (duration_minutes * 60)

        print("\n" + "=" * 70)
        print("📹 DATA RECORDER - Started")
        print("=" * 70)
        print(f"   Market ID:     {market_id_str}")
        print(f"   Duration:      {duration_minutes} minutes")
        print(f"   Interval:      {interval_seconds} seconds")
        print(f"   Output File:   {self.csv_path}")
        print("-" * 70)
        print("   Press Ctrl+C to stop recording safely")
        print("=" * 70 + "\n")

        # 创建 CSV 文件并写入表头
        with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'best_bid', 'best_ask', 'spread', 'last_trade_price', 'volume'])

        # 开始录制循环
        try:
            while time.time() < end_time:
                loop_start = time.time()

                # 获取数据
                raw_data = self._fetch_market_data(market_id_str)

                if raw_data:
                    # 解析数据
                    parsed = self._parse_market_data(raw_data)

                    # 写入 CSV (追加模式，立即 flush)
                    with open(self.csv_path, 'a', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        writer.writerow([
                            parsed['timestamp'],
                            f"{parsed['best_bid']:.6f}",
                            f"{parsed['best_ask']:.6f}",
                            f"{parsed['spread']:.6f}",
                            f"{parsed['last_trade_price']:.6f}",
                            f"{parsed['volume']:.2f}"
                        ])
                        f.flush()

                    self.records_count += 1

                    # 打印日志
                    ts = datetime.now().strftime('%H:%M:%S')
                    print(f"[REC] {ts} | Bid: {parsed['best_bid']:.4f} | Ask: {parsed['best_ask']:.4f} | Spread: {parsed['spread']:.4f}")

                else:
                    ts = datetime.now().strftime('%H:%M:%S')
                    print(f"[ERR] {ts} | Failed to fetch data (errors: {self.errors_count})")

                # 等待下一次采样
                elapsed = time.time() - loop_start
                sleep_time = max(0, interval_seconds - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)

        except KeyboardInterrupt:
            print("\n\n⏹️  Recording stopped by user (Ctrl+C)")

        # 打印摘要
        self._print_summary()

        return self.csv_path

    def _print_summary(self):
        """打印录制摘要"""
        duration = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0

        print("\n" + "=" * 70)
        print("📊 RECORDING SUMMARY")
        print("=" * 70)
        print(f"   File:          {self.csv_path}")
        print(f"   Records:       {self.records_count}")
        print(f"   Errors:        {self.errors_count}")
        print(f"   Duration:      {duration / 60:.1f} minutes")
        print(f"   Avg Interval:  {duration / max(self.records_count, 1):.1f} seconds")
        print("=" * 70)
        print("✅ 录制已保存")
        print("=" * 70 + "\n")


# ========== 枚举定义 ==========
class Side(Enum):
    BUY = "BUY"
    SELL = "SELL"

class Platform(Enum):
    POLYMARKET = "polymarket"
    OPINION = "opinion"

class ExecutionMode(Enum):
    ATOMIC = "atomic"          # 原子交易：无单腿风险
    NON_ATOMIC = "non_atomic"  # 非原子交易：有单腿风险

class GasStrategy(Enum):
    STANDARD = "standard"      # 慢，便宜
    PRIORITY = "priority"      # 中等
    FLASHBOTS = "flashbots"    # 快，贵，且防抢跑

# ========== 真实市场参数 (2024-2025) ==========
REAL_MARKET_PARAMS = {
    # 延迟配置
    'mev_bot_latency_range': (3, 25),

    # Gas费用 (USD) - 调整Flashbots费用
    'gas_costs': {
        GasStrategy.STANDARD: {'base': 2, 'max': 5},
        GasStrategy.PRIORITY: {'base': 5, 'max': 12},
        GasStrategy.FLASHBOTS: {'base': 8, 'max': 20},  # 降低：私有池成本更可控
    },

    # 平台手续费
    'platform_fees': {
        Platform.POLYMARKET: 0.00,  # 假设PM Maker/Taker 0费率或低费率环境
        Platform.OPINION: 0.01,     # 对手方 1%
    },

    # 最小盈利价差
    'min_profit_rate': 0.005,

    # 风险概率
    'black_swan_probability': 0.001,
    'liquidity_crisis_probability': 0.005,

    # 单腿风险 (非原子模式下)
    'leg_risk_probability': {
        GasStrategy.STANDARD: 0.15,    # 降低：不要太残酷
        GasStrategy.PRIORITY: 0.03,
        GasStrategy.FLASHBOTS: 0.00,   # Flashbots 走私有池，通常原子化
    },

    # 被抢跑概率
    'frontrun_probability': {
        GasStrategy.STANDARD: 0.25,    # 降低：给retail一点活路
        GasStrategy.PRIORITY: 0.08,
        GasStrategy.FLASHBOTS: 0.00,   # Flashbots 防抢跑
    },

    # 上链成功率
    'chain_success_rate': {
        GasStrategy.STANDARD: 0.70,
        GasStrategy.PRIORITY: 0.90,
        GasStrategy.FLASHBOTS: 0.99,
    },
}

# ========== 核心工具类 ==========

@dataclass
class LatencyProfile:
    name: str
    discovery_ms: float
    submission_ms: float
    fill_ms: float
    gas_strategy: GasStrategy
    capital_usd: float  # 资金体量
    api_rate_limit: int

    def get_total_latency(self) -> float:
        return self.discovery_ms + self.submission_ms + self.fill_ms

@dataclass
class TradeResult:
    success: bool
    event_id: str
    bot_profile: str
    execution_mode: str = ''
    
    # 核心数据
    units_filled: float = 0.0
    fill_rate: float = 0.0
    pm_price: float = 0.0
    op_price: float = 0.0
    gross_spread: float = 0.0
    
    # 财务数据
    net_profit: float = 0.0
    net_profit_rate: float = 0.0
    gas_cost: float = 0.0
    slippage_cost: float = 0.0
    total_fees: float = 0.0
    
    # 风险标记
    leg_risk_triggered: bool = False
    was_frontrun: bool = False
    tx_reverted: bool = False
    precheck_rejected: bool = False # 新增：预检查拒绝
    
    # 诊断
    total_latency_ms: float = 0.0
    rank_in_race: int = 0

@dataclass
class Participant:
    name: str
    latency_ms: float
    desired_units: float
    is_bot: bool = False
    gas_strategy: GasStrategy = GasStrategy.STANDARD
    capital_usd: float = 1000.0
    
    # 执行结果
    actual_fill: float = 0.0
    pm_avg_price: float = 0.0
    op_avg_price: float = 0.0
    pm_cost: float = 0.0
    op_revenue: float = 0.0
    pm_slippage: float = 0.0
    op_slippage: float = 0.0
    rank: int = 0
    
    # 风险状态
    was_frontrun: bool = False
    leg_risk_triggered: bool = False

# ========== OU过程价格生成器 (V6.0 核心修复) ==========
class OUPriceGenerator:
    """
    Ornstein-Uhlenbeck 过程 - 金融工程中均值回归的标准模型

    用于生成真实的价格动态：
    - true_price: 事件的真实获胜概率（基础真理）
    - PM价格 = true_price + PM噪音（流动性好，紧跟真实价格）
    - OP价格 = true_price + OP噪音 + 滞后（流动性差，有延迟）

    套利空间来自信息传导延迟，而非随机跳动
    """
    def __init__(self, rng: np.random.RandomState,
                 theta: float = 0.1,       # 均值回归速度（降低，让价格波动更大）
                 sigma: float = 0.04,      # 波动率（提高，创造更多机会）
                 dt: float = 1.0):         # 时间步长
        self.rng = rng
        self.theta = theta
        self.sigma = sigma
        self.dt = dt
        self.true_price = None
        self.pm_price_history = []

    def initialize(self, base_prob: float):
        """初始化真实价格"""
        self.true_price = np.clip(base_prob, 0.05, 0.95)
        self.pm_price_history = [self.true_price]

    def step(self) -> float:
        """OU过程演化一步，更新真实价格"""
        if self.true_price is None:
            raise ValueError("必须先调用 initialize()")

        # OU 过程: dX = theta * (mu - X) * dt + sigma * dW
        # 这里 mu = 0.5 (中性概率)
        mu = 0.5
        dW = self.rng.normal(0, np.sqrt(self.dt))
        drift = self.theta * (mu - self.true_price) * self.dt
        diffusion = self.sigma * dW

        self.true_price = np.clip(self.true_price + drift + diffusion, 0.05, 0.95)
        return self.true_price

    def get_pm_price(self) -> float:
        """
        PM价格：流动性好，紧跟真实价格
        噪音小，几乎无滞后
        """
        noise = self.rng.normal(0, 0.003)  # 非常小的噪音
        pm_price = np.clip(self.true_price + noise, 0.01, 0.99)
        self.pm_price_history.append(pm_price)
        return pm_price

    def get_op_price(self, lag_weight: float = 0.3) -> float:
        """
        OP价格：流动性差，有滞后 + 更大噪音

        套利空间的来源：
        1. OP反应慢，当PM价格下跌时OP还没跟上（OP高估）
        2. OP流动性差导致的价格偏离

        关键：当PM价格在下跌趋势时，OP因为滞后会暂时高估，创造套利机会
        """
        # 基础噪音（比PM大）
        base_noise = self.rng.normal(0, 0.005)

        # 滞后效应：部分跟随历史PM价格
        if len(self.pm_price_history) > 1:
            lagged_price = self.pm_price_history[-2]

            # 滞后成分 + 当前成分
            lagged_component = lagged_price * lag_weight
            current_component = self.true_price * (1 - lag_weight)
            base_op = current_component + lagged_component

            # 30%概率出现额外偏离（模拟做市商报价激进或流动性突变）
            if self.rng.random() < 0.30:
                # 倾向于高估（有利于套利），偏离幅度2%-6%
                extra_bias = self.rng.uniform(0.02, 0.06)
            else:
                extra_bias = 0

            op_price = base_op + base_noise + extra_bias
        else:
            # 初始时，OP稍微高估
            op_price = self.true_price + base_noise + self.rng.uniform(0.01, 0.03)

        return np.clip(op_price, 0.01, 0.99)


# ========== CSV 价格加载器 (真实数据回测) ==========
@dataclass
class PriceSnapshot:
    """单个时间点的价格快照"""
    timestamp: datetime
    best_bid: float
    best_ask: float
    spread: float
    last_trade_price: float
    volume: float
    liquidity: float = 0.0


class CSVPriceLoader:
    """
    CSV 价格数据加载器 - 用于真实数据回测

    从录制的 CSV 文件加载价格数据，逐行提供给回测引擎。
    模拟 OU 过程生成器的接口，可无缝替换。
    """

    def __init__(self, csv_path: str, op_spread_offset: float = 0.02):
        """
        初始化 CSV 加载器

        Args:
            csv_path: CSV 文件路径
            op_spread_offset: OP 价格相对于 PM 的偏移量 (模拟套利空间)
                              正值表示 OP 比 PM 贵 (有套利机会)
        """
        self.csv_path = csv_path
        self.op_spread_offset = op_spread_offset
        self.data: Optional[pd.DataFrame] = None
        self.current_index = 0
        self.total_rows = 0

        # 当前价格状态
        self.current_snapshot: Optional[PriceSnapshot] = None
        self.pm_price_history: List[float] = []

        # 统计信息
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None

    def load(self) -> bool:
        """
        加载 CSV 文件

        Returns:
            bool: 加载是否成功
        """
        try:
            self.data = pd.read_csv(self.csv_path)

            # 验证必需列
            required_cols = ['timestamp', 'best_bid', 'best_ask']
            missing = [c for c in required_cols if c not in self.data.columns]
            if missing:
                logger.error(f"CSV 缺少必需列: {missing}")
                return False

            # 解析时间戳
            self.data['timestamp'] = pd.to_datetime(self.data['timestamp'])

            # 填充可选列
            if 'spread' not in self.data.columns:
                self.data['spread'] = self.data['best_ask'] - self.data['best_bid']
            if 'last_trade_price' not in self.data.columns:
                self.data['last_trade_price'] = (self.data['best_bid'] + self.data['best_ask']) / 2
            if 'volume' not in self.data.columns:
                self.data['volume'] = 0.0
            if 'liquidity' not in self.data.columns:
                self.data['liquidity'] = 0.0

            self.total_rows = len(self.data)
            self.current_index = 0

            if self.total_rows > 0:
                self.start_time = self.data['timestamp'].iloc[0]
                self.end_time = self.data['timestamp'].iloc[-1]

            logger.info(f"✅ CSV 加载成功: {self.csv_path}")
            logger.info(f"   数据行数: {self.total_rows}")
            logger.info(f"   时间范围: {self.start_time} -> {self.end_time}")

            return True

        except FileNotFoundError:
            logger.error(f"❌ 文件不存在: {self.csv_path}")
            return False
        except Exception as e:
            logger.error(f"❌ CSV 加载失败: {e}")
            return False

    def initialize(self, base_prob: float = None):
        """
        初始化 (兼容 OUPriceGenerator 接口)

        Args:
            base_prob: 忽略，仅为接口兼容
        """
        self.current_index = 0
        self.pm_price_history = []
        if self.data is not None and len(self.data) > 0:
            first_row = self.data.iloc[0]
            self.current_snapshot = self._row_to_snapshot(first_row)
            self.pm_price_history.append(self.current_snapshot.best_bid)

    def _row_to_snapshot(self, row: pd.Series) -> PriceSnapshot:
        """将 DataFrame 行转换为 PriceSnapshot"""
        return PriceSnapshot(
            timestamp=row['timestamp'],
            best_bid=float(row['best_bid']),
            best_ask=float(row['best_ask']),
            spread=float(row['spread']),
            last_trade_price=float(row['last_trade_price']),
            volume=float(row['volume']),
            liquidity=float(row.get('liquidity', 0))
        )

    def step(self) -> float:
        """
        前进一步，返回当前 "真实价格" (中间价)

        Returns:
            float: 当前中间价格
        """
        if self.data is None or self.current_index >= self.total_rows:
            # 数据耗尽，返回最后一个价格
            if self.current_snapshot:
                return (self.current_snapshot.best_bid + self.current_snapshot.best_ask) / 2
            return 0.5

        row = self.data.iloc[self.current_index]
        self.current_snapshot = self._row_to_snapshot(row)
        self.current_index += 1

        mid_price = (self.current_snapshot.best_bid + self.current_snapshot.best_ask) / 2
        return mid_price

    def get_pm_price(self) -> float:
        """
        获取 Polymarket 价格 (直接使用 CSV 中的 best_ask)

        套利逻辑: 我们在 PM 买入 (吃 ask)

        Returns:
            float: PM ask 价格
        """
        if self.current_snapshot is None:
            return 0.5

        pm_price = self.current_snapshot.best_ask
        self.pm_price_history.append(pm_price)
        return pm_price

    def get_op_price(self, lag_weight: float = 0.3) -> float:
        """
        获取对手平台价格 (模拟)

        因为我们只录制了 Polymarket 数据，需要模拟 OP 价格。
        策略: OP bid = PM mid + offset (模拟 OP 比 PM 稍贵)

        套利逻辑: 我们在 OP 卖出 (吃 bid)

        Args:
            lag_weight: 滞后权重 (用于模拟 OP 反应慢)

        Returns:
            float: OP bid 价格
        """
        if self.current_snapshot is None:
            return 0.5

        # 基础价格 = PM 中间价
        pm_mid = (self.current_snapshot.best_bid + self.current_snapshot.best_ask) / 2

        # 添加滞后效应
        if len(self.pm_price_history) > 1:
            lagged = self.pm_price_history[-2]
            base_op = pm_mid * (1 - lag_weight) + lagged * lag_weight
        else:
            base_op = pm_mid

        # 添加 OP 偏移 (模拟套利空间)
        op_price = base_op + self.op_spread_offset

        return np.clip(op_price, 0.01, 0.99)

    def has_more_data(self) -> bool:
        """检查是否还有更多数据"""
        return self.current_index < self.total_rows

    def get_progress(self) -> Tuple[int, int, float]:
        """
        获取进度

        Returns:
            (current_index, total_rows, percentage)
        """
        pct = (self.current_index / self.total_rows * 100) if self.total_rows > 0 else 0
        return self.current_index, self.total_rows, pct

    def get_current_timestamp(self) -> Optional[datetime]:
        """获取当前时间戳"""
        if self.current_snapshot:
            return self.current_snapshot.timestamp
        return None

    def get_all_data(self) -> Optional[pd.DataFrame]:
        """获取完整数据 (用于绘图)"""
        return self.data.copy() if self.data is not None else None

    def get_summary(self) -> Dict:
        """获取数据摘要"""
        if self.data is None:
            return {}

        return {
            'total_rows': self.total_rows,
            'start_time': str(self.start_time),
            'end_time': str(self.end_time),
            'avg_bid': self.data['best_bid'].mean(),
            'avg_ask': self.data['best_ask'].mean(),
            'avg_spread': self.data['spread'].mean(),
            'min_spread': self.data['spread'].min(),
            'max_spread': self.data['spread'].max(),
            'total_volume': self.data['volume'].iloc[-1] if 'volume' in self.data else 0
        }


# ========== 数据源枚举 ==========
class DataSource(Enum):
    SYNTHETIC = "synthetic"  # OU 过程生成
    CSV = "csv"              # CSV 文件加载


# ========== 智能交易大脑 (V6.0 重大修复) ==========
# SmartTrader 已移至 infra/math_utils.py

# ========== 订单簿与费用 ==========

@dataclass
class OrderBook:
    platform: Platform
    timestamp: datetime
    mid_price: float
    bid_levels: List[Tuple[float, float]] = field(default_factory=list)
    ask_levels: List[Tuple[float, float]] = field(default_factory=list)
    liquidity_crisis: bool = False
    # V6.0: 保存初始流动性用于回血
    _initial_ask_levels: List[Tuple[float, float]] = field(default_factory=list)
    _initial_bid_levels: List[Tuple[float, float]] = field(default_factory=list)

    def get_best_ask(self) -> Optional[Tuple[float, float]]:
        return self.ask_levels[0] if self.ask_levels else None

    def get_best_bid(self) -> Optional[Tuple[float, float]]:
        return self.bid_levels[0] if self.bid_levels else None

    def get_total_liquidity(self, side: Side) -> float:
        """获取某一侧的总流动性"""
        levels = self.ask_levels if side == Side.BUY else self.bid_levels
        return sum(qty for _, qty in levels)

    def replenish_liquidity(self, rng: random.Random, replenish_rate: float = 0.3):
        """
        V6.0 核心修复：流动性回血

        模拟做市商行为：被消耗的流动性会逐渐恢复
        replenish_rate: 每次恢复的比例 (0.3 = 30%)
        """
        if not self._initial_ask_levels:
            return

        for i, (price, init_qty) in enumerate(self._initial_ask_levels):
            if i < len(self.ask_levels):
                current_price, current_qty = self.ask_levels[i]
                # 恢复部分流动性，并加入一点随机性
                restored_qty = current_qty + (init_qty - current_qty) * replenish_rate
                restored_qty *= rng.uniform(0.9, 1.1)
                self.ask_levels[i] = (current_price, max(restored_qty, init_qty * 0.2))

        for i, (price, init_qty) in enumerate(self._initial_bid_levels):
            if i < len(self.bid_levels):
                current_price, current_qty = self.bid_levels[i]
                restored_qty = current_qty + (init_qty - current_qty) * replenish_rate
                restored_qty *= rng.uniform(0.9, 1.1)
                self.bid_levels[i] = (current_price, max(restored_qty, init_qty * 0.2))

    def consume_liquidity_with_exponential_slippage(
        self, side: Side, quantity: float, capital_size: float
    ) -> Tuple[float, float, float, float]:
        """执行交易并计算滑点"""
        levels = self.ask_levels if side == Side.BUY else self.bid_levels
        if not levels: return 0.0, 0.0, 0.0, 0.0

        if self.liquidity_crisis: # 危机时深度打折
            levels = [(p, q * 0.2) for p, q in levels]

        remaining = quantity
        total_cost = 0.0
        consumed = []
        initial_price = levels[0][0]

        for i, (price, available) in enumerate(levels):
            if remaining <= 0: break

            # 价格恶化：层级越深，价格越差
            level_penalty = 1 + 0.001 * (i + 1)
            adj_price = price * level_penalty if side == Side.BUY else price / level_penalty

            fill = min(remaining, available)
            total_cost += fill * adj_price
            remaining -= fill
            consumed.append((i, fill))

        # 更新订单簿
        for i, qty in reversed(consumed):
            p, av = levels[i]
            if av - qty <= 0.01: levels.pop(i)
            else: levels[i] = (p, av - qty)

        filled = quantity - remaining
        avg_price = total_cost / filled if filled > 0 else 0.0
        slippage = abs(avg_price - initial_price) * filled if filled > 0 else 0.0

        return filled, avg_price, total_cost, slippage

# FeeCalculator 已移至 infra/math_utils.py

# ========== 核心引擎 (V6.0 重构) ==========

class SharedBacktestEngine:
    """
    V6.0 核心修复：
    1. 使用 OU 过程生成真实价格，PM/OP基于真实价格加噪音
    2. 预检查考虑固定成本（Gas费）
    3. 最优下单量计算避免贪婪算法
    4. 流动性回血机制
    5. 支持 CSV 真实数据回测
    6. 集成 RiskManager 进行风险控制
    """

    PROFILES = {
        'retail': LatencyProfile('retail', 150, 100, 80, GasStrategy.STANDARD, 1000, 100),
        'semi_pro': LatencyProfile('semi_pro', 50, 30, 40, GasStrategy.PRIORITY, 10000, 1000),
        'pro': LatencyProfile('pro', 15, 15, 15, GasStrategy.FLASHBOTS, 50000, 5000),
    }

    def __init__(self, bot_profiles, execution_mode=ExecutionMode.NON_ATOMIC,
                 min_profit_rate=0.005, seed=None,
                 data_source: DataSource = DataSource.SYNTHETIC,
                 csv_path: str = None,
                 op_spread_offset: float = 0.02,
                 risk_manager: RiskManager = None):
        """
        初始化回测引擎

        Args:
            bot_profiles: 机器人配置列表
            execution_mode: 执行模式
            min_profit_rate: 最小盈利率
            seed: 随机种子
            data_source: 数据源 (SYNTHETIC 或 CSV)
            csv_path: CSV 文件路径 (仅当 data_source=CSV 时需要)
            op_spread_offset: OP 价格偏移 (仅 CSV 模式)
            risk_manager: Optional RiskManager instance for risk control
        """
        self.bot_profiles = bot_profiles
        self.execution_mode = execution_mode
        self.min_profit_rate = min_profit_rate
        self.seed = seed if seed else int(time.time())
        self.data_source = data_source
        self.csv_path = csv_path
        self.op_spread_offset = op_spread_offset

        self.rng = random.Random(self.seed)
        self.np_rng = np.random.RandomState(self.seed)

        # Initialize RiskManager (use provided or create default)
        self.risk_manager = risk_manager or RiskManager(
            max_daily_loss=-100.0,      # Default: halt at -$100
            max_position_size=500.0,    # Default: max $500 per trade
            max_consecutive_losses=10   # Default: pause after 10 consecutive losses
        )

        # 根据数据源初始化价格生成器
        if data_source == DataSource.CSV and csv_path:
            self.price_gen = CSVPriceLoader(csv_path, op_spread_offset)
            if not self.price_gen.load():
                logger.error("CSV 加载失败，回退到合成数据")
                self.price_gen = OUPriceGenerator(self.np_rng)
                self.data_source = DataSource.SYNTHETIC
        else:
            self.price_gen = OUPriceGenerator(self.np_rng)

        # 统计数据
        self.stats = {
            'black_swan': 0, 'frontrun': 0, 'leg_risk': 0,
            'reverted': 0, 'chain_fail': 0, 'precheck_rejected': 0,
            'no_opportunity': 0, 'profitable_trades': 0,
            'total_ticks': 0, 'risk_blocked': 0  # NEW: Risk manager blocks
        }
        self.analyzers = {p: [] for p in bot_profiles}

        # 交易记录 (用于绘图)
        self.trade_history: List[Dict] = []
        self.price_history: List[Dict] = []

        # 共享订单簿（跨事件持久化）
        self.pm_book: Optional[OrderBook] = None
        self.op_book: Optional[OrderBook] = None

        logger.info(
            f"🚀 SharedBacktestEngine initialized | "
            f"Profiles: {bot_profiles} | "
            f"Data Source: {data_source.value}"
        )

    def _generate_books(self, pm_price: float, op_price: float):
        """
        V6.0: 基于 OU 过程生成的价格构建订单簿

        套利逻辑：PM买入 (吃ask) -> OP卖出 (吃bid)
        套利条件：op_bid > pm_ask

        关键修复：
        - PM订单簿：ask从mid_price开始向上
        - OP订单簿：bid从mid_price开始向下
        - 只有当op_price > pm_price时才可能有正价差
        """
        # PM 深度好，流动性更强
        pm_book = OrderBook(Platform.POLYMARKET, datetime.now(), pm_price)
        liq_pm = self.rng.uniform(4000, 10000)

        # PM ask levels: 从mid向上 (买入价)
        # best_ask = mid * (1 + spread/2)
        pm_spread = 0.002  # PM流动性好，点差小
        ask_levels = []
        for i in range(5):
            p = pm_price * (1 + pm_spread * (i + 1))
            q = liq_pm * (0.6 ** i)
            ask_levels.append((p, q))
        pm_book.ask_levels = ask_levels
        pm_book._initial_ask_levels = list(ask_levels)

        # OP 深度差，流动性更弱
        op_book = OrderBook(Platform.OPINION, datetime.now(), op_price)
        liq_op = self.rng.uniform(2000, 5000)

        # OP bid levels: 从mid向下 (卖出价)
        # best_bid = mid * (1 - spread/2)
        op_spread = 0.003  # OP流动性差，点差大
        bid_levels = []
        for i in range(5):
            p = op_price * (1 - op_spread * (i + 1))
            q = liq_op * (0.6 ** i)
            bid_levels.append((p, q))
        op_book.bid_levels = bid_levels
        op_book._initial_bid_levels = list(bid_levels)

        return pm_book, op_book

    async def _execute_opportunity(self, event_id: str, tick_in_event: int):
        """
        执行单个套利机会

        tick_in_event: 事件内的第几个时间片，用于流动性回血
        """
        self.stats['total_ticks'] += 1

        # 1. 风险事件检查
        if self.rng.random() < REAL_MARKET_PARAMS['black_swan_probability']:
            self.stats['black_swan'] += 1
            return  # API 挂了

        # 2. OU 过程演化价格
        self.price_gen.step()
        pm_price = self.price_gen.get_pm_price()
        op_price = self.price_gen.get_op_price()

        # 记录价格历史 (用于绘图)
        timestamp = None
        if self.data_source == DataSource.CSV and hasattr(self.price_gen, 'get_current_timestamp'):
            timestamp = self.price_gen.get_current_timestamp()

        self.price_history.append({
            'tick': self.stats['total_ticks'],
            'timestamp': timestamp,
            'pm_price': pm_price,
            'op_price': op_price,
            'spread': op_price - pm_price
        })

        # 3. 生成/更新订单簿
        if self.pm_book is None or tick_in_event == 0:
            # 新事件，重新生成订单簿
            self.pm_book, self.op_book = self._generate_books(pm_price, op_price)
        else:
            # 流动性回血（每3个tick回血一次）
            if tick_in_event % 3 == 0:
                self.pm_book.replenish_liquidity(self.rng, 0.25)
                self.op_book.replenish_liquidity(self.rng, 0.25)
            # 更新中间价格
            self.pm_book.mid_price = pm_price
            self.op_book.mid_price = op_price

        pm_ask = self.pm_book.get_best_ask()
        op_bid = self.op_book.get_best_bid()

        if not pm_ask or not op_bid:
            return

        # 计算毛价差
        gross_spread = op_bid[0] - pm_ask[0]

        # 基础门槛过滤（太小的价差不值得看）
        if gross_spread < self.min_profit_rate * 0.5:
            self.stats['no_opportunity'] += 1
            return

        # 4. 构建参与者
        participants = []
        pm_liquidity = self.pm_book.get_total_liquidity(Side.BUY)
        op_liquidity = self.op_book.get_total_liquidity(Side.SELL)
        max_liq = min(pm_liquidity, op_liquidity)

        for name in self.bot_profiles:
            prof = self.PROFILES[name]
            latency = prof.get_total_latency() * self.rng.uniform(0.8, 1.2)
            p = Participant(
                name, latency, 0,  # desired_units 稍后计算
                is_bot=True,
                gas_strategy=prof.gas_strategy,
                capital_usd=prof.capital_usd
            )
            participants.append(p)

        # 5. 排序（竞速）
        participants.sort(key=lambda x: x.latency_ms)

        # 6. 依次执行
        for rank, p in enumerate(participants, 1):
            p.rank = rank

            # --- 估算 Gas 成本 ---
            g_conf = REAL_MARKET_PARAMS['gas_costs'][p.gas_strategy]
            est_gas = (g_conf['base'] + g_conf['max']) / 2

            # --- 费率 ---
            total_fee_rate = (
                REAL_MARKET_PARAMS['platform_fees'][Platform.POLYMARKET] +
                REAL_MARKET_PARAMS['platform_fees'][Platform.OPINION]
            )

            # --- V6.0 预检查：考虑固定成本 ---
            should_trade, reason = SmartTrader.precheck_profitability(
                spread=gross_spread,
                fee_rate=total_fee_rate,
                fixed_cost=est_gas,
                capital=p.capital_usd
            )

            if not should_trade:
                self.analyzers[p.name].append(TradeResult(
                    success=False, event_id=event_id, bot_profile=p.name,
                    precheck_rejected=True, net_profit=0,
                    gross_spread=gross_spread, gas_cost=0
                ))
                self.stats['precheck_rejected'] += 1
                continue

            # --- V6.0 最优下单量计算 ---
            curr_pm_liq = self.pm_book.get_total_liquidity(Side.BUY)
            curr_op_liq = self.op_book.get_total_liquidity(Side.SELL)
            curr_liq = min(curr_pm_liq, curr_op_liq)

            optimal_qty, expected_profit = SmartTrader.calculate_optimal_amount(
                spread=gross_spread,
                fee_rate=total_fee_rate,
                liquidity_depth=curr_liq,
                capital=p.capital_usd,
                fixed_cost=est_gas,
                mid_price=pm_price
            )

            # 预期利润检查
            if expected_profit < 3.0 or optimal_qty < 50:
                self.analyzers[p.name].append(TradeResult(
                    success=False, event_id=event_id, bot_profile=p.name,
                    precheck_rejected=True, net_profit=0,
                    gross_spread=gross_spread, gas_cost=0
                ))
                self.stats['precheck_rejected'] += 1
                continue

            # --- V6.1 风险管理检查 (BEFORE execution) ---
            risk_ok, risk_reason = self.risk_manager.check_trade_risk(
                amount=optimal_qty,
                expected_profit=expected_profit,
                profile_name=p.name
            )

            if not risk_ok:
                self.analyzers[p.name].append(TradeResult(
                    success=False, event_id=event_id, bot_profile=p.name,
                    precheck_rejected=True, net_profit=0,
                    gross_spread=gross_spread, gas_cost=0
                ))
                self.stats['risk_blocked'] += 1
                logger.debug(f"🛡️ [{p.name}] Trade blocked by RiskManager: {risk_reason}")
                continue

            # --- 抢跑检查 ---
            fail_prob = REAL_MARKET_PARAMS['frontrun_probability'][p.gas_strategy]
            if self.rng.random() < fail_prob:
                p.was_frontrun = True
                self.stats['frontrun'] += 1
                # Record loss in RiskManager
                self.risk_manager.record_trade_result(
                    profit=-est_gas,
                    amount=optimal_qty,
                    profile_name=p.name,
                    event_id=event_id
                )
                self.analyzers[p.name].append(TradeResult(
                    success=False, event_id=event_id, bot_profile=p.name,
                    was_frontrun=True, net_profit=-est_gas, gas_cost=est_gas,
                    gross_spread=gross_spread
                ))
                continue

            # --- 执行撮合 ---
            p.desired_units = optimal_qty

            pm_fill, pm_avg, pm_c, pm_s = self.pm_book.consume_liquidity_with_exponential_slippage(
                Side.BUY, p.desired_units, p.capital_usd
            )
            op_fill, op_avg, op_r, op_s = self.op_book.consume_liquidity_with_exponential_slippage(
                Side.SELL, p.desired_units, p.capital_usd
            )

            # --- 单腿风险 (非原子) ---
            if self.execution_mode == ExecutionMode.NON_ATOMIC:
                lr_prob = REAL_MARKET_PARAMS['leg_risk_probability'][p.gas_strategy]
                if self.rng.random() < lr_prob:
                    p.leg_risk_triggered = True
                    self.stats['leg_risk'] += 1
                    loss = pm_c * 0.2 + est_gas
                    # Record loss in RiskManager
                    self.risk_manager.record_trade_result(
                        profit=-loss,
                        amount=p.desired_units,
                        profile_name=p.name,
                        event_id=event_id
                    )
                    self.analyzers[p.name].append(TradeResult(
                        success=False, event_id=event_id, bot_profile=p.name,
                        leg_risk_triggered=True, net_profit=-loss, gas_cost=est_gas,
                        gross_spread=gross_spread, units_filled=pm_fill
                    ))
                    continue

            # --- 成功结算 ---
            fill = min(pm_fill, op_fill)
            pm_fee, op_fee, real_gas = FeeCalculator.calculate(
                pm_c, op_r, p.gas_strategy, self.rng,
                platform_fees=REAL_MARKET_PARAMS['platform_fees'],
                gas_costs=REAL_MARKET_PARAMS['gas_costs']
            )

            gross_p = op_r - pm_c
            net_p = gross_p - (pm_fee + op_fee + real_gas) - (pm_s + op_s)

            is_success = net_p > 0
            if is_success:
                self.stats['profitable_trades'] += 1

            # Record result in RiskManager
            self.risk_manager.record_trade_result(
                profit=net_p,
                amount=fill,
                profile_name=p.name,
                event_id=event_id
            )

            self.analyzers[p.name].append(TradeResult(
                success=is_success, event_id=event_id, bot_profile=p.name,
                units_filled=fill,
                fill_rate=fill / p.desired_units if p.desired_units > 0 else 0,
                pm_price=pm_avg, op_price=op_avg, gross_spread=gross_spread,
                net_profit=net_p, gas_cost=real_gas, slippage_cost=pm_s + op_s,
                total_fees=pm_fee + op_fee + real_gas, rank_in_race=p.rank,
                total_latency_ms=p.latency_ms
            ))

    async def run_backtest(self, num_events=10, events_per_day=5, duration_days=3):
        """
        运行回测

        对于合成数据 (SYNTHETIC): 每个事件内部有多个 tick
        对于 CSV 数据: 遍历整个 CSV 文件
        """
        if self.data_source == DataSource.CSV:
            return await self._run_csv_backtest()
        else:
            return await self._run_synthetic_backtest(num_events, events_per_day, duration_days)

    async def _run_synthetic_backtest(self, num_events=10, events_per_day=5, duration_days=3):
        """运行合成数据回测 (OU 过程)"""
        total_events = num_events
        ticks_per_event = events_per_day * duration_days

        logger.info(f"🚀 V6.0 启动 | OU价格模型 + 智能下单 | 事件数: {total_events}, 每事件tick: {ticks_per_event}")

        for event_idx in range(total_events):
            base_prob = self.rng.uniform(0.3, 0.7)
            self.price_gen.initialize(base_prob)
            self.pm_book = None
            self.op_book = None

            for tick in range(ticks_per_event):
                await self._execute_opportunity(f"evt_{event_idx}_t{tick}", tick)

            if event_idx % 5 == 0:
                await asyncio.sleep(0)

        logger.info(f"📊 统计: {self.stats}")
        return self._pack_results()

    async def _run_csv_backtest(self):
        """运行 CSV 真实数据回测"""
        if not isinstance(self.price_gen, CSVPriceLoader):
            logger.error("数据源不是 CSV")
            return self._pack_results()

        total_rows = self.price_gen.total_rows
        logger.info(f"🚀 V6.0 启动 | CSV真实数据回测 | 数据点: {total_rows}")

        # 初始化
        self.price_gen.initialize()
        self.pm_book = None
        self.op_book = None

        tick = 0
        last_progress = 0

        while self.price_gen.has_more_data():
            await self._execute_opportunity(f"csv_t{tick}", tick)
            tick += 1

            # 进度显示
            current, total, pct = self.price_gen.get_progress()
            if int(pct / 10) > last_progress:
                last_progress = int(pct / 10)
                logger.info(f"📊 进度: {current}/{total} ({pct:.1f}%)")

            # 防止阻塞
            if tick % 100 == 0:
                await asyncio.sleep(0)

        logger.info(f"📊 回测完成 | 统计: {self.stats}")
        return self._pack_results()

    def get_price_history_df(self) -> pd.DataFrame:
        """获取价格历史 DataFrame (用于绘图)"""
        return pd.DataFrame(self.price_history)

    def get_trade_history_df(self) -> pd.DataFrame:
        """获取交易历史 DataFrame"""
        all_trades = []
        for profile, trades in self.analyzers.items():
            for t in trades:
                trade_dict = t.__dict__.copy()
                trade_dict['profile'] = profile
                all_trades.append(trade_dict)
        return pd.DataFrame(all_trades)

    def _pack_results(self):
        packed = {}
        for p, trades in self.analyzers.items():
            df = pd.DataFrame([t.__dict__ for t in trades])
            metrics = {}
            if not df.empty:
                metrics['总机会数'] = len(df)
                metrics['成功交易'] = len(df[df['success'] == True])
                metrics['成功率%'] = metrics['成功交易'] / len(df) * 100 if len(df) > 0 else 0
                metrics['净收益'] = df['net_profit'].sum()
                metrics['总Gas费用'] = df['gas_cost'].sum()
                metrics['总滑点成本'] = df['slippage_cost'].sum()
                metrics['平均fill_rate%'] = df['fill_rate'].mean() * 100 if 'fill_rate' in df else 0
                metrics['被抢跑次数'] = df['was_frontrun'].sum()
                metrics['单腿风险次数'] = df['leg_risk_triggered'].sum()
                metrics['预检查拒绝'] = df['precheck_rejected'].sum()
                metrics['平均竞争对手数'] = 0  # V6.0 暂不计算
            packed[p] = (df, metrics)
        return packed

class BacktestVisualizer:
    """
    Backtest visualization and reporting class.

    Provides methods to visualize backtest results and generate
    formatted reports for analysis.

    Attributes:
        results: Dictionary mapping profile names to (DataFrame, metrics) tuples.
        stats: Optional statistics dictionary from the backtest engine.
        capital: Initial capital used in the backtest (for ROI calculations).
    """

    def __init__(self, results: Dict, stats: Dict = None, capital: float = 1000.0):
        """
        Initialize the BacktestVisualizer.

        Args:
            results: Backtest results dictionary {profile: (df, metrics)}.
            stats: Optional statistics dictionary from the engine.
            capital: Initial capital for ROI calculations.
        """
        self.results = results
        self.stats = stats or {}
        self.capital = capital

    def plot_all(self, output_path: str = 'backtest_v5_result.png') -> None:
        """
        Generate and save cumulative profit chart.

        Creates a line plot showing cumulative profit over time for each
        bot profile in the results.

        Args:
            output_path: File path to save the generated chart.
        """
        print("📊 正在绘图...")
        plt.figure(figsize=(10, 6))
        for p, (df, _) in self.results.items():
            if not df.empty:
                df['cumsum'] = df['net_profit'].cumsum()
                plt.plot(df.index, df['cumsum'], label=p.upper())
        plt.title("Cumulative Profit (V6.0 Smart Sizing)")
        plt.xlabel("Trade Number")
        plt.ylabel("Cumulative Profit ($)")
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.savefig(output_path)
        print(f"✅ 图表已保存: {output_path}")

    def print_report(self) -> Dict:
        """
        Print a detailed backtest report to console.

        Generates a formatted report including:
        - Overall statistics (ticks, opportunities, risk events)
        - Per-profile performance metrics
        - Risk management statistics
        - Profit/loss summary with logic validation

        Returns:
            Dict: Summary metrics including total_profit.
        """
        print("\n" + "=" * 80)
        print("📊 回测成绩单 - BACKTEST REPORT")
        print("=" * 80)

        # Overall statistics section
        print("\n【总体统计】")
        print("-" * 50)
        print(f"   总 Tick 数:      {self.stats.get('total_ticks', 0):,}")
        print(f"   无机会:          {self.stats.get('no_opportunity', 0):,}")
        print(f"   预检查拒绝:      {self.stats.get('precheck_rejected', 0):,}")
        print(f"   风险管理阻止:    {self.stats.get('risk_blocked', 0):,}")
        print(f"   被抢跑:          {self.stats.get('frontrun', 0):,}")
        print(f"   单腿风险:        {self.stats.get('leg_risk', 0):,}")
        print(f"   盈利交易:        {self.stats.get('profitable_trades', 0):,}")

        # Log key stats
        logger.info(
            f"📊 Backtest Stats | Ticks: {self.stats.get('total_ticks', 0)} | "
            f"Profitable: {self.stats.get('profitable_trades', 0)} | "
            f"Risk Blocked: {self.stats.get('risk_blocked', 0)}"
        )

        # Per-profile details section
        print("\n【各配置收益详情】")
        print("=" * 80)
        print(f"{'配置':<12} {'成功率':>10} {'净收益($)':>12} {'总Gas':>10} {'总滑点':>10} {'被抢跑':>8} {'单腿风险':>8}")
        print("-" * 80)

        total_profit = 0
        profile_profits = {}

        for profile, (df, metrics) in self.results.items():
            if metrics:
                success_rate = metrics.get('成功率%', 0)
                net_profit = metrics.get('净收益', 0)
                total_gas = metrics.get('总Gas费用', 0)
                total_slip = metrics.get('总滑点成本', 0)
                frontrun = metrics.get('被抢跑次数', 0)
                leg_risk = metrics.get('单腿风险次数', 0)

                print(f"{profile.upper():<12} {success_rate:>9.1f}% {net_profit:>12.2f} {total_gas:>10.2f} {total_slip:>10.2f} {frontrun:>8} {leg_risk:>8}")
                total_profit += net_profit
                profile_profits[profile] = net_profit
            else:
                print(f"{profile.upper():<12} {'N/A':>10} {'N/A':>12} {'N/A':>10} {'N/A':>10} {'N/A':>8} {'N/A':>8}")
                profile_profits[profile] = 0

        print("-" * 80)
        print(f"{'合计':<12} {'':<10} {total_profit:>12.2f}")
        print("=" * 80)

        # Logic validation section
        print("\n【收益逻辑验证】")
        try:
            retail_net = profile_profits.get('retail', 0)
            semi_net = profile_profits.get('semi_pro', 0)
            pro_net = profile_profits.get('pro', 0)

            if pro_net > semi_net > retail_net:
                print("✅ 符合预期: PRO > SEMI_PRO > RETAIL (速度越快，收益越高)")
            elif pro_net >= semi_net >= retail_net:
                print("⚠️ 基本符合: PRO >= SEMI_PRO >= RETAIL")
            else:
                print(f"❌ 结果异常: PRO=${pro_net:.2f}, SEMI=${semi_net:.2f}, RETAIL=${retail_net:.2f}")
        except Exception as e:
            print(f"   验证失败: {e}")

        # Summary section
        print("\n" + "=" * 80)
        if total_profit > 0:
            print(f"💰 总净收益: +${total_profit:.2f} (盈利)")
        elif total_profit < 0:
            print(f"💸 总净收益: -${abs(total_profit):.2f} (亏损)")
        else:
            print(f"⚖️ 总净收益: $0.00 (持平)")
        print("=" * 80 + "\n")

        return {'total_profit': total_profit, 'profile_profits': profile_profits}


# ========== 终端颜色工具 ==========
class Colors:
    """
    ANSI color codes for terminal output formatting.

    Provides color constants for enhancing CLI output readability.
    Use Colors.RESET after colored text to restore default formatting.

    Example:
        >>> print(f"{Colors.GREEN}Success!{Colors.RESET}")
        >>> print(f"{Colors.BOLD}{Colors.BLUE}Header{Colors.RESET}")
    """
    # Basic colors
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'

    # Formatting
    BOLD = '\033[1m'
    DIM = '\033[2m'
    UNDERLINE = '\033[4m'

    # Reset
    RESET = '\033[0m'

    @classmethod
    def success(cls, text: str) -> str:
        """Format text as success (green)."""
        return f"{cls.GREEN}{text}{cls.RESET}"

    @classmethod
    def error(cls, text: str) -> str:
        """Format text as error (red)."""
        return f"{cls.RED}{text}{cls.RESET}"

    @classmethod
    def warning(cls, text: str) -> str:
        """Format text as warning (yellow)."""
        return f"{cls.YELLOW}{text}{cls.RESET}"

    @classmethod
    def info(cls, text: str) -> str:
        """Format text as info (cyan)."""
        return f"{cls.CYAN}{text}{cls.RESET}"

    @classmethod
    def header(cls, text: str) -> str:
        """Format text as header (bold blue)."""
        return f"{cls.BOLD}{cls.BLUE}{text}{cls.RESET}"


# ========== 数据管理器 ==========
class DataManager:
    """
    Data file management class for CSV operations.

    Handles file discovery, listing, loading, and validation for CSV data files
    used in backtesting. Encapsulates all file system operations
    related to data management.

    Attributes:
        data_dir: Directory path where CSV files are stored.

    Example:
        >>> dm = DataManager("data")
        >>> files = dm.list_csv_files()
        >>> df = dm.load_csv(files[0]['path'])
    """

    DEFAULT_DATA_DIR = "data"

    def __init__(self, data_dir: str = None):
        """
        Initialize the DataManager.

        Args:
            data_dir: Directory containing CSV files. Defaults to "data".
        """
        self.data_dir = data_dir or self.DEFAULT_DATA_DIR

    def ensure_data_dir_exists(self) -> bool:
        """
        Ensure the data directory exists, creating it if necessary.

        Returns:
            bool: True if directory exists or was created successfully.
        """
        if not os.path.exists(self.data_dir):
            try:
                os.makedirs(self.data_dir)
                logger.info(f"📁 创建数据目录: {self.data_dir}")
                return True
            except OSError as e:
                logger.error(f"❌ 无法创建数据目录: {e}")
                return False
        return True

    def list_csv_files(self) -> List[Dict]:
        """
        List all CSV files in the data directory.

        Scans the data directory for CSV files and returns metadata
        about each file including path, size, modification time, and row count.

        Returns:
            List[Dict]: List of file metadata dictionaries with keys:
                - path: Full file path
                - name: File name
                - size_kb: File size in KB
                - mtime: Modification time (formatted string)
                - rows: Number of data rows (excluding header)

        Example:
            >>> dm = DataManager()
            >>> files = dm.list_csv_files()
            >>> for f in files:
            ...     print(f"{f['name']}: {f['rows']} rows")
        """
        import glob as glob_module

        if not os.path.exists(self.data_dir):
            return []

        pattern = os.path.join(self.data_dir, "*.csv")
        files = glob_module.glob(pattern)

        # Sort by modification time (newest first)
        files.sort(key=os.path.getmtime, reverse=True)

        result = []
        for filepath in files:
            filename = os.path.basename(filepath)
            stat = os.stat(filepath)
            size_kb = stat.st_size / 1024
            mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")

            # Count rows
            try:
                with open(filepath, 'r') as f:
                    rows = sum(1 for _ in f) - 1  # Subtract header row
            except Exception:
                rows = 0

            result.append({
                'path': filepath,
                'name': filename,
                'size_kb': size_kb,
                'mtime': mtime,
                'rows': rows
            })

        return result

    def get_file_by_index(self, index: int) -> Optional[Dict]:
        """
        Get file metadata by index from the file list.

        Args:
            index: Zero-based index into the sorted file list.

        Returns:
            Dict or None: File metadata dictionary if found, None otherwise.
        """
        files = self.list_csv_files()
        if 0 <= index < len(files):
            return files[index]
        return None

    def validate_csv_file(self, filepath: str) -> Tuple[bool, str]:
        """
        Validate that a CSV file exists and has required columns.

        Args:
            filepath: Path to the CSV file to validate.

        Returns:
            Tuple[bool, str]: (is_valid, message)
        """
        if not os.path.exists(filepath):
            return False, f"文件不存在: {filepath}"

        try:
            df = pd.read_csv(filepath, nrows=1)
            required_cols = ['timestamp', 'best_bid', 'best_ask']
            missing = [c for c in required_cols if c not in df.columns]

            if missing:
                return False, f"缺少必需列: {missing}"

            return True, "验证通过"

        except Exception as e:
            return False, f"读取失败: {e}"

    def get_csv_summary(self, filepath: str) -> Optional[Dict]:
        """
        Get summary statistics for a CSV file.

        Args:
            filepath: Path to the CSV file.

        Returns:
            Dict or None: Summary statistics including row count,
                         average prices, and spread statistics.
        """
        try:
            df = pd.read_csv(filepath)
            return {
                'rows': len(df),
                'avg_bid': df['best_bid'].mean() if 'best_bid' in df else 0,
                'avg_ask': df['best_ask'].mean() if 'best_ask' in df else 0,
                'avg_spread': df['spread'].mean() if 'spread' in df else 0,
                'min_spread': df['spread'].min() if 'spread' in df else 0,
                'max_spread': df['spread'].max() if 'spread' in df else 0,
            }
        except Exception as e:
            logger.error(f"获取CSV摘要失败: {e}")
            return None

    def load_csv(self, filepath: str) -> Optional[pd.DataFrame]:
        """
        Load a CSV file into a pandas DataFrame.

        Validates the file exists and contains required columns before loading.
        Automatically parses timestamp column and fills missing optional columns.

        Args:
            filepath: Path to the CSV file to load.

        Returns:
            pd.DataFrame or None: Loaded DataFrame with parsed timestamps,
                                  or None if loading fails.

        Raises:
            No exceptions raised - errors are logged and None is returned.

        Example:
            >>> dm = DataManager()
            >>> df = dm.load_csv("data/market_abc_20240101.csv")
            >>> if df is not None:
            ...     print(f"Loaded {len(df)} rows")
        """
        # Validate file first
        is_valid, message = self.validate_csv_file(filepath)
        if not is_valid:
            logger.error(f"CSV validation failed: {message}")
            return None

        try:
            df = pd.read_csv(filepath)

            # Parse timestamp column
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])

            # Fill optional columns with defaults
            if 'spread' not in df.columns and 'best_bid' in df.columns and 'best_ask' in df.columns:
                df['spread'] = df['best_ask'] - df['best_bid']

            if 'last_trade_price' not in df.columns and 'best_bid' in df.columns and 'best_ask' in df.columns:
                df['last_trade_price'] = (df['best_bid'] + df['best_ask']) / 2

            if 'volume' not in df.columns:
                df['volume'] = 0.0

            if 'liquidity' not in df.columns:
                df['liquidity'] = 0.0

            logger.info(f"✅ Loaded CSV: {filepath} ({len(df)} rows)")
            return df

        except Exception as e:
            logger.error(f"Failed to load CSV: {e}")
            return None

    def print_file_list(self) -> int:
        """
        Print a formatted table of available CSV files.

        Displays file name, row count, size, and modification time
        in a formatted table.

        Returns:
            int: Number of files found.
        """
        files = self.list_csv_files()

        if not files:
            print(f"\n❌ {self.data_dir}/ 目录下没有 CSV 文件")
            print("   请先使用「扫描并录制市场」功能录制数据")
            return 0

        print("\n" + "=" * 80)
        print("📂 可用的 CSV 数据文件")
        print("=" * 80)
        print(f"{'#':<4} {'文件名':<45} {'行数':>8} {'大小':>10} {'修改时间':<18}")
        print("-" * 80)

        for idx, f in enumerate(files, 1):
            print(f"{idx:<4} {f['name']:<45} {f['rows']:>8} {f['size_kb']:>8.1f}KB {f['mtime']:<18}")

        print("-" * 80)
        print(f"共找到 {len(files)} 个文件")
        print("=" * 80)

        return len(files)


# ========== 输入验证工具 ==========
class InputValidator:
    """
    Input validation utility for CLI applications.

    Provides safe input collection methods that handle invalid inputs
    gracefully without crashing the application.

    Example:
        >>> validator = InputValidator()
        >>> num = validator.get_int("Enter a number: ", default=10, min_val=1, max_val=100)
        >>> choice = validator.get_choice("Select option: ", ['a', 'b', 'c'])
    """

    @staticmethod
    def get_int(
        prompt: str,
        default: int = None,
        min_val: int = None,
        max_val: int = None
    ) -> Optional[int]:
        """
        Get an integer input from user with validation.

        Args:
            prompt: The prompt to display to the user.
            default: Default value if user enters empty string.
            min_val: Minimum allowed value (inclusive).
            max_val: Maximum allowed value (inclusive).

        Returns:
            int or None: Validated integer, default value, or None if cancelled.
        """
        while True:
            try:
                user_input = input(prompt).strip()

                # Handle empty input
                if not user_input:
                    if default is not None:
                        return default
                    print("   ❌ 请输入一个数字")
                    continue

                # Handle cancel commands
                if user_input.lower() in ('q', 'quit', 'b', 'back', 'cancel'):
                    return None

                value = int(user_input)

                # Validate range
                if min_val is not None and value < min_val:
                    print(f"   ❌ 数值不能小于 {min_val}")
                    continue
                if max_val is not None and value > max_val:
                    print(f"   ❌ 数值不能大于 {max_val}")
                    continue

                return value

            except ValueError:
                print("   ❌ 无效输入，请输入数字")
            except KeyboardInterrupt:
                print("\n")
                return None

    @staticmethod
    def get_float(
        prompt: str,
        default: float = None,
        min_val: float = None,
        max_val: float = None
    ) -> Optional[float]:
        """
        Get a float input from user with validation.

        Args:
            prompt: The prompt to display to the user.
            default: Default value if user enters empty string.
            min_val: Minimum allowed value (inclusive).
            max_val: Maximum allowed value (inclusive).

        Returns:
            float or None: Validated float, default value, or None if cancelled.
        """
        while True:
            try:
                user_input = input(prompt).strip()

                # Handle empty input
                if not user_input:
                    if default is not None:
                        return default
                    print("   ❌ 请输入一个数字")
                    continue

                # Handle cancel commands
                if user_input.lower() in ('q', 'quit', 'b', 'back', 'cancel'):
                    return None

                value = float(user_input)

                # Validate range
                if min_val is not None and value < min_val:
                    print(f"   ❌ 数值不能小于 {min_val}")
                    continue
                if max_val is not None and value > max_val:
                    print(f"   ❌ 数值不能大于 {max_val}")
                    continue

                return value

            except ValueError:
                print("   ❌ 无效输入，请输入数字")
            except KeyboardInterrupt:
                print("\n")
                return None

    @staticmethod
    def get_choice(
        prompt: str,
        valid_choices: List[str],
        case_sensitive: bool = False
    ) -> Optional[str]:
        """
        Get a choice from a predefined list of options.

        Args:
            prompt: The prompt to display to the user.
            valid_choices: List of valid choice strings.
            case_sensitive: Whether comparison should be case-sensitive.

        Returns:
            str or None: The selected choice or None if cancelled.
        """
        while True:
            try:
                user_input = input(prompt).strip()

                if not user_input:
                    print(f"   ❌ 请从以下选项中选择: {', '.join(valid_choices)}")
                    continue

                # Handle cancel commands
                if user_input.lower() in ('q', 'quit', 'b', 'back', 'cancel'):
                    return None

                # Validate choice
                compare_input = user_input if case_sensitive else user_input.lower()
                compare_choices = valid_choices if case_sensitive else [c.lower() for c in valid_choices]

                if compare_input in compare_choices:
                    # Return original case version
                    idx = compare_choices.index(compare_input)
                    return valid_choices[idx]

                print(f"   ❌ 无效选择，请从以下选项中选择: {', '.join(valid_choices)}")

            except KeyboardInterrupt:
                print("\n")
                return None

    @staticmethod
    def get_confirmation(prompt: str, default: bool = False) -> bool:
        """
        Get a yes/no confirmation from user.

        Args:
            prompt: The prompt to display (should indicate default, e.g., "(y/n)").
            default: Default value if user enters empty string.

        Returns:
            bool: True for yes, False for no.
        """
        while True:
            try:
                user_input = input(prompt).strip().lower()

                if not user_input:
                    return default

                if user_input in ('y', 'yes', '是', '1'):
                    return True
                if user_input in ('n', 'no', '否', '0'):
                    return False

                print("   ❌ 请输入 y 或 n")

            except KeyboardInterrupt:
                print("\n")
                return False


# ========== 回测会话管理器 ==========
class BacktestSession:
    """
    Backtest session manager - orchestrates the complete backtest workflow.

    This class encapsulates all the logic needed to run a backtest,
    allowing the UI layer to call a single method instead of
    managing multiple components.

    Attributes:
        data_manager: DataManager instance for file operations.
        validator: InputValidator for user input handling.
    """

    def __init__(self, data_dir: str = "data"):
        """
        Initialize the BacktestSession.

        Args:
            data_dir: Directory containing CSV data files.
        """
        self.data_manager = DataManager(data_dir)
        self.validator = InputValidator()

    def get_csv_file_selection(self) -> Optional[str]:
        """
        Display available CSV files and get user selection.

        Returns:
            str or None: Selected file path, or None if cancelled.
        """
        file_count = self.data_manager.print_file_list()

        if file_count == 0:
            return None

        files = self.data_manager.list_csv_files()

        selection = self.validator.get_int(
            "\n请选择文件序号 (或 'b' 返回): ",
            min_val=1,
            max_val=len(files)
        )

        if selection is None:
            return None

        selected = files[selection - 1]
        print(f"\n✅ 已选择: {selected['name']}")
        return selected['path']

    def display_csv_preview(self, csv_path: str) -> None:
        """
        Display a preview of CSV file statistics.

        Args:
            csv_path: Path to the CSV file.
        """
        print("\n" + "=" * 80)
        print("🎞️ 真实数据回测 - Real Data Backtest")
        print("=" * 80)
        print(f"   数据文件: {csv_path}")

        summary = self.data_manager.get_csv_summary(csv_path)
        if summary:
            print(f"   数据行数: {summary['rows']}")
            print(f"   平均 Bid:  {summary['avg_bid']:.4f}")
            print(f"   平均 Ask:  {summary['avg_ask']:.4f}")
            print(f"   平均 Spread: {summary['avg_spread']:.4f}")

        print("-" * 80)

    def collect_backtest_config(self) -> Optional[Dict]:
        """
        Collect backtest configuration from user.

        Returns:
            Dict or None: Configuration dict with min_profit and op_offset,
                         or None if cancelled.
        """
        print("\n⚙️ 回测配置")

        min_profit = self.validator.get_float(
            "   最小盈利率 % (默认=0.3): ",
            default=0.3,
            min_val=0.0,
            max_val=100.0
        )
        if min_profit is None:
            return None

        op_offset = self.validator.get_float(
            "   OP价格偏移 (默认=0.02, 模拟套利空间): ",
            default=0.02,
            min_val=0.0,
            max_val=1.0
        )
        if op_offset is None:
            return None

        print(f"\n   最小盈利率: {min_profit:.2f}%")
        print(f"   OP价格偏移: {op_offset}")
        print("-" * 80)

        return {
            'min_profit_rate': min_profit / 100,  # Convert to decimal
            'op_spread_offset': op_offset
        }

    def collect_synthetic_config(self) -> Optional[Dict]:
        """
        Collect synthetic backtest configuration from user.

        Returns:
            Dict or None: Configuration dict with num_events and duration_days,
                         or None if cancelled.
        """
        print("\n" + "=" * 80)
        print("🔄 模拟回测 - Synthetic Backtest (OU Process)")
        print("=" * 80)

        num_events = self.validator.get_int(
            "   事件数量 (默认=15): ",
            default=15,
            min_val=1,
            max_val=1000
        )
        if num_events is None:
            return None

        duration_days = self.validator.get_int(
            "   持续天数 (默认=3): ",
            default=3,
            min_val=1,
            max_val=365
        )
        if duration_days is None:
            return None

        print(f"\n   事件数: {num_events}, 天数: {duration_days}")

        return {
            'num_events': num_events,
            'duration_days': duration_days
        }

    async def run_csv_backtest(self, csv_path: str, config: Dict) -> Optional[Dict]:
        """
        Execute a CSV-based backtest.

        Args:
            csv_path: Path to CSV data file.
            config: Configuration dict from collect_backtest_config().

        Returns:
            Dict or None: Results summary, or None if failed.
        """
        print("\n🚀 正在运行回测...")

        engine = SharedBacktestEngine(
            bot_profiles=['retail', 'semi_pro', 'pro'],
            min_profit_rate=config['min_profit_rate'],
            data_source=DataSource.CSV,
            csv_path=csv_path,
            op_spread_offset=config['op_spread_offset']
        )

        results = await engine.run_backtest()

        # Display results
        visualizer = BacktestVisualizer(results, engine.stats)
        summary = visualizer.print_report()

        return summary

    async def run_synthetic_backtest(self, config: Dict) -> Optional[Dict]:
        """
        Execute a synthetic (OU process) backtest.

        Args:
            config: Configuration dict from collect_synthetic_config().

        Returns:
            Dict or None: Results summary, or None if failed.
        """
        print("\n🚀 正在运行模拟回测...")

        engine = SharedBacktestEngine(
            bot_profiles=['retail', 'semi_pro', 'pro'],
            seed=42,
            min_profit_rate=0.003
        )

        results = await engine.run_backtest(
            num_events=config['num_events'],
            events_per_day=5,
            duration_days=config['duration_days']
        )

        # Display results
        visualizer = BacktestVisualizer(results, engine.stats)
        summary = visualizer.print_report()

        return summary


# ========== 市场扫描会话管理器 ==========
class MarketSession:
    """
    Market scanning and recording session manager.

    Encapsulates the workflow for scanning markets, selecting one,
    and optionally recording data.
    """

    def __init__(self):
        """Initialize the MarketSession."""
        self.validator = InputValidator()
        self.scanner = None

    def scan_markets(
        self,
        max_spread: float = 0.05,
        min_volume: float = 1000,
        min_price: float = 0.20,
        max_price: float = 0.80,
        limit: int = 20
    ) -> List[MarketInfo]:
        """
        Scan for active markets matching criteria.

        Args:
            max_spread: Maximum allowed spread.
            min_volume: Minimum volume requirement.
            min_price: Minimum mid-price filter.
            max_price: Maximum mid-price filter.
            limit: Maximum number of markets to return.

        Returns:
            List[MarketInfo]: List of matching markets.
        """
        print("\n" + "=" * 70)
        print("🔍 Market Scanner - Polymarket Gamma API")
        print("=" * 70)

        self.scanner = MarketScanner(
            max_spread=max_spread,
            min_volume=min_volume,
            min_price=min_price,
            max_price=max_price
        )

        print("\n📡 正在扫描热门市场 (仅显示价格在 20%-80% 之间的活跃市场)...")

        return self.scanner.scan_top_markets(limit=limit)

    def display_markets(self, markets: List[MarketInfo]) -> None:
        """
        Display markets in a formatted table.

        Args:
            markets: List of markets to display.
        """
        if not markets:
            print("❌ 未找到符合条件的市场")
            return

        display_markets = markets[:10]

        print("\n" + "=" * 110)
        print("📊 TOP 10 活跃市场 (价格 20%-80%，按交易量排序)")
        print("=" * 110)
        print(f"{'#':<4} {'Market ID':<20} {'Question':<35} {'Price':>8} {'Volume':>12} {'Spread':>8}")
        print("-" * 110)

        for idx, m in enumerate(display_markets, 1):
            mid_price = (m.best_bid + m.best_ask) / 2
            question = m.question[:32] + "..." if len(m.question) > 35 else m.question
            market_id_short = m.market_id[:18] + ".." if len(m.market_id) > 20 else m.market_id
            price_str = f"{mid_price:.1%}"
            volume_str = f"${m.volume:,.0f}"
            spread_str = f"{m.spread:.4f}"

            print(f"{idx:<4} {market_id_short:<20} {question:<35} {price_str:>8} {volume_str:>12} {spread_str:>8}")

        print("-" * 110)
        print(f"共找到 {len(markets)} 个符合条件的市场 (显示前10个)")
        print("=" * 110)

    def select_market(self, markets: List[MarketInfo]) -> Optional[MarketInfo]:
        """
        Let user select a market from the list.

        Args:
            markets: List of available markets.

        Returns:
            MarketInfo or None: Selected market or None if cancelled.
        """
        if not markets:
            return None

        display_markets = markets[:10]

        print("\n📝 市场选择")
        print("-" * 40)

        selection = self.validator.get_int(
            "请输入你想监控的市场序号 (1-10) 或 'b' 返回: ",
            min_val=1,
            max_val=len(display_markets)
        )

        if selection is None:
            return None

        selected = display_markets[selection - 1]

        # Display confirmation
        print("\n" + "=" * 70)
        print(f"✅ 已锁定市场:")
        print(f"   ID:       {selected.market_id}")
        print(f"   Question: {selected.question}")
        print(f"   Volume:   ${selected.volume:,.0f}")
        print(f"   Spread:   {selected.spread:.4f}")
        print(f"   Bid/Ask:  {selected.best_bid:.3f} / {selected.best_ask:.3f}")
        print("=" * 70)

        return selected

    def start_recording(
        self,
        market_id: str,
        duration_minutes: int = 60,
        interval_seconds: int = 3
    ) -> Optional[str]:
        """
        Start recording market data.

        Args:
            market_id: Market ID to record.
            duration_minutes: Recording duration in minutes.
            interval_seconds: Sampling interval in seconds.

        Returns:
            str or None: Path to saved CSV file, or None if cancelled/failed.
        """
        print(f"\n🎯 已锁定市场 ID: {market_id}")
        print("\n" + "-" * 50)

        if not self.validator.get_confirmation("是否开始录制数据? (y/n): "):
            print("\n📝 已跳过录制")
            print(f"   你可以稍后使用此 Market ID 进行录制:")
            print(f"   {market_id}")
            return None

        # Get duration from user
        duration = self.validator.get_int(
            "录制时长 (分钟, 默认=60): ",
            default=60,
            min_val=1,
            max_val=1440  # Max 24 hours
        )

        if duration is None:
            duration = 60

        # Start recording
        recorder = DataRecorder(output_dir="data")

        try:
            csv_path = recorder.record(
                market_id=market_id,
                duration_minutes=duration,
                interval_seconds=interval_seconds
            )
            print(f"\n📁 数据已保存至: {csv_path}")
            return csv_path

        except KeyboardInterrupt:
            print("\n录制已安全停止")
            return None


# ========== 钱包检查器 ==========
class WalletChecker:
    """
    Wallet connection and balance checker.

    Encapsulates all wallet verification logic for startup checks.
    """

    # Balance thresholds
    LOW_GAS_THRESHOLD = 0.1
    LOW_USDC_THRESHOLD = 10.0

    def __init__(self):
        """Initialize the WalletChecker."""
        self.wallet_manager = None
        self.wallet_address = None

    def check(self) -> bool:
        """
        Perform complete wallet check.

        Verifies:
        1. Wallet address is configured
        2. Connection to Polygon network works
        3. Balance levels are adequate

        Returns:
            bool: True if all checks pass, False otherwise.
        """
        print("\n" + "=" * 70)
        print("🔗 Real Wallet Check - Polygon Network")
        print("=" * 70)

        # Step 1: Get wallet address from environment
        self.wallet_address = os.getenv("MY_WALLET_ADDRESS") or os.getenv("WALLET_ADDRESS")

        if not self.wallet_address:
            print("❌ Error: 钱包地址未配置")
            print("   请在 .env 文件中设置 MY_WALLET_ADDRESS")
            print("=" * 70 + "\n")
            return False

        # Step 2: Initialize and connect
        self.wallet_manager = WalletManager()

        print("\n📡 Connecting to Polygon Network...")
        if not self.wallet_manager.connect():
            print("❌ Connection Failed!")
            print("   - 检查网络连接")
            print("   - 尝试其他 RPC 节点")
            print("=" * 70 + "\n")
            return False

        print(f"✅ Connection Status: Connected")
        print(f"   RPC: {self.wallet_manager.rpc_url}")

        # Step 3: Verify chain ID
        chain_id = self.wallet_manager.get_chain_id()
        if chain_id == 137:
            print(f"✅ Chain ID: {chain_id} (Polygon Mainnet)")
        else:
            print(f"⚠️  Chain ID: {chain_id} (Expected: 137 for Polygon)")

        # Step 4: Display current block
        block_number = self.wallet_manager.get_current_block()
        if block_number:
            print(f"📦 Current Block: {block_number:,}")

        # Step 5: Fetch and display balances
        print(f"\n💰 Wallet: {self.wallet_address}")
        print("-" * 70)

        balances = self.wallet_manager.get_balance(self.wallet_address)
        matic_balance = balances["matic"]
        usdc_balance = balances["usdc"]

        print(f"   MATIC Balance: {matic_balance:.6f} MATIC")
        print(f"   USDC Balance:  {usdc_balance:.2f} USDC")

        # Step 6: Check balance thresholds
        warnings = []
        if matic_balance < self.LOW_GAS_THRESHOLD:
            warnings.append(f"⚠️  Low Gas: MATIC={matic_balance:.6f} (建议 >= {self.LOW_GAS_THRESHOLD})")

        if usdc_balance < self.LOW_USDC_THRESHOLD:
            warnings.append(f"⚠️  Low Funds: USDC={usdc_balance:.2f} (建议 >= ${self.LOW_USDC_THRESHOLD})")

        if warnings:
            print("\n" + "!" * 70)
            for w in warnings:
                print(f"   {w}")
            print("!" * 70)

        print("\n" + "=" * 70)
        print("✅ Wallet check completed.")
        print("=" * 70 + "\n")

        return True