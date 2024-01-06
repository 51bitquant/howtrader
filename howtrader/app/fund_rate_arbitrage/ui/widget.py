from typing import Dict, Any
from howtrader.event import Event, EventEngine
from howtrader.trader.engine import MainEngine
from howtrader.trader.ui import QtCore, QtGui, QtWidgets
from howtrader.trader.ui.widget import (
    BaseCell,
    EnumCell,
    MsgCell,
    TimeCell,
    BaseMonitor
)
from ..base import (
    APP_NAME
)
from ..engine import FundRateEngine

from howtrader.trader.object import SubscribeRequest
from howtrader.trader.event import EVENT_TICK, EVENT_FUND_RATE_LOG, EVENT_FUNd_RATE_STRATEGY, EVENT_FUND_RATE_DATA
from howtrader.trader.utility import load_json, save_json, get_digits
from howtrader.trader.object import Exchange, PremiumIndexData, TickData

class FundRateManager(QtWidgets.QWidget):
    """"""

    signal_log = QtCore.pyqtSignal(Event)
    signal_strategy = QtCore.pyqtSignal(Event)

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine):
        super(FundRateManager, self).__init__()

        self.main_engine = main_engine
        self.event_engine = event_engine
        self.fund_rate_engine: FundRateEngine = main_engine.get_engine(APP_NAME)

        self.managers = {}

        self.init_ui()
        self.register_event()
        self.fund_rate_engine.init_engine()
        self.update_class_combo()

    def init_ui(self):
        """"""
        self.setWindowTitle("资金费率套利")

        # Create widgets
        self.class_combo = QtWidgets.QComboBox()

        add_button = QtWidgets.QPushButton("添加策略")
        add_button.clicked.connect(self.add_strategy)

        init_button = QtWidgets.QPushButton("全部初始化")
        init_button.clicked.connect(self.fund_rate_engine.init_all_strategies)

        start_button = QtWidgets.QPushButton("全部启动")
        start_button.clicked.connect(self.fund_rate_engine.start_all_strategies)

        stop_button = QtWidgets.QPushButton("全部停止")
        stop_button.clicked.connect(self.fund_rate_engine.stop_all_strategies)

        clear_button = QtWidgets.QPushButton("清空日志")
        clear_button.clicked.connect(self.clear_log)

        self.scroll_layout = QtWidgets.QVBoxLayout()
        self.scroll_layout.addStretch()

        scroll_widget = QtWidgets.QWidget()
        scroll_widget.setLayout(self.scroll_layout)

        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(scroll_widget)

        self.orderbook = OrderbookWidget(self.main_engine, self.event_engine)
        self.orderbook.setMinimumWidth(500)

        self.log_monitor = LogMonitor(self.main_engine, self.event_engine)

        self.contract_fund_rate_monitor = ContractFundRateMonitor(
            self.main_engine, self.event_engine
        )

        self.contract_fund_rate_monitor.itemDoubleClicked.connect(self.orderbook.update_with_cell)

        # Set layout
        hbox1 = QtWidgets.QHBoxLayout()
        hbox1.addWidget(self.class_combo)
        hbox1.addWidget(add_button)
        hbox1.addStretch()
        hbox1.addWidget(init_button)
        hbox1.addWidget(start_button)
        hbox1.addWidget(stop_button)
        hbox1.addWidget(clear_button)

        grid = QtWidgets.QGridLayout()  # 网格布局.
        grid.addWidget(self.orderbook, 0, 0, 1,1)
        grid.addWidget(self.contract_fund_rate_monitor, 0,1, 1,1)
        grid.addWidget(self.log_monitor, 0, 2, 1,1)
        grid.addWidget(scroll_area, 1,0, 1,3)

        vbox = QtWidgets.QVBoxLayout()
        vbox.addLayout(hbox1)
        vbox.addLayout(grid)

        self.setLayout(vbox)

        # grid = QtWidgets.QGridLayout()  # 网格布局.
        # grid.addWidget(scroll_area, 0, 0, 2,1)
        #
        # grid.addWidget(self.orderbook, 0, 1)
        #
        # grid.addWidget(self.contract_fund_rate_monitor, 0,2)
        # grid.addWidget(self.log_monitor, 1, 2)
        #
        # vbox = QtWidgets.QVBoxLayout()
        # vbox.addLayout(hbox1)
        # vbox.addLayout(grid)
        #
        # self.setLayout(vbox)

    def update_class_combo(self):
        """"""
        self.class_combo.addItems(
            self.fund_rate_engine.get_all_strategy_class_names()
        )

    def register_event(self):
        """"""
        self.signal_strategy.connect(self.process_strategy_event)

        self.event_engine.register(
            EVENT_FUNd_RATE_STRATEGY, self.signal_strategy.emit
        )

    def process_strategy_event(self, event):
        """
        Update strategy status onto its monitor.
        """
        data = event.data
        strategy_name = data["strategy_name"]

        if strategy_name in self.managers:
            manager = self.managers[strategy_name]
            manager.update_data(data)
        else:
            manager = StrategyManager(self, self.fund_rate_engine, data)
            self.scroll_layout.insertWidget(0, manager)
            self.managers[strategy_name] = manager

    def remove_strategy(self, strategy_name):
        """"""
        manager = self.managers.pop(strategy_name)
        manager.deleteLater()

    def add_strategy(self):
        """"""
        class_name = str(self.class_combo.currentText())
        if not class_name:
            return

        parameters = self.fund_rate_engine.get_strategy_class_parameters(class_name)
        editor = SettingEditor(parameters, class_name=class_name)
        n = editor.exec_()

        if n == editor.Accepted:
            setting = editor.get_setting()
            spot_vt_symbol = setting.pop("spot_vt_symbol")
            future_vt_symbol = setting.pop("future_vt_symbol")
            strategy_name = setting.pop("strategy_name")

            self.fund_rate_engine.add_strategy(
                class_name, strategy_name, spot_vt_symbol, future_vt_symbol, setting
            )

    def clear_log(self):
        """"""
        self.log_monitor.setRowCount(0)

    def show(self):
        """"""
        self.showMaximized()


