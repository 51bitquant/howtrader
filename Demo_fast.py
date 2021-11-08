"""
    简单EMA策略.

"""
from jiamtrader.trader.object import Interval
from datetime import datetime
from jiamtrader.app.cta_strategy.backtesting import BacktestingEngine

from strategies.double_adx_strategy import AdxStrategy

if __name__ == '__main__':
    # 回测引擎初始化
    engine = BacktestingEngine()

    # 设置交易对产品的参数
    engine.set_parameters(
        vt_symbol="BTCUSDT.BINANCE",  # 交易的标的
        interval=Interval.MINUTE,
        start=datetime(2020, 1, 1),  # 开始时间
        rate=7.5 / 10000,  # 手续费
        slippage=0.5,  # 交易滑点
        size=1,  # 合约乘数
        pricetick=0.5,  # 8500.5 8500.01
        capital=100000,  # 初始资金
        # end=datetime(2018, 6, 1)  # 结束时间
    )

    # 添加策略
    engine.add_strategy(AdxStrategy, {})

    # 加载
    engine.load_data()

    # 运行回测
    engine.run_backtesting()

    # 统计结果
    engine.calculate_result()

    # 计算策略的统计指标 Sharp ratio, drawdown
    engine.calculate_statistics()

    # 绘制图表
    engine.show_chart()