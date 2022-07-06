from howtrader.app.tradingview.template import TVTemplate
from howtrader.app.tradingview.engine import TVEngine
from howtrader.trader.object import TickData, TradeData, OrderData, ContractData, Product
from typing import Optional
from howtrader.event import Event, EVENT_TIMER
from decimal import Decimal
from howtrader.trader.utility import round_to

class SimpleTVStrategy(TVTemplate):
    """Simple TradingView Strategy"""

    author: str = "51bitquant"

    trade_volume: float = 0
    max_slippage_percent: float = 0.5  # 0.5%
    parameters: list = ["trade_volume", "max_slippage_percent"]

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
        self.tick: Optional[TickData] = None
        self.orders: list = []
        self.timer_count: int = 0
        self.target_pos: Decimal = Decimal("0")
        self.is_new_signal:bool = False
        self.contract: Optional[ContractData] = tv_engine.main_engine.get_contract(vt_symbol)


    def on_init(self) -> None:
        """
        Callback when strategy is inited.
        """
        self.write_log("strategy inited")

    def on_start(self) -> None:
        """
        Callback when strategy is started.
        """
        self.tv_engine.event_engine.register(EVENT_TIMER, self.process_timer)
        self.write_log("strategy started")

    def on_stop(self):
        """
        Callback when strategy is stopped.
        """
        self.tv_engine.event_engine.unregister(EVENT_TIMER, self.process_timer)
        self.write_log("strategy stop")

    def process_timer(self, event: Event) -> None:
        if self.tick is None:
            # self.write_log("the tick is None, did you connect to exchange or network didn't work well?")
            return None

        if not self.contract:
            self.write_log(f"contract is not found: {self.vt_symbol}")
            return None

        self.timer_count += 1
        if self.timer_count < 5 and len(self.orders) > 0:
            # if there are active orders, will wait 5s for the order filled.
            # 如果有未成交的订单存就等待5s，让订单尽可能成交
            return
        self.timer_count = 0

        self.cancel_all()

        if len(self.orders) > 0:
            return None

        if self.is_new_signal:

            delta = self.target_pos - self.pos
            if abs(delta) < self.contract.min_volume:
                # the target finished.
                self.is_new_signal = False

            if delta > 0:
                price = Decimal(self.tick.ask_price_1 * (1+self.max_slippage_percent/100)) # # max slippage percent
                price = round_to(price, self.contract.pricetick)
                orderids = self.buy(price, abs(delta))

                print(f"sending long order: {price}@{delta}, orderids:{orderids}") # for debug
                self.orders.extend(orderids)

            elif delta < 0:
                if self.contract.product == Product.FUTURES:
                    price = Decimal(self.tick.bid_price_1 * (1-self.max_slippage_percent/100)) # max slippage percent
                    price = round_to(price, self.contract.pricetick)
                    orderids = self.short(price, abs(delta))
                    print(f"sending short order: {price}@{delta}, orderids:{orderids}") # for debug
                    self.orders.extend(orderids)

                elif self.contract.product == Product.SPOT:
                    price = Decimal(self.tick.bid_price_1 * (1 - self.max_slippage_percent / 100))  # max slippage percent
                    price = round_to(price, self.contract.pricetick)
                    orderids = self.sell(price, abs(delta))
                    print(f"sending sell order: {price}@{delta}, orderids:{orderids}") # for debug
                    self.orders.extend(orderids)


    def on_tick(self, tick: TickData) -> None:
        """
        Callback of new tick data update.
        """
        if tick.bid_price_1 > 0:
            self.tick = tick
        else:
            self.tick = None

    def on_trade(self, trade: TradeData) -> None:
        """
        Callback of new trade data update.
        """

    def on_signal(self, signal: dict) -> None:
        """
        the signal contains
        """
        action = signal.get('action', None)
        if action is None:
            self.write_log("the signal doesn't contain action: long/short/exit")
            return None

        action = action.lower()  # to lowercase
        if self.contract is None:
            self.write_log('contract is None, did you connect to the exchange?')
            return None

        if self.trade_volume > 0:
            v = str(self.trade_volume)
            volume = round_to(Decimal(v), self.contract.min_volume)
        else:
            v = signal.get('volume', None)
            if v is None:
                self.write_log("Signal missing volume for placing order volume.")
                return None
            volume = round_to(Decimal(str(v)), self.contract.min_volume)

        if action == 'long':
            self.target_pos = self.pos + volume
            self.is_new_signal = True

        elif action == 'short':
            self.target_pos = self.pos - volume
            self.is_new_signal = True

        elif action == 'exit':
            self.target_pos = 0
            self.is_new_signal = True

        else:
            pass
            self.is_new_signal = True
            # you can extend your signal here.

        self.write_log(f"received signal: {signal}")

    def on_order(self, order: OrderData) -> None:
        """
        Callback of new order data update.
        """

        if not order.is_active():
            # if order is not active, then remove it from self.orders
            self.orders.remove(order.vt_orderid)
