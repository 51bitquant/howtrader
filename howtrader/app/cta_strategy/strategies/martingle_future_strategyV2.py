from howtrader.app.cta_strategy import (
    CtaTemplate,
    StopOrder
)

from howtrader.trader.object import TickData, BarData, TradeData, OrderData
from howtrader.app.cta_strategy.engine import CtaEngine
from howtrader.trader.object import Status, Direction, ContractData, AccountData
from howtrader.trader.utility import ArrayManager, BarGenerator
from typing import Optional
from decimal import Decimal


class MartingleFutureStrategyV2(CtaTemplate):
    """
    1. 马丁策略.
    币安邀请链接: https://www.binancezh.pro/cn/futures/ref/51bitquant
    币安合约邀请码：51bitquant
    """

    """
    1. 开仓条件是 最高价回撤一定比例 4%
    2. 止盈2%
    3. 加仓: 入场后, 价格最低下跌超过5%， 最低点反弹上去1%, 那么就可以加仓. 均价止盈2%.
    """
    author = "51bitquant"

    # 策略的核心参数.
    donchian_window = 2880  # two days
    open_pos_when_drawdown_pct = 0.04  # 最高值回撤2%时开仓.

    dump_down_pct = 0.04  #
    bounce_back_pct = 0.01  #

    exit_profit_pct = 0.02  # 出场平仓百分比 2%
    initial_trading_value = 1000  # 首次开仓价值 1000USDT.
    trading_value_multiplier = 1.3  # 加仓的比例.
    max_increase_pos_times = 7  # 最大的加仓次数
    trading_fee = 0.00075

    # 变量
    avg_price = 0.0  # 当前持仓的平均价格.
    last_entry_price = 0.0  # 上一次入场的价格.
    current_pos = 0.0  # 当前的持仓的数量.
    current_increase_pos_times = 0  # 当前的加仓的次数.

    upband = 0.0
    downband = 0.0
    entry_lowest = 0.0  # 进场之后的最低价.

    # 统计总的利润.
    total_profit = 0

    parameters = ["donchian_window", "open_pos_when_drawdown_pct", "dump_down_pct", "bounce_back_pct",
                  "exit_profit_pct", "initial_trading_value",
                  "trading_value_multiplier", "max_increase_pos_times", "trading_fee"]

    variables = ["avg_price", "last_entry_price", "current_pos", "current_increase_pos_times",
                 "upband", "downband", "entry_lowest", "total_profit"]

    def __init__(self, cta_engine: CtaEngine, strategy_name, vt_symbol, setting):
        """"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)

        self.last_filled_order: Optional[OrderData, None] = None
        self.tick: Optional[TickData, None] = None
        self.contract: Optional[ContractData, None] = None
        self.account: Optional[AccountData, None] = None
        self.bg = BarGenerator(self.on_bar) # generate 1min bar.
        self.am = ArrayManager(3000)  # default is 100, we need 3000

        # self.cta_engine.event_engine.register(EVENT_ACCOUNT + 'BINANCE.币名称', self.process_acccount_event)
        # self.cta_engine.event_engine.register(EVENT_ACCOUNT + "BINANCE.USDT", self.process_account_event)

        self.buy_orders = []  # 买单id列表。
        self.sell_orders = []  # 卖单id列表。
        self.min_notional = 11  # 最小的交易金额.

    def on_init(self):
        """
        Callback when strategy is inited.
        """
        self.write_log("策略初始化")
        self.load_bar(3)  # 加载3天的数据.

    def on_start(self):
        """
        Callback when strategy is started.
        """
        self.write_log("策略启动")

    def on_stop(self):
        """
        Callback when strategy is stopped.
        """
        self.write_log("策略停止")

    # def process_account_event(self, event: Event):
    #     self.account: AccountData = event.data
    #     if self.account:
    #         print(
    #             f"self.account: available{self.account.available}, balance:{self.account.balance}, frozen: {self.account.frozen}")

    def on_tick(self, tick: TickData):
        """
        Callback of new tick data update.
        """
        if tick.bid_price_1 > 0 and tick.ask_price_1 > 0:
            self.tick = tick
            self.bg.update_tick(tick)

    def on_bar(self, bar: BarData):
        """
        Callback of new bar data update.
        """
        am = self.am
        am.update_bar(bar)
        if not am.inited:
            return

        current_close = am.close_array[-1]
        current_low = am.low_array[-1]

        self.upband, self.downband = am.donchian(self.donchian_window, array=False)  # 返回最新的布林带值.

        dump_pct = self.upband / current_low - 1

        if self.entry_lowest > 0:
            self.entry_lowest = min(self.entry_lowest, bar.low_price)

        # 回调一定比例的时候.
        if self.current_pos * current_close < self.min_notional:
            # 每次下单要大于等于10USDT, 为了简单设置11USDT.
            if dump_pct >= self.open_pos_when_drawdown_pct and len(self.buy_orders) == 0:
                # 这里没有仓位.
                # 重置当前的数据.
                self.cancel_all()
                self.current_increase_pos_times = 0
                self.avg_price = 0
                self.entry_lowest = 0

                price = current_close
                vol = self.initial_trading_value / price
                orderids = self.buy(Decimal(price), Decimal(vol))
                self.buy_orders.extend(orderids)  # 以及已经下单的orderids.
        else:
            if len(self.sell_orders) <= 0 < self.avg_price:
                # 有利润平仓的时候
                # 清理掉其他买单.

                profit_percent = bar.close_price / self.avg_price - 1
                if profit_percent >= self.exit_profit_pct:
                    self.cancel_all()
                    orderids = self.short(Decimal(bar.close_price), Decimal(abs(self.current_pos)))
                    self.sell_orders.extend(orderids)

            if self.entry_lowest > 0 >= len(self.buy_orders):
                # 考虑加仓的条件: 1） 当前有仓位,且仓位值要大于11USDTyi以上，2）加仓的次数小于最大的加仓次数，3）当前的价格比上次入场的价格跌了一定的百分比。

                dump_down_pct = self.last_entry_price / self.entry_lowest - 1
                bounce_back_pct = bar.close_price / self.entry_lowest - 1

                if self.current_increase_pos_times <= self.max_increase_pos_times and dump_down_pct >= self.dump_down_pct and bounce_back_pct >= self.bounce_back_pct:
                    # ** 表示的是乘方.
                    self.cancel_all()  # 清理其他卖单.
                    increase_pos_value = self.initial_trading_value * self.trading_value_multiplier ** self.current_increase_pos_times
                    # if self.account and self.account.available >= increase_pos_value:
                    price = bar.close_price
                    vol = increase_pos_value / price
                    orderids = self.buy(Decimal(price), Decimal(vol))
                    self.buy_orders.extend(orderids)

        self.put_event()

    def on_order(self, order: OrderData):
        """
        Callback of new order data update.
        """
        if order.status == Status.ALLTRADED:
            if order.direction == Direction.LONG:
                # 买单成交.

                self.current_increase_pos_times += 1
                self.last_entry_price =float(order.price)  # 记录上一次成绩的价格.
                self.entry_lowest = float(order.price)

        if not order.is_active():
            if order.vt_orderid in self.sell_orders:
                self.sell_orders.remove(order.vt_orderid)

            elif order.vt_orderid in self.buy_orders:
                self.buy_orders.remove(order.vt_orderid)

        self.put_event()  # 更新UI使用.

    def on_trade(self, trade: TradeData):
        """
        Callback of new trade data update.
        """
        if trade.direction == Direction.LONG:
            total = self.avg_price * self.current_pos + float(trade.price) * float(trade.volume)
            self.current_pos += float(trade.volume)
            self.avg_price = total / self.current_pos
        elif trade.direction == Direction.SHORT:
            self.current_pos -= float(trade.volume)

            # 计算统计下总体的利润.
            self.total_profit += (float(trade.price) - self.avg_price) * float(trade.volume) - float(trade.volume) * float(trade.price) * 2 * self.trading_fee

        self.put_event()

    def on_stop_order(self, stop_order: StopOrder):
        """
        Callback of stop order update.
        """
        pass