class StrategyManager(QtWidgets.QFrame):
    """
    Manager for a strategy
    """

    def __init__(
        self, fund_rate_manager: FundRateManager,fund_rate_engine: FundRateEngine, data: dict
    ):
        """"""
        super(StrategyManager, self).__init__()

        self.fund_rate_manager:FundRateManager = fund_rate_manager
        self.fund_rate_engine: FundRateEngine = fund_rate_engine

        self.strategy_name = data["strategy_name"]
        self._data = data

        self.init_ui()

    def init_ui(self):
        """"""
        self.setFixedHeight(300)
        self.setFrameShape(self.Box)
        self.setLineWidth(1)

        self.init_button = QtWidgets.QPushButton("初始化")
        self.init_button.clicked.connect(self.init_strategy)

        self.start_button = QtWidgets.QPushButton("启动")
        self.start_button.clicked.connect(self.start_strategy)
        self.start_button.setEnabled(False)

        self.stop_button = QtWidgets.QPushButton("停止")
        self.stop_button.clicked.connect(self.stop_strategy)
        self.stop_button.setEnabled(False)

        # 添加编辑的功能.
        self.edit_button = QtWidgets.QPushButton('编辑')
        self.edit_button.clicked.connect(self.edit_strategy)
        self.edit_button.setEnabled(True)

        self.remove_button = QtWidgets.QPushButton("移除")
        self.remove_button.clicked.connect(self.remove_strategy)

        strategy_name = self._data["strategy_name"]
        spot_vt_symbol = self._data["spot_vt_symbol"]
        future_vt_symbol = self._data["future_vt_symbol"]
        class_name = self._data["class_name"]
        author = self._data["author"]

        label_text = (
            f"{strategy_name} - {spot_vt_symbol}-{future_vt_symbol} ({class_name} by {author})"
        )
        label = QtWidgets.QLabel(label_text)
        label.setAlignment(QtCore.Qt.AlignCenter)

        self.parameters_monitor = DataMonitor(self._data["parameters"])
        self.variables_monitor = DataMonitor(self._data["variables"])

        hbox = QtWidgets.QHBoxLayout()
        hbox.addWidget(self.init_button)
        hbox.addWidget(self.start_button)
        hbox.addWidget(self.stop_button)
        hbox.addWidget(self.edit_button)
        hbox.addWidget(self.remove_button)

        vbox = QtWidgets.QVBoxLayout()
        vbox.addWidget(label)
        vbox.addLayout(hbox)
        vbox.addWidget(self.parameters_monitor)
        vbox.addWidget(self.variables_monitor)
        self.setLayout(vbox)

    def update_data(self, data: dict):
        """"""
        self._data = data

        self.parameters_monitor.update_data(data["parameters"])
        self.variables_monitor.update_data(data["variables"])

        # Update button status
        variables = data["variables"]
        inited = variables["inited"]
        trading = variables["trading"]

        if not inited:
            return
        self.init_button.setEnabled(False)

        if trading:
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.remove_button.setEnabled(False)
            self.edit_button.setEnabled(False)
        else:
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.remove_button.setEnabled(True)
            self.edit_button.setEnabled(True)

    def init_strategy(self):
        """"""
        self.fund_rate_engine.init_strategy(self.strategy_name)

    def start_strategy(self):
        """"""
        self.fund_rate_engine.start_strategy(self.strategy_name)

    def stop_strategy(self):
        """"""
        self.fund_rate_engine.stop_strategy(self.strategy_name)

    def edit_strategy(self):
        """"""
        strategy_name = self._data["strategy_name"]

        parameters = self.fund_rate_engine.get_strategy_parameters(strategy_name)
        editor = SettingEditor(parameters, strategy_name=strategy_name)
        n = editor.exec_()

        if n == editor.Accepted:
            setting = editor.get_setting()
            self.fund_rate_engine.edit_strategy(strategy_name, setting)

    def remove_strategy(self):
        """"""
        result = self.fund_rate_engine.remove_strategy(self.strategy_name)

        # Only remove strategy gui manager if it has been removed from engine
        if result:
            self.fund_rate_manager.remove_strategy(self.strategy_name)

