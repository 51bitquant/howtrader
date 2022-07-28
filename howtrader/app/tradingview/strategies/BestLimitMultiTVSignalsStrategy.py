from howtrader.app.tradingview.template import TVTemplate
from howtrader.app.tradingview.engine import TVEngine
from howtrader.trader.object import TickData, TradeData, OrderData, ContractData, Product
from typing import Optional
from howtrader.event import Event, EVENT_TIMER
from decimal import Decimal
from howtrader.trader.utility import round_to
from random import uniform
from howtrader.trader.object import Direction

class BestLimitMultiTVSignalsStrategy(TVTemplate):
    """Place Best Limit order for TV strategy for multi signals

    split a large order to small order, and use best limit price to place order automatically until it filled. For more detail, read the codes below.

    使用最优价格(买一/卖一)去下限价单，把大单拆成小单，不断去循环下单，直到下单完成。
    """

    author: str = "51bitquant"

    # the order volume you want to trade, if you trade BTCUSDT, the volume is BTC amount, if you set zero, will use from TV or other signal.
    # 订单的数量，如果你是交易BTCUSDT, 这个数量是BTC的数量, 如果设置为零，那么交易使用会使用来自tradingview或则其他第三方的信号
    order_volume: float = 0.0

    # place max order volume per order 单次最大的下单数量.
    min_volume_per_order: float = 0.0
    max_volume_per_order: float = 0.0

    parameters: list = ["order_volume","min_volume_per_order", "max_volume_per_order"]

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
        self.order_price: float = 0

        self.target_volume: Decimal = Decimal("0") # trade volume target 需要交易的数量.
        self.traded_volume: Decimal = Decimal("0") # have already traded volume 已经交易的数量
        self.direction: Optional[Direction] = None #

        self.contract: Optional[ContractData] = tv_engine.main_engine.get_contract(vt_symbol)

        self.signals = []  # store the signals.

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

    def on_stop(self):
        """
        Callback when strategy is stopped.
        """
        self.write_log("strategy stop")

    def on_tick(self, tick: TickData):
        """"""
        self.last_tick = tick

        if self.direction == Direction.LONG:
            if len(self.orders) == 0:
                self.buy_best_limit()
            elif self.order_price != self.last_tick.bid_price_1:
                self.cancel_all()
        elif self.direction == Direction.SHORT:
            if len(self.orders) == 0:
                self.sell_best_limit()
            elif self.order_price != self.last_tick.ask_price_1:
                self.cancel_all()
        else:

            if len(self.signals) > 0:
                signal = self.signals.pop(0)
                self.resolve_signal(signal)

    def resolve_signal(self, signal: dict) -> None:
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

    def on_signal(self, signal: dict) -> None:
        """
        the signal contains
        """
        self.write_log(f"received signal: {signal}")
        self.signals.append(signal)

    def on_order(self, order: OrderData) -> None:
        """
        Callback of new order data update.
        """
        if not order.is_active():
            try:
            # if order is not active, then remove it from self.orders
                self.orders.remove(order.vt_orderid)
                self.order_price = 0
            except Exception:
                pass

    def on_trade(self, trade: TradeData):
        """"""
        self.traded_volume += trade.volume

        if self.traded_volume >= self.target_volume:
            self.write_log(f"algo trading finished: traded_volume：{self.traded_volume}，target_volume：{self.target_volume}")
            self.traded_volume = Decimal("0")
            self.target_volume = Decimal("0")
            self.direction = None

    def buy_best_limit(self) -> None:
        """"""
        volume_left = self.target_volume - self.traded_volume
        rand_volume = self.generate_rand_volume()
        order_volume = min(rand_volume, volume_left)
        order_volume = round_to(order_volume, self.contract.min_volume)
        if order_volume < self.contract.min_volume or order_volume < 0:
            return None

        self.order_price = self.last_tick.bid_price_1
        orderids = self.buy(Decimal(str(self.order_price)), order_volume)
        self.orders.extend(orderids)

    def sell_best_limit(self) -> None:
        """"""
        volume_left = self.target_volume - self.traded_volume
        rand_volume = self.generate_rand_volume()
        order_volume = min(rand_volume, volume_left)
        order_volume = round_to(order_volume, self.contract.min_volume)
        if order_volume < self.contract.min_volume or order_volume < 0:
            return None

        self.order_price = self.last_tick.ask_price_1
        if self.contract.product == Product.SPOT:
            orderids = self.sell(Decimal(str(self.order_price)), Decimal(order_volume))
            self.orders.extend(orderids)
        elif self.contract.product == Product.FUTURES:
            orderids = self.short(Decimal(str(self.order_price)), Decimal(order_volume))
            self.orders.extend(orderids)

    def generate_rand_volume(self):
        """"""
        rand_volume = uniform(self.min_volume_per_order, self.max_volume_per_order)
        return Decimal(str(rand_volume))
