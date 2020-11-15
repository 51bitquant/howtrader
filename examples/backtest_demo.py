from howtrader.app.cta_strategy.backtesting import BacktestingEngine, OptimizationSetting
from howtrader.trader.object import Interval
from datetime import datetime
from howtrader.app.cta_strategy.strategies.atr_rsi_strategy import AtrRsiStrategy

engine = BacktestingEngine()
engine.set_parameters(
    vt_symbol="BTCUSDT.BINANCE",
    interval=Interval.MINUTE,
    start=datetime(2019, 10, 1),
    end=datetime(2020, 5, 1),
    rate=6/ 10000,
    slippage=0,
    size=1,
    pricetick=0.01,
    capital=1_000_000,
)

engine.add_strategy(AtrRsiStrategy, {})


engine.load_data()
engine.run_backtesting()
df = engine.calculate_result()
engine.calculate_statistics()
engine.show_chart()

setting = OptimizationSetting()
setting.set_target("sharpe_ratio")
setting.add_parameter("atr_length", 3, 39, 1)
setting.add_parameter("atr_ma_length", 10, 30, 1)

engine.run_ga_optimization(setting)