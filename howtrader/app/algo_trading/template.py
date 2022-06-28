from typing import Dict
from howtrader.trader.object import TickData, OrderData, TradeData, ContractData
from howtrader.trader.constant import OrderType, Offset, Direction
from howtrader.trader.utility import virtual
from decimal import Decimal
from typing import Optional

class AlgoTemplate:
    """"""

    _count: int = 0
    display_name: str = ""
    default_setting: dict = {}
    variables: list = []

    def __init__(
        self,
        algo_engine: "AlgoEngine",
        algo_name: str,
        setting: dict
    ) -> None:
        """构造函数"""
        self.algo_engine: "AlgoEngine" = algo_engine
        self.algo_name: str = algo_name

        self.active: bool = False
        self.active_orders: Dict[str, OrderData] = {}  # vt_orderid:order

        self.variables.insert(0, "active")

    @classmethod
    def new(cls, algo_engine: "AlgoEngine", setting: dict) -> "AlgoTemplate":
        """创建一个新的算法实例"""
        cls._count += 1
        algo_name: str = f"{cls.__name__}_{cls._count}"
        algo = cls(algo_engine, algo_name, setting)
        return algo

    def update_tick(self, tick: TickData) -> None:
        """"""
        if self.active:
            self.on_tick(tick)

    def update_order(self, order: OrderData) -> None:
        """"""
        if order.is_active():
            self.active_orders[order.vt_orderid] = order
        elif order.vt_orderid in self.active_orders:
            self.active_orders.pop(order.vt_orderid)

        self.on_order(order)

    def update_trade(self, trade: TradeData) -> None:
        """"""
        self.on_trade(trade)

    def update_timer(self) -> None:
        """"""
        if self.active:
            self.on_timer()

    def on_start(self) -> None:
        """"""
        pass

    @virtual
    def on_stop(self) -> None:
        """"""
        pass

    @virtual
    def on_tick(self, tick: TickData) -> None:
        """"""
        pass

    @virtual
    def on_order(self, order: OrderData) -> None:
        """"""
        pass

    @virtual
    def on_trade(self, trade: TradeData) -> None:
        """"""
        pass

    @virtual
    def on_timer(self) -> None:
        """"""
        pass

    def start(self) -> None:
        """"""
        self.active = True
        self.on_start()
        self.put_variables_event()

    def stop(self) -> None:
        """"""
        self.active = False
        self.cancel_all()
        self.on_stop()
        self.put_variables_event()

        self.write_log("停止算法")

    def subscribe(self, vt_symbol: str) -> None:
        """"""
        self.algo_engine.subscribe(self, vt_symbol)

    def buy(
        self,
        vt_symbol: str,
        price: Decimal,
        volume: Decimal,
        order_type: OrderType = OrderType.LIMIT,
        offset: Offset = Offset.NONE
    ) -> Optional[str]:
        """"""
        if not self.active:
            return None

        msg: str = f"委托买入{vt_symbol}：{volume}@{price}"
        self.write_log(msg)

        return self.algo_engine.send_order(
            self,
            vt_symbol,
            Direction.LONG,
            price,
            volume,
            order_type,
            offset
        )

    def sell(
        self,
        vt_symbol: str,
        price: Decimal,
        volume: Decimal,
        order_type: OrderType = OrderType.LIMIT,
        offset: Offset = Offset.NONE
    ) -> Optional[str]:
        """"""
        if not self.active:
            return None

        msg: str = f"委托卖出{vt_symbol}：{volume}@{price}"
        self.write_log(msg)

        return self.algo_engine.send_order(
            self,
            vt_symbol,
            Direction.SHORT,
            price,
            volume,
            order_type,
            offset
        )

    def cancel_order(self, vt_orderid: str) -> None:
        """"""
        self.algo_engine.cancel_order(self, vt_orderid)

    def cancel_all(self) -> None:
        """"""
        if not self.active_orders:
            return

        for vt_orderid in self.active_orders.keys():
            self.cancel_order(vt_orderid)

    def get_tick(self, vt_symbol: str) -> Optional[TickData]:
        """"""
        return self.algo_engine.get_tick(self, vt_symbol)

    def get_contract(self, vt_symbol: str) -> Optional[ContractData]:
        """"""
        return self.algo_engine.get_contract(self, vt_symbol)

    def write_log(self, msg: str) -> None:
        """"""
        self.algo_engine.write_log(msg, self)

    def put_parameters_event(self) -> None:
        """"""
        parameters: dict = {}
        for name in self.default_setting.keys():
            parameters[name] = getattr(self, name)

        self.algo_engine.put_parameters_event(self, parameters)

    def put_variables_event(self) -> None:
        """"""
        variables: dict = {}
        for name in self.variables:
            variables[name] = getattr(self, name)

        self.algo_engine.put_variables_event(self, variables)