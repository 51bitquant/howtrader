from howtrader.app.cta_strategy import (
    CtaTemplate,
    StopOrder
)

from howtrader.trader.object import TickData, BarData, TradeData, OrderData

from howtrader.app.cta_strategy.engine import CtaEngine
from howtrader.trader.object import Status
from typing import Optional
from howtrader.trader.utility import BarGenerator
from decimal import Decimal


class FutureNeutralGridStrategy(CtaTemplate):
    """
    币安合约中性网格
    策略在震荡行情下表现很好，但是如果发生趋势行情，单次止损会比较大，导致亏损过多。

    免责声明: 本策略仅供测试参考，本人不负有任何责任。使用前请熟悉代码。测试其中的bugs, 请清楚里面的功能后再使用。
    币安邀请链接: https://www.binancezh.pro/cn/futures/ref/51bitquant
    合约邀请码：51bitquant

    """
    author = "51bitquant"

    high_price = 0.0  # 执行策略的最高价.
    low_price = 0.0  # 执行策略的最低价.
    grid_count = 100  # 网格的数量.
    order_volume = 0.05  # 每次下单的数量.
    max_open_orders = 2  # 一边订单的数量.

    trade_count = 0

    parameters = ["high_price", "low_price", "grid_count", "order_volume", "max_open_orders"]

    variables = ["trade_count"]

    def __init__(self, cta_engine: CtaEngine, strategy_name, vt_symbol, setting):
        """"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)

        self.long_orders = []  # 所有的long orders.
        self.short_orders = []  # 所有的short orders.
        self.tick: Optional[TickData] = None
        self.bg = BarGenerator(self.on_bar)
        self.step_price = 0

    def on_init(self):
        """
        Callback when strategy is inited.
        """
        self.write_log("策略初始化")

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

    def on_tick(self, tick: TickData):
        """
        Callback of new tick data update.
        """
        if tick and tick.bid_price_1 > 0:
            self.tick = tick

        self.bg.update_tick(tick)

    def on_bar(self, bar: BarData):
        """
        Callback of new bar data update.
        """
        if not self.tick:
            return

        if len(self.long_orders) == 0 or len(self.short_orders) == 0:

            self.step_price = (self.high_price - self.low_price) / self.grid_count
            mid_count = round((self.tick.bid_price_1 - self.low_price) / self.step_price)
            if len(self.long_orders) == 0:

                for i in range(self.max_open_orders):
                    price = self.low_price + (mid_count - i - 1) * self.step_price
                    if price < self.low_price:
                        break

                    orders = self.buy(Decimal(price), Decimal(self.order_volume))
                    self.long_orders.extend(orders)

            if len(self.short_orders) == 0:
                for i in range(self.max_open_orders):
                    price = self.low_price + (mid_count + i + 1) * self.step_price
                    if price > self.high_price:
                        break

                    orders = self.short(Decimal(price), Decimal(self.order_volume))
                    self.short_orders.extend(orders)

        if len(self.short_orders + self.long_orders) > 100:
            self.cancel_all()

        self.put_event()

    def on_order(self, order: OrderData):
        """
        Callback of new order data update.
        """

        if order.vt_orderid not in (self.short_orders + self.long_orders):
            return

        if order.status == Status.ALLTRADED:

            if order.vt_orderid in self.long_orders:
                self.long_orders.remove(order.vt_orderid)
                self.trade_count += 1

                short_price = order.price + Decimal(self.step_price)

                if short_price <= self.high_price:
                    orders = self.short(short_price, Decimal(self.order_volume))
                    self.short_orders.extend(orders)

                if len(self.long_orders) < self.max_open_orders:
                    count = len(self.long_orders) + 1
                    long_price = order.price - Decimal(self.step_price) * Decimal(str(count))
                    if long_price >= self.low_price:
                        orders = self.buy(long_price, Decimal(self.order_volume))
                        self.long_orders.extend(orders)

            if order.vt_orderid in self.short_orders:
                self.short_orders.remove(order.vt_orderid)
                self.trade_count += 1
                long_price = order.price - Decimal(self.step_price)
                if long_price >= self.low_price:
                    orders = self.buy(long_price, Decimal(self.order_volume))
                    self.long_orders.extend(orders)

                if len(self.short_orders) < self.max_open_orders:
                    count = len(self.long_orders) + 1
                    short_price = order.price + Decimal(self.step_price) * Decimal(str(count))
                    if short_price <= self.high_price:
                        orders = self.short(short_price, Decimal(self.order_volume))
                        self.short_orders.extend(orders)

        if not order.is_active():
            if order.vt_orderid in self.long_orders:
                self.long_orders.remove(order.vt_orderid)

            elif order.vt_orderid in self.short_orders:
                self.short_orders.remove(order.vt_orderid)

        self.put_event()

    def on_trade(self, trade: TradeData):
        """
        Callback of new trade data update.
        """
        self.put_event()

    def on_stop_order(self, stop_order: StopOrder):
        """
        Callback of stop order update.
        """
        pass
