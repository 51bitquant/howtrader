import sys
from threading import Thread
from queue import Queue, Empty
from copy import copy
from collections import defaultdict
from typing import Any, Dict, List

from howtrader.event import Event, EventEngine
from howtrader.trader.engine import BaseEngine, MainEngine
from howtrader.trader.constant import Exchange
from howtrader.trader.object import (
    SubscribeRequest,
    TickData,
    BarData,
    ContractData
)
from howtrader.trader.event import EVENT_TICK, EVENT_CONTRACT, EVENT_TIMER
from howtrader.trader.utility import load_json, save_json, BarGenerator
from howtrader.trader.database import BaseDatabase, get_database
from howtrader.app.spread_trading.base import EVENT_SPREAD_DATA, SpreadData


APP_NAME: str = "DataRecorder"

EVENT_RECORDER_LOG: str = "eRecorderLog"
EVENT_RECORDER_UPDATE: str = "eRecorderUpdate"
EVENT_RECORDER_EXCEPTION: str = "eRecorderException"


class RecorderEngine(BaseEngine):
    """
    For running data recorder.
    """

    setting_filename: str = "data_recorder_setting.json"

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine) -> None:
        """"""
        super().__init__(main_engine, event_engine, APP_NAME)

        self.queue: Queue = Queue()
        self.thread: Thread = Thread(target=self.run)
        self.active: bool = False

        self.tick_recordings: Dict[str, Dict] = {}
        self.bar_recordings: Dict[str, Dict] = {}
        self.bar_generators: Dict[str, BarGenerator] = {}

        self.timer_count: int = 0
        self.timer_interval: int = 10

        self.ticks: Dict[str, List[TickData]] = defaultdict(list)
        self.bars: Dict[str, List[BarData]] = defaultdict(list)

        self.database: BaseDatabase = get_database()

        self.load_setting()
        self.register_event()
        self.start()
        self.put_event()

    def load_setting(self) -> None:
        """"""
        setting: dict = load_json(self.setting_filename)
        self.tick_recordings = setting.get("tick", {})
        self.bar_recordings = setting.get("bar", {})

    def save_setting(self) -> None:
        """"""
        setting: dict = {
            "tick": self.tick_recordings,
            "bar": self.bar_recordings
        }
        save_json(self.setting_filename, setting)

    def run(self) -> None:
        """"""
        while self.active:
            try:
                task: Any = self.queue.get(timeout=1)
                task_type, data = task

                if task_type == "tick":
                    self.database.save_tick_data(data)
                elif task_type == "bar":
                    self.database.save_bar_data(data)

            except Empty:
                continue

            except Exception:
                self.active = False

                info = sys.exc_info()
                event: Event = Event(EVENT_RECORDER_EXCEPTION, info)
                self.event_engine.put(event)

    def close(self) -> None:
        """"""
        self.active = False

        if self.thread.is_alive():
            self.thread.join()

    def start(self) -> None:
        """"""
        self.active = True
        self.thread.start()

    def add_bar_recording(self, vt_symbol: str) -> None:
        """"""
        if vt_symbol in self.bar_recordings:
            self.write_log(f"已在K线记录列表中：{vt_symbol}")
            return

        if Exchange.LOCAL.value not in vt_symbol:
            contract: ContractData = self.main_engine.get_contract(vt_symbol)
            if not contract:
                self.write_log(f"找不到合约：{vt_symbol}")
                return

            self.bar_recordings[vt_symbol] = {
                "symbol": contract.symbol,
                "exchange": contract.exchange.value,
                "gateway_name": contract.gateway_name
            }

            self.subscribe(contract)
        else:
            self.bar_recordings[vt_symbol] = {}

        self.save_setting()
        self.put_event()

        self.write_log(f"添加K线记录成功：{vt_symbol}")

    def add_tick_recording(self, vt_symbol: str) -> None:
        """"""
        if vt_symbol in self.tick_recordings:
            self.write_log(f"已在Tick记录列表中：{vt_symbol}")
            return

        # For normal contract
        if Exchange.LOCAL.value not in vt_symbol:
            contract: ContractData = self.main_engine.get_contract(vt_symbol)
            if not contract:
                self.write_log(f"找不到合约：{vt_symbol}")
                return

            self.tick_recordings[vt_symbol] = {
                "symbol": contract.symbol,
                "exchange": contract.exchange.value,
                "gateway_name": contract.gateway_name
            }

            self.subscribe(contract)
        # No need to subscribe for spread data
        else:
            self.tick_recordings[vt_symbol] = {}

        self.save_setting()
        self.put_event()

        self.write_log(f"添加Tick记录成功：{vt_symbol}")

    def remove_bar_recording(self, vt_symbol: str) -> None:
        """"""
        if vt_symbol not in self.bar_recordings:
            self.write_log(f"不在K线记录列表中：{vt_symbol}")
            return

        self.bar_recordings.pop(vt_symbol)
        self.save_setting()
        self.put_event()

        self.write_log(f"移除K线记录成功：{vt_symbol}")

    def remove_tick_recording(self, vt_symbol: str) -> None:
        """"""
        if vt_symbol not in self.tick_recordings:
            self.write_log(f"不在Tick记录列表中：{vt_symbol}")
            return

        self.tick_recordings.pop(vt_symbol)
        self.save_setting()
        self.put_event()

        self.write_log(f"移除Tick记录成功：{vt_symbol}")

    def register_event(self) -> None:
        """"""
        self.event_engine.register(EVENT_TIMER, self.process_timer_event)
        self.event_engine.register(EVENT_TICK, self.process_tick_event)
        self.event_engine.register(EVENT_CONTRACT, self.process_contract_event)
        self.event_engine.register(EVENT_SPREAD_DATA, self.process_spread_event)

    def update_tick(self, tick: TickData) -> None:
        """"""
        if tick.vt_symbol in self.tick_recordings:
            self.record_tick(copy(tick))

        if tick.vt_symbol in self.bar_recordings:
            bg: BarGenerator = self.get_bar_generator(tick.vt_symbol)
            bg.update_tick(copy(tick))

    def process_timer_event(self, event: Event) -> None:
        """"""
        self.timer_count += 1
        if self.timer_count < self.timer_interval:
            return
        self.timer_count = 0

        for bars in self.bars.values():
            self.queue.put(("bar", bars))
        self.bars.clear()

        for ticks in self.ticks.values():
            self.queue.put(("tick", ticks))
        self.ticks.clear()

    def process_tick_event(self, event: Event) -> None:
        """"""
        tick: TickData = event.data
        self.update_tick(tick)

    def process_contract_event(self, event: Event) -> None:
        """"""
        contract: ContractData = event.data
        vt_symbol: str = contract.vt_symbol

        if (vt_symbol in self.tick_recordings or vt_symbol in self.bar_recordings):
            self.subscribe(contract)

    def process_spread_event(self, event: Event) -> None:
        """"""
        spread: SpreadData = event.data
        tick: TickData = spread.to_tick()

        # Filter not inited spread data
        if tick.datetime:
            self.update_tick(tick)

    def write_log(self, msg: str) -> None:
        """"""
        event: Event = Event(
            EVENT_RECORDER_LOG,
            msg
        )
        self.event_engine.put(event)

    def put_event(self) -> None:
        """"""
        tick_symbols: List[str] = list(self.tick_recordings.keys())
        tick_symbols.sort()

        bar_symbols: List[str] = list(self.bar_recordings.keys())
        bar_symbols.sort()

        data: dict = {
            "tick": tick_symbols,
            "bar": bar_symbols
        }

        event: Event = Event(
            EVENT_RECORDER_UPDATE,
            data
        )
        self.event_engine.put(event)

    def record_tick(self, tick: TickData) -> None:
        """"""
        self.ticks[tick.vt_symbol].append(tick)

    def record_bar(self, bar: BarData) -> None:
        """"""
        self.bars[bar.vt_symbol].append(bar)

    def get_bar_generator(self, vt_symbol: str) -> BarGenerator:
        """"""
        bg: BarGenerator = self.bar_generators.get(vt_symbol, None)

        if not bg:
            bg: BarGenerator = BarGenerator(self.record_bar)
            self.bar_generators[vt_symbol] = bg

        return bg

    def subscribe(self, contract: ContractData) -> None:
        """"""
        req: SubscribeRequest = SubscribeRequest(
            symbol=contract.symbol,
            exchange=contract.exchange
        )
        self.main_engine.subscribe(req, contract.gateway_name)