import importlib
import traceback
from collections import defaultdict
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, List, Optional, Type
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from copy import copy
from tzlocal import get_localzone
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
    HistoryRequest,
    CancelRequest,
    LogData,
    TickData,
    BarData,
    OrderData,
    TradeData,
    ContractData,
    PositionData
)
from howtrader.trader.event import (
    EVENT_TICK,
    EVENT_ORDER,
    EVENT_TRADE,
    EVENT_POSITION
)
from howtrader.trader.constant import (
    Direction,
    OrderType,
    Interval,
    Exchange,
    Offset,
    Status
)
from howtrader.trader.utility import load_json, save_json, extract_vt_symbol, round_to
from howtrader.trader.converter import OffsetConverter
from howtrader.trader.database import BaseDatabase, get_database

from .base import (
    APP_NAME,
    EVENT_CTA_LOG,
    EVENT_CTA_STRATEGY,
    EVENT_CTA_STOPORDER,
    EngineType,
    StopOrder,
    StopOrderStatus,
    STOPORDER_PREFIX
)
from .template import CtaTemplate


# 停止单状态映射
STOP_STATUS_MAP: Dict[Status, StopOrderStatus] = {
    Status.SUBMITTING: StopOrderStatus.WAITING,
    Status.NOTTRADED: StopOrderStatus.WAITING,
    Status.PARTTRADED: StopOrderStatus.TRIGGERED,
    Status.ALLTRADED: StopOrderStatus.TRIGGERED,
    Status.CANCELLED: StopOrderStatus.CANCELLED,
    Status.REJECTED: StopOrderStatus.CANCELLED
}

LOCAL_TZ = get_localzone()


