
from howtrader.app.cta_strategy.backtesting import BacktestingEngine, OptimizationSetting
from strategies.atr_rsi_strategy import AtrRsiStrategy
from strategies.boll_channel_strategy import BollChannelStrategy
from howtrader.trader.object import Interval
from datetime import datetime


def run_backtesting(strategy_class, setting, vt_symbol, interval, start, end, rate, slippage, size, pricetick, capital):
    engine = BacktestingEngine()
    engine.set_parameters(
        vt_symbol=vt_symbol,
        interval=interval,
        start=start,
        end=end,
        rate=rate,
        slippage=slippage,
        size=size,
        pricetick=pricetick,
        capital=capital
    )
    engine.add_strategy(strategy_class, setting)
    engine.load_data()
    engine.run_backtesting()
    df = engine.calculate_result()
    return df

def show_portafolio(df):
    engine = BacktestingEngine()
    engine.calculate_statistics(df)
    engine.show_chart(df)


df1 = run_backtesting(
    strategy_class=AtrRsiStrategy,
    setting={},
    vt_symbol="BTCUSDT.BINANCE",
    interval=Interval.MINUTE,
    start=datetime(2020, 1, 1),
    end=datetime(2021, 1, 1),
    rate=4/10000,
    slippage=0.2,
    size=300,
    pricetick=0.2,
    capital=1_000_000,
    )


df2 = run_backtesting(
    strategy_class=BollChannelStrategy,
    setting={'fixed_size': 16},
    vt_symbol="BTCUSDT.BINANCE",
    interval=Interval.MINUTE,
    start=datetime(2020, 1, 1),
    end=datetime(2021, 1, 1),
    rate=4/10000,
    slippage=1,
    size=10,
    pricetick=1,
    capital=1000000,
    )

print(df1)
print(df2)

dfp = df1 + df2
dfp =dfp.dropna()
show_portafolio(dfp)