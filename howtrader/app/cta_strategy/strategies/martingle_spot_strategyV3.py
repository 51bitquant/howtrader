from howtrader.app.cta_strategy import (
    CtaTemplate,
    StopOrder
)

from howtrader.trader.object import TickData, BarData, TradeData, OrderData

from howtrader.app.cta_strategy.engine import CtaEngine
from howtrader.trader.object import Status, Direction, Interval, ContractData, AccountData

from typing import Optional
from howtrader.trader.utility import BarGenerator
from decimal import Decimal


class MartingleSpotStrategyV3(CtaTemplate):
    """
    1. 马丁策略.
    币安邀请链接: https://www.binancezh.pro/cn/futures/ref/51bitquant
    币安合约邀请码：51bitquant

    ## 策略思路

    1. 挑选1小时涨幅超过2.6%的币，或者4小涨幅超过4.6%的币, 然后入场
    2. 利润超过1%，且最高价回调1%后平仓，当然你可以选择自己的参数
    3. 如果入场后，没有利润，价格继续下跌。那么入场价格下跌5%后，采用马丁策略加仓。

    """
    author = "51bitquant"

    # 策略的核心参数.
    initial_trading_value = 200  # 首次开仓价值 1000USDT.
    trading_value_multiplier = 2  # 加仓的比例.
    max_increase_pos_count = 5  # 最大的加仓次数

    hour_pump_pct = 0.026  # 小时的上涨百分比
    four_hour_pump_pct = 0.046  # 四小时的上涨百分比.
    high_close_change_pct = 0.03  # 最高价/收盘价 -1, 防止上引线过长.
    increase_pos_when_dump_pct = 0.05  # 价格下跌 5%就继续加仓.
    exit_profit_pct = 0.01  # 出场平仓百分比 1%
    exit_pull_back_pct = 0.01  # 最高价回调超过1%，且利润超过1% 就出场.
    trading_fee = 0.00075  # 交易手续费

    # 变量
    avg_price = 0.0  # 当前持仓的平均价格.
    last_entry_price = 0.0  # 上一次入场的价格.
    entry_highest_price = 0.0
    current_pos = 0.0  # 当前的持仓的数量.
    current_increase_pos_count = 0  # 当前的加仓的次数.
    total_profit = 0  # 统计总的利润.

    parameters = ["initial_trading_value", "trading_value_multiplier", "max_increase_pos_count",
                  "hour_pump_pct", "four_hour_pump_pct", "high_close_change_pct", "increase_pos_when_dump_pct",
                  "exit_profit_pct",
                  "exit_pull_back_pct", "trading_fee"]

    variables = ["avg_price", "last_entry_price", "entry_highest_price", "current_pos", "current_increase_pos_count",
                 "total_profit"]

    def __init__(self, cta_engine: CtaEngine, strategy_name, vt_symbol, setting):
        """"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)

        self.last_filled_order: Optional[OrderData] = None
        self.tick: Optional[TickData] = None
        self.contract: Optional[ContractData] = None
        self.account: Optional[AccountData] = None

        self.bg_1hour = BarGenerator(self.on_bar, 1, on_window_bar=self.on_1hour_bar, interval=Interval.HOUR)  # 1hour
        self.bg_4hour = BarGenerator(self.on_bar, 4, on_window_bar=self.on_4hour_bar, interval=Interval.HOUR)  # 4hour

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
            self.bg_1hour.update_tick(tick)
            self.bg_4hour.update_tick(tick)

    def on_bar(self, bar: BarData):
        """
        Callback of new bar data update.
        """
        if self.entry_highest_price > 0:
            self.entry_highest_price = max(bar.high_price, self.entry_highest_price)

        if self.current_pos * bar.close_price >= self.min_notional:

            if len(self.sell_orders) <= 0 < self.avg_price:
                # 有利润平仓的时候
                # 清理掉其他买单.

                profit_percent = bar.close_price / self.avg_price - 1
                profit_pull_back_pct = self.entry_highest_price / bar.close_price - 1
                if profit_percent >= self.exit_profit_pct and profit_pull_back_pct >= self.exit_pull_back_pct:
                    self.cancel_all()
                    orderids = self.sell(Decimal(bar.close_price), Decimal(abs(self.current_pos)))
                    self.sell_orders.extend(orderids)

            if len(self.buy_orders) <= 0:
                # 考虑加仓的条件: 1） 当前有仓位,且仓位值要大于11USDTyi以上，2）加仓的次数小于最大的加仓次数，3）当前的价格比上次入场的价格跌了一定的百分比。

                dump_down_pct = self.last_entry_price / bar.close_price - 1

                if self.current_increase_pos_count <= self.max_increase_pos_count and dump_down_pct >= self.increase_pos_when_dump_pct:
                    # ** 表示的是乘方.
                    self.cancel_all()  # 清理其他卖单.

                    increase_pos_value = self.initial_trading_value * self.trading_value_multiplier ** self.current_increase_pos_count
                    price = bar.close_price
                    vol = increase_pos_value / price
                    orderids = self.buy(Decimal(price), Decimal(vol))
                    self.buy_orders.extend(orderids)

        self.bg_1hour.update_bar(bar)
        self.bg_4hour.update_bar(bar)

        self.put_event()

    def on_1hour_bar(self, bar: BarData):

        close_change_pct = bar.close_price / bar.open_price - 1  # 收盘价涨了多少.
        high_change_pct = bar.high_price / bar.close_price - 1  # 计算上引线

        # 回调一定比例的时候.
        if self.current_pos * bar.close_price < self.min_notional:
            # 每次下单要大于等于10USDT, 为了简单设置11USDT.
            if close_change_pct >= self.hour_pump_pct and high_change_pct < self.high_close_change_pct and len(
                    self.buy_orders) == 0:
                # 这里没有仓位.
                # 重置当前的数据.
                self.cancel_all()
                self.current_increase_pos_count = 0
                self.avg_price = 0
                self.entry_highest_price = 0.0

                price = bar.close_price
                vol = self.initial_trading_value / price
                orderids = self.buy(Decimal(price), Decimal(vol))
                self.buy_orders.extend(orderids)  # 以及已经下单的orderids.

    def on_4hour_bar(self, bar: BarData):
        close_change_pct = bar.close_price / bar.open_price - 1  # 收盘价涨了多少.
        high_change_pct = bar.high_price / bar.close_price - 1  # 计算上引线

        # 回调一定比例的时候.
        if self.current_pos * bar.close_price < self.min_notional:
            # 每次下单要大于等于10USDT, 为了简单设置11USDT.
            if close_change_pct >= self.four_hour_pump_pct and high_change_pct < self.high_close_change_pct and len(
                    self.buy_orders) == 0:
                # 这里没有仓位.
                # 重置当前的数据.
                self.cancel_all()
                self.current_increase_pos_count = 0
                self.avg_price = 0
                self.entry_highest_price = 0.0

                price = bar.close_price
                vol = self.initial_trading_value / price
                orderids = self.buy(Decimal(price), Decimal(vol))
                self.buy_orders.extend(orderids)  # 以及已经下单的orderids.

    def on_order(self, order: OrderData):
        """
        Callback of new order data update.
        """
        if order.status == Status.ALLTRADED:
            if order.direction == Direction.LONG:
                # 买单成交.
                self.current_increase_pos_count += 1
                self.last_entry_price = float(order.price)  # 记录上一次成绩的价格.
                self.entry_highest_price = float(order.price)

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
            profit = (float(trade.price) - self.avg_price) * float(trade.volume)
            total_fee = float(trade.volume) * float(trade.price) * 2 * self.trading_fee
            self.total_profit += profit - total_fee

        self.put_event()

    def on_stop_order(self, stop_order: StopOrder):
        """
        Callback of stop order update.
        """
        pass
