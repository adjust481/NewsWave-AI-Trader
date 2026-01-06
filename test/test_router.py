# test_router.py
from strategies.router import StrategyRouter

def show(label, orders):
    print(f"\n[{label}] 指令数 = {len(orders)}")
    for o in orders:
        print(" ", o)

if __name__ == "__main__":
    router = StrategyRouter()

    # 场景 1：指定用套利模式
    ms_arb = {
        "mode": "arb",
        "pm_ask": 0.45,
        "pm_bid": 0.44,
        "op_ask": 0.55,
        "op_bid": 0.54,
        "gas_cost_usd": 0.0,
    }
    orders1 = router.on_tick(ms_arb)
    show("mode=arb (应该走 OU 套利)", orders1)

    # 场景 2：指定用狙击模式
    ms_sniper = {
        "mode": "sniper",
        "current_ask": 0.40,
        "gas_cost_usd": 0.0,
    }
    orders2 = router.on_tick(ms_sniper)
    show("mode=sniper (应该走 Sniper)", orders2)
