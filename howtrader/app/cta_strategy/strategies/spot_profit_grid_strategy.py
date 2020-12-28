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
from howtrader.trader.object import Status
from howtrader.trader.object import GridPositionCalculator
from typing import Union

NORMAL_TIMER_INTERVAL = 5
PROFIT_TIMER_INTERVAL = 5
STOP_TIMER_INTERVAL = 60


class SpotProfitGridStrategy(CtaTemplate):
    """
    币安现货网格策略，添加止盈止损的功能.
    该策略没有止盈止损功能，一直在成交的上下方进行高卖低卖操作, 达到最大的单子数量的时候，会计算仓位均价，然后进行平仓操作.
    免责声明: 本策略仅供测试参考，本人不负有任何责任。使用前请熟悉代码。测试其中的bugs, 请清楚里面的功能后再使用。
    币安邀请链接: https://www.binancezh.pro/cn/futures/ref/51bitquant
    合约邀请码：51bitquant
    """
    author = "51bitquant"

    grid_step = 2.0  # 网格间隙.
    profit_step = 2.0  # 获利的间隔.
    trading_size = 1.0  # 每次下单的头寸.
    max_pos = 100  # 最大的头寸数, 表示不会触发止损的条件.
    profit_orders_counts = 10  # 出现单边吃单太多的时候会考虑止盈.
    trailing_stop_multiplier = 2.0
    stop_minutes = 360.0  # sleep for six hour

    # 变量
    avg_price = 0.0
    current_pos = 0.0

    parameters = ["grid_step", "profit_step", "trading_size", "max_pos", "profit_orders_counts",
                  "trailing_stop_multiplier", "stop_minutes"]

    variables = ["avg_price", "current_pos"]

    def __init__(self, cta_engine: CtaEngine, strategy_name, vt_symbol, setting):
        """"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)

        self.position_calculator = GridPositionCalculator(grid_step=self.grid_step)  # 计算仓位用的对象
        self.current_pos = self.position_calculator.pos
        self.avg_price = self.position_calculator.avg_price

        self.normal_timer_interval = 0
        self.profit_order_interval = 0
        self.stop_order_interval = 0
        self.stop_strategy_interval = 0

        self.long_orders = []  # 所有的long orders.
        self.short_orders = []  # 所有的short orders.
        self.profit_orders = []  # profit orders.
        self.stop_orders = []  # stop orders.

        self.trigger_stop_loss = False  # 是否触发止损。

        self.last_filled_order: Union[OrderData, None] = None

        self.tick: Union[TickData,None] = None

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

        self.position_calculator = GridPositionCalculator(
            grid_step=self.grid_step)  # 计算仓位用的对象 
        self.avg_price = self.position_calculator.avg_price
        self.current_pos = self.position_calculator.pos

    def on_stop(self):
        """
        Callback when strategy is stopped.
        """
        self.write_log("策略停止")
        self.cta_engine.event_engine.unregister(EVENT_TIMER, self.process_timer_event)

    def process_timer_event(self, event: Event):

        if self.tick is None:
            return

        if self.trigger_stop_loss:
            self.stop_strategy_interval += 1  # 如果触发了止损，然后就会开始计时.

        self.normal_timer_interval += 1

        if self.normal_timer_interval >= NORMAL_TIMER_INTERVAL:
            self.normal_timer_interval = 0

            # 仓位为零的时候
            if abs(self.position_calculator.pos) < self.trading_size:
                if len(self.long_orders) == 0 and len(self.short_orders) == 0:
                    if self.trigger_stop_loss:
                        # 如果触发了止损就需要休息一段时间.
                        if self.stop_order_interval < self.stop_minutes * 60:
                            return
                        else:
                            self.stop_order_interval = 0
                            self.trigger_stop_loss = False

                    buy_price = self.tick.bid_price_1 - self.grid_step / 2
                    sell_price = self.tick.bid_price_1 + self.grid_step / 2
                    long_ids = self.buy(buy_price, self.trading_size)
                    short_ids = self.sell(sell_price, self.trading_size)

                    self.long_orders.extend(long_ids)
                    self.short_orders.extend(short_ids)

                    print(
                        f"开启网格交易，双边下单：LONG: { self.long_orders}: {buy_price}, SHORT: { self.short_orders}:{sell_price}")

                elif len(self.long_orders) == 0 or len(self.short_orders) == 0:
                    print(f"仓位为零且单边网格没有订单, 先撤掉所有订单")
                    self.cancel_all()

            elif abs(self.position_calculator.pos) >= self.trading_size:

                if len(self.long_orders) > 0 and len(self.short_orders) > 0:
                    return

                if self.last_filled_order:
                    price = self.last_filled_order.price
                else:
                    price = self.tick.bid_price_1

                buy_step = self.get_step()
                sell_step = self.get_step()

                buy_price = price - buy_step * self.grid_step
                sell_price = price + sell_step * self.grid_step

                buy_price = min(self.tick.bid_price_1, buy_price)
                sell_price = max(self.tick.ask_price_1, sell_price)
                long_ids = self.buy(buy_price, self.trading_size)
                short_ids = self.sell(sell_price, self.trading_size)

                self.long_orders.extend(long_ids)
                self.short_orders.extend(short_ids)
                print(f"仓位不为零, 根据上个订单下双边网格.LONG:{long_ids}:{buy_price}, SHORT: {short_ids}:{sell_price}")

        self.profit_order_interval += 1

        if self.profit_order_interval >= PROFIT_TIMER_INTERVAL:
            self.profit_order_interval = 0

            if abs(self.position_calculator.pos) >= self.profit_orders_counts * self.trading_size and len(
                    self.profit_orders) == 0:
                print(f"单边网格出现超过{self.profit_orders_counts}个订单以上,头寸为:{self.position_calculator.pos}, 考虑设置止盈的情况")

                if self.position_calculator.pos > 0:
                    price = max(self.tick.ask_price_1 * (1 + 0.0001),
                                self.position_calculator.avg_price + self.profit_step)
                    order_ids = self.sell(price, abs(self.position_calculator.pos))
                    self.profit_orders.extend(order_ids)
                    print(f"多头止盈情况: {self.position_calculator.pos}@{price}")
                elif self.position_calculator.pos < 0:
                    price = min(self.tick.bid_price_1 * (1 - 0.0001),
                                self.position_calculator.avg_price - self.profit_step)
                    order_ids = self.buy(price, abs(self.position_calculator.pos))
                    self.profit_orders.extend(order_ids)
                    print(f"空头止盈情况: {self.position_calculator.pos}@{price}")

        self.stop_order_interval += 1
        if self.stop_order_interval >= STOP_TIMER_INTERVAL:
            self.stop_order_interval = 0

            for vt_id in self.stop_orders:
                self.cancel_order(vt_id)

            # 如果仓位达到最大值的时候.
            if abs(self.position_calculator.pos) >= self.max_pos * self.trading_size:

                if self.last_filled_order:
                    if self.position_calculator.pos > 0:
                        if self.tick.bid_price_1 < self.last_filled_order.price - self.trailing_stop_multiplier * self.grid_step:
                            vt_ids = self.sell(self.tick.bid_price_1, abs(self.position_calculator.pos))
                            self.stop_orders.extend(vt_ids)

                    elif self.position_calculator.pos < 0:
                        if self.tick.ask_price_1 > self.last_filled_order.price + self.trailing_stop_multiplier * self.grid_step:
                            vt_ids = self.buy(self.tick.ask_price_1, abs(self.position_calculator.pos))
                            self.stop_orders.extend(vt_ids)

                else:
                    if self.position_calculator.pos > 0:
                        if self.tick.bid_price_1 < self.position_calculator.avg_price - self.max_pos * self.grid_step:
                            vt_ids = self.sell(self.tick.bid_price_1, abs(self.position_calculator.pos))
                            self.stop_orders.extend(vt_ids)

                    elif self.position_calculator.pos < 0:
                        if self.tick.ask_price_1 > self.position_calculator.avg_price + self.max_pos * self.grid_step:
                            vt_ids = self.buy(self.tick.ask_price_1, abs(self.position_calculator.pos))
                            self.stop_orders.extend(vt_ids)

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
        self.position_calculator.update_position(order)

        self.current_pos = self.position_calculator.pos
        self.avg_price = self.position_calculator.avg_price

        if order.status == Status.ALLTRADED:
            if order.vt_orderid in (self.long_orders + self.short_orders):

                if order.vt_orderid in self.long_orders:
                    self.long_orders.remove(order.vt_orderid)

                if order.vt_orderid in self.short_orders:
                    self.short_orders.remove(order.vt_orderid)

                self.cancel_all()
                print(f"订单买卖单完全成交, 先撤销所有订单")

                self.last_filled_order = order

                if abs(self.position_calculator.pos) < self.trading_size:
                    print("仓位为零， 需要重新开始.")
                    return

                # tick 存在且仓位数量还没有达到设置的最大值.
                if self.tick and abs(self.position_calculator.pos) < self.max_pos * self.trading_size:
                    buy_step = self.get_step()
                    sell_step = self.get_step()

                    # 解决步长的问题.
                    buy_price = order.price - buy_step * self.grid_step
                    sell_price = order.price + sell_step * self.grid_step

                    buy_price = min(self.tick.bid_price_1 * (1 - 0.0001), buy_price)
                    sell_price = max(self.tick.ask_price_1 * (1 + 0.0001), sell_price)

                    long_ids = self.buy(buy_price, self.trading_size)
                    short_ids = self.sell(sell_price, self.trading_size)

                    self.long_orders.extend(long_ids)
                    self.short_orders.extend(short_ids)

                    print(
                        f"订单完全成交, 分别下双边网格: LONG: {self.long_orders}:{buy_price}, SHORT: {self.short_orders}:{sell_price}")

            elif order.vt_orderid in self.profit_orders:
                self.profit_orders.remove(order.vt_orderid)
                if abs(self.position_calculator.pos) < self.trading_size:
                    self.cancel_all()
                    print(f"止盈单子成交,且仓位为零, 先撤销所有订单，然后重新开始")

            elif order.vt_orderid in self.stop_orders:
                self.stop_orders.remove(order.vt_orderid)
                if abs(self.position_calculator.pos) < self.trading_size:
                    self.trigger_stop_loss = True
                    self.cancel_all()

                    print("止损单子成交，且仓位为零, 先撤销所有订单，然后重新开始")

        if not order.is_active():
            if order.vt_orderid in self.long_orders:
                self.long_orders.remove(order.vt_orderid)

            elif order.vt_orderid in self.short_orders:
                self.short_orders.remove(order.vt_orderid)

            elif order.vt_orderid in self.profit_orders:
                self.profit_orders.remove(order.vt_orderid)

            elif order.vt_orderid in self.stop_orders:
                self.stop_orders.remove(order.vt_orderid)

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