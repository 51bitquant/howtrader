from copy import copy
from typing import Dict, List
from datetime import datetime, timedelta
from tzlocal import get_localzone

from howtrader.event import EventEngine, Event
from howtrader.chart import ChartWidget, CandleItem, VolumeItem
from howtrader.trader.engine import MainEngine
from howtrader.trader.ui import QtWidgets, QtCore
from howtrader.trader.event import EVENT_TICK
from howtrader.trader.object import ContractData, TickData, BarData, SubscribeRequest
from howtrader.trader.utility import BarGenerator
from howtrader.trader.constant import Interval
from vnpy_spreadtrading.base import SpreadData, EVENT_SPREAD_DATA

from ..engine import APP_NAME, EVENT_CHART_HISTORY, ChartWizardEngine


class ChartWizardWidget(QtWidgets.QWidget):
    """"""

    signal_tick = QtCore.pyqtSignal(Event)
    signal_spread = QtCore.pyqtSignal(Event)
    signal_history = QtCore.pyqtSignal(Event)

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine) -> None:
        """"""
        super().__init__()

        self.main_engine: MainEngine = main_engine
        self.event_engine: EventEngine = event_engine
        self.chart_engine: ChartWizardEngine = main_engine.get_engine(APP_NAME)

        self.bgs: Dict[str, BarGenerator] = {}
        self.charts: Dict[str, ChartWidget] = {}

        self.init_ui()
        self.register_event()

    def init_ui(self) -> None:
        """"""
        self.setWindowTitle("K线图表")

        self.tab: QtWidgets.QTabWidget = QtWidgets.QTabWidget()
        self.symbol_line: QtWidgets.QLineEdit = QtWidgets.QLineEdit()

        self.button = QtWidgets.QPushButton("新建图表")
        self.button.clicked.connect(self.new_chart)

        hbox = QtWidgets.QHBoxLayout()
        hbox.addWidget(QtWidgets.QLabel("本地代码"))
        hbox.addWidget(self.symbol_line)
        hbox.addWidget(self.button)
        hbox.addStretch()

        vbox = QtWidgets.QVBoxLayout()
        vbox.addLayout(hbox)
        vbox.addWidget(self.tab)

        self.setLayout(vbox)

    def create_chart(self) -> ChartWidget:
        """"""
        chart = ChartWidget()
        chart.add_plot("candle", hide_x_axis=True)
        chart.add_plot("volume", maximum_height=200)
        chart.add_item(CandleItem, "candle", "candle")
        chart.add_item(VolumeItem, "volume", "volume")
        chart.add_cursor()
        return chart

    def show(self) -> None:
        """"""
        self.showMaximized()

    def new_chart(self) -> None:
        """"""
        # Filter invalid vt_symbol
        vt_symbol: str = self.symbol_line.text()
        if not vt_symbol:
            return

        if vt_symbol in self.charts:
            return

        if "LOCAL" not in vt_symbol:
            contract: ContractData = self.main_engine.get_contract(vt_symbol)
            if not contract:
                return

        # Create new chart
        self.bgs[vt_symbol] = BarGenerator(self.on_bar)

        chart: ChartWidget = self.create_chart()
        self.charts[vt_symbol] = chart

        self.tab.addTab(chart, vt_symbol)

        # Query history data
        end: datetime = datetime.now(get_localzone())
        start: datetime = end - timedelta(days=5)

        self.chart_engine.query_history(
            vt_symbol,
            Interval.MINUTE,
            start,
            end
        )

    def register_event(self) -> None:
        """"""
        self.signal_tick.connect(self.process_tick_event)
        self.signal_history.connect(self.process_history_event)
        self.signal_spread.connect(self.process_spread_event)

        self.event_engine.register(EVENT_CHART_HISTORY, self.signal_history.emit)
        self.event_engine.register(EVENT_TICK, self.signal_tick.emit)
        self.event_engine.register(EVENT_SPREAD_DATA, self.signal_spread.emit)

    def process_tick_event(self, event: Event) -> None:
        """"""
        tick: TickData = event.data
        bg: BarGenerator = self.bgs.get(tick.vt_symbol, None)

        if bg:
            bg.update_tick(tick)

            chart: ChartWidget = self.charts[tick.vt_symbol]
            bar: BarData = copy(bg.bar)
            bar.datetime = bar.datetime.replace(second=0, microsecond=0)
            chart.update_bar(bar)

    def process_history_event(self, event: Event) -> None:
        """"""
        history: List[BarData] = event.data
        if not history:
            return

        bar: BarData = history[0]
        chart: ChartWidget = self.charts[bar.vt_symbol]
        chart.update_history(history)

        # Subscribe following data update
        contract: ContractData = self.main_engine.get_contract(bar.vt_symbol)
        if contract:
            req: SubscribeRequest = SubscribeRequest(
                contract.symbol,
                contract.exchange
            )
            self.main_engine.subscribe(req, contract.gateway_name)

    def process_spread_event(self, event: Event) -> None:
        """"""
        spread: SpreadData = event.data
        tick: TickData = spread.to_tick()

        bg: BarGenerator = self.bgs.get(tick.vt_symbol, None)
        if bg:
            bg.update_tick(tick)

            chart: ChartWidget = self.charts[tick.vt_symbol]
            bar: BarData = copy(bg.bar)
            bar.datetime = bar.datetime.replace(second=0, microsecond=0)
            chart.update_bar(bar)

    def on_bar(self, bar: BarData) -> None:
        """"""
        chart: ChartWidget = self.charts[bar.vt_symbol]
        chart.update_bar(bar)