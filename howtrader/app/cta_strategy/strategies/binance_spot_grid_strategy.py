from howtrader.app.cta_strategy import (
    CtaTemplate,
    StopOrder,
    TickData,
    BarData,
    TradeData,
    OrderData
)

from howtrader.app.cta_strategy.engine import CtaEngine
from howtrader.trader.event import EVENT_TIMER, EVENT_ACCOUNT
from howtrader.event import Event
from howtrader.trader.object import Status
from typing import Union


TIMER_WAITING_INTERVAL = 30

class BinanceSpotGridStrategy(CtaTemplate):
    """
    币安现货网格交易策略
    免责声明: 本策略仅供测试参考，本人不负有任何责任。使用前请熟悉代码。测试其中的bugs, 请清楚里面的功能后使用。
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

        self.last_filled_order: Union[OrderData, None] = None  # 联合类型, 或者叫可选类型，二选一那种.
        self.tick: Union[TickData, None] = None  #

        print("交易的交易对:", vt_symbol)

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
        self.cta_engine.event_engine.register(EVENT_ACCOUNT + "USDT", self.process_account_event)
        self.cta_engine.event_engine.register(EVENT_ACCOUNT + "bnb", self.process_account_event)
        self.cta_engine.event_engine.register(EVENT_ACCOUNT + "usdt", self.process_account_event)
    def on_stop(self):
        """
        Callback when strategy is stopped.
        """
        self.write_log("策略停止")
        self.cta_engine.event_engine.unregister(EVENT_TIMER, self.process_timer_event)

    def process_timer_event(self, event: Event):

        if self.tick is None:
            return

        self.timer_interval += 1
        if self.timer_interval >= TIMER_WAITING_INTERVAL:

            self.timer_interval = 0
            # 如果你想比较高频可以把定时器给关了。

            if len(self.buy_orders) == 0 and len(self.sell_orders) == 0:

                if abs(self.pos) > self.max_size * self.trading_size:
                    # 限制下单的数量.
                    return

                buy_price = self.tick.bid_price_1 - self.grid_step / 2
                sell_price = self.tick.ask_price_1 + self.grid_step / 2

                buy_orders_ids = self.buy(buy_price, self.trading_size)
                sell_orders_ids = self.sell(sell_price, self.trading_size)

                self.buy_orders.extend(buy_orders_ids)
                self.sell_orders.extend(sell_orders_ids)

                print(f"开启网格交易，双边下单：BUY: {buy_orders_ids}@{buy_price}, SELL: {sell_orders_ids}@{sell_price}")

            else:
                # 网格两边的数量不对等.
                self.cancel_all()

    def process_account_event(self, event:Event):
        print("收到的账户资金的信息:", event.data)

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
            print(f"订单买卖单完全成交, 先撤销所有订单")

            self.last_filled_order = order

            # tick 存在且仓位数量还没有达到设置的最大值.
            if self.tick and abs(self.pos) < self.max_size * self.trading_size:
                step = self.get_step()

                buy_price = order.price - step * self.grid_step
                sell_price = order.price + step * self.grid_step

                buy_price = min(self.tick.bid_price_1 * (1 - 0.0001), buy_price)
                sell_price = max(self.tick.ask_price_1 * (1 + 0.0001), sell_price)

                buy_ids = self.buy(buy_price, self.trading_size)
                sell_ids = self.sell(sell_price, self.trading_size)

                self.buy_orders.extend(buy_ids)
                self.sell_orders.extend(sell_ids)

                print(
                    f"订单完全成交, 分别下双边网格: BUY: {buy_ids}@{buy_price}, SELL: {sell_ids}@{sell_price}")

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
        """
        这个步长的乘积，随你你设置， 你可以都设置为1
        :return:
        """

        pos = abs(self.pos)

        if pos < 3 * self.trading_size:
            return 1

        elif pos < 5 * self.trading_size:
            return 2

        elif pos < 7 * self.trading_size:
            return 3

        return 4

        # or you can set it to only one.
        # return 1