class CtaEngine(BaseEngine):
    """"""

    engine_type: EngineType = EngineType.LIVE  # live trading engine

    setting_filename: str = "cta_strategy_setting.json"
    data_filename: str = "cta_strategy_data.json"

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine) -> None:
        """"""
        super(CtaEngine, self).__init__(
            main_engine, event_engine, APP_NAME)

        self.strategy_setting: dict = {}  # strategy_name: dict
        self.strategy_data: dict = {}     # strategy_name: dict

        self.classes: dict = {}           # class_name: stategy_class
        self.strategies: dict = {}        # strategy_name: strategy

        self.symbol_strategy_map: defaultdict = defaultdict(
            list)                   # vt_symbol: strategy list
        self.orderid_strategy_map: Dict[str, CtaTemplate] = {}  # vt_orderid: strategy
        self.strategy_orderid_map: defaultdict = defaultdict(
            set)                    # strategy_name: orderid list

        self.stop_order_count: int = 0   # for generating stop_orderid
        self.stop_orders: Dict[str, StopOrder] = {}       # stop_orderid: stop_order

        self.init_executor: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=1)

        self.rq_symbols: set = set()

        # self.vt_tradeids: set = set()    # for filtering duplicate trade

        self.offset_converter: OffsetConverter = OffsetConverter(self.main_engine)

        self.database: BaseDatabase = get_database()
        self.sync_strategy_data_lock = threading.Lock()

    def init_engine(self) -> None:
        """"""
        self.load_strategy_class()
        self.load_strategy_setting()
        self.load_strategy_data()
        self.register_event()
        self.write_log("Initialize cta engine")

    def close(self) -> None:
        """"""
        self.stop_all_strategies()

    def register_event(self) -> None:
        """"""
        self.event_engine.register(EVENT_TICK, self.process_tick_event)
        self.event_engine.register(EVENT_ORDER, self.process_order_event)
        self.event_engine.register(EVENT_TRADE, self.process_trade_event)
        self.event_engine.register(EVENT_POSITION, self.process_position_event)

    def process_tick_event(self, event: Event) -> None:
        """"""
        tick: TickData = event.data

        strategies: list = self.symbol_strategy_map[tick.vt_symbol]
        if not strategies:
            return

        self.check_stop_order(tick)

        for strategy in strategies:
            if strategy.inited:
                self.call_strategy_func(strategy, strategy.on_tick, tick)

    def process_order_event(self, event: Event) -> None:
        """"""
        order: OrderData = event.data

        self.offset_converter.update_order(order)

        strategy: Optional[CtaTemplate] = self.orderid_strategy_map.get(order.vt_orderid, None)
        if not strategy:
            return

        # Remove vt_orderid if order is no longer active.
        vt_orderids: list = self.strategy_orderid_map[strategy.strategy_name]
        if order.vt_orderid in vt_orderids and not order.is_active():
            vt_orderids.remove(order.vt_orderid)

        # For server stop order, call strategy on_stop_order function
        if order.type == OrderType.STOP:
            so: StopOrder = StopOrder(
                vt_symbol=order.vt_symbol,
                direction=order.direction,
                offset=order.offset,
                price=order.price,
                volume=order.volume,
                stop_orderid=order.vt_orderid,
                strategy_name=strategy.strategy_name,
                datetime=order.datetime,
                status=STOP_STATUS_MAP[order.status],
                vt_orderids=[order.vt_orderid],
            )
            self.call_strategy_func(strategy, strategy.on_stop_order, so)

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

        strategy: Optional[CtaTemplate] = self.orderid_strategy_map.get(trade.vt_orderid, None)
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

    def check_stop_order(self, tick: TickData) -> None:
        """"""
        for stop_order in list(self.stop_orders.values()):
            if stop_order.vt_symbol != tick.vt_symbol:
                continue

            long_triggered = (
                stop_order.direction == Direction.LONG and tick.last_price >= stop_order.price
            )
            short_triggered = (
                stop_order.direction == Direction.SHORT and tick.last_price <= stop_order.price
            )

            if long_triggered or short_triggered:
                strategy: CtaTemplate = self.strategies[stop_order.strategy_name]

                # To get excuted immediately after stop order is
                # triggered, use limit price if available, otherwise
                # use ask_price_5 or bid_price_5
                if stop_order.direction == Direction.LONG:
                    if tick.limit_up:
                        price = tick.limit_up
                    else:
                        price = tick.ask_price_5
                else:
                    if tick.limit_down:
                        price = tick.limit_down
                    else:
                        price = tick.bid_price_5

                contract: Optional[ContractData] = self.main_engine.get_contract(stop_order.vt_symbol)

                vt_orderids: list = self.send_limit_order(
                    strategy,
                    contract,
                    stop_order.direction,
                    stop_order.offset,
                    Decimal(str(price)),
                    stop_order.volume,
                    stop_order.lock,
                    stop_order.net
                )

                # Update stop order status if placed successfully
                if vt_orderids:
                    # Remove from relation map.
                    self.stop_orders.pop(stop_order.stop_orderid)

                    strategy_vt_orderids: list = self.strategy_orderid_map[strategy.strategy_name]
                    if stop_order.stop_orderid in strategy_vt_orderids:
                        strategy_vt_orderids.remove(stop_order.stop_orderid)

                    # Change stop order status to cancelled and update to strategy.
                    stop_order.status = StopOrderStatus.TRIGGERED
                    stop_order.vt_orderids = vt_orderids

                    self.call_strategy_func(
                        strategy, strategy.on_stop_order, stop_order
                    )
                    self.put_stop_order_event(stop_order)

    def send_server_order(
        self,
        strategy: CtaTemplate,
        contract: ContractData,
        direction: Direction,
        offset: Offset,
        price: Decimal,
        volume: Decimal,
        type: OrderType,
        lock: bool,
        net: bool
    ) -> list:
        """
        Send a new order to server.
        """
        # Create request and send order.
        original_req: OrderRequest = OrderRequest(
            symbol=contract.symbol,
            exchange=contract.exchange,
            direction=direction,
            offset=offset,
            type=type,
            price=price,
            volume=volume,
            reference=f"{APP_NAME}_{strategy.strategy_name}"
        )

        # Convert with offset converter
        req_list: List[OrderRequest] = self.offset_converter.convert_order_request(original_req, lock, net)

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

    def send_limit_order(
        self,
        strategy: CtaTemplate,
        contract: ContractData,
        direction: Direction,
        offset: Offset,
        price: Decimal,
        volume: Decimal,
        lock: bool,
        net: bool,
        maker: bool = False
    ) -> list:
        """
        Send a limit order to server.
        """
        order_type = OrderType.MAKER if maker else OrderType.LIMIT
        return self.send_server_order(
            strategy,
            contract,
            direction,
            offset,
            price,
            volume,
            order_type,
            lock,
            net
        )

    def send_server_stop_order(
        self,
        strategy: CtaTemplate,
        contract: ContractData,
        direction: Direction,
        offset: Offset,
        price: Decimal,
        volume: Decimal,
        lock: bool,
        net: bool
    ) -> list:
        """
        Send a stop order to server.

        Should only be used if stop order supported
        on the trading server.
        """
        return self.send_server_order(
            strategy,
            contract,
            direction,
            offset,
            price,
            volume,
            OrderType.STOP,
            lock,
            net
        )

    def send_local_stop_order(
        self,
        strategy: CtaTemplate,
        direction: Direction,
        offset: Offset,
        price: Decimal,
        volume: Decimal,
        lock: bool,
        net: bool
    ) -> list:
        """
        Create a new local stop order.
        """
        self.stop_order_count += 1
        stop_orderid: str = f"{STOPORDER_PREFIX}.{self.stop_order_count}"

        stop_order: StopOrder = StopOrder(
            vt_symbol=strategy.vt_symbol,
            direction=direction,
            offset=offset,
            price=price,
            volume=volume,
            stop_orderid=stop_orderid,
            strategy_name=strategy.strategy_name,
            datetime=datetime.now(LOCAL_TZ),
            lock=lock,
            net=net
        )

        self.stop_orders[stop_orderid] = stop_order

        vt_orderids: list = self.strategy_orderid_map[strategy.strategy_name]
        vt_orderids.add(stop_orderid)

        self.call_strategy_func(strategy, strategy.on_stop_order, stop_order)
        self.put_stop_order_event(stop_order)

        return [stop_orderid]

    def cancel_server_order(self, strategy: CtaTemplate, vt_orderid: str) -> None:
        """
        Cancel existing order by vt_orderid.
        """
        order: Optional[OrderData] = self.main_engine.get_active_order(vt_orderid)
        if not order:
            self.write_log(f"cancel order failed, order is not active: {vt_orderid}", strategy)
            return None

        req: CancelRequest = order.create_cancel_request()
        self.main_engine.cancel_order(req, order.gateway_name)

    def cancel_local_stop_order(self, strategy: CtaTemplate, stop_orderid: str) -> None:
        """
        Cancel a local stop order.
        """
        stop_order: Optional[StopOrder] = self.stop_orders.get(stop_orderid, None)
        if not stop_order:
            return
        strategy: CtaTemplate = self.strategies[stop_order.strategy_name]

        # Remove from relation map.
        self.stop_orders.pop(stop_orderid)

        vt_orderids: list = self.strategy_orderid_map[strategy.strategy_name]
        if stop_orderid in vt_orderids:
            vt_orderids.remove(stop_orderid)

        # Change stop order status to cancelled and update to strategy.
        stop_order.status = StopOrderStatus.CANCELLED

        self.call_strategy_func(strategy, strategy.on_stop_order, stop_order)
        self.put_stop_order_event(stop_order)

    def send_order(
        self,
        strategy: CtaTemplate,
        direction: Direction,
        offset: Offset,
        price: Decimal,
        volume: Decimal,
        stop: bool,
        lock: bool,
        net: bool,
        maker: bool = False
    ) -> list:
        """
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

        if stop:
            if contract.stop_supported:
                return self.send_server_stop_order(
                    strategy, contract, direction, offset, price, volume, lock, net
                )
            else:
                return self.send_local_stop_order(
                    strategy, direction, offset, price, volume, lock, net
                )
        else:
            return self.send_limit_order(
                strategy, contract, direction, offset, price, volume, lock, net, maker
            )

    def cancel_order(self, strategy: CtaTemplate, vt_orderid: str) -> None:
        """
        """
        if vt_orderid.startswith(STOPORDER_PREFIX):
            self.cancel_local_stop_order(strategy, vt_orderid)
        else:
            self.cancel_server_order(strategy, vt_orderid)

    def cancel_all(self, strategy: CtaTemplate) -> None:
        """
        Cancel all active orders of a strategy.
        """
        vt_orderids: list = self.strategy_orderid_map[strategy.strategy_name]
        if not vt_orderids:
            return

        for vt_orderid in copy(vt_orderids):
            self.cancel_order(strategy, vt_orderid)

    def get_engine_type(self) -> EngineType:
        """"""
        return self.engine_type

    def get_pricetick(self, strategy: CtaTemplate) -> Optional[Decimal]:
        """
        Return contract pricetick data.
        """
        contract: Optional[ContractData] = self.main_engine.get_contract(strategy.vt_symbol)

        if contract:
            return contract.pricetick
        else:
            return None

    def get_position(self, vt_positionid) -> Optional[PositionData]:
        return self.main_engine.get_position(vt_positionid)

    def query_order(self, vt_orderid: str) -> None:
        order: Optional[OrderData] = self.main_engine.get_order(vt_orderid)
        if order:
            req: OrderQueryRequest = order.create_query_request()
            self.main_engine.query_order(req, order.gateway_name)

    def load_bar(
        self,
        vt_symbol: str,
        days: int,
        interval: Interval,
        callback: Callable[[BarData], None],
        use_database: bool
    ) -> List[BarData]:
        """"""
        symbol, exchange = extract_vt_symbol(vt_symbol)
        end: datetime = datetime.now(LOCAL_TZ)
        start: datetime = end - timedelta(days)

        # Pass gateway and datafeed if use_database set to True
        if not use_database:
            # Query bars from gateway if available
            contract: Optional[ContractData] = self.main_engine.get_contract(vt_symbol)

            if contract and contract.history_data:
                req: HistoryRequest = HistoryRequest(
                    symbol=symbol,
                    exchange=exchange,
                    interval=interval,
                    start=start,
                    end=end
                )
                bars: List[BarData] = self.main_engine.query_history(req, contract.gateway_name)
                if bars:
                    return bars
            # Try to query bars from datafeed, if not found, load from database.
            # else:
            #     bars: List[BarData] = self.query_bar_from_datafeed(symbol, exchange, interval, start, end)

        bars: List[BarData] = self.database.load_bar_data(
                symbol=symbol,
                exchange=exchange,
                interval=interval,
                start=start,
                end=end,
            )
        if bars:
            return bars

        return []

    def query_latest_kline(self, vt_symbol: str, interval: Interval, limit: int = 1000) -> None:
        symbol, exchange = extract_vt_symbol(vt_symbol)
        contract: Optional[ContractData] = self.main_engine.get_contract(vt_symbol)
        if not contract:
            self.write_log(f"contract is not found, pls check your vt_symbol: {vt_symbol}")
            return
        if not contract.history_data:
            self.write_log(f"the contract is not support querying kline data")
            return

        req: HistoryRequest = HistoryRequest(
                symbol=symbol,
                exchange=exchange,
                interval=interval,
                limit=limit
        )

        self.main_engine.query_latest_kline(req, contract.gateway_name)

    def load_tick(
        self,
        vt_symbol: str,
        days: int,
        callback: Callable[[TickData], None]
    ) -> List[TickData]:
        """"""
        symbol, exchange = extract_vt_symbol(vt_symbol)
        end: datetime = datetime.now(LOCAL_TZ)
        start: datetime = end - timedelta(days)

        ticks: List[TickData] = self.database.load_tick_data(
            symbol=symbol,
            exchange=exchange,
            start=start,
            end=end,
        )

        return ticks

    def call_strategy_func(
        self, strategy: CtaTemplate, func: Callable, params: Any = None
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
        self, class_name: str, strategy_name: str, vt_symbol: str, setting: dict
    ) -> None:
        """
        Add a new strategy.
        """
        if strategy_name in self.strategies:
            self.write_log(f"create strategy failed，strategy {strategy_name} already existed")
            return

        strategy_class: Optional[Type[CtaTemplate]] = self.classes.get(class_name, None)
        if not strategy_class:
            self.write_log(f"create strategy failed，strategy class {class_name} not found")
            return

        if "." not in vt_symbol:
            self.write_log("create strategy failed, vt_symbol doesn't contain exchange name, correct format like BTCUSDT.BINANCE")
            return

        _, exchange_str = vt_symbol.split(".")
        if exchange_str not in Exchange.__members__:
            self.write_log("create strategy failed, exchange not found")
            return

        strategy: CtaTemplate = strategy_class(self, strategy_name, vt_symbol, setting)
        self.strategies[strategy_name] = strategy

        # Add vt_symbol to strategy map.
        strategies: list = self.symbol_strategy_map[vt_symbol]
        strategies.append(strategy)

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
        strategy: CtaTemplate = self.strategies[strategy_name]

        if strategy.inited:
            self.write_log(f"{strategy_name} already initialzed")
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
        strategy: CtaTemplate = self.strategies[strategy_name]
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
        strategy: CtaTemplate = self.strategies[strategy_name]
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
        strategy: CtaTemplate = self.strategies[strategy_name]
        strategy.update_setting(setting)

        self.update_strategy_setting(strategy_name, setting)
        self.put_strategy_event(strategy)

    def remove_strategy(self, strategy_name: str) -> bool:
        """
        Remove a strategy.
        """
        strategy: CtaTemplate = self.strategies[strategy_name]
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
        self.load_strategy_class_from_folder(path1, "howtrader.app.cta_strategy.strategies")

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
                if (isinstance(value, type) and issubclass(value, CtaTemplate) and value is not CtaTemplate):
                    self.classes[value.__name__] = value
        except:  # noqa
            msg: str = f"strategy module {module_name} failed to load，raise exception: \n{traceback.format_exc()}"
            self.write_log(msg)

    def load_strategy_data(self) -> None:
        """
        Load strategy data from json file.
        """
        self.strategy_data = load_json(self.data_filename)

    def sync_strategy_data(self, strategy: CtaTemplate) -> None:
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
        strategy_class: Type[CtaTemplate] = self.classes[class_name]

        parameters: dict = {}
        for name in strategy_class.parameters:
            parameters[name] = getattr(strategy_class, name)

        return parameters

    def get_strategy_parameters(self, strategy_name) -> dict:
        """
        Get parameters of a strategy.
        """
        strategy: CtaTemplate = self.strategies[strategy_name]
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
                strategy_config["vt_symbol"],
                strategy_config["setting"]
            )

    def update_strategy_setting(self, strategy_name: str, setting: dict) -> None:
        """
        Update setting file.
        """
        strategy: CtaTemplate = self.strategies[strategy_name]

        self.strategy_setting[strategy_name] = {
            "class_name": strategy.__class__.__name__,
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

    def put_stop_order_event(self, stop_order: StopOrder) -> None:
        """
        Put an event to update stop order status.
        """
        event: Event = Event(EVENT_CTA_STOPORDER, stop_order)
        self.event_engine.put(event)

    def put_strategy_event(self, strategy: CtaTemplate) -> None:
        """
        Put an event to update strategy status.
        """
        data: dict = strategy.get_data()
        event: Event = Event(EVENT_CTA_STRATEGY, data)
        self.event_engine.put(event)

    def write_log(self, msg: str, strategy: CtaTemplate = None) -> None:
        """
        Create cta engine log event.
        """
        if strategy:
            msg: str = f"[{strategy.strategy_name}]  {msg}"

        log: LogData = LogData(msg=msg, gateway_name=APP_NAME)
        event: Event = Event(type=EVENT_CTA_LOG, data=log)
        self.event_engine.put(event)

    def send_email(self, msg: str, strategy: CtaTemplate = None) -> None:
        """
        Send email to default receiver.
        """
        if strategy:
            subject: str = f"{strategy.strategy_name}"
        else:
            subject: str = "CTA Engine"

        self.main_engine.send_email(subject, msg)