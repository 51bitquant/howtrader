from howtrader.trader.constant import Direction
from howtrader.trader.object import TradeData, OrderData, TickData
from howtrader.app.algo_trading import AlgoTemplate, AlgoEngine
import math
from decimal import Decimal

class GridAlgo(AlgoTemplate):
    """"""

    display_name = "Grid 网格"

    default_setting = {
        "vt_symbol": "",
        "price": 0.0,
        "step_price": 0.0,
        "step_volume": 0,
        "interval": 10,
    }

    variables = [
        "pos",
        "timer_count",
        "vt_orderid"
    ]

    def __init__(
        self,
        algo_engine: AlgoEngine,
        algo_name: str,
        setting: dict
    ):
        """"""
        super().__init__(algo_engine, algo_name, setting)

        # Parameters
        self.vt_symbol = setting["vt_symbol"]
        self.price = setting["price"]
        self.step_price = setting["step_price"]
        self.step_volume = setting["step_volume"]
        self.interval = setting["interval"]

        # Variables
        self.timer_count = 0
        self.vt_orderid = ""
        self.pos = 0
        self.last_tick = None

        self.subscribe(self.vt_symbol)
        self.put_parameters_event()
        self.put_variables_event()

    def on_tick(self, tick: TickData):
        """"""
        self.last_tick = tick

    def on_timer(self):
        """"""
        if not self.last_tick:
            return

        self.timer_count += 1
        if self.timer_count < self.interval:
            self.put_variables_event()
            return
        self.timer_count = 0

        if self.vt_orderid:
            self.cancel_all()

        # Calculate target volume to buy and sell
        target_buy_distance = (
            self.price - self.last_tick.ask_price_1) / self.step_price
        target_buy_position = math.floor(
            target_buy_distance) * self.step_volume
        target_buy_volume = target_buy_position - self.pos

        # Calculate target volume to sell
        target_sell_distance = (
            self.price - self.last_tick.bid_price_1) / self.step_price
        target_sell_position = math.ceil(
            target_sell_distance) * self.step_volume
        target_sell_volume = self.pos - target_sell_position

        # Buy when price dropping
        if target_buy_volume > 0:
            self.vt_orderid = self.buy(
                self.vt_symbol,
                Decimal(self.last_tick.ask_price_1),
                Decimal(min(target_buy_volume, self.last_tick.ask_volume_1))
            )
        # Sell when price rising
        elif target_sell_volume > 0:
            self.vt_orderid = self.sell(
                self.vt_symbol,
                Decimal(self.last_tick.bid_price_1),
                Decimal(min(target_sell_volume, self.last_tick.bid_volume_1))
            )

        # Update UI
        self.put_variables_event()

    def on_order(self, order: OrderData):
        """"""
        if not order.is_active():
            self.vt_orderid = ""
            self.put_variables_event()

    def on_trade(self, trade: TradeData):
        """"""
        if trade.direction == Direction.LONG:
            self.pos += float(trade.volume)
        else:
            self.pos -= float(trade.volume)

        self.put_variables_event()
