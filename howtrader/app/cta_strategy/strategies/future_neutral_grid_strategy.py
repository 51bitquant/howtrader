from howtrader.app.cta_strategy import (
    CtaTemplate,
    StopOrder,
    TickData,
    BarData,
    TradeData,
    OrderData
)

from howtrader.app.cta_strategy.engine import CtaEngine
from howtrader.trader.event import EVENT_TIMER
from howtrader.event import Event
from howtrader.trader.object import Status, Direction
from typing import Union
from howtrader.trader.utility import floor_to, round_to


class NeutralGridPositionCalculator(object):
    """
    用来计算网格头寸的平均价格
    Use for calculating the grid position's average price.

    :param grid_step: 网格间隙.
    """

    def __init__(self):
        self.pos = 0
        self.avg_price = 0
        self.profit = 0

    def update_position(self, order: OrderData):
        if order.status != Status.ALLTRADED:
            return

        previous_pos = self.pos
        previous_avg = self.avg_price

        if order.direction == Direction.LONG:
            self.pos += order.volume

            if self.pos == 0:
                self.avg_price = 0
            else:

                if previous_pos == 0:
                    self.avg_price = order.price

                elif previous_pos > 0:
                    self.avg_price = (previous_pos * previous_avg + order.volume * order.price) / abs(self.pos)

                elif previous_pos < 0 < self.pos:
                    self.avg_price = order.price

        elif order.direction == Direction.SHORT:
            self.pos -= order.volume

            if self.pos == 0:
                self.avg_price = 0
            else:

                if previous_pos == 0:
                    self.avg_price = order.price

                elif previous_pos < 0:
                    self.avg_price = (abs(previous_pos) * previous_avg + order.volume * order.price) / abs(self.pos)

                elif previous_pos > 0 > self.pos:
                    self.avg_price = order.price


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
    trading_size = 0.05  # 每次下单的数量.
    max_open_orders = 5  # 一边订单的数量.


    # 变量
    avg_price = 0.0  # 持仓的均价
    current_pos = 0.0  # 当前仓位
    step_price = 0.0  # 网格的间隔
    trade_count = 0

    parameters = ["high_price", "low_price", "grid_count", "trading_size", "max_open_orders"]

    variables = ["avg_price", "current_pos", "step_price", "trade_count"]

    def __init__(self, cta_engine: CtaEngine, strategy_name, vt_symbol, setting):
        """"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)

        self.long_orders = []  # 所有的long orders.
        self.short_orders = []  # 所有的short orders.
        self.tick: Union[TickData, None] = None
        self.pos_calculator = NeutralGridPositionCalculator()

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
        self.pos_calculator = NeutralGridPositionCalculator()
        self.avg_price = self.pos_calculator.avg_price
        self.current_pos = self.pos_calculator.pos

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

    def on_bar(self, bar: BarData):
        """
        Callback of new bar data update.
        """
        if not self.tick:
            return

        step_price = (self.high_price - self.low_price) / self.grid_count

        arr = str(self.tick.bid_price_1).split('.')
        if len(arr) == 2:
            value = len(arr[1])
            self.step_price = floor_to(step_price, 1 / (10 ** value))
        else:
            self.step_price = floor_to(step_price, 1)

        mid_count = round((self.tick.bid_price_1 - self.low_price) / self.step_price)

        if len(self.long_orders) == 0:

            for i in range(self.max_open_orders):
                price = self.low_price + (mid_count - i - 1) * self.step_price
                if price < self.low_price:
                    return

                orders = self.buy(price, self.trading_size)
                self.long_orders.extend(orders)

        if len(self.short_orders) == 0:
            for i in range(self.max_open_orders):
                price = self.low_price + (mid_count + i + 1) * self.step_price
                if price > self.high_price:
                    return

                orders = self.short(price, self.trading_size)
                self.short_orders.extend(orders)

        if len(self.short_orders + self.long_orders) > 100:
            self.cancel_all()

    def on_order(self, order: OrderData):
        """
        Callback of new order data update.
        """

        if order.vt_orderid not in (self.short_orders + self.long_orders):
            return

        self.pos_calculator.update_position(order)

        self.current_pos = self.pos_calculator.pos
        self.avg_price = self.pos_calculator.avg_price

        if order.status == Status.ALLTRADED:

            if order.vt_orderid in self.long_orders:
                self.long_orders.remove(order.vt_orderid)
                self.trade_count += 1

                short_price = order.price + self.step_price
                if short_price <= self.high_price:
                    orders = self.short(short_price, self.trading_size)
                    self.short_orders.extend(orders)

                if len(self.long_orders) < self.max_open_orders:
                    long_price = order.price - self.step_price * self.max_open_orders
                    if long_price >= self.low_price:
                        orders = self.buy(long_price, self.trading_size)
                        self.long_orders.extend(orders)

            if order.vt_orderid in self.short_orders:
                self.short_orders.remove(order.vt_orderid)
                self.trade_count += 1
                long_price = order.price - self.step_price
                if long_price >= self.low_price:
                    orders = self.buy(long_price, self.trading_size)
                    self.long_orders.extend(orders)

                if len(self.short_orders) < self.max_open_orders:
                    short_price = order.price + self.step_price * self.max_open_orders
                    if short_price <= self.high_price:
                        orders = self.short(short_price, self.trading_size)
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