class OrderbookWidget(QtWidgets.QFrame):
    """
    General manual trading widget.
    """

    signal_tick = QtCore.pyqtSignal(Event)

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine):
        """"""
        super().__init__()

        self.main_engine: MainEngine = main_engine
        self.event_engine: EventEngine = event_engine

        self.vt_symbol_spot: str = ""
        self.vt_symbol_future: str = ""

        self.price_digits_spot: int = 0
        self.price_digits_future: int = 0
        self.spot_tick = None
        self.future_tick = None

        self.init_ui()
        self.register_event()

    def init_ui(self) -> None:
        """"""
        self.setFixedWidth(300)

        # Trading function area

        self.symbol_line_spot = QtWidgets.QLineEdit()
        self.symbol_line_spot.returnPressed.connect(self.set_vt_symbol_spot)

        self.symbol_line_future = QtWidgets.QLineEdit()
        self.symbol_line_future.returnPressed.connect(self.set_vt_symbol_future)

        grid = QtWidgets.QGridLayout()
        grid.addWidget(QtWidgets.QLabel("现货代码: "), 1, 0)
        grid.addWidget(self.symbol_line_spot, 1, 1, 1, 1)

        grid.addWidget(QtWidgets.QLabel("合约代码: "), 1, 2, 1,1)
        grid.addWidget(self.symbol_line_future, 1, 3, 1, 1)


        # Market depth display area
        bid_color = "rgb(255,174,201)"
        ask_color = "rgb(160,255,160)"


        self.spot_bp1_label = self.create_label(bid_color)
        self.spot_bp2_label = self.create_label(bid_color)
        self.spot_bp3_label = self.create_label(bid_color)
        self.spot_bp4_label = self.create_label(bid_color)
        self.spot_bp5_label = self.create_label(bid_color)

        self.spot_bv1_label = self.create_label(
            bid_color, alignment=QtCore.Qt.AlignRight)
        self.spot_bv2_label = self.create_label(
            bid_color, alignment=QtCore.Qt.AlignRight)
        self.spot_bv3_label = self.create_label(
            bid_color, alignment=QtCore.Qt.AlignRight)
        self.spot_bv4_label = self.create_label(
            bid_color, alignment=QtCore.Qt.AlignRight)
        self.spot_bv5_label = self.create_label(
            bid_color, alignment=QtCore.Qt.AlignRight)

        self.spot_ap1_label = self.create_label(ask_color)
        self.spot_ap2_label = self.create_label(ask_color)
        self.spot_ap3_label = self.create_label(ask_color)
        self.spot_ap4_label = self.create_label(ask_color)
        self.spot_ap5_label = self.create_label(ask_color)

        self.spot_av1_label = self.create_label(
            ask_color, alignment=QtCore.Qt.AlignRight)
        self.spot_av2_label = self.create_label(
            ask_color, alignment=QtCore.Qt.AlignRight)
        self.spot_av3_label = self.create_label(
            ask_color, alignment=QtCore.Qt.AlignRight)
        self.spot_av4_label = self.create_label(
            ask_color, alignment=QtCore.Qt.AlignRight)
        self.spot_av5_label = self.create_label(
            ask_color, alignment=QtCore.Qt.AlignRight)

        self.bid_price_gap_label =  QtWidgets.QLabel()
        self.bid_price_gap_pct_label = QtWidgets.QLabel()
        self.bid_price_gap_label.setText('bid价差：0')
        self.bid_price_gap_pct_label.setText('bid价差百分比: 0')

        form = QtWidgets.QFormLayout()

        spot_price_label = QtWidgets.QLabel()
        spot_price_label.setText('价格')

        spot_volume_label = QtWidgets.QLabel()
        spot_volume_label.setText("数量")

        form.addRow(spot_price_label, spot_volume_label)
        form.addRow(self.spot_ap5_label, self.spot_av5_label)
        form.addRow(self.spot_ap4_label, self.spot_av4_label)
        form.addRow(self.spot_ap3_label, self.spot_av3_label)
        form.addRow(self.spot_ap2_label, self.spot_av2_label)
        form.addRow(self.spot_ap1_label, self.spot_av1_label)
        form.addRow(self.spot_bp1_label, self.spot_bv1_label)
        form.addRow(self.spot_bp2_label, self.spot_bv2_label)
        form.addRow(self.spot_bp3_label, self.spot_bv3_label)
        form.addRow(self.spot_bp4_label, self.spot_bv4_label)
        form.addRow(self.spot_bp5_label, self.spot_bv5_label)

        ##############################################
        self.future_bp1_label = self.create_label(bid_color)
        self.future_bp2_label = self.create_label(bid_color)
        self.future_bp3_label = self.create_label(bid_color)
        self.future_bp4_label = self.create_label(bid_color)
        self.future_bp5_label = self.create_label(bid_color)

        self.future_bv1_label = self.create_label(
            bid_color, alignment=QtCore.Qt.AlignRight)
        self.future_bv2_label = self.create_label(
            bid_color, alignment=QtCore.Qt.AlignRight)
        self.future_bv3_label = self.create_label(
            bid_color, alignment=QtCore.Qt.AlignRight)
        self.future_bv4_label = self.create_label(
            bid_color, alignment=QtCore.Qt.AlignRight)
        self.future_bv5_label = self.create_label(
            bid_color, alignment=QtCore.Qt.AlignRight)

        self.future_ap1_label = self.create_label(ask_color)
        self.future_ap2_label = self.create_label(ask_color)
        self.future_ap3_label = self.create_label(ask_color)
        self.future_ap4_label = self.create_label(ask_color)
        self.future_ap5_label = self.create_label(ask_color)

        self.future_av1_label = self.create_label(
            ask_color, alignment=QtCore.Qt.AlignRight)
        self.future_av2_label = self.create_label(
            ask_color, alignment=QtCore.Qt.AlignRight)
        self.future_av3_label = self.create_label(
            ask_color, alignment=QtCore.Qt.AlignRight)
        self.future_av4_label = self.create_label(
            ask_color, alignment=QtCore.Qt.AlignRight)
        self.future_av5_label = self.create_label(
            ask_color, alignment=QtCore.Qt.AlignRight)

        self.ask_price_gap_pct_label = QtWidgets.QLabel()
        self.ask_price_gap_pct_label.setText('ask价差百分比: 0')

        future_price_label = QtWidgets.QLabel()
        future_price_label.setText('价格')

        future_volume_label = QtWidgets.QLabel()
        future_volume_label.setText("数量")

        form2 = QtWidgets.QFormLayout()

        form2.addRow(future_price_label, future_volume_label)
        form2.addRow(self.future_ap5_label, self.future_av5_label)
        form2.addRow(self.future_ap4_label, self.future_av4_label)
        form2.addRow(self.future_ap3_label, self.future_av3_label)
        form2.addRow(self.future_ap2_label, self.future_av2_label)
        form2.addRow(self.future_ap1_label, self.future_av1_label)
        form2.addRow(self.future_bp1_label, self.future_bv1_label)
        form2.addRow(self.future_bp2_label, self.future_bv2_label)
        form2.addRow(self.future_bp3_label, self.future_bv3_label)
        form2.addRow(self.future_bp4_label, self.future_bv4_label)
        form2.addRow(self.future_bp5_label, self.future_bv5_label)

        hbox = QtWidgets.QHBoxLayout()
        hbox.addLayout(form)
        hbox.addLayout(form2)

        gap_hbox = QtWidgets.QHBoxLayout()
        gap_grid = QtWidgets.QGridLayout()

        gap_grid.addWidget(self.bid_price_gap_pct_label ,1, 0, 1,1)
        gap_grid.addWidget(self.ask_price_gap_pct_label, 1,2,1,1)
        gap_hbox.addLayout(gap_grid)

        # Overall layout
        vbox = QtWidgets.QVBoxLayout()
        vbox.addLayout(grid)
        vbox.addLayout(hbox)
        vbox.addLayout(gap_hbox)

        self.setLayout(vbox)

    def create_label(
        self,
        color: str = "",
        alignment: int = QtCore.Qt.AlignLeft
    ) -> QtWidgets.QLabel:
        """
        Create label with certain font color.
        """
        label = QtWidgets.QLabel()
        if color:
            label.setStyleSheet(f"color:{color}")
        label.setAlignment(alignment)
        label.setText("0")
        return label

    def register_event(self) -> None:
        """"""
        self.signal_tick.connect(self.process_tick_event)
        self.event_engine.register(EVENT_TICK, self.signal_tick.emit)

    def process_tick_event(self, event: Event) -> None:
        """"""
        tick = event.data
        if tick.vt_symbol == self.vt_symbol_spot:

            price_digits = self.price_digits_spot
            self.spot_tick = tick

            if self.future_tick and tick.bid_price_1 > 0:
                r = (self.future_tick.bid_price_1 / tick.bid_price_1 - 1) * 100
                self.bid_price_gap_pct_label.setText(f"bid价差百分比: {r:.3f}%")

            self.spot_bp1_label.setText(f"{tick.bid_price_1:.{price_digits}f}")
            self.spot_bv1_label.setText(str(tick.bid_volume_1))
            self.spot_ap1_label.setText(f"{tick.ask_price_1:.{price_digits}f}")
            self.spot_av1_label.setText(str(tick.ask_volume_1))

            if tick.bid_price_2:
                self.spot_bp2_label.setText(f"{tick.bid_price_2:.{price_digits}f}")
                self.spot_bv2_label.setText(str(tick.bid_volume_2))
                self.spot_ap2_label.setText(f"{tick.ask_price_2:.{price_digits}f}")
                self.spot_av2_label.setText(str(tick.ask_volume_2))

                self.spot_bp3_label.setText(f"{tick.bid_price_3:.{price_digits}f}")
                self.spot_bv3_label.setText(str(tick.bid_volume_3))
                self.spot_ap3_label.setText(f"{tick.ask_price_3:.{price_digits}f}")
                self.spot_av3_label.setText(str(tick.ask_volume_3))

                self.spot_bp4_label.setText(f"{tick.bid_price_4:.{price_digits}f}")
                self.spot_bv4_label.setText(str(tick.bid_volume_4))
                self.spot_ap4_label.setText(f"{tick.ask_price_4:.{price_digits}f}")
                self.spot_av4_label.setText(str(tick.ask_volume_4))

                self.spot_bp5_label.setText(f"{tick.bid_price_5:.{price_digits}f}")
                self.spot_bv5_label.setText(str(tick.bid_volume_5))
                self.spot_ap5_label.setText(f"{tick.ask_price_5:.{price_digits}f}")
                self.spot_av5_label.setText(str(tick.ask_volume_5))

        if tick.vt_symbol == self.vt_symbol_future:
            self.future_tick = tick
            price_digits = self.price_digits_future

            if self.spot_tick and self.spot_tick.ask_price_1 > 0:
                r = (tick.ask_price_1 / self.spot_tick.ask_price_1 - 1) * 100
                self.ask_price_gap_pct_label.setText(f"ask价差百分比:{r:.3f}%")

            self.future_bp1_label.setText(f"{tick.bid_price_1:.{price_digits}f}")
            self.future_bv1_label.setText(str(tick.bid_volume_1))
            self.future_ap1_label.setText(f"{tick.ask_price_1:.{price_digits}f}")
            self.future_av1_label.setText(str(tick.ask_volume_1))



            if tick.bid_price_2:
                self.future_bp2_label.setText(f"{tick.bid_price_2:.{price_digits}f}")
                self.future_bv2_label.setText(str(tick.bid_volume_2))
                self.future_ap2_label.setText(f"{tick.ask_price_2:.{price_digits}f}")
                self.future_av2_label.setText(str(tick.ask_volume_2))

                self.future_bp3_label.setText(f"{tick.bid_price_3:.{price_digits}f}")
                self.future_bv3_label.setText(str(tick.bid_volume_3))
                self.future_ap3_label.setText(f"{tick.ask_price_3:.{price_digits}f}")
                self.future_av3_label.setText(str(tick.ask_volume_3))

                self.future_bp4_label.setText(f"{tick.bid_price_4:.{price_digits}f}")
                self.future_bv4_label.setText(str(tick.bid_volume_4))
                self.future_ap4_label.setText(f"{tick.ask_price_4:.{price_digits}f}")
                self.future_av4_label.setText(str(tick.ask_volume_4))

                self.future_bp5_label.setText(f"{tick.bid_price_5:.{price_digits}f}")
                self.future_bv5_label.setText(str(tick.bid_volume_5))
                self.future_ap5_label.setText(f"{tick.ask_price_5:.{price_digits}f}")
                self.future_av5_label.setText(str(tick.ask_volume_5))


    def set_vt_symbol_spot(self) -> None:
        """
        Set the tick depth data to monitor by vt_symbol.
        """
        vt_symbol = str(self.symbol_line_spot.text())
        if not vt_symbol:
            return

        self.vt_symbol_spot = vt_symbol

        # Update name line widget and clear all labels
        contract = self.main_engine.get_contract(vt_symbol)
        if contract:
            gateway_name = contract.gateway_name
            self.price_digits_spot = get_digits(contract.pricetick)
        else:
            return

        # Subscribe tick data

        req = SubscribeRequest(
            symbol=vt_symbol.split('.')[0], exchange=Exchange.BINANCE
        )

        self.main_engine.subscribe(req, gateway_name)

    def set_vt_symbol_future(self) -> None:
        """
        Set the tick depth data to monitor by vt_symbol.
        """
        vt_symbol = str(self.symbol_line_future.text())
        if not vt_symbol:
            return

        self.vt_symbol_future = vt_symbol

        # Update name line widget and clear all labels
        contract = self.main_engine.get_contract(vt_symbol)
        if contract:
            gateway_name = contract.gateway_name
            self.price_digits_future = get_digits(contract.pricetick)
        else:
            return

        # Subscribe tick data

        req = SubscribeRequest(
            symbol=vt_symbol.split('.')[0], exchange=Exchange.BINANCE
        )

        self.main_engine.subscribe(req, gateway_name)

    def update_with_cell(self, cell: BaseCell):

        data = cell.get_data()
        symbol:str = data.symbol
        if symbol:
            self.symbol_line_spot.setText(f"{symbol.lower()}.BINANCE")
            self.symbol_line_future.setText(f"{symbol.upper()}.BINANCE")
            self.set_vt_symbol_future()
            self.set_vt_symbol_spot()

