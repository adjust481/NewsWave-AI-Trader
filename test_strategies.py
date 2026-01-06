# test_strategies.py
import sys
import os
from datetime import datetime

# 💡 路径黑魔法：确保能找到 infra 和 strategies
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from strategies.ou_arb import OUArbStrategy
from strategies.sniper import SniperStrategy
from infra.logging_utils import logger

def test_sniper():
    print("\n" + "="*50)
    print("🔫 测试 1: 狙击手策略 (SniperStrategy)")
    print("="*50)
    
    # 初始化策略：设定目标价 0.50，最小价差 0.02 (即 0.48 以下买入)
    # 注意：如果你的 __init__ 参数不同，请在这里修改
    sniper = SniperStrategy(name="Sniper_001", target_price=0.50, min_gap=0.02)
    
    # --- 场景 A: 价格太高，不该买 ---
    state_high = {"best_ask": 0.55, "best_bid": 0.54}
    orders = sniper.on_tick(state_high)
    print(f"场景 [价格 0.55 > 目标 0.50]: 指令数={len(orders)}")
    if not orders:
        print("✅ pass (保持静默)")
    else:
        print(f"❌ fail (意外开火): {orders}")

    # --- 场景 B: 价格极低，应该买 ---
    state_low = {"best_ask": 0.40, "best_bid": 0.39}
    orders = sniper.on_tick(state_low)
    print(f"场景 [价格 0.40 < 目标 0.50]: 指令数={len(orders)}")
    
    if orders and orders[0].side == "BUY":
        print(f"✅ pass (成功开火): {orders[0]}")
    else:
        print(f"❌ fail (未开火)")

    # --- 场景 C: 价格高于目标，应该卖出止盈 (如果你加了 Exit 逻辑) ---
    state_profit = {"best_ask": 0.60, "best_bid": 0.55} # Bid 0.55 > Target 0.50
    orders = sniper.on_tick(state_profit)
    print(f"场景 [Bid 0.55 > 目标 0.50]: 指令数={len(orders)}")
    
    if orders and orders[0].side == "SELL":
        print(f"✅ pass (触发止盈): {orders[0]}")
    else:
        print("⚠️ note (未触发止盈，取决于你是否写了 Exit 逻辑)")

def test_ou_arb():
    print("\n" + "="*50)
    print("⚖️  测试 2: OU 套利策略 (OUArbStrategy)")
    print("="*50)
    
    ou = OUArbStrategy(name="OU_Worker")
    
    # --- 场景 A: 无价差 ---
    state_flat = {
        "pm_ask": 0.50, "pm_bid": 0.49,
        "op_ask": 0.50, "op_bid": 0.49
    }
    # 假设你的代码需要 op_bid - pm_ask > threshold
    # 这里 0.49 - 0.50 = -0.01 (无利可图)
    orders = ou.on_tick(state_flat)
    print(f"场景 [无价差]: 指令数={len(orders)}")
    if not orders:
         print("✅ pass")
    else:
         print(f"❌ fail: {orders}")

    # --- 场景 B: 巨大价差 (OP 贵，PM 便宜) ---
    state_opportunity = {
        "pm_ask": 0.40, "pm_bid": 0.39, # PM 卖价 0.40 (我们可以买)
        "op_ask": 0.61, "op_bid": 0.60  # OP 买价 0.60 (我们可以卖)
    }
    # 价差 = 0.60 - 0.40 = 0.20 (暴利)
    orders = ou.on_tick(state_opportunity)
    print(f"场景 [价差 0.20]: 指令数={len(orders)}")
    
    if len(orders) >= 1: # 可能是 1 个组合指令，也可能是 2 个单腿指令
        print(f"✅ pass: {orders}")
    else:
        print("❌ fail (错失机会)")

if __name__ == "__main__":
    test_sniper()
    test_ou_arb()
