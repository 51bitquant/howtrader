from howtrader.app.cta_strategy.backtesting import BacktestingEngine, OptimizationSetting
from howtrader.app.cta_strategy.strategies.turtle_signal_strategy import TurtleSignalStrategy
from datetime import datetime

engine = BacktestingEngine()
engine.set_parameters(
    vt_symbol="BTCUSDT.BINANCE",
    interval="1h",
    start=datetime(2017, 1, 1),
    end=datetime(2019, 11, 30),
    rate=1 / 10000,
    slippage=0.5,
    size=1,
    pricetick=0.5,
    capital=1_000_000,
)
engine.add_strategy(TurtleSignalStrategy, {})

engine.load_data()
engine.run_backtesting()
df = engine.calculate_result()
engine.calculate_statistics()
engine.show_chart()

import pandas as pd
from datetime import datetime
import matplotlib.pyplot as plt
import numpy as np

pd.set_option('mode.chained_assignment', None)


def calculate_trades_result(trades):
    """
    Deal with trade data
    """
    dt, direction, offset, price, volume = [], [], [], [], []
    for i in trades.values():
        dt.append(i.datetime)
        direction.append(i.direction.value)
        offset.append(i.offset.value)
        price.append(i.price)
        volume.append(i.volume)

    # Generate DataFrame with datetime, direction, offset, price, volume
    df = pd.DataFrame()
    df["direction"] = direction
    df["offset"] = offset
    df["price"] = price
    df["volume"] = volume

    df["current_time"] = dt
    df["last_time"] = df["current_time"].shift(1)

    # Calculate trade amount
    df["amount"] = df["price"] * df["volume"]
    df["acum_amount"] = df["amount"].cumsum()

    # Calculate pos, net pos(with direction), acumluation pos(with direction)
    def calculate_pos(df):
        if df["direction"] == "多":
            result = df["volume"]
        else:
            result = - df["volume"]

        return result

    df["pos"] = df.apply(calculate_pos, axis=1)

    df["net_pos"] = df["pos"].cumsum()
    df["acum_pos"] = df["volume"].cumsum()

    # Calculate trade result, acumulation result
    # ej: trade result(buy->sell) means (new price - old price) * volume
    df["result"] = -1 * df["pos"] * df["price"]
    df["acum_result"] = df["result"].cumsum()

    # Filter column data when net pos comes to zero
    def get_acum_trade_result(df):
        if df["net_pos"] == 0:
            return df["acum_result"]

    df["acum_trade_result"] = df.apply(get_acum_trade_result, axis=1)

    def get_acum_trade_volume(df):
        if df["net_pos"] == 0:
            return df["acum_pos"]

    df["acum_trade_volume"] = df.apply(get_acum_trade_volume, axis=1)

    def get_acum_trade_duration(df):
        if df["net_pos"] == 0:
            return df["current_time"] - df["last_time"]

    df["acum_trade_duration"] = df.apply(get_acum_trade_duration, axis=1)

    def get_acum_trade_amount(df):
        if df["net_pos"] == 0:
            return df["acum_amount"]

    df["acum_trade_amount"] = df.apply(get_acum_trade_amount, axis=1)

    # Select row data with net pos equil to zero
    df = df.dropna()

    return df


def generate_trade_df(trades, size, rate, slippage, capital):
    """
    Calculate trade result from increment
    """
    df = calculate_trades_result(trades)

    trade_df = pd.DataFrame()
    trade_df["close_direction"] = df["direction"]
    trade_df["close_time"] = df["current_time"]
    trade_df["close_price"] = df["price"]
    trade_df["pnl"] = df["acum_trade_result"] - \
                      df["acum_trade_result"].shift(1).fillna(0)

    trade_df["volume"] = df["acum_trade_volume"] - \
                         df["acum_trade_volume"].shift(1).fillna(0)
    trade_df["duration"] = df["current_time"] - \
                           df["last_time"]
    trade_df["turnover"] = df["acum_trade_amount"] - \
                           df["acum_trade_amount"].shift(1).fillna(0)

    trade_df["commission"] = trade_df["turnover"] * rate
    trade_df["slipping"] = trade_df["volume"] * size * slippage

    trade_df["net_pnl"] = trade_df["pnl"] - \
                          trade_df["commission"] - trade_df["slipping"]

    result = calculate_base_net_pnl(trade_df, capital)
    return result


def calculate_base_net_pnl(df, capital):
    """
    Calculate statistic base on net pnl
    """
    df["acum_pnl"] = df["net_pnl"].cumsum()
    df["balance"] = df["acum_pnl"] + capital
    df["return"] = np.log(
        df["balance"] / df["balance"].shift(1)
    ).fillna(0)
    df["highlevel"] = (
        df["balance"].rolling(
            min_periods=1, window=len(df), center=False).max()
    )
    df["drawdown"] = df["balance"] - df["highlevel"]
    df["ddpercent"] = df["drawdown"] / df["highlevel"] * 100

    df.reset_index(drop=True, inplace=True)

    return df


