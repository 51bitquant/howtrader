from random import uniform

from howtrader.trader.constant import Offset, Direction
from howtrader.trader.object import TradeData, OrderData, TickData
from howtrader.app.algo_trading.engine import AlgoEngine
from howtrader.trader.utility import round_to
from decimal import Decimal

from ..template import AlgoTemplate


class BestLimitAlgo(AlgoTemplate):
    """"""

    display_name = "BestLimit 最优限价"

    default_setting = {
        "vt_symbol": "",
        "direction": [Direction.LONG.value, Direction.SHORT.value],
        "volume": 0.0,
        "min_volume": 0.0,
        "max_volume": 0.0,
        "volume_change": [
            "1",
            "0.1",
            "0.01",
            "0.001",
            "0.0001",
            "0.00001"
        ],
        "offset": [
            Offset.NONE.value,
            Offset.OPEN.value,
            Offset.CLOSE.value,
            Offset.CLOSETODAY.value,
            Offset.CLOSEYESTERDAY.value
        ]
    }

    variables = [
        "traded",
        "vt_orderid",
        "order_price",
        "last_tick",
    ]

    def __init__(
        self,
        algo_engine: AlgoEngine,
        algo_name: str,
        setting: dict
    ):
        """"""
        super().__init__(algo_engine, algo_name, setting)

        # 参数
        self.vt_symbol = setting["vt_symbol"]
        self.direction = Direction(setting["direction"])
        self.volume = setting["volume"]
        self.offset = Offset(setting["offset"])

        self.min_volume = setting["min_volume"]
        self.max_volume = setting["max_volume"]

        if "." in setting["volume_change"]:
            self.volume_change = float(setting["volume_change"])
        else:
            self.volume_change = int(setting["volume_change"])

        # 变量
        self.vt_orderid = ""
        self.traded = 0
        self.last_tick = None
        self.order_price = 0

        self.put_parameters_event()
        self.put_variables_event()

        # 检查最大/最小挂单量
        if self.min_volume <= 0:
            self.write_log("最小挂单量必须大于0，算法启动失败")
            self.stop()
            return

        if self.max_volume < self.min_volume:
            self.write_log("最大挂单量必须不小于最小委托量，算法启动失败")
            self.stop()
            return

        self.subscribe(self.vt_symbol)

    def on_tick(self, tick: TickData):
        """"""
        self.last_tick = tick

        if self.direction == Direction.LONG:
            if not self.vt_orderid:
                self.buy_best_limit()
            elif self.order_price != self.last_tick.bid_price_1:
                self.cancel_all()
        else:
            if not self.vt_orderid:
                self.sell_best_limit()
            elif self.order_price != self.last_tick.ask_price_1:
                self.cancel_all()

        self.put_variables_event()

    def on_trade(self, trade: TradeData):
        """"""
        self.traded += float(trade.volume)

        if self.traded >= self.volume:
            self.write_log(f"已交易数量：{self.traded}，总数量：{self.volume}")
            self.stop()
        else:
            self.put_variables_event()

    def on_order(self, order: OrderData):
        """"""
        if not order.is_active():
            self.vt_orderid = ""
            self.order_price = 0
            self.put_variables_event()

    def buy_best_limit(self):
        """"""
        volume_left = self.volume - self.traded

        rand_volume = self.generate_rand_volume()
        order_volume = min(rand_volume, volume_left)

        self.order_price = self.last_tick.bid_price_1
        self.vt_orderid = self.buy(
            self.vt_symbol,
            Decimal(self.order_price),
            Decimal(order_volume),
            offset=self.offset
        )

    def sell_best_limit(self):
        """"""
        volume_left = self.volume - self.traded

        rand_volume = self.generate_rand_volume()
        order_volume = min(rand_volume, volume_left)

        self.order_price = self.last_tick.ask_price_1
        self.vt_orderid = self.sell(
            self.vt_symbol,
            Decimal(self.order_price),
            Decimal(order_volume),
            offset=self.offset
        )

    def generate_rand_volume(self):
        """"""
        rand_volume = uniform(self.min_volume, self.max_volume)
        rand_volume = round_to(Decimal(rand_volume), Decimal(self.volume_change))

        if self.volume_change == 1:
            return int(rand_volume)

        return float(rand_volume)