from howtrader.app.cta_strategy import (
    CtaTemplate,
    StopOrder
)

from howtrader.trader.object import TickData, BarData, TradeData, OrderData

from howtrader.app.cta_strategy.engine import CtaEngine
from howtrader.trader.event import EVENT_TIMER, EVENT_ACCOUNT
from howtrader.event import Event
from howtrader.trader.object import Status
from typing import Optional
from decimal import Decimal

BINANCE_SPOT_GRID_TIMER_WAITING_INTERVAL = 30


class SpotSimpleGridStrategy(CtaTemplate):
    """
    币安现货简单网格交易策略
    该策略没有止盈止损功能，一直在成交的上下方进行高卖低卖操作.
    免责声明: 本策略仅供测试参考，本人不负有任何责任。使用前请熟悉代码。测试其中的bugs, 请清楚里面的功能后再使用。
    币安邀请链接: https://www.binancezh.pro/cn/futures/ref/51bitquant
    合约邀请码：51bitquant
    """
    author = "51bitquant"

    grid_step = 2.0  # 网格间隙.
    trading_size = 0.5  # 每次下单的头寸.
    max_size = 100.0  # 最大单边的数量.

    parameters = ["grid_step", "trading_size", "max_size"]

    def __init__(self, cta_engine: CtaEngine, strategy_name, vt_symbol, setting):
        """"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)

        self.buy_orders = []  # 所有的buy orders.
        self.sell_orders = []  # 所有的sell orders.

        self.timer_interval = 0

        self.last_filled_order: Optional[OrderData] = None  # 联合类型, 或者叫可选类型，二选一那种.
        self.tick: Optional[TickData] = None  #

        # # 订阅现货的资产信息. BINANCE.资产名, 或者BINANCES.资产名
        # self.cta_engine.event_engine.register(EVENT_ACCOUNT + "BINANCE.USDT", self.process_account_event)

        # # 订阅合约的资产信息
        # self.cta_engine.event_engine.register(EVENT_ACCOUNT + "BINANCES.USDT", self.process_account_event)

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
        self.cta_engine.event_engine.register(EVENT_TIMER, self.process_timer_event)

    def on_stop(self):
        """
        Callback when strategy is stopped.
        """
        self.write_log("策略停止")
        self.cta_engine.event_engine.unregister(EVENT_TIMER, self.process_timer_event)

    def process_account_event(self, event:Event):
        self.write_log(f"收到的账户资金的信息: {event.data}")

    def process_timer_event(self, event: Event):

        if self.tick is None:
            return

        self.timer_interval += 1
        if self.timer_interval >= BINANCE_SPOT_GRID_TIMER_WAITING_INTERVAL:

            self.timer_interval = 0
            # 如果你想比较高频可以把定时器给关了。

            if len(self.buy_orders) == 0 and len(self.sell_orders) == 0:

                if abs(self.pos) > self.max_size * self.trading_size:
                    # 限制下单的数量.
                    return

                buy_price = self.tick.bid_price_1 - self.grid_step / 2
                sell_price = self.tick.ask_price_1 + self.grid_step / 2

                buy_orders_ids = self.buy(Decimal(buy_price), Decimal(self.trading_size))
                sell_orders_ids = self.sell(Decimal(sell_price), Decimal(self.trading_size))

                self.buy_orders.extend(buy_orders_ids)
                self.sell_orders.extend(sell_orders_ids)

            elif len(self.buy_orders) == 0 or len(self.sell_orders) == 0:
                # 网格两边的数量不对等.
                self.cancel_all()

    def on_tick(self, tick: TickData):
        """
        Callback of new tick data update.
        """
        self.tick = tick

    def on_bar(self, bar: BarData):
        """
        Callback of new bar data update.
        """
        pass

    def on_order(self, order: OrderData):
        """
        Callback of new order data update.
        """

        if order.status == Status.ALLTRADED:

            if order.vt_orderid in self.buy_orders:
                self.buy_orders.remove(order.vt_orderid)

            if order.vt_orderid in self.sell_orders:
                self.sell_orders.remove(order.vt_orderid)

            self.cancel_all()

            self.last_filled_order = order

            # tick 存在且仓位数量还没有达到设置的最大值.
            if self.tick and abs(self.pos) < self.max_size * self.trading_size:
                step = self.get_step()

                buy_price = float(order.price) - step * self.grid_step
                sell_price = float(order.price) + step * self.grid_step

                buy_price = min(self.tick.bid_price_1 * (1 - 0.0001), buy_price)
                sell_price = max(self.tick.ask_price_1 * (1 + 0.0001), sell_price)

                buy_ids = self.buy(Decimal(buy_price), Decimal(self.trading_size))
                sell_ids = self.sell(Decimal(sell_price), Decimal(self.trading_size))

                self.buy_orders.extend(buy_ids)
                self.sell_orders.extend(sell_ids)

        if not order.is_active():
            if order.vt_orderid in self.buy_orders:
                self.buy_orders.remove(order.vt_orderid)

            elif order.vt_orderid in self.sell_orders:
                self.sell_orders.remove(order.vt_orderid)

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

    def get_step(self) -> int:
        return 1