def buy2sell(df, capital):
    """
    Generate DataFrame with only trade from buy to sell
    """
    buy2sell = df[df["close_direction"] == "空"]
    result = calculate_base_net_pnl(buy2sell, capital)
    return result


def short2cover(df, capital):
    """
    Generate DataFrame with only trade from short to cover
    """
    short2cover = df[df["close_direction"] == "多"]
    result = calculate_base_net_pnl(short2cover, capital)
    return result


def statistics_trade_result(df, capital, show_chart=True):
    """"""
    end_balance = df["balance"].iloc[-1]
    max_drawdown = df["drawdown"].min()
    max_ddpercent = df["ddpercent"].min()

    pnl_medio = df["net_pnl"].mean()
    trade_count = len(df)
    duration_medio = df["duration"].mean().total_seconds() / 3600
    commission_medio = df["commission"].mean()
    slipping_medio = df["slipping"].mean()

    win = df[df["net_pnl"] > 0]
    win_amount = win["net_pnl"].sum()
    win_pnl_medio = win["net_pnl"].mean()
    win_duration_medio = win["duration"].mean().total_seconds() / 3600
    win_count = len(win)

    loss = df[df["net_pnl"] < 0]
    loss_amount = loss["net_pnl"].sum()
    loss_pnl_medio = loss["net_pnl"].mean()
    loss_duration_medio = loss["duration"].mean().total_seconds() / 3600
    loss_count = len(loss)

    winning_rate = win_count / trade_count
    win_loss_pnl_ratio = - win_pnl_medio / loss_pnl_medio

    total_return = (end_balance / capital - 1) * 100
    return_drawdown_ratio = -total_return / max_ddpercent

    output(f"起始资金：\t{capital:,.2f}")
    output(f"结束资金：\t{end_balance:,.2f}")
    output(f"总收益率：\t{total_return:,.2f}%")
    output(f"最大回撤: \t{max_drawdown:,.2f}")
    output(f"百分比最大回撤: {max_ddpercent:,.2f}%")
    output(f"收益回撤比：\t{return_drawdown_ratio:,.2f}")

    output(f"总成交次数:\t{trade_count}")
    output(f"盈利成交次数:\t{win_count}")
    output(f"亏损成交次数:\t{loss_count}")
    output(f"胜率:\t\t{winning_rate:,.2f}")
    output(f"盈亏比:\t\t{win_loss_pnl_ratio:,.2f}")

    output(f"平均每笔盈亏:\t{pnl_medio:,.2f}")
    output(f"平均持仓小时:\t{duration_medio:,.2f}")
    output(f"平均每笔手续费:\t{commission_medio:,.2f}")
    output(f"平均每笔滑点:\t{slipping_medio:,.2f}")

    output(f"总盈利金额:\t{win_amount:,.2f}")
    output(f"盈利交易均值:\t{win_pnl_medio:,.2f}")
    output(f"盈利持仓小时:\t{win_duration_medio:,.2f}")

    output(f"总亏损金额:\t{loss_amount:,.2f}")
    output(f"亏损交易均值:\t{loss_pnl_medio:,.2f}")
    output(f"亏损持仓小时:\t{loss_duration_medio:,.2f}")

    if not show_chart:
        return

    plt.figure(figsize=(10, 12))

    acum_pnl_plot = plt.subplot(3, 1, 1)
    acum_pnl_plot.set_title("Balance Plot")
    df["balance"].plot(legend=True)

    pnl_plot = plt.subplot(3, 1, 2)
    pnl_plot.set_title("Pnl Per Trade")
    df["net_pnl"].plot(legend=True)

    distribution_plot = plt.subplot(3, 1, 3)
    distribution_plot.set_title("Trade Pnl Distribution")
    df["net_pnl"].hist(bins=100)

    plt.show()


def output(msg):
    """
    Output message with datetime.
    """
    print(f"{datetime.now()}\t{msg}")


def exhaust_trade_result(
        trades,
        size: int = 10,
        rate: float = 0.0,
        slippage: float = 0.0,
        capital: int = 1000000,
        show_long_short_condition=True
):
    """
    Exhaust all trade result.
    """

    total_trades = generate_trade_df(trades, size, rate, slippage, capital)
    statistics_trade_result(total_trades, capital)

    if not show_long_short_condition:
        return
    long_trades = buy2sell(total_trades, capital)
    short_trades = short2cover(total_trades, capital)

    output("-----------------------")
    output("纯多头交易")
    statistics_trade_result(long_trades, capital)

    output("-----------------------")
    output("纯空头交易")
    statistics_trade_result(short_trades, capital)


exhaust_trade_result(engine.trades, size=1, rate=8 / 10000, slippage=0.5)
