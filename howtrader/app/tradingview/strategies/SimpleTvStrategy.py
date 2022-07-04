from howtrader.app.tradingview.template import TVTemplate
from howtrader.app.tradingview.engine import TVEngine
from howtrader.trader.object import TickData, TradeData, OrderData, ContractData, Product
from typing import Optional
from howtrader.event import Event, EVENT_TIMER
from decimal import Decimal

class SimpleTVStrategy(TVTemplate):
    """the limit order Strategy"""

    author: str = "51bitquant"

    trade_volume: float = 0

    parameters: list = ["trade_volume"]
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
        self.signal_data = None #
        tv_engine.event_engine.register(EVENT_TIMER, self.process_timer)
        self.orders: list = []
        self.timer_count: int = 0

        self.contract: Optional[ContractData] = tv_engine.main_engine.get_contract(vt_symbol)


    def on_init(self) -> None:
        """
        Callback when strategy is inited.
        """
        self.write_log("on init")

    def on_start(self) -> None:
        """
        Callback when strategy is started.
        """

    def on_stop(self):
        """
        Callback when strategy is stopped.
        """
        self.write_log("strategy stop")

    def process_timer(self, event: Event) -> None:
        if self.tick is None:
            return None

        if not self.contract:
            self.write_log(f"contract is not found: {self.vt_symbol}")
            return None

        self.timer_count += 1
        if self.timer_count < 5:
            return
        self.timer_count = 0

        self.cancel_all()

        if len(self.orders) > 0:
            return None

        if self.signal_data:
            action = self.signal_data.get('action').upper()

            if self.trade_volume > 0:
                volume = Decimal(str(self.trade_volume))
            else:
                volume = Decimal(str(self.signal_data.get('volume')))

            if action == 'LONG': # open long order
                price = Decimal(self.tick.bid_price_1 * 1.01)
                v = volume - self.pos
                if v < self.contract.min_volume:
                    self.signal_data = None
                    return None

                orderids = self.buy(price, v)
                self.orders.extend(orderids)

            elif action == 'SHORT': # open short order

                price = Decimal(self.tick.ask_price_1 * 0.99)
                v = volume * Decimal("-1") - self.pos
                v = abs(v)
                if v < self.contract.min_volume: # filter small order volume.
                    self.signal_data = None
                    return None

                orderids = self.short(price, v)
                self.orders.extend(orderids)

            elif action == "EXIT": # exit your position
                if self.pos > 0:
                    if self.pos < self.contract.min_volume:
                        self.signal_data = None
                        return

                    price = Decimal(self.tick.ask_price_1 * 0.99)
                    orderids = self.short(price, abs(self.pos))
                    self.orders.extend(orderids)

                elif self.pos < 0:
                    if abs(self.pos) < self.contract.min_volume:
                        self.signal_data = None
                        return None

                    price = Decimal(self.tick.bid_price_1 * 1.01)
                    orderids = self.buy(price, abs(self.pos))
                    self.orders.extend(orderids)
                else:
                    self.signal_data = None


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
        self.signal_data = signal
        self.write_log(f"{signal}")

    def on_order(self, order: OrderData) -> None:
        """
        Callback of new order data update.
        """

        if not order.is_active():
            # if order is not active, then remove it from self.orders
            self.orders.remove(order.vt_orderid)
