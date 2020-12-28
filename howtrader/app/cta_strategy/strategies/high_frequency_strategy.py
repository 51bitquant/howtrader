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
from howtrader.trader.object import Direction, Status
from howtrader.trader.object import GridPositionCalculator


class HighFrequencyStrategy(CtaTemplate):
    """
    网格的高频策略，挂上下买卖单，等待成交，然后通过不断加仓降低均价

    免责声明: 本策略仅供测试参考，本人不负有任何责任。使用前请熟悉代码。测试其中的bugs, 请清楚里面的功能后在使用。
    币安邀请链接: https://www.binancezh.pro/cn/futures/ref/51bitquant
    合约邀请码：51bitquant
    """
    author = "51bitquant"

    grid_step = 1.0
    stop_multiplier = 15.0
    trading_size = 1.0
    max_pos = 15.0  # 最大的持仓数量.
    stop_mins = 15.0  # 出现亏损是，暂停多长时间.

    # 变量.
    avg_price = 0.0
    current_pos = 0.0

    parameters = ["grid_step", "stop_multiplier", "trading_size", "max_pos", "stop_mins"]
    variables = ["avg_price", "current_pos"]

    def __init__(self, cta_engine: CtaEngine, strategy_name, vt_symbol, setting):
        """"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)

        self.position = GridPositionCalculator(grid_step=self.grid_step)
        self.avg_price = self.position.avg_price
        self.current_pos = self.position.pos

        # orders
        self.long_orders = []
        self.short_orders = []

        self.stop_orders = []
        self.profit_orders = []

        self.timer_count = 0
        self.stop_loss_interval = 0
        self.trigger_stop_loss = False
        self.cancel_order_interval = 0

        self.tick: TickData = None
        self.last_filled_order: OrderData = None

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

    def process_timer_event(self, event: Event):

        self.timer_count += 1

        if self.timer_count >= 60:
            self.timer_count = 0

            # 撤销止损单子.
            for vt_id in self.stop_orders:
                self.cancel_order(vt_id)

        if self.trigger_stop_loss:
            self.stop_loss_interval += 1

        # 止盈的条件, 可以放到tick里面，也可以放到定时器这里.
        if abs(self.position.pos) > 0 and self.tick:

            if self.position.pos > 0 and len(self.profit_orders) == 0:

                price = self.position.avg_price + self.grid_step
                price = max(price, self.tick.ask_price_1 * (1 + 0.0001))

                vts = self.sell(price, abs(self.position.pos))
                self.profit_orders.extend(vts)
                print(f"多头重新下止盈单子: {vts}@{price}")

            elif self.position.pos < 0 and len(self.profit_orders) == 0:

                price = self.position.avg_price - self.grid_step
                price = min(price, self.tick.bid_price_1 * (1 - 0.0001))

                vts = self.cover(price, abs(self.position.pos))
                self.profit_orders.extend(vts)
                print(f"空头重新下止盈单子: {vts}@{price}")

        self.cancel_order_interval += 1

        if self.cancel_order_interval >= 15:

            self.cancel_order_interval = 0

            if abs(self.position.pos) < self.trading_size and (len(self.long_orders) == 0 or len(self.short_orders) == 0):
                self.cancel_all()
                print("当前没有仓位，多空单子不对等，需要重新开始. 先撤销所有订单.")

            elif 0 < abs(self.position.pos) < (self.max_pos * self.trading_size):
                if self.position.pos > 0 and len(self.long_orders) == 0 and self.last_filled_order:

                    step = self.get_step()
                    price = self.last_filled_order.price - self.grid_step * step
                    price = min(price, self.tick.bid_price_1 * (1 - 0.0001))
                    ids = self.buy(price, self.trading_size)
                    self.long_orders.extend(ids)

                elif self.position.pos < 0 and len(self.short_orders) == 0 and self.last_filled_order:

                    step = self.get_step()
                    price = self.last_filled_order.price + self.grid_step * step
                    price = max(price, self.tick.ask_price_1 * (1 + 0.0001))

                    ids = self.short(price, self.trading_size)
                    self.short_orders.extend(ids)

    def on_tick(self, tick: TickData):
        """
        Callback of new tick data update.
        """
        self.tick = tick

        if not self.trading:
            return

        if tick.bid_price_1 <= 0 or tick.ask_price_1 <= 0:
            self.write_log(f"tick价格异常: bid1: {tick.bid_price_1}, ask1: {tick.ask_price_1}")
            return

        if abs(self.position.pos) < self.trading_size:  # 仓位为零的情况.

            if len(self.long_orders) == 0 and len(self.short_orders) == 0:

                if self.trigger_stop_loss:
                    # 记录设置过的止损条件.
                    if self.stop_loss_interval < self.stop_mins * 60:  # 休息15分钟.
                        return
                    else:
                        self.trigger_stop_loss = False
                        self.stop_loss_interval = 0

                buy_price = tick.bid_price_1 - self.grid_step / 2
                sell_price = tick.bid_price_1 + self.grid_step / 2

                long_ids = self.buy(buy_price, self.trading_size)
                short_ids = self.short(sell_price, self.trading_size)

                self.long_orders.extend(long_ids)
                self.short_orders.extend(short_ids)

                print(f"开始新的一轮状态: long_orders: {long_ids}@{buy_price}, short_orders:{short_ids}@{sell_price}")

        if abs(self.position.pos) >= (self.max_pos * self.trading_size) and len(self.stop_orders) == 0:

            if self.position.pos > 0 and tick.ask_price_1 < self.position.avg_price - self.stop_multiplier * self.grid_step:
                vt_ids = self.sell(tick.ask_price_1, abs(self.position.pos))
                stop_price = self.position.avg_price - self.stop_multiplier * self.grid_step
                self.stop_orders.extend(vt_ids)
                self.trigger_stop_loss = True
                print(f"下多头止损单: stop_price: {stop_price}stop@{tick.ask_price_1}")

            elif self.position.pos < 0 and tick.bid_price_1 > self.position.avg_price + self.stop_multiplier * self.grid_step:

                stop_price = self.position.avg_price + self.stop_multiplier * self.grid_step
                vt_ids = self.cover(tick.bid_price_1, abs(self.position.pos))
                self.stop_orders.extend(vt_ids)
                self.trigger_stop_loss = True
                print(f"下空头止损单: stop_price: {stop_price}stop@{tick.bid_price_1}")

    def on_bar(self, bar: BarData):
        """
        Callback of new bar data update.
        """
        pass

    def get_step(self) -> int:

        pos = abs(self.position.pos)

        if pos < 3 * self.trading_size:
            return 1

        elif pos < 5 * self.trading_size:
            return 2

        elif pos < 8 * self.trading_size:
            return 3

        elif pos < 11 * self.trading_size:
            return 5

        elif pos < 13 * self.trading_size:
            return 6

        return 8

    def on_order(self, order: OrderData):
        """
        Callback of new order data update.
        """
        self.position.update_position(order)
        self.current_pos = self.position.pos
        self.avg_price = self.position.avg_price

        if order.vt_orderid in self.long_orders:
            if order.status == Status.ALLTRADED:
                self.long_orders.remove(order.vt_orderid)

                print("多头成交，撤销空头订单和止盈订单")
                for vt_id in (self.short_orders + self.profit_orders):
                    self.cancel_order(vt_id)

                self.last_filled_order = order

                if self.position.pos > 0:
                    if abs(self.position.pos) < self.trading_size * self.max_pos:
                        if not self.tick:
                            return

                        step = self.get_step()
                        price = order.price - self.grid_step * step
                        price = min(price, self.tick.bid_price_1 * (1 - 0.0001))
                        ids = self.buy(price, self.trading_size)
                        self.long_orders.extend(ids)
                        print(f"多头仓位继续下多头订单: {ids}@{price}")

            elif order.status in [Status.REJECTED, Status.CANCELLED]:
                self.long_orders.remove(order.vt_orderid)

        elif order.vt_orderid in self.short_orders:
            if order.status == Status.ALLTRADED:
                self.short_orders.remove(order.vt_orderid)

                print("空头成交，撤销多头订单和止盈订单")
                for vt_id in (self.long_orders + self.profit_orders):
                    self.cancel_order(vt_id)

                self.last_filled_order = order

                if self.position.pos < 0:
                    if abs(self.position.pos) < self.trading_size * self.max_pos:
                        if not self.tick:
                            return

                        step = self.get_step()
                        price = order.price + self.grid_step * step
                        price = max(price, self.tick.ask_price_1 * (1 + 0.0001))

                        ids = self.short(price, self.trading_size)
                        self.short_orders.extend(ids)

                        print(f"空头仓位继续下空头订单: {ids}@{price}")

            elif order.status in [Status.REJECTED, Status.CANCELLED]:
                self.short_orders.remove(order.vt_orderid)  # remove orderid

        elif order.vt_orderid in self.stop_orders:
            if not order.is_active():
                self.stop_orders.remove(order.vt_orderid)

        elif order.vt_orderid in self.profit_orders:
            if not order.is_active():
                self.profit_orders.remove(order.vt_orderid)

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
