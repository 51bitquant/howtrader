from howtrader.app.tradingview.template import TVTemplate
from howtrader.app.tradingview.engine import TVEngine
from howtrader.trader.object import TickData, TradeData, OrderData, ContractData, Product
from typing import Optional
from howtrader.event import Event, EVENT_TIMER
from decimal import Decimal
from howtrader.trader.utility import round_to
from random import uniform
from howtrader.trader.object import Direction


class MyTVSimpleStrategy(TVTemplate):
    """自定义信号， 通过市价单去实现.

    self-customized signals and place order in market order
    """

    author: str = "51bitquant"

    # the order volume you want to trade, if you trade BTCUSDT, the volume is BTC amount, if you set zero, will use from TV or other signal.
    # 订单的数量，如果你是交易BTCUSDT, 这个数量是BTC的数量, 如果设置为零，那么交易使用会使用来自tradingview或则其他第三方的信号
    order_volume: float = 0.0

    # the price slippage for taker order, 0.5 means 0.5%
    max_slippage_percent: float = 0.5  # 0.5%

    parameters: list = ["order_volume", "max_slippage_percent"]

    def __init__(
            self,
            tv_engine: TVEngine,
            strategy_name: str,
            tv_id: str,
            vt_symbol: str,
            setting: dict,
    ) -> None:
        """"""
        super().__init__(tv_engine, strategy_name, tv_id, vt_symbol, setting)
        self.orders: list = []

        self.target_volume: Decimal = Decimal("0")  # trade volume target 需要交易的数量.
        self.traded_volume: Decimal = Decimal("0")  # have already traded volume 已经交易的数量
        self.direction: Optional[Direction] = None  #

        self.contract: Optional[ContractData] = tv_engine.main_engine.get_contract(vt_symbol)
        self.timer_count = 0
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
        if not tick or tick.bid_price_1 <= 0 or not self.contract:
            return None

        self.timer_count += 1
        if self.timer_count < 3:
            return None

        self.timer_count = 0

        if len(self.orders) > 0:
            self.cancel_all()
            return None

        volume = self.target_volume - self.traded_volume

        if volume > self.contract.min_volume and volume * tick.bid_price_1 >= 10:  # 下单的价值要大于10USDT

            if self.direction == Direction.LONG:
                price = Decimal(tick.ask_price_1 * (1 + self.max_slippage_percent / 100))
                price = round_to(price, self.contract.pricetick)
                orderids = self.buy(price, volume)
                self.orders.extend(orderids)

            elif self.direction == Direction.SHORT:
                price = Decimal(tick.bid_price_1 * (1 - self.max_slippage_percent / 100))
                price = round_to(price, self.contract.pricetick)

                if self.contract.product == Product.FUTURES:  # for futures market
                    orderids = self.short(price, volume)
                    self.orders.extend(orderids)

                elif self.contract.product == Product.SPOT:  # for spot market
                    orderids = self.sell(price, volume)
                    self.orders.extend(orderids)

        else:
            self.traded_volume = Decimal("0")
            self.target_volume = Decimal("0")
            self.direction = None

            if len(self.signals) > 0:
                signal = self.signals.pop(0)
                self.resolve_signal(signal)

    def resolve_signal(self, signal: dict) -> None:
        action = signal.get('action', None)
        if action is None:
            self.write_log(f"current action is : {action}")
            return None

        action = action.lower()  # 把信号转成小写了。
        if self.contract is None:
            self.write_log('contract is None, did you connect to the exchange?')
            return None

        if self.order_volume > 0:
            v = str(self.order_volume)
            volume = round_to(Decimal(v), self.contract.min_volume)
        else:
            v = signal.get('volume', None)
            if v is None:
                self.write_log("missing volume from signal for placing order volume.")
                return None

            volume = round_to(Decimal(str(v)), self.contract.min_volume)

        volume = abs(volume)
        self.traded_volume = Decimal("0")

        if action == 'l_1':
            if self.pos < 0:
                self.target_volume = volume + abs(self.pos)
            else:
                self.target_volume = volume
            self.direction = Direction.LONG

        elif action == 'l_2':
            self.target_volume = volume
            self.direction = Direction.LONG

        elif action == 's_1':
            if self.pos > 0:
                self.target_volume = volume + self.pos
            else:
                self.target_volume = volume
            self.direction = Direction.SHORT

        elif action == 's_2':
            self.target_volume = volume
            self.direction = Direction.SHORT

        elif action == 'tp_1_l':

            if self.pos > 0:
                if self.pos >= volume:
                    self.target_volume = volume
                    self.direction = Direction.SHORT
                else:
                    self.target_volume = self.pos
                    self.direction = Direction.SHORT

        elif action == 'tp_2_l':
            if self.pos > 0:
                self.target_volume = self.pos
                self.direction = Direction.SHORT

        elif action == 'tp_1_s':
            if self.pos < 0:
                if abs(self.pos) >= volume:
                    self.target_volume = volume
                    self.direction = Direction.LONG

                else:
                    self.target_volume = abs(self.pos)
                    self.direction = Direction.LONG

        elif action == 'tp_2_s':
            if self.pos < 0:
                self.target_volume = abs(self.pos)
                self.direction = Direction.LONG

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

            except Exception:
                pass

    def on_trade(self, trade: TradeData):
        """"""
        self.traded_volume += trade.volume

        if self.traded_volume >= self.target_volume:
            self.write_log(
                f"signal trading finished: traded_volume：{self.traded_volume}，target_volume：{self.target_volume}")
            self.traded_volume = Decimal("0")
            self.target_volume = Decimal("0")
            self.direction = None
