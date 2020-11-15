
from howtrader.app.spread_trading.backtesting import BacktestingEngine
from howtrader.app.spread_trading.strategies.statistical_arbitrage_strategy import (
    StatisticalArbitrageStrategy
)
from howtrader.app.spread_trading.base import LegData, SpreadData
from datetime import datetime



spread = SpreadData(
    name="IF-Spread",
    legs=[LegData("IF1911.CFFEX"), LegData("IF1912.CFFEX")],
    price_multipliers={"IF1911.CFFEX": 1, "IF1912.CFFEX": -1},
    trading_multipliers={"IF1911.CFFEX": 1, "IF1912.CFFEX": -1},
    active_symbol="IF1911.CFFEX",
    inverse_contracts={"IF1911.CFFEX": False, "IF1912.CFFEX": False},
    min_volume=1
)

#%%
engine = BacktestingEngine()
engine.set_parameters(
    spread=spread,
    interval="1m",
    start=datetime(2019, 6, 10),
    end=datetime(2019, 11, 10),
    rate=0,
    slippage=0,
    size=300,
    pricetick=0.2,
    capital=1_000_000,
)
engine.add_strategy(StatisticalArbitrageStrategy, {})

engine.load_data()
engine.run_backtesting()
df = engine.calculate_result()
engine.calculate_statistics()
engine.show_chart()