""""""
from abc import ABC
from copy import copy
from typing import Any, Callable

from howtrader.trader.constant import Interval, Direction, Offset
from howtrader.trader.object import BarData, TickData, OrderData, TradeData, ContractData
from howtrader.trader.utility import virtual

class FundRateArbitrageTemplate(ABC):
    """"""

    author = ""
    parameters = []
    variables = []

    def __init__(
        self,
        fund_rate_engine: Any,
        strategy_name: str,
        spot_vt_symbol: str,
        future_vt_symbol: str,
        setting: dict,
    ):
        """"""
        self.fund_rate_engine = fund_rate_engine
        self.strategy_name = strategy_name
        self.spot_vt_symbol = spot_vt_symbol
        self.future_vt_symbol = future_vt_symbol

        self.inited = False
        self.trading = False

        # Copy a new variables list here to avoid duplicate insert when multiple
        # strategy instances are created with the same strategy class.
        self.variables = copy(self.variables)
        self.variables.insert(0, "inited")
        self.variables.insert(1, "trading")

        self.update_setting(setting)

    def update_setting(self, setting: dict):
        """
        Update strategy parameter wtih value in setting dict.
        """
        for name in self.parameters:
            if name in setting:
                setattr(self, name, setting[name])

    @classmethod
    def get_class_parameters(cls):
        """
        Get default parameters dict of strategy class.
        """
        class_parameters = {}
        for name in cls.parameters:
            class_parameters[name] = getattr(cls, name)
        return class_parameters

    def get_parameters(self):
        """
        Get strategy parameters dict.
        """
        strategy_parameters = {}
        for name in self.parameters:
            strategy_parameters[name] = getattr(self, name)
        return strategy_parameters

    def get_variables(self):
        """
        Get strategy variables dict.
        """
        strategy_variables = {}
        for name in self.variables:
            strategy_variables[name] = getattr(self, name)
        return strategy_variables

    def get_data(self):
        """
        Get strategy data.
        """
        strategy_data = {
            "strategy_name": self.strategy_name,
            "spot_vt_symbol": self.spot_vt_symbol,
            "future_vt_symbol": self.future_vt_symbol,
            "class_name": self.__class__.__name__,
            "author": self.author,
            "parameters": self.get_parameters(),
            "variables": self.get_variables(),
        }
        return strategy_data

    @virtual
    def on_init(self):
        """
        Callback when strategy is inited.
        """
        pass

    @virtual
    def on_start(self):
        """
        Callback when strategy is started.
        """
        pass

    @virtual
    def on_stop(self):
        """
        Callback when strategy is stopped.
        """
        pass

    @virtual
    def on_tick(self, tick: TickData):
        """
        Callback of new tick data update.
        """
        pass

    @virtual
    def on_trade(self, trade: TradeData):
        """
        Callback of new trade data update.
        """
        pass

    @virtual
    def on_order(self, order: OrderData):
        """
        Callback of new order data update.
        """
        pass


    def buy(self, vt_symbol: str, price: float, volume: float, stop: bool = False, lock: bool = False, limit_maker=False):
        """
        Send buy order to open a long position.
        """
        return self.send_order(Direction.LONG, Offset.OPEN, vt_symbol, price, volume, stop, lock, limit_maker=limit_maker)

    def sell(self, vt_symbol:str, price: float, volume: float, stop: bool = False, lock: bool = False, limit_maker=False):
        """
        Send sell order to close a long position.
        """
        return self.send_order(Direction.SHORT, Offset.CLOSE, vt_symbol, price, volume, stop, lock, limit_maker=limit_maker)

    def short(self, vt_symbol:str, price: float, volume: float, stop: bool = False, lock: bool = False, limit_maker=False):
        """
        Send short order to open as short position.
        """
        return self.send_order(Direction.SHORT, Offset.OPEN, vt_symbol, price, volume, stop, lock, limit_maker=limit_maker)

    def cover(self,vt_symbol:str, price: float, volume: float, stop: bool = False, lock: bool = False,limit_maker=False):
        """
        Send cover order to close a short position.
        """
        return self.send_order(Direction.LONG, Offset.CLOSE, vt_symbol, price, volume, stop, lock, limit_maker=limit_maker)

    def send_order(
        self,
        direction: Direction,
        offset: Offset,
        vt_symbol: str,
        price: float,
        volume: float,
        stop: bool = False,
        lock: bool = False,
        limit_maker: bool = False
    ):
        """
        Send a new order.
        """
        if self.trading:
            vt_orderids = self.fund_rate_engine.send_order(
                self, direction, offset, vt_symbol, price, volume, stop, lock, limit_maker
            )
            return vt_orderids
        else:
            return []

    def cancel_order(self, vt_orderid: str):
        """
        Cancel an existing order.
        """
        if self.trading:
            self.fund_rate_engine.cancel_order(self, vt_orderid)

    def cancel_all(self):
        """
        Cancel all orders sent by strategy.
        """
        if self.trading:
            self.fund_rate_engine.cancel_all(self)

    def write_log(self, msg: str):
        """
        Write a log message.
        """
        self.fund_rate_engine.write_log(msg, self)

    def get_pricetick(self, vt_symbol: str):
        """
        Return pricetick data of trading contract.
        """
        return self.fund_rate_engine.get_pricetick(vt_symbol)

    def get_contract(self, vt_symbol: str) -> ContractData:
        """"""
        return self.fund_rate_engine.get_contract(vt_symbol)

    def put_event(self):
        """
        Put an strategy data event for ui update.
        """
        if self.inited:
            self.fund_rate_engine.put_strategy_event(self)  # put event 会调用策略的event来更新数据.

    def send_email(self, msg):
        """
        Send email to default receiver.
        """
        if self.inited:
            self.fund_rate_engine.send_email(msg, self)

    def sync_data(self):
        """
        Sync strategy variables value into disk storage.
        """
        if self.trading:
            self.fund_rate_engine.sync_strategy_data(self)