from abc import ABC
from copy import copy
from typing import Any, Callable, List

from howtrader.trader.constant import Direction, Offset
from howtrader.trader.object import TickData, OrderData, TradeData
from howtrader.trader.utility import virtual

from decimal import Decimal


class TVTemplate(ABC):
    """TV strategy Template"""

    author: str = "51bitquant"
    parameters: list = []
    variables: list = []

    def __init__(
            self,
            tv_engine: Any,
            strategy_name: str,
            tv_id: str,
            vt_symbol: str,
            setting: dict,
    ) -> None:
        """"""
        self.tv_engine: Any = tv_engine
        self.strategy_name: str = strategy_name
        self.tv_id: str = tv_id
        self.vt_symbol: str = vt_symbol

        self.inited: bool = False
        self.trading: bool = False
        self.pos: Decimal = Decimal("0")

        # Copy a new variables list here to avoid duplicate insert when multiple
        # strategy instances are created with the same strategy class.
        self.variables = copy(self.variables)
        self.variables.insert(0, "inited")
        self.variables.insert(1, "trading")
        self.variables.insert(2, "pos")

        self.update_setting(setting)

    def update_setting(self, setting: dict) -> None:
        """
        Update strategy parameter with value in setting dict.
        """
        for name in self.parameters:
            if name in setting:
                setattr(self, name, setting[name])

    @classmethod
    def get_class_parameters(cls) -> dict:
        """
        Get default parameters dict of strategy class.
        """
        class_parameters: dict = {}
        for name in cls.parameters:
            class_parameters[name] = getattr(cls, name)
        return class_parameters

    def get_parameters(self) -> dict:
        """
        Get strategy parameters dict.
        """
        strategy_parameters: dict = {}
        for name in self.parameters:
            strategy_parameters[name] = getattr(self, name)
        return strategy_parameters

    def get_variables(self) -> dict:
        """
        Get strategy variables dict.
        """
        strategy_variables: dict = {}
        for name in self.variables:
            strategy_variables[name] = getattr(self, name)
        return strategy_variables

    def get_data(self) -> dict:
        """
        Get strategy data.
        """
        strategy_data: dict = {
            "strategy_name": self.strategy_name,
            "vt_symbol": self.vt_symbol,
            "tv_id": self.tv_id,
            "class_name": self.__class__.__name__,
            "author": self.author,
            "parameters": self.get_parameters(),
            "variables": self.get_variables(),
        }
        return strategy_data

    @virtual
    def on_init(self) -> None:
        """
        Callback when strategy is inited.
        """
        pass

    @virtual
    def on_start(self) -> None:
        """
        Callback when strategy is started.
        """
        pass

    @virtual
    def on_stop(self) -> None:
        """callback when strategy is stop"""
        pass

    @virtual
    def on_tick(self, tick: TickData) -> None:
        """
        Callback of new tick data update.
        """
        pass

    @virtual
    def on_trade(self, trade: TradeData) -> None:
        """
        Callback of new trade data update.
        """
        pass

    @virtual
    def on_order(self, order: OrderData) -> None:
        """
        Callback of new order data update.
        """
        pass

    @virtual
    def on_signal(self, signal: dict) -> None:
        """
        signal from tradingview
        signal contains key and value, the key & value depends on how you config from tradingview
        but it should contains the tv_id, and passphrase, the passphrase for safety
        """

    def buy(
            self,
            price: Decimal,
            volume: Decimal,
            maker: bool = False
    ) -> list:
        """
        Send buy order to open a long position.
        """
        return self.send_order(
            Direction.LONG,
            Offset.OPEN,
            price,
            volume,
            maker=maker
        )

    def sell(
            self,
            price: Decimal,
            volume: Decimal,
            maker: bool = False
    ) -> list:
        """
        Send sell order to close a long position.
        """
        return self.send_order(
            Direction.SHORT,
            Offset.CLOSE,
            price,
            volume,
            maker=maker
        )

    def short(
            self,
            price: Decimal,
            volume: Decimal,
            maker: bool = False
    ) -> list:
        """
        Send short order to open as short position.
        """
        return self.send_order(
            Direction.SHORT,
            Offset.OPEN,
            price,
            volume,
            maker=maker
        )

    def cover(
            self,
            price: Decimal,
            volume: Decimal,
            maker: bool = False
    ) -> list:
        """
        Send cover order to close a short position.
        """
        return self.send_order(
            Direction.LONG,
            Offset.CLOSE,
            price,
            volume,
            maker=maker
        )

    def send_order(
            self,
            direction: Direction,
            offset: Offset,
            price: Decimal,
            volume: Decimal,
            maker: bool = False
    ) -> list:
        """
        Send a new order.
        """
        if self.trading:
            vt_orderids: list = self.tv_engine.send_order(self, direction, offset, price, volume, maker=maker)
            return vt_orderids
        else:
            return []

    def cancel_order(self, vt_orderid: str) -> None:
        """
        Cancel an existing order.
        """
        if self.trading:
            self.tv_engine.cancel_order(self, vt_orderid)

    def query_order(self, vt_orderid: str) -> None:
        self.tv_engine.query_order(vt_orderid)

    def cancel_all(self) -> None:
        """
        Cancel all orders sent by strategy.
        """
        if self.trading:
            self.tv_engine.cancel_all(self)

    def write_log(self, msg: str) -> None:
        """
        Write a log message.
        """
        self.tv_engine.write_log(msg, self)

    def get_pricetick(self) -> float:
        """
        Return pricetick data of trading contract.
        """
        return self.tv_engine.get_pricetick(self)

    def put_event(self) -> None:
        """
        Put an strategy data event for ui update.
        """
        if self.inited:
            self.tv_engine.put_strategy_event(self)

    def send_email(self, msg) -> None:
        """
        Send email to default receiver.
        """
        if self.inited:
            self.tv_engine.send_email(msg, self)

    def sync_data(self) -> None:
        """
        Sync strategy variables value into disk storage.
        """
        if self.trading:
            self.tv_engine.sync_strategy_data(self)
