
from datetime import datetime
from importlib import reload

import howtrader.app.portfolio_strategy
reload(howtrader.app.portfolio_strategy)

from howtrader.app.portfolio_strategy import BacktestingEngine
from howtrader.trader.constant import Interval

import howtrader.app.portfolio_strategy.strategies.pair_trading_strategy as stg
reload(stg)
from howtrader.app.portfolio_strategy.strategies.pair_trading_strategy import PairTradingStrategy


engine = BacktestingEngine()
engine.set_parameters(
    vt_symbols=["BTCUSDT.BINANCE", "ETHUSDT.BINANCE"],
    interval=Interval.MINUTE,
    start=datetime(2019, 1, 1),
    end=datetime(2020, 4, 30),
    rates={
        "BTCUSDT.BINANCE": 0/10000,
        "ETHUSDT.BINANCE": 0/10000
    },
    slippages={
        "BTCUSDT.BINANCE": 0,
        "ETHUSDT.BINANCE": 0
    },
    sizes={
        "BTCUSDT.BINANCE": 1,
        "ETHUSDT.BINANCE": 20
    },
    priceticks={
        "BTCUSDT.BINANCE": 0.01,
        "ETHUSDT.BINANCE": 0.01
    },
    capital=1_000_000,
)

setting = {
    "boll_window": 20,
    "boll_dev": 1,
}
engine.add_strategy(PairTradingStrategy, setting)


engine.load_data()
engine.run_backtesting()
df = engine.calculate_result()
engine.calculate_statistics()
engine.show_chart()