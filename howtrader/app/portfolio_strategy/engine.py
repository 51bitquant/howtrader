import importlib
import glob
import traceback
from collections import defaultdict
from pathlib import Path
from types import ModuleType
from typing import Dict, List, Set, Tuple, Type, Any, Callable, Optional
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from tzlocal import get_localzone

from howtrader.event import Event, EventEngine
from howtrader.trader.engine import BaseEngine, MainEngine
from howtrader.trader.object import (
    OrderRequest,
    CancelRequest,
    SubscribeRequest,
    HistoryRequest,
    LogData,
    TickData,
    OrderData,
    TradeData,
    PositionData,
    BarData,
    ContractData
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
    Offset
)
from howtrader.trader.utility import load_json, save_json, extract_vt_symbol, round_to
from howtrader.trader.datafeed import BaseDatafeed, get_datafeed
from howtrader.trader.converter import OffsetConverter
from howtrader.trader.database import BaseDatabase, get_database

from .base import (
    APP_NAME,
    EVENT_PORTFOLIO_LOG,
    EVENT_PORTFOLIO_STRATEGY
)
from .template import StrategyTemplate


class StrategyEngine(BaseEngine):
    """"""

    setting_filename: str = "portfolio_strategy_setting.json"
    data_filename: str = "portfolio_strategy_data.json"

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine) -> None:
        """"""
        super().__init__(main_engine, event_engine, APP_NAME)

        self.strategy_data: Dict[str, Dict] = {}

        self.classes: Dict[str, Type[StrategyTemplate]] = {}
        self.strategies: Dict[str, StrategyTemplate] = {}

        self.symbol_strategy_map: Dict[str, List[StrategyTemplate]] = defaultdict(list)
        self.orderid_strategy_map: Dict[str, StrategyTemplate] = {}

        self.init_executor: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=1)

        self.vt_tradeids: Set[str] = set()

        self.offset_converter: OffsetConverter = OffsetConverter(self.main_engine)

        self.database: BaseDatabase = get_database()
        self.datafeed: BaseDatafeed = get_datafeed()

    def init_engine(self) -> None:
        """"""
        self.init_datafeed()
        self.load_strategy_class()
        self.load_strategy_setting()
        self.load_strategy_data()
        self.register_event()
        self.write_log("组合策略引擎初始化成功")

    def close(self) -> None:
        """"""
        self.stop_all_strategies()

    def register_event(self) -> None:
        """"""
        self.event_engine.register(EVENT_TICK, self.process_tick_event)
        self.event_engine.register(EVENT_ORDER, self.process_order_event)
        self.event_engine.register(EVENT_TRADE, self.process_trade_event)
        self.event_engine.register(EVENT_POSITION, self.process_position_event)

    def init_datafeed(self) -> None:
        """
        Init datafeed client.
        """
        result: bool = self.datafeed.init()
        if result:
            self.write_log("数据服务初始化成功")

    def query_bar_from_datafeed(
        self, symbol: str, exchange: Exchange, interval: Interval, start: datetime, end: datetime
    ) -> List[BarData]:
        """
        Query bar data from datafeed.
        """
        req: HistoryRequest = HistoryRequest(
            symbol=symbol,
            exchange=exchange,
            interval=interval,
            start=start,
            end=end
        )
        data: List[BarData] = self.datafeed.query_bar_history(req)
        return data

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

        strategy: Optional[StrategyTemplate] = self.orderid_strategy_map.get(order.vt_orderid, None)
        if not strategy:
            return

        self.call_strategy_func(strategy, strategy.update_order, order)

    def process_trade_event(self, event: Event) -> None:
        """"""
        trade: TradeData = event.data

        # Filter duplicate trade push
        if trade.vt_tradeid in self.vt_tradeids:
            return
        self.vt_tradeids.add(trade.vt_tradeid)

        self.offset_converter.update_trade(trade)

        strategy: Optional[StrategyTemplate] = self.orderid_strategy_map.get(trade.vt_orderid, None)
        if not strategy:
            return

        self.call_strategy_func(strategy, strategy.update_trade, trade)

    def process_position_event(self, event: Event) -> None:
        """"""
        position: PositionData = event.data

        self.offset_converter.update_position(position)

    def send_order(
        self,
        strategy: StrategyTemplate,
        vt_symbol: str,
        direction: Direction,
        offset: Offset,
        price: float,
        volume: float,
        lock: bool,
        net: bool,
    ) -> list:
        """
        Send a new order to server.
        """
        contract: Optional[ContractData] = self.main_engine.get_contract(vt_symbol)
        if not contract:
            self.write_log(f"委托失败，找不到合约：{vt_symbol}", strategy)
            return ""

        # Round order price and volume to nearest incremental value
        price: float = round_to(price, contract.pricetick)
        volume: float = round_to(volume, contract.min_volume)

        # Create request and send order.
        original_req: OrderRequest = OrderRequest(
            symbol=contract.symbol,
            exchange=contract.exchange,
            direction=direction,
            offset=offset,
            type=OrderType.LIMIT,
            price=price,
            volume=volume,
            reference=f"{APP_NAME}_{strategy.strategy_name}"
        )

        # Convert with offset converter
        req_list: List[OrderRequest] = self.offset_converter.convert_order_request(original_req, lock, net)

        # Send Orders
        vt_orderids: list = []

        for req in req_list:
            vt_orderid: str = self.main_engine.send_order(
                req, contract.gateway_name)

            # Check if sending order successful
            if not vt_orderid:
                continue

            vt_orderids.append(vt_orderid)

            self.offset_converter.update_order_request(req, vt_orderid)

            # Save relationship between orderid and strategy.
            self.orderid_strategy_map[vt_orderid] = strategy

        return vt_orderids

    def cancel_order(self, strategy: StrategyTemplate, vt_orderid: str) -> None:
        """"""
        order: Optional[OrderData] = self.main_engine.get_order(vt_orderid)
        if not order:
            self.write_log(f"撤单失败，找不到委托{vt_orderid}", strategy)
            return

        req: CancelRequest = order.create_cancel_request()
        self.main_engine.cancel_order(req, order.gateway_name)

    def get_pricetick(self, strategy: StrategyTemplate, vt_symbol: str) -> float:
        """
        Return contract pricetick data.
        """
        contract: Optional[ContractData] = self.main_engine.get_contract(vt_symbol)

        if contract:
            return contract.pricetick
        else:
            return None

    def load_bars(self, strategy: StrategyTemplate, days: int, interval: Interval) -> None:
        """"""
        vt_symbols: list = strategy.vt_symbols
        dts: Set[datetime] = set()
        history_data: Dict[Tuple, BarData] = {}

        # Load data from rqdata/gateway/database
        for vt_symbol in vt_symbols:
            data: List[BarData] = self.load_bar(vt_symbol, days, interval)

            for bar in data:
                dts.add(bar.datetime)
                history_data[(bar.datetime, vt_symbol)] = bar

        # Convert data structure and push to strategy
        dts: list = list(dts)
        dts.sort()

        bars: dict = {}

        for dt in dts:
            for vt_symbol in vt_symbols:
                bar: Optional[BarData] = history_data.get((dt, vt_symbol), None)

                # If bar data of vt_symbol at dt exists
                if bar:
                    bars[vt_symbol] = bar
                # Otherwise, use previous data to backfill
                elif vt_symbol in bars:
                    old_bar: BarData = bars[vt_symbol]

                    bar = BarData(
                        symbol=old_bar.symbol,
                        exchange=old_bar.exchange,
                        datetime=dt,
                        open_price=old_bar.close_price,
                        high_price=old_bar.close_price,
                        low_price=old_bar.close_price,
                        close_price=old_bar.close_price,
                        gateway_name=old_bar.gateway_name
                    )
                    bars[vt_symbol] = bar

            self.call_strategy_func(strategy, strategy.on_bars, bars)

    def load_bar(self, vt_symbol: str, days: int, interval: Interval) -> List[BarData]:
        """"""
        symbol, exchange = extract_vt_symbol(vt_symbol)
        end: datetime = datetime.now(get_localzone())
        start: datetime = end - timedelta(days)
        contract: Optional[ContractData] = self.main_engine.get_contract(vt_symbol)
        data: List[BarData]

        # Query bars from gateway if available
        if contract and contract.history_data:
            req: HistoryRequest = HistoryRequest(
                symbol=symbol,
                exchange=exchange,
                interval=interval,
                start=start,
                end=end
            )
            data = self.main_engine.query_history(req, contract.gateway_name)
        # Try to query bars from datafeed, if not found, load from database.
        else:
            data = self.query_bar_from_datafeed(symbol, exchange, interval, start, end)

        if not data:
            data = self.database.load_bar_data(
                symbol=symbol,
                exchange=exchange,
                interval=interval,
                start=start,
                end=end,
            )

        return data

    def call_strategy_func(
        self, strategy: StrategyTemplate, func: Callable, params: Any = None
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

            msg: str = f"触发异常已停止\n{traceback.format_exc()}"
            self.write_log(msg, strategy)

    def add_strategy(
        self, class_name: str, strategy_name: str, vt_symbols: list, setting: dict
    ) -> None:
        """
        Add a new strategy.
        """
        if strategy_name in self.strategies:
            self.write_log(f"创建策略失败，存在重名{strategy_name}")
            return

        strategy_class: Optional[StrategyTemplate] = self.classes.get(class_name, None)
        if not strategy_class:
            self.write_log(f"创建策略失败，找不到策略类{class_name}")
            return

        strategy: StrategyTemplate = strategy_class(self, strategy_name, vt_symbols, setting)
        self.strategies[strategy_name] = strategy

        # Add vt_symbol to strategy map.
        for vt_symbol in vt_symbols:
            strategies: list = self.symbol_strategy_map[vt_symbol]
            strategies.append(strategy)

        self.save_strategy_setting()
        self.put_strategy_event(strategy)

    def init_strategy(self, strategy_name: str) -> None:
        """
        Init a strategy.
        """
        self.init_executor.submit(self._init_strategy, strategy_name)

    def _init_strategy(self, strategy_name: str) -> None:
        """
        Init strategies in queue.
        """
        strategy: StrategyTemplate = self.strategies[strategy_name]

        if strategy.inited:
            self.write_log(f"{strategy_name}已经完成初始化，禁止重复操作")
            return

        self.write_log(f"{strategy_name}开始执行初始化")

        # Call on_init function of strategy
        self.call_strategy_func(strategy, strategy.on_init)

        # Restore strategy data(variables)
        data: Optional[dict] = self.strategy_data.get(strategy_name, None)
        if data:
            for name in strategy.variables:
                value: Optional[Any] = data.get(name, None)
                if name == "pos":
                    pos = getattr(strategy, name)
                    pos.update(value)
                elif value is not None:
                    setattr(strategy, name, value)

        # Subscribe market data
        for vt_symbol in strategy.vt_symbols:
            contract: Optional[ContractData] = self.main_engine.get_contract(vt_symbol)
            if contract:
                req: SubscribeRequest = SubscribeRequest(
                    symbol=contract.symbol, exchange=contract.exchange)
                self.main_engine.subscribe(req, contract.gateway_name)
            else:
                self.write_log(f"行情订阅失败，找不到合约{vt_symbol}", strategy)

        # Put event to update init completed status.
        strategy.inited = True
        self.put_strategy_event(strategy)
        self.write_log(f"{strategy_name}初始化完成")

    def start_strategy(self, strategy_name: str) -> None:
        """
        Start a strategy.
        """
        strategy: StrategyTemplate = self.strategies[strategy_name]
        if not strategy.inited:
            self.write_log(f"策略{strategy.strategy_name}启动失败，请先初始化")
            return

        if strategy.trading:
            self.write_log(f"{strategy_name}已经启动，请勿重复操作")
            return

        self.call_strategy_func(strategy, strategy.on_start)
        strategy.trading = True

        self.put_strategy_event(strategy)

    def stop_strategy(self, strategy_name: str) -> None:
        """
        Stop a strategy.
        """
        strategy: StrategyTemplate = self.strategies[strategy_name]
        if not strategy.trading:
            return

        # Call on_stop function of the strategy
        self.call_strategy_func(strategy, strategy.on_stop)

        # Change trading status of strategy to False
        strategy.trading = False

        # Cancel all orders of the strategy
        strategy.cancel_all()

        # Sync strategy variables to data file
        self.sync_strategy_data(strategy)

        # Update GUI
        self.put_strategy_event(strategy)

    def edit_strategy(self, strategy_name: str, setting: dict) -> None:
        """
        Edit parameters of a strategy.
        """
        strategy: StrategyTemplate = self.strategies[strategy_name]
        strategy.update_setting(setting)

        self.save_strategy_setting()
        self.put_strategy_event(strategy)

    def remove_strategy(self, strategy_name: str) -> bool:
        """
        Remove a strategy.
        """
        strategy: StrategyTemplate = self.strategies[strategy_name]
        if strategy.trading:
            self.write_log(f"策略{strategy.strategy_name}移除失败，请先停止")
            return

        # Remove from symbol strategy map
        for vt_symbol in strategy.vt_symbols:
            strategies: list = self.symbol_strategy_map[vt_symbol]
            strategies.remove(strategy)

        # Remove from vt_orderid strategy map
        for vt_orderid in strategy.active_orderids:
            if vt_orderid in self.orderid_strategy_map:
                self.orderid_strategy_map.pop(vt_orderid)

        # Remove from strategies
        self.strategies.pop(strategy_name)
        self.save_strategy_setting()

        return True

    def load_strategy_class(self) -> None:
        """
        Load strategy class from source code.
        """
        path1: Path = Path(__file__).parent.joinpath("strategies")
        self.load_strategy_class_from_folder(path1, "vnpy_portfoliostrategy.strategies")

        path2: Path = Path.cwd().joinpath("strategies")
        self.load_strategy_class_from_folder(path2, "strategies")

    def load_strategy_class_from_folder(self, path: Path, module_name: str = "") -> None:
        """
        Load strategy class from certain folder.
        """
        for suffix in ["py", "pyd", "so"]:
            pathname: str = str(path.joinpath(f"*.{suffix}"))
            for filepath in glob.glob(pathname):
                stem: str = Path(filepath).stem
                strategy_module_name: str = f"{module_name}.{stem}"
                self.load_strategy_class_from_module(strategy_module_name)

    def load_strategy_class_from_module(self, module_name: str) -> None:
        """
        Load strategy class from module file.
        """
        try:
            module: ModuleType = importlib.import_module(module_name)

            for name in dir(module):
                value = getattr(module, name)
                if (isinstance(value, type) and issubclass(value, StrategyTemplate) and value is not StrategyTemplate):
                    self.classes[value.__name__] = value
        except:  # noqa
            msg: str = f"策略文件{module_name}加载失败，触发异常：\n{traceback.format_exc()}"
            self.write_log(msg)

    def load_strategy_data(self) -> None:
        """
        Load strategy data from json file.
        """
        self.strategy_data = load_json(self.data_filename)

    def sync_strategy_data(self, strategy: StrategyTemplate) -> None:
        """
        Sync strategy data into json file.
        """
        data: dict = strategy.get_variables()
        data.pop("inited")      # Strategy status (inited, trading) should not be synced.
        data.pop("trading")

        self.strategy_data[strategy.strategy_name] = data
        save_json(self.data_filename, self.strategy_data)

    def get_all_strategy_class_names(self) -> list:
        """
        Return names of strategy classes loaded.
        """
        return list(self.classes.keys())

    def get_strategy_class_parameters(self, class_name: str) -> dict:
        """
        Get default parameters of a strategy class.
        """
        strategy_class: StrategyTemplate = self.classes[class_name]

        parameters: dict = {}
        for name in strategy_class.parameters:
            parameters[name] = getattr(strategy_class, name)

        return parameters

    def get_strategy_parameters(self, strategy_name) -> dict:
        """
        Get parameters of a strategy.
        """
        strategy: StrategyTemplate = self.strategies[strategy_name]
        return strategy.get_parameters()

    def init_all_strategies(self) -> None:
        """"""
        for strategy_name in self.strategies.keys():
            self.init_strategy(strategy_name)

    def start_all_strategies(self) -> None:
        """"""
        for strategy_name in self.strategies.keys():
            self.start_strategy(strategy_name)

    def stop_all_strategies(self) -> None:
        """"""
        for strategy_name in self.strategies.keys():
            self.stop_strategy(strategy_name)

    def load_strategy_setting(self) -> None:
        """
        Load setting file.
        """
        strategy_setting: dict = load_json(self.setting_filename)

        for strategy_name, strategy_config in strategy_setting.items():
            self.add_strategy(
                strategy_config["class_name"],
                strategy_name,
                strategy_config["vt_symbols"],
                strategy_config["setting"]
            )

    def save_strategy_setting(self) -> None:
        """
        Save setting file.
        """
        strategy_setting: dict = {}

        for name, strategy in self.strategies.items():
            strategy_setting[name] = {
                "class_name": strategy.__class__.__name__,
                "vt_symbols": strategy.vt_symbols,
                "setting": strategy.get_parameters()
            }

        save_json(self.setting_filename, strategy_setting)

    def put_strategy_event(self, strategy: StrategyTemplate) -> None:
        """
        Put an event to update strategy status.
        """
        data: dict = strategy.get_data()
        event: Event = Event(EVENT_PORTFOLIO_STRATEGY, data)
        self.event_engine.put(event)

    def write_log(self, msg: str, strategy: StrategyTemplate = None) -> None:
        """
        Create portfolio engine log event.
        """
        if strategy:
            msg: str = f"{strategy.strategy_name}: {msg}"

        log: LogData = LogData(msg=msg, gateway_name=APP_NAME)
        event: Event = Event(type=EVENT_PORTFOLIO_LOG, data=log)
        self.event_engine.put(event)

    def send_email(self, msg: str, strategy: StrategyTemplate = None) -> None:
        """
        Send email to default receiver.
        """
        if strategy:
            subject: str = f"{strategy.strategy_name}"
        else:
            subject: str = "组合策略引擎"

        self.main_engine.send_email(subject, msg)