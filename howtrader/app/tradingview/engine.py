import importlib
import traceback
from collections import defaultdict
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, List, Optional, Type
from concurrent.futures import ThreadPoolExecutor
from copy import copy
from glob import glob
from concurrent.futures import Future
import threading
from decimal import Decimal

from howtrader.event import Event, EventEngine
from howtrader.trader.engine import BaseEngine, MainEngine
from howtrader.trader.object import (
    OrderRequest,
    OrderQueryRequest,
    SubscribeRequest,
    CancelRequest,
    LogData,
    TickData,
    OrderData,
    TradeData,
    ContractData,
    PositionData
)
from howtrader.trader.event import (
    EVENT_TICK,
    EVENT_ORDER,
    EVENT_TRADE,
    EVENT_POSITION,
    EVENT_TV_STRATEGY,
    EVENT_TV_LOG,
    EVENT_TV_SIGNAL
)
from howtrader.trader.constant import (
    Direction,
    OrderType,
    Exchange,
    Offset
)
from howtrader.trader.converter import OffsetConverter
from howtrader.trader.utility import load_json, save_json, extract_vt_symbol, round_to

APP_NAME = "TradingView"
from .template import TVTemplate


class TVEngine(BaseEngine):
    """TradingView Engine"""

    setting_filename: str = "tv_strategy_setting.json"
    data_filename: str = "tv_strategy_data.json"

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine) -> None:
        """"""
        super(TVEngine, self).__init__(
            main_engine, event_engine, APP_NAME)

        self.strategy_setting: dict = {}  # strategy_name: dict
        self.strategy_data: dict = {}  # strategy_name: dict

        self.classes: dict = {}  # class_name: stategy_class
        self.strategies: dict = {}  # strategy_name: strategy

        self.symbol_strategy_map: defaultdict = defaultdict(
            list)  # vt_symbol: strategy list

        self.tv_id_strategy_map: defaultdict = defaultdict(list)

        self.orderid_strategy_map: Dict[str, TVTemplate] = {}  # vt_orderid: strategy

        self.strategy_orderid_map: defaultdict = defaultdict(
            set)  # strategy_name: orderid list

        self.init_executor: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=1)

        # self.vt_tradeids: set = set()    # for filtering duplicate trade

        self.offset_converter: OffsetConverter = OffsetConverter(self.main_engine)
        self.sync_strategy_data_lock = threading.Lock()

    def init_engine(self) -> None:
        """"""
        self.load_strategy_class()
        self.load_strategy_setting()
        self.load_strategy_data()
        self.register_event()
        self.write_log("Init TV engine")

    def close(self) -> None:
        """"""
        self.stop_all_strategies()

    def register_event(self) -> None:
        """"""
        self.event_engine.register(EVENT_TICK, self.process_tick_event)
        self.event_engine.register(EVENT_ORDER, self.process_order_event)
        self.event_engine.register(EVENT_TRADE, self.process_trade_event)
        self.event_engine.register(EVENT_POSITION, self.process_position_event)
        self.event_engine.register(EVENT_TV_SIGNAL, self.process_tv_signal)

    def process_tick_event(self, event: Event) -> None:
        """"""
        tick: TickData = event.data
        strategies: list = self.symbol_strategy_map[tick.vt_symbol]
        if not strategies:
            return

        for strategy in strategies:
            if strategy.inited:
                self.call_strategy_func(strategy, strategy.on_tick, tick)

    def process_order_event(self, event: Event) -> None:
        """"""
        order: OrderData = event.data

        self.offset_converter.update_order(order)

        strategy: Optional[TVTemplate] = self.orderid_strategy_map.get(order.vt_orderid, None)
        if not strategy:
            return

        # Remove vt_orderid if order is no longer active.
        vt_orderids: list = self.strategy_orderid_map[strategy.strategy_name]
        if order.vt_orderid in vt_orderids and not order.is_active():
            vt_orderids.remove(order.vt_orderid)

        # Call strategy on_order function
        self.call_strategy_func(strategy, strategy.on_order, order)

    def process_trade_event(self, event: Event) -> None:
        """"""
        trade: TradeData = event.data

        # Filter duplicate trade push:
        # for we don't use the tradeid to track the tradeData, so the below code is deprecated
        # if trade.vt_tradeid in self.vt_tradeids:
        #     return
        # self.vt_tradeids.add(trade.vt_tradeid)

        self.offset_converter.update_trade(trade)

        strategy: Optional[TVTemplate] = self.orderid_strategy_map.get(trade.vt_orderid, None)
        if not strategy:
            return None

        # Update strategy pos before calling on_trade method
        if trade.direction == Direction.LONG:
            strategy.pos += trade.volume
        else:
            strategy.pos -= trade.volume

        self.call_strategy_func(strategy, strategy.on_trade, trade)

        # Sync strategy variables to data file
        self.sync_strategy_data(strategy)

        # Update GUI
        self.put_strategy_event(strategy)

    def process_position_event(self, event: Event) -> None:
        """"""
        position: PositionData = event.data
        self.offset_converter.update_position(position)

    def process_tv_signal(self, event: Event) -> None:
        data: dict = event.data
        tv_id: str = data.get('tv_id', None)
        if not tv_id:
            return

        strategies: list = self.tv_id_strategy_map[tv_id]
        if not strategies:
            return

        for strategy in strategies:
            if strategy.inited:
                self.call_strategy_func(strategy, strategy.on_signal, data)


    def send_order(
        self,
        strategy: TVTemplate,
        direction: Direction,
        offset: Offset,
        price: Decimal,
        volume: Decimal,
        maker: bool = False
    ) -> list:
        """
        send order to exchange
        """
        contract: Optional[ContractData] = self.main_engine.get_contract(strategy.vt_symbol)
        if not contract:
            self.write_log(f"send order failed, didn't find symbol: {strategy.vt_symbol}", strategy)
            return []

        # Round order price and volume to nearest incremental value
        price: Decimal = round_to(price, contract.pricetick)
        volume: Decimal = round_to(volume, contract.min_volume)
        if abs(volume) < contract.min_volume:
            self.write_log(f"send order failed, order volume: {volume}, required min_volume: {contract.min_volume}")
            return []

        order_type = OrderType.MAKER if maker else OrderType.LIMIT
        original_req: OrderRequest = OrderRequest(
            symbol=contract.symbol,
            exchange=contract.exchange,
            direction=direction,
            offset=offset,
            type=order_type,
            price=price,
            volume=volume,
            reference=f"{APP_NAME}_{strategy.strategy_name}"
        )

        # Convert with offset converter
        req_list: List[OrderRequest] = self.offset_converter.convert_order_request(original_req, False, False)

        # Send Orders
        vt_orderids: list = []

        for req in req_list:
            vt_orderid: str = self.main_engine.send_order(req, contract.gateway_name)

            # Check if sending order successful
            if not vt_orderid:
                continue

            vt_orderids.append(vt_orderid)

            self.offset_converter.update_order_request(req, vt_orderid)

            # Save relationship between orderid and strategy.
            self.orderid_strategy_map[vt_orderid] = strategy
            self.strategy_orderid_map[strategy.strategy_name].add(vt_orderid)

        return vt_orderids

    def cancel_order(self, strategy: TVTemplate, vt_orderid: str) -> None:
        """
        """
        order: Optional[OrderData] = self.main_engine.get_active_order(vt_orderid)
        if not order:
            self.write_log(f"cancel order failed, order is not active: {vt_orderid}", strategy)
            return

        req: CancelRequest = order.create_cancel_request()
        self.main_engine.cancel_order(req, order.gateway_name)

    def query_order(self, vt_orderid: str) -> None:
        order: Optional[OrderData] = self.main_engine.get_order(vt_orderid)
        if order:
            req: OrderQueryRequest = order.create_query_request()
            self.main_engine.query_order(req, order.gateway_name)

    def cancel_all(self, strategy: TVTemplate) -> None:
        """
        Cancel all active orders of a strategy.
        """
        vt_orderids: list = self.strategy_orderid_map[strategy.strategy_name]
        if not vt_orderids:
            return

        for vt_orderid in copy(vt_orderids):
            self.cancel_order(strategy, vt_orderid)

    def get_pricetick(self, strategy: TVTemplate) -> Optional[Decimal]:
        """
        Return contract pricetick data.
        """
        contract: Optional[ContractData] = self.main_engine.get_contract(strategy.vt_symbol)

        if contract:
            return contract.pricetick
        else:
            return None

    def call_strategy_func(
        self, strategy: TVTemplate, func: Callable, params: Any = None
    ) -> None:
        """
        Call function of a strategy and catch any exception raised.
        """
        try:
            if params:
                func(params)
            else:
                func()
        except Exception:
            strategy.trading = False
            strategy.inited = False

            msg: str = f"raise exception and strategy was stopped: \n{traceback.format_exc()}"
            self.write_log(msg, strategy)

    def add_strategy(
        self, class_name: str, strategy_name: str, tv_id, vt_symbol: str, setting: dict
    ) -> None:
        """
        Add a new strategy.
        """
        if strategy_name in self.strategies:
            self.write_log(f"create strategy failed，strategy {strategy_name} already existed")
            return

        strategy_class: Optional[Type[TVTemplate]] = self.classes.get(class_name, None)
        if not strategy_class:
            self.write_log(f"create strategy failed，strategy class {class_name} not found")
            return

        if "." not in vt_symbol:
            self.write_log("create strategy failed, vt_symbol doesn't contain exchange name, correct vt_symbol like BTCUSDT.BINANCE")
            return

        _, exchange_str = vt_symbol.split(".")
        if exchange_str not in Exchange.__members__:
            self.write_log("create strategy failed, exchange not support")
            return

        strategy: TVTemplate = strategy_class(self, strategy_name, tv_id, vt_symbol, setting)
        self.strategies[strategy_name] = strategy

        # Add vt_symbol to strategy map.
        strategies: list = self.symbol_strategy_map[vt_symbol]
        strategies.append(strategy)

        stras = self.tv_id_strategy_map[tv_id]
        stras.append(strategy)

        # Update to setting file.
        self.update_strategy_setting(strategy_name, setting)

        self.put_strategy_event(strategy)

    def init_strategy(self, strategy_name: str) -> Future:
        """
        Init a strategy.
        """
        return self.init_executor.submit(self._init_strategy, strategy_name)

    def _init_strategy(self, strategy_name: str) -> None:
        """
        Init strategies in queue.
        """
        strategy: TVTemplate = self.strategies[strategy_name]

        if strategy.inited:
            self.write_log(f"{strategy_name} already initialized")
            return

        self.write_log(f"start initializing {strategy_name}")

        # Restore strategy data(variables)
        data: Optional[dict] = self.strategy_data.get(strategy_name, None)
        if data:
            for name in strategy.variables:
                value = data.get(name, None)
                if value is not None:
                    if name == 'pos':
                        setattr(strategy, name, Decimal(str(value)))
                    else:
                        setattr(strategy, name, value)

        # Call on_init function of strategy
        self.call_strategy_func(strategy, strategy.on_init)

        # Subscribe market data
        contract: Optional[ContractData] = self.main_engine.get_contract(strategy.vt_symbol)
        if contract:
            req: SubscribeRequest = SubscribeRequest(
                symbol=contract.symbol, exchange=contract.exchange)
            self.main_engine.subscribe(req, contract.gateway_name)
        else:
            self.write_log(f"failed to subscribe market data, symbol not found: {strategy.vt_symbol}", strategy)

        # Put event to update init completed status.
        strategy.inited = True
        self.put_strategy_event(strategy)
        self.write_log(f"finish initializing {strategy_name}")

    def start_strategy(self, strategy_name: str) -> None:
        """
        Start a strategy.
        """
        strategy: TVTemplate = self.strategies[strategy_name]
        if not strategy.inited:
            self.write_log(f"strategy {strategy.strategy_name} failed to start，pls initialize strategy first")
            return None

        if strategy.trading:
            self.write_log(f"{strategy_name} already started")
            return None

        self.call_strategy_func(strategy, strategy.on_start)
        strategy.trading = True

        self.put_strategy_event(strategy)

    def stop_strategy(self, strategy_name: str) -> None:
        """
        Stop a strategy.
        """
        strategy: TVTemplate = self.strategies[strategy_name]
        if not strategy.trading:
            return

        # Call on_stop function of the strategy
        self.call_strategy_func(strategy, strategy.on_stop)

        # Change trading status of strategy to False
        strategy.trading = False

        # Cancel all orders of the strategy
        self.cancel_all(strategy)

        # Sync strategy variables to data file
        self.sync_strategy_data(strategy)

        # Update GUI
        self.put_strategy_event(strategy)

    def edit_strategy(self, strategy_name: str, setting: dict) -> None:
        """
        Edit parameters of a strategy.
        """
        strategy: TVTemplate = self.strategies[strategy_name]
        strategy.update_setting(setting)

        self.update_strategy_setting(strategy_name, setting)
        self.put_strategy_event(strategy)

    def remove_strategy(self, strategy_name: str) -> bool:
        """
        Remove a strategy.
        """
        strategy: TVTemplate = self.strategies[strategy_name]
        if strategy.trading:
            self.write_log(f"strategy {strategy.strategy_name} failed to remove，pls stop strategy first.")
            return False

        # Remove setting
        self.remove_strategy_setting(strategy_name)

        # Remove from symbol strategy map
        strategies: list = self.symbol_strategy_map[strategy.vt_symbol]
        strategies.remove(strategy)

        # Remove from active orderid map
        if strategy_name in self.strategy_orderid_map:
            vt_orderids: list = self.strategy_orderid_map.pop(strategy_name)

            # Remove vt_orderid strategy map
            for vt_orderid in vt_orderids:
                if vt_orderid in self.orderid_strategy_map:
                    self.orderid_strategy_map.pop(vt_orderid)

        # Remove from strategies
        self.strategies.pop(strategy_name)

        self.write_log(f"strategy {strategy.strategy_name} was removed")
        return True

    def load_strategy_class(self) -> None:
        """
        Load strategy class from source code.
        """
        path1: Path = Path(__file__).parent.joinpath("strategies")
        self.load_strategy_class_from_folder(path1, "howtrader.app.tradingview.strategies")

        path2: Path = Path.cwd().joinpath("strategies")
        self.load_strategy_class_from_folder(path2, "strategies")

    def load_strategy_class_from_folder(self, path: Path, module_name: str = "") -> None:
        """
        Load strategy class from certain folder.
        """
        for suffix in ["py", "pyd", "so"]:
            pathname: str = str(path.joinpath(f"*.{suffix}"))
            for filepath in glob(pathname):
                filename = Path(filepath).stem
                name: str = f"{module_name}.{filename}"
                self.load_strategy_class_from_module(name)

    def load_strategy_class_from_module(self, module_name: str) -> None:
        """
        Load strategy class from module file.
        """
        try:
            module: ModuleType = importlib.import_module(module_name)

            # reload the model, in case any modification
            importlib.reload(module)

            for name in dir(module):
                value = getattr(module, name)
                # if (isinstance(value, type) and issubclass(value, TVTemplate) and value is not TVTemplate):
                if isinstance(value, type) and issubclass(value, TVTemplate) and value is not TVTemplate:
                    self.classes[value.__name__] = value

        except:  # noqa
            msg: str = f"strategy module {module_name} failed to load，raise exception: \n{traceback.format_exc()}"
            self.write_log(msg)

    def load_strategy_data(self) -> None:
        """
        Load strategy data from json file.
        """
        self.strategy_data = load_json(self.data_filename)

    def sync_strategy_data(self, strategy: TVTemplate) -> None:
        """
        Sync strategy data into json file.
        """
        data: dict = strategy.get_variables()
        data.pop("inited")      # Strategy status (inited, trading) should not be synced.
        data.pop("trading")
        self.sync_strategy_data_lock.acquire()
        self.strategy_data[strategy.strategy_name] = data
        save_json(self.data_filename, self.strategy_data)
        self.sync_strategy_data_lock.release()

    def get_all_strategy_class_names(self) -> list:
        """
        Return names of strategy classes loaded.
        """
        return list(self.classes.keys())

    def get_strategy_class_parameters(self, class_name: str) -> dict:
        """
        Get default parameters of a strategy class.
        """
        strategy_class: Type[TVTemplate] = self.classes[class_name]

        parameters: dict = {}
        for name in strategy_class.parameters:
            parameters[name] = getattr(strategy_class, name)

        return parameters

    def get_strategy_parameters(self, strategy_name) -> dict:
        """
        Get parameters of a strategy.
        """
        strategy: TVTemplate = self.strategies[strategy_name]
        return strategy.get_parameters()

    def init_all_strategies(self) -> Dict[str, Future]:
        """
        """
        futures: Dict[str, Future] = {}
        for strategy_name in self.strategies.keys():
            futures[strategy_name] = self.init_strategy(strategy_name)
        return futures

    def start_all_strategies(self) -> None:
        """
        """
        for strategy_name in self.strategies.keys():
            self.start_strategy(strategy_name)

    def stop_all_strategies(self) -> None:
        """
        """
        for strategy_name in self.strategies.keys():
            self.stop_strategy(strategy_name)

    def load_strategy_setting(self) -> None:
        """
        Load setting file.
        """
        self.strategy_setting = load_json(self.setting_filename)

        for strategy_name, strategy_config in self.strategy_setting.items():
            self.add_strategy(
                strategy_config["class_name"],
                strategy_name,
                strategy_config['tv_id'],
                strategy_config["vt_symbol"],
                strategy_config["setting"]
            )

    def update_strategy_setting(self, strategy_name: str, setting: dict) -> None:
        """
        Update setting file.
        """
        strategy: TVTemplate = self.strategies[strategy_name]

        self.strategy_setting[strategy_name] = {
            "class_name": strategy.__class__.__name__,
            "tv_id": strategy.tv_id,
            "vt_symbol": strategy.vt_symbol,
            "setting": setting,
        }

        save_json(self.setting_filename, self.strategy_setting)

    def remove_strategy_setting(self, strategy_name: str) -> None:
        """
        Update setting file.
        """
        if strategy_name not in self.strategy_setting:
            return

        self.strategy_setting.pop(strategy_name)
        save_json(self.setting_filename, self.strategy_setting)

    def put_strategy_event(self, strategy: TVTemplate) -> None:
        """
        Put an event to update strategy status.
        """
        data: dict = strategy.get_data()
        event: Event = Event(EVENT_TV_STRATEGY, data)
        self.event_engine.put(event)

    def write_log(self, msg: str, strategy: TVTemplate = None) -> None:
        """
        Create cta engine log event.
        """
        if strategy:
            msg: str = f"[{strategy.strategy_name}]  {msg}"

        log: LogData = LogData(msg=msg, gateway_name=APP_NAME)
        event: Event = Event(type=EVENT_TV_LOG, data=log)
        self.event_engine.put(event)

    def send_email(self, msg: str, strategy: TVTemplate = None) -> None:
        """
        Send email to default receiver.
        """
        if strategy:
            subject: str = f"{strategy.strategy_name}"
        else:
            subject: str = "TV Engine"

        self.main_engine.send_email(subject, msg)