class DataMonitor(QtWidgets.QTableWidget):
    """
    Table monitor for parameters and variables.
    """

    def __init__(self, data: dict):
        """"""
        super(DataMonitor, self).__init__()

        self._data = data
        self.cells = {}

        self.init_ui()

    def init_ui(self):
        """"""
        labels = list(self._data.keys())
        self.setColumnCount(len(labels))
        self.setHorizontalHeaderLabels(labels)

        self.setRowCount(1)
        self.verticalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.Stretch
        )
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(self.NoEditTriggers)

        for column, name in enumerate(self._data.keys()):
            value = self._data[name]

            cell = QtWidgets.QTableWidgetItem(str(value))
            cell.setTextAlignment(QtCore.Qt.AlignCenter)

            self.setItem(0, column, cell)
            self.cells[name] = cell

    def update_data(self, data: dict):
        """"""
        for name, value in data.items():
            cell = self.cells[name]
            cell.setText(str(value))


class ContractFundRateMonitor(QtWidgets.QTableWidget):
    """
     Monitor the contract fund rate
     """

    event_type = EVENT_FUND_RATE_DATA
    data_key = "vt_symbol"
    sorting = True

    headers = {
        "symbol": {"display": "交易对", "cell": BaseCell, "update": True},
        "lastFundingRateStr": {"display": "资金费率%", "cell": BaseCell, "update": True},
        "nextFundingTimeStr": {"display": "距离下次结算", "cell": BaseCell, "update": True},
        # "bid_spread_pct": {"display": "bid价差%", "cell": BaseCell, "update": True},
        # "ask_spread_pct": {"display": "ask价差%", "cell": BaseCell, "update": True}
    }

    signal: QtCore.pyqtSignal = QtCore.pyqtSignal(Event)

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine):
        """"""
        super(ContractFundRateMonitor, self).__init__()

        self.main_engine: MainEngine = main_engine
        self.event_engine: EventEngine = event_engine
        self.cells: Dict[str, dict] = {}

        self.init_ui()
        self.register_event()

    def init_ui(self) -> None:
        """"""
        self.init_table()
        self.init_menu()

    def init_table(self) -> None:
        """
        Initialize table.
        """
        self.setColumnCount(len(self.headers))

        labels = [d["display"] for d in self.headers.values()]
        self.setHorizontalHeaderLabels(labels)

        self.verticalHeader().setVisible(False)
        self.setEditTriggers(self.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(self.sorting)

    def init_menu(self) -> None:
        """
        Create right click menu.
        """
        self.menu = QtWidgets.QMenu(self)

        resize_action = QtWidgets.QAction("调整列宽", self)
        resize_action.triggered.connect(self.resize_columns)
        self.menu.addAction(resize_action)

    def register_event(self) -> None:
        """
        Register event handler into event engine.
        """
        if self.event_type:
            self.signal.connect(self.process_event)
            self.event_engine.register(self.event_type, self.signal.emit)

    def process_event(self, event: Event) -> None:
        """
        Process new data from event and update into table.
        """
        # Disable sorting to prevent unwanted error.
        if self.sorting:
            self.setSortingEnabled(False)

        # Update data into table.
        data: PremiumIndexData  = event.data

        # future_tick: TickData = self.main_engine.get_tick(f"{data.symbol.upper()}.BINANCE")
        # spot_tick:TickData = self.main_engine.get_tick(f"{data.symbol.lower()}.BINANCE")
        #
        # if future_tick and spot_tick and spot_tick.bid_price_1 > 0 and spot_tick.ask_price_1 > 0:
        #     data.ask_spread_pct = round((future_tick.ask_price_1/spot_tick.ask_price_1 - 1) * 100, 3)
        #     data.bid_spread_pct = round((future_tick.bid_price_1/spot_tick.bid_price_1 - 1) * 100, 3)

        if not self.data_key:
            self.insert_new_row(data)
        else:
            key = data.__getattribute__(self.data_key)

            if key in self.cells:
                self.update_old_row(data)
            else:
                self.insert_new_row(data)

        # Enable sorting
        if self.sorting:
            self.setSortingEnabled(True)

    def insert_new_row(self, data: Any):
        """
        Insert a new row at the top of table.
        """
        self.insertRow(0)

        row_cells = {}
        for column, header in enumerate(self.headers.keys()):
            setting = self.headers[header]

            content = data.__getattribute__(header)
            cell = setting["cell"](content, data)
            self.setItem(0, column, cell)

            if setting["update"]:
                row_cells[header] = cell

        if self.data_key:
            key = data.__getattribute__(self.data_key)
            self.cells[key] = row_cells

    def update_old_row(self, data: Any) -> None:
        """
        Update an old row in table.
        """
        key = data.__getattribute__(self.data_key)
        row_cells = self.cells[key]

        for header, cell in row_cells.items():
            content = data.__getattribute__(header)
            cell.set_content(content, data)

    def resize_columns(self) -> None:
        """
        Resize all columns according to contents.
        """
        self.horizontalHeader().resizeSections(QtWidgets.QHeaderView.ResizeToContents)

    def contextMenuEvent(self, event: QtGui.QContextMenuEvent) -> None:
        """
        Show menu with right click.
        """
        self.menu.popup(QtGui.QCursor.pos())


class LogMonitor(BaseMonitor):
    """
    Monitor for log data.
    """

    event_type = EVENT_FUND_RATE_LOG
    data_key = ""
    sorting = False

    headers = {
        "time": {"display": "时间", "cell": TimeCell, "update": False},
        "msg": {"display": "信息", "cell": MsgCell, "update": False},
    }

    def init_ui(self):
        """
        Stretch last column.
        """
        super(LogMonitor, self).init_ui()

        self.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.Stretch
        )

    def insert_new_row(self, data):
        """
        Insert a new row at the top of table.
        """
        super(LogMonitor, self).insert_new_row(data)
        self.resizeRowToContents(0)


