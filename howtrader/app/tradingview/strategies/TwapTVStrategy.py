from howtrader.app.tradingview.template import TVTemplate
from howtrader.app.tradingview.engine import TVEngine
from howtrader.trader.object import TickData, TradeData, OrderData, ContractData, Product
from typing import Optional
from howtrader.event import Event, EVENT_TIMER
from decimal import Decimal
from howtrader.trader.utility import round_to
from random import uniform
from howtrader.trader.object import Direction

class TwapTVStrategy(TVTemplate):
    """Time Weighted Average Price TV strategy

    """

    author: str = "51bitquant"

    # the order volume you want to trade, if you trade BTCUSDT, the volume is BTC amount, if you set zero, will use from TV or other signal.
    # 订单的数量，如果你是交易BTCUSDT, 这个数量是BTC的数量, 如果设置为零，那么交易使用会使用来自tradingview或则其他第三方的信号
    order_volume: float = 0.0  # the total order you want to trade
    interval: int = 5  # place order recycle.
    total_order_time: int = 30 # total time for placing order in seconds.

    parameters: list = ["order_volume","interval", "total_order_time"]

    def __init__(
            self,
            tv_engine: TVEngine,
            strategy_name: str,
            tv_id:str,
            vt_symbol: str,
            setting: dict,
    ) -> None:
        """"""
        super().__init__(tv_engine, strategy_name, tv_id, vt_symbol, setting)
        self.last_tick: Optional[TickData] = None
        self.orders: list = []

        self.target_volume: Decimal = Decimal("0") # trade volume target 需要交易的数量.
        self.traded_volume: Decimal = Decimal("0") # have already traded volume 已经交易的数量
        self.direction: Optional[Direction] = None #

        self.contract: Optional[ContractData] = tv_engine.main_engine.get_contract(vt_symbol)

        # define variables for strategy.
        self.timer_count: int = 0
        self.every_order_volume: Decimal = Decimal("0")

    def on_init(self) -> None:
        """
        Callback when strategy is inited.
        """
        self.write_log("strategy inited")

    def on_start(self) -> None:
        """
        Callback when strategy is started.
        """
        self.write_log("strategy started")
        self.tv_engine.event_engine.register(EVENT_TIMER, self.process_timer_event)

    def on_stop(self):
        """
        Callback when strategy is stopped.
        """
        self.tv_engine.event_engine.unregister(EVENT_TIMER, self.process_timer_event)
        self.write_log("strategy stop")

    def on_signal(self, signal: dict) -> None:
        """
        the signal contains
        """
        self.write_log(f"received signal: {signal}")

        action = signal.get('action', None)
        if action is None:
            self.write_log("the signal doesn't contain action: long/short/exit")
            return None

        action = action.lower()  # to lowercase
        if self.contract is None:
            self.write_log('contract is None, did you connect to the exchange?')
            return None

        if self.order_volume > 0:
            v = str(self.order_volume)
            volume = round_to(Decimal(v), self.contract.min_volume)
        else:
            v = signal.get('volume', None)
            if v is None:
                self.write_log("Signal missing volume from signal for placing order volume.")
                return None
            volume = round_to(Decimal(str(v)), self.contract.min_volume)

        volume = abs(volume)

        # formula = float(volume) / (self.total_order_time / self.interval)
        self.every_order_volume = volume * Decimal(str(self.interval)) / Decimal(str(self.total_order_time))
        self.every_order_volume = round_to(self.every_order_volume, self.contract.min_volume)
        # if received new signal, reset the timer_count & total_count
        self.timer_count = 0
        self.traded_volume = Decimal("0")

        if action == 'long':
            if self.pos < 0:
                self.target_volume = volume + abs(self.pos)
            else:
                self.target_volume = volume
            self.direction = Direction.LONG

        elif action == 'short':
            if self.pos > 0:
                self.target_volume = volume + self.pos
            else:
                self.target_volume = volume
            self.direction = Direction.SHORT

        elif action == 'exit':
            if abs(self.pos) < self.contract.min_volume:
                self.write_log(f"ignore exit signal, current pos: {self.pos}")
                return None

            self.target_volume = abs(self.pos)
            if self.pos > 0:
                self.direction = Direction.SHORT
            else:
                self.direction = Direction.LONG
        else:
            pass
            # extend your signal here.

    def on_tick(self, tick: TickData):
        """"""
        if tick and tick.bid_price_1 > 0:
            self.last_tick = tick
        else:
            self.last_tick = None

    def on_order(self, order: OrderData) -> None:
        """
        Callback of new order data update.
        """
        if not order.is_active():
            try:
            # if order is not active, then remove it from self.orders
                self.orders.remove(order.vt_orderid)
            except Exception as error:
                pass

    def on_trade(self, trade: TradeData):
        """"""
        self.traded_volume += trade.volume
        if self.traded_volume >= self.target_volume:
            self.write_log(f"algo trading finished: traded_volume：{self.traded_volume}，target_volume：{self.target_volume}")
            self.traded_volume = Decimal("0")
            self.target_volume = Decimal("0")
            self.direction = None

    def process_timer_event(self, event: Event) -> None:

        self.timer_count += 1

        if self.timer_count < self.interval:
            return None

        self.timer_count = 0

        if not self.last_tick:
            return None

        tick: TickData = self.last_tick
        self.last_tick = None  # to ensure that the tick is always the latest tick data

        if len(self.orders) > 0:
            self.cancel_all()

        left_volume = self.target_volume - self.traded_volume
        volume = min(self.every_order_volume, left_volume)

        if volume < self.contract.min_volume or volume < 0:
            return None

        if self.direction == Direction.LONG:
            orderids = self.buy(Decimal(str(tick.bid_price_1)), volume)
            self.orders.extend(orderids)
        elif self.direction == Direction.SHORT:

            if self.contract.product == Product.SPOT:
                orderids = self.sell(Decimal(str(tick.ask_price_1)), volume)
                self.orders.extend(orderids)

            elif self.contract.product == Product.FUTURES:
                orderids = self.short(Decimal(str(tick.ask_price_1)), volume)
                self.orders.extend(orderids)
