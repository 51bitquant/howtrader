from howtrader.trader.constant import Offset, Direction, OrderType
from howtrader.trader.object import TradeData, OrderData, TickData
from howtrader.app.algo_trading.engine import AlgoEngine

from ..template import AlgoTemplate
from decimal import Decimal


class DmaAlgo(AlgoTemplate):
    """"""

    display_name = "DMA 直接委托"

    default_setting = {
        "vt_symbol": "",
        "direction": [Direction.LONG.value, Direction.SHORT.value],
        "order_type": [
            OrderType.TAKER.value,
            OrderType.LIMIT.value,
            OrderType.STOP.value,
            OrderType.FAK.value,
            OrderType.FOK.value
        ],
        "price": 0.0,
        "volume": 0.0,
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
        "order_status",
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
        self.order_type = OrderType(setting["order_type"])
        self.price = setting["price"]
        self.volume = setting["volume"]
        self.offset = Offset(setting["offset"])

        # 变量
        self.vt_orderid = ""
        self.traded = 0
        self.order_status = ""

        self.subscribe(self.vt_symbol)
        self.put_parameters_event()
        self.put_variables_event()

    def on_tick(self, tick: TickData):
        """"""
        if not self.vt_orderid:
            if self.direction == Direction.LONG:
                self.vt_orderid = self.buy(
                    self.vt_symbol,
                    Decimal(self.price),
                    Decimal(self.volume),
                    self.order_type,
                    self.offset
                )

            else:
                self.vt_orderid = self.sell(
                    self.vt_symbol,
                    Decimal(self.price),
                    Decimal(self.volume),
                    self.order_type,
                    self.offset
                )
        self.put_variables_event()

    def on_order(self, order: OrderData):
        """"""
        self.traded = float(order.traded)
        self.order_status = order.status

        if not order.is_active():
            self.stop()
        self.put_variables_event()

    def on_trade(self, trade: TradeData):
        """"""
        pass