class SettingEditor(QtWidgets.QDialog):
    """
    For creating new strategy and editing strategy parameters.
    """

    def __init__(
        self, parameters: dict, strategy_name: str = "", class_name: str = ""
    ):
        """"""
        super(SettingEditor, self).__init__()

        self.parameters = parameters
        self.strategy_name = strategy_name
        self.class_name = class_name

        self.edits = {}

        self.init_ui()

    def init_ui(self):
        """"""
        form = QtWidgets.QFormLayout()

        # Add spot_vt_symbol, future_vt_symbol,  name edit if add new strategy
        if self.class_name:
            self.setWindowTitle(f"添加资金费率套利策略：{self.class_name}")
            button_text = "添加"
            parameters = {"strategy_name": "", "spot_vt_symbol": "", "future_vt_symbol": ""}
            parameters.update(self.parameters)
        else:
            self.setWindowTitle(f"参数编辑：{self.strategy_name}")
            button_text = "确定"
            parameters = self.parameters

        for name, value in parameters.items():
            type_ = type(value)

            edit = QtWidgets.QLineEdit(str(value))
            if type_ is int:
                validator = QtGui.QIntValidator()
                edit.setValidator(validator)
            elif type_ is float:
                validator = QtGui.QDoubleValidator()
                edit.setValidator(validator)

            form.addRow(f"{name} {type_}", edit)

            self.edits[name] = (edit, type_)

        button = QtWidgets.QPushButton(button_text)
        button.clicked.connect(self.accept)
        form.addRow(button)

        widget = QtWidgets.QWidget()
        widget.setLayout(form)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)

        vbox = QtWidgets.QVBoxLayout()
        vbox.addWidget(scroll)
        self.setLayout(vbox)

    def get_setting(self):
        """"""
        setting = {}

        if self.class_name:
            setting["class_name"] = self.class_name

        for name, tp in self.edits.items():
            edit, type_ = tp
            value_text = edit.text()

            if type_ == bool:
                if value_text == "True":
                    value = True
                else:
                    value = False
            else:
                value = type_(value_text)

            setting[name] = value

        return setting
