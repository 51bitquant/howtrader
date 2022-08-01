"""
Basic widgets for UI.
"""

import csv
from datetime import datetime
import platform
from enum import Enum
from typing import Any, Dict, List, Optional
from copy import copy
from tzlocal import get_localzone

import importlib_metadata
from decimal import Decimal
from .qt import Qt, QtCore, QtGui, QtWidgets
from ..constant import Direction, Exchange, Offset, OrderType, Product
from ..engine import MainEngine, Event, EventEngine
from ..event import (
    EVENT_QUOTE,
    EVENT_TICK,
    EVENT_TRADE,
    EVENT_ORDER,
    EVENT_POSITION,
    EVENT_ACCOUNT,
    EVENT_LOG
)
from ..object import (
    OrderRequest,
    SubscribeRequest,
    CancelRequest,
    ContractData,
    PositionData,
    OrderData,
    QuoteData,
    TickData
)
from ..utility import load_json, save_json, get_digits, extract_vt_symbol, round_to
from ..setting import SETTING_FILENAME, SETTINGS, QUICK_TRADER_SETTINGS

COLOR_LONG = QtGui.QColor("red")
COLOR_SHORT = QtGui.QColor("green")
COLOR_BID = QtGui.QColor(255, 174, 201)
COLOR_ASK = QtGui.QColor(160, 255, 160)
COLOR_BLACK = QtGui.QColor("black")


class BaseCell(QtWidgets.QTableWidgetItem):
    """
    General cell used in tablewidgets.
    """

    def __init__(self, content: Any, data: Any) -> None:
        """"""
        super(BaseCell, self).__init__()
        self.setTextAlignment(QtCore.Qt.AlignCenter)
        self.set_content(content, data)

    def set_content(self, content: Any, data: Any) -> None:
        """
        Set text content.
        """
        self.setText(str(content))
        self._data = data

    def get_data(self) -> Any:
        """
        Get data object.
        """
        return self._data


class EnumCell(BaseCell):
    """
    Cell used for showing enum data.
    """

    def __init__(self, content: str, data: Any) -> None:
        """"""
        super(EnumCell, self).__init__(content, data)

    def set_content(self, content: Any, data: Any) -> None:
        """
        Set text using enum.constant.value.
        """
        if content:
            super(EnumCell, self).set_content(content.value, data)


class DirectionCell(EnumCell):
    """
    Cell used for showing direction data.
    """

    def __init__(self, content: str, data: Any) -> None:
        """"""
        super(DirectionCell, self).__init__(content, data)

    def set_content(self, content: Any, data: Any) -> None:
        """
        Cell color is set according to direction.
        """
        super(DirectionCell, self).set_content(content, data)

        if content is Direction.SHORT:
            self.setForeground(COLOR_SHORT)
        else:
            self.setForeground(COLOR_LONG)


class BidCell(BaseCell):
    """
    Cell used for showing bid price and volume.
    """

    def __init__(self, content: Any, data: Any) -> None:
        """"""
        super(BidCell, self).__init__(content, data)

        self.setForeground(COLOR_BID)


class AskCell(BaseCell):
    """
    Cell used for showing ask price and volume.
    """

    def __init__(self, content: Any, data: Any) -> None:
        """"""
        super(AskCell, self).__init__(content, data)

        self.setForeground(COLOR_ASK)


class PnlCell(BaseCell):
    """
    Cell used for showing pnl data.
    """

    def __init__(self, content: Any, data: Any) -> None:
        """"""
        super(PnlCell, self).__init__(content, data)

    def set_content(self, content: Any, data: Any) -> None:
        """
        Cell color is set based on whether pnl is
        positive or negative.
        """
        super(PnlCell, self).set_content(content, data)

        if str(content).startswith("-"):
            self.setForeground(COLOR_SHORT)
        else:
            self.setForeground(COLOR_LONG)


class TimeCell(BaseCell):
    """
    Cell used for showing time string from datetime object.
    """

    local_tz = get_localzone()

    def __init__(self, content: Any, data: Any) -> None:
        """"""
        super(TimeCell, self).__init__(content, data)

    def set_content(self, content: Any, data: Any) -> None:
        """"""
        if content is None:
            return

        content: datetime = content.astimezone(self.local_tz)
        timestamp: str = content.strftime("%H:%M:%S")

        millisecond: int = int(content.microsecond / 1000)
        if millisecond:
            timestamp = f"{timestamp}.{millisecond}"
        else:
            timestamp = f"{timestamp}.000"

        self.setText(timestamp)
        self._data = data


class MsgCell(BaseCell):
    """
    Cell used for showing msg data.
    """

    def __init__(self, content: str, data: Any) -> None:
        """"""
        super(MsgCell, self).__init__(content, data)
        self.setTextAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)


class BaseMonitor(QtWidgets.QTableWidget):
    """
    Monitor data update.
    """

    event_type: str = ""
    data_key: str = ""
    sorting: bool = False
    headers: dict = {}

    signal: QtCore.Signal = QtCore.Signal(Event)

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine) -> None:
        """"""
        super(BaseMonitor, self).__init__()

        self.main_engine: MainEngine = main_engine
        self.event_engine: EventEngine = event_engine
        self.cells: Dict[str, dict] = {}

        self.init_ui()
        # self.load_setting()
        self.register_event()

    def __del__(self) -> None:
        """"""
        # self.save_setting()

    def init_ui(self) -> None:
        """"""
        self.init_table()
        self.init_menu()

    def init_table(self) -> None:
        """
        Initialize table.
        """
        self.setColumnCount(len(self.headers))

        labels: list = [d["display"] for d in self.headers.values()]
        self.setHorizontalHeaderLabels(labels)

        self.verticalHeader().setVisible(False)
        self.setEditTriggers(self.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(self.sorting)

    def init_menu(self) -> None:
        """
        Create right click menu.
        """
        self.menu: QtWidgets.QMenu = QtWidgets.QMenu(self)

        resize_action: QtGui.QAction = QtWidgets.QAction("resize column", self)
        resize_action.triggered.connect(self.resize_columns)
        self.menu.addAction(resize_action)

        save_action: QtGui.QAction = QtWidgets.QAction("save data", self)
        save_action.triggered.connect(self.save_csv)
        self.menu.addAction(save_action)

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
        data = event.data

        if not self.data_key:
            self.insert_new_row(data)
        else:
            key: str = data.__getattribute__(self.data_key)

            if key in self.cells:
                self.update_old_row(data)
            else:
                self.insert_new_row(data)

        # Enable sorting
        if self.sorting:
            self.setSortingEnabled(True)

    def insert_new_row(self, data: Any) -> None:
        """
        Insert a new row at the top of table.
        """
        self.insertRow(0)

        row_cells: dict = {}
        for column, header in enumerate(self.headers.keys()):
            setting: dict = self.headers[header]

            content = data.__getattribute__(header)
            cell: QtWidgets.QTableWidgetItem = setting["cell"](content, data)
            self.setItem(0, column, cell)

            if setting["update"]:
                row_cells[header] = cell

        if self.data_key:
            key: str = data.__getattribute__(self.data_key)
            self.cells[key] = row_cells

    def update_old_row(self, data: Any) -> None:
        """
        Update an old row in table.
        """
        key: str = data.__getattribute__(self.data_key)
        row_cells = self.cells[key]

        for header, cell in row_cells.items():
            content = data.__getattribute__(header)
            cell.set_content(content, data)

    def resize_columns(self) -> None:
        """
        Resize all columns according to contents.
        """
        self.horizontalHeader().resizeSections(QtWidgets.QHeaderView.ResizeToContents)

    def save_csv(self) -> None:
        """
        Save table data into a csv file
        """
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "save_data", "", "CSV(*.csv)")

        if not path:
            return

        with open(path, "w") as f:
            writer = csv.writer(f, lineterminator="\n")

            headers: list = [d["display"] for d in self.headers.values()]
            writer.writerow(headers)

            for row in range(self.rowCount()):
                if self.isRowHidden(row):
                    continue

                row_data: list = []
                for column in range(self.columnCount()):
                    item: QtWidgets.QTableWidgetItem = self.item(row, column)
                    if item:
                        row_data.append(str(item.text()))
                    else:
                        row_data.append("")
                writer.writerow(row_data)

    def contextMenuEvent(self, event: QtGui.QContextMenuEvent) -> None:
        """
        Show menu with right click.
        """
        self.menu.popup(QtGui.QCursor.pos())

    def save_setting(self) -> None:
        """"""
        settings: QtCore.QSettings = QtCore.QSettings(self.__class__.__name__, "custom")
        settings.setValue("column_state", self.horizontalHeader().saveState())

    # def load_setting(self) -> None:
    #     """"""
    #     settings: QtCore.QSettings = QtCore.QSettings(self.__class__.__name__, "custom")
    #     column_state = settings.value("column_state")
    #
    #     if isinstance(column_state, QtCore.QByteArray):
    #         self.horizontalHeader().restoreState(column_state)
    #         self.horizontalHeader().setSortIndicator(-1, QtCore.Qt.AscendingOrder)


class TickMonitor(BaseMonitor):
    """
    Monitor for tick data.
    """

    event_type: str = EVENT_TICK
    data_key: str = "vt_symbol"
    sorting: bool = True

    headers: dict = {
        "symbol": {"display": "symbol", "cell": BaseCell, "update": False},
        "exchange": {"display": "exchange", "cell": EnumCell, "update": False},
        "name": {"display": "name", "cell": BaseCell, "update": True},
        "last_price": {"display": "last_price", "cell": BaseCell, "update": True},
        "volume": {"display": "volume", "cell": BaseCell, "update": True},
        "open_price": {"display": "open_price", "cell": BaseCell, "update": True},
        "high_price": {"display": "high_price", "cell": BaseCell, "update": True},
        "low_price": {"display": "low_price", "cell": BaseCell, "update": True},
        "bid_price_1": {"display": "bid_price_1", "cell": BidCell, "update": True},
        "bid_volume_1": {"display": "bid_volume_1", "cell": BidCell, "update": True},
        "ask_price_1": {"display": "ask_price_1", "cell": AskCell, "update": True},
        "ask_volume_1": {"display": "ask_volume_1", "cell": AskCell, "update": True},
        "datetime": {"display": "datetime", "cell": TimeCell, "update": True},
        "gateway_name": {"display": "gateway", "cell": BaseCell, "update": False},
    }


class LogMonitor(BaseMonitor):
    """
    Monitor for log data.
    """

    event_type: str = EVENT_LOG
    data_key: str = ""
    sorting: bool = False

    headers: dict = {
        "time": {"display": "time", "cell": TimeCell, "update": False},
        "msg": {"display": "msg", "cell": MsgCell, "update": False},
        "gateway_name": {"display": "gateway", "cell": BaseCell, "update": False},
    }


class TradeMonitor(BaseMonitor):
    """
    Monitor for trade data.
    """

    event_type: str = EVENT_TRADE
    data_key: str = ""
    sorting: bool = True

    headers: dict = {
        "tradeid": {"display": "tradeid ", "cell": BaseCell, "update": False},
        "orderid": {"display": "orderid", "cell": BaseCell, "update": False},
        "symbol": {"display": "symbol", "cell": BaseCell, "update": False},
        "exchange": {"display": "exchange", "cell": EnumCell, "update": False},
        "direction": {"display": "direction", "cell": DirectionCell, "update": False},
        "offset": {"display": "offset", "cell": EnumCell, "update": False},
        "price": {"display": "price", "cell": BaseCell, "update": False},
        "volume": {"display": "volume", "cell": BaseCell, "update": False},
        "datetime": {"display": "datetime", "cell": TimeCell, "update": False},
        "gateway_name": {"display": "gateway", "cell": BaseCell, "update": False},
    }


class OrderMonitor(BaseMonitor):
    """
    Monitor for order data.
    """

    event_type: str = EVENT_ORDER
    data_key: str = "vt_orderid"
    sorting: bool = True

    headers: dict = {
        "orderid": {"display": "orderid", "cell": BaseCell, "update": False},
        "reference": {"display": "reference", "cell": BaseCell, "update": False},
        "symbol": {"display": "symbol", "cell": BaseCell, "update": False},
        "exchange": {"display": "exchange", "cell": EnumCell, "update": False},
        "type": {"display": "type", "cell": EnumCell, "update": False},
        "direction": {"display": "direction", "cell": DirectionCell, "update": False},
        "offset": {"display": "offset", "cell": EnumCell, "update": False},
        "price": {"display": "price", "cell": BaseCell, "update": True},
        "volume": {"display": "volume", "cell": BaseCell, "update": True},
        "traded": {"display": "traded", "cell": BaseCell, "update": True},
        "status": {"display": "status", "cell": EnumCell, "update": True},
        "datetime": {"display": "datetime", "cell": TimeCell, "update": True},
        "gateway_name": {"display": "gateway", "cell": BaseCell, "update": False},
    }

    def init_ui(self) -> None:
        """
        Connect signal.
        """
        super(OrderMonitor, self).init_ui()

        self.setToolTip("double click will cancel the order")
        self.itemDoubleClicked.connect(self.cancel_order)

    def cancel_order(self, cell: BaseCell) -> None:
        """
        Cancel order if cell double clicked.
        """
        order: OrderData = cell.get_data()
        req: CancelRequest = order.create_cancel_request()
        self.main_engine.cancel_order(req, order.gateway_name)


class PositionMonitor(BaseMonitor):
    """
    Monitor for position data.
    """

    event_type: str = EVENT_POSITION
    data_key: str = "vt_positionid"
    sorting: bool = True

    headers: dict = {
        "symbol": {"display": "symbol", "cell": BaseCell, "update": False},
        "exchange": {"display": "exchange", "cell": EnumCell, "update": False},
        "direction": {"display": "direction", "cell": DirectionCell, "update": False},
        "volume": {"display": "volume", "cell": BaseCell, "update": True},
        "yd_volume": {"display": "yesterday_volume", "cell": BaseCell, "update": True},
        "frozen": {"display": "frozen", "cell": BaseCell, "update": True},
        "price": {"display": "price", "cell": BaseCell, "update": True},
        "pnl": {"display": "pnl", "cell": PnlCell, "update": True},
        "gateway_name": {"display": "gateway", "cell": BaseCell, "update": False},
    }


class AccountMonitor(BaseMonitor):
    """
    Monitor for account data.
    """

    event_type: str = EVENT_ACCOUNT
    data_key: str = "vt_accountid"
    sorting: bool = True

    headers: dict = {
        "accountid": {"display": "accountid", "cell": BaseCell, "update": False},
        "balance": {"display": "balance", "cell": BaseCell, "update": True},
        "frozen": {"display": "frozen", "cell": BaseCell, "update": True},
        "available": {"display": "available", "cell": BaseCell, "update": True},
        "gateway_name": {"display": "gateway", "cell": BaseCell, "update": False},
    }


class QuoteMonitor(BaseMonitor):
    """
    Monitor for quote data.
    """

    event_type: str = EVENT_QUOTE
    data_key: str = "vt_quoteid"
    sorting: bool = True

    headers: dict = {
        "quoteid": {"display": "quoteid", "cell": BaseCell, "update": False},
        "reference": {"display": "reference", "cell": BaseCell, "update": False},
        "symbol": {"display": "symbol", "cell": BaseCell, "update": False},
        "exchange": {"display": "exchange", "cell": EnumCell, "update": False},
        "bid_offset": {"display": "bid_offset", "cell": EnumCell, "update": False},
        "bid_volume": {"display": "bid_volume", "cell": BidCell, "update": False},
        "bid_price": {"display": "bid_price", "cell": BidCell, "update": False},
        "ask_price": {"display": "ask_price", "cell": AskCell, "update": False},
        "ask_volume": {"display": "ask_volume", "cell": AskCell, "update": False},
        "ask_offset": {"display": "ask_offset", "cell": EnumCell, "update": False},
        "status": {"display": "status", "cell": EnumCell, "update": True},
        "datetime": {"display": "datetime", "cell": TimeCell, "update": True},
        "gateway_name": {"display": "gateway", "cell": BaseCell, "update": False},
    }

    def init_ui(self):
        """
        Connect signal.
        """
        super().init_ui()

        self.setToolTip("double click will cancel the quote")
        self.itemDoubleClicked.connect(self.cancel_quote)

    def cancel_quote(self, cell: BaseCell) -> None:
        """
        Cancel quote if cell double clicked.
        """
        quote: QuoteData = cell.get_data()
        req: CancelRequest = quote.create_cancel_request()
        self.main_engine.cancel_quote(req, quote.gateway_name)


class ConnectDialog(QtWidgets.QDialog):
    """
    Start connection of a certain gateway.
    """

    def __init__(self, main_engine: MainEngine, gateway_name: str) -> None:
        """"""
        super().__init__()

        self.main_engine: MainEngine = main_engine
        self.gateway_name: str = gateway_name
        self.filename: str = f"connect_{gateway_name.lower()}.json"

        self.widgets: Dict[str, QtWidgets.QWidget] = {}

        self.init_ui()

    def init_ui(self) -> None:
        """"""
        self.setWindowTitle(f"connect {self.gateway_name}")

        # Default setting provides field name, field data type and field default value.
        default_setting: dict = self.main_engine.get_default_setting(
            self.gateway_name)

        # Saved setting provides field data used last time.
        loaded_setting: dict = load_json(self.filename)

        # Initialize line edits and form layout based on setting.
        form: QtWidgets.QFormLayout = QtWidgets.QFormLayout()

        for field_name, field_value in default_setting.items():
            field_type: type = type(field_value)

            if field_type == list:
                widget: QtWidgets.QComboBox = QtWidgets.QComboBox()
                widget.addItems(field_value)

                if field_name in loaded_setting:
                    saved_value = loaded_setting[field_name]
                    ix: int = widget.findText(saved_value)
                    widget.setCurrentIndex(ix)
            else:
                widget: QtWidgets.QLineEdit = QtWidgets.QLineEdit(str(field_value))

                if field_name in loaded_setting:
                    saved_value = loaded_setting[field_name]
                    widget.setText(str(saved_value))

                if "password" in field_name:
                    widget.setEchoMode(QtWidgets.QLineEdit.Password)

                if field_type == int:
                    validator: QtGui.QIntValidator = QtGui.QIntValidator()
                    widget.setValidator(validator)

            form.addRow(f"{field_name} <{field_type.__name__}>", widget)
            self.widgets[field_name] = (widget, field_type)

        button: QtWidgets.QPushButton = QtWidgets.QPushButton("connect")
        button.clicked.connect(self.connect)
        form.addRow(button)

        self.setLayout(form)

    def connect(self) -> None:
        """
        Get setting value from line edits and connect the gateway.
        """
        setting: dict = {}
        for field_name, tp in self.widgets.items():
            widget, field_type = tp
            if field_type == list:
                field_value = str(widget.currentText())
            else:
                try:
                    field_value = field_type(widget.text())
                except ValueError:
                    field_value = field_type()
            setting[field_name] = field_value

        save_json(self.filename, setting)

        self.main_engine.connect(setting, self.gateway_name)
        self.accept()


class MyLabel(QtWidgets.QLabel):
    clicked: QtCore.Signal = QtCore.Signal(str)

    def __init__(self, parent=None):
        super(MyLabel, self).__init__(parent)

    def mousePressEvent(self, event):
        self.clicked.emit(self.text())


class TradingWidget(QtWidgets.QWidget):
    """
    General manual trading widget.
    """

    signal_tick: QtCore.Signal = QtCore.Signal(Event)

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine) -> None:
        """"""
        super().__init__()

        self.main_engine: MainEngine = main_engine
        self.event_engine: EventEngine = event_engine

        self.vt_symbol: str = ""
        self.contract: Optional[ContractData] = None
        self.order_type = OrderType.LIMIT # the default order type.
        self.init_ui()
        self.register_event()

    def init_ui(self) -> None:
        """"""
        self.setFixedWidth(300)

        # Trading function area
        self.vt_symbol_line: QtWidgets.QLineEdit = QtWidgets.QLineEdit()
        self.vt_symbol_line.setFocusPolicy(Qt.FocusPolicy.ClickFocus)  # ClickFocus
        self.vt_symbol_line.returnPressed.connect(self.set_vt_symbol)

        self.symbol_line: QtWidgets.QLineEdit = QtWidgets.QLineEdit()
        self.symbol_line.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.symbol_line.setReadOnly(True)

        order_type_limit = QtWidgets.QRadioButton("limit")
        order_type_limit.setChecked(True)
        order_type_maker = QtWidgets.QRadioButton("maker")
        order_type_taker = QtWidgets.QRadioButton("taker")
        order_type_limit.toggled.connect(self.change_order_type)
        order_type_maker.toggled.connect(self.change_order_type)
        order_type_taker.toggled.connect(self.change_order_type)

        order_type_layout = QtWidgets.QHBoxLayout()
        order_type_layout.addWidget(order_type_limit)
        order_type_layout.addWidget(order_type_maker)
        order_type_layout.addWidget(order_type_taker)

        double_validator: QtGui.QDoubleValidator = QtGui.QDoubleValidator()
        double_validator.setBottom(0)

        # price
        self.price_line: QtWidgets.QLineEdit = QtWidgets.QLineEdit()
        self.price_line.setPlaceholderText("price")
        self.price_line.setFocusPolicy(Qt.FocusPolicy.ClickFocus)  # ClickFocus
        self.price_line.setAlignment(Qt.AlignCenter)
        self.price_line.setClearButtonEnabled(True)
        self.price_line.setValidator(double_validator)
        price_minus_button = QtWidgets.QPushButton("-")
        price_plus_button = QtWidgets.QPushButton("+")
        price_minus_button.clicked.connect(self.price_minus_clicked)
        price_plus_button.clicked.connect(self.price_plus_clicked)

        # price layout
        price_layout: QtWidgets.QGridLayout = QtWidgets.QGridLayout()
        price_layout.addWidget(price_minus_button, 0, 0, 1, 1)
        price_layout.addWidget(self.price_line, 0, 1, 1, 2)
        price_layout.addWidget(price_plus_button, 0, 3, 1, 1)

        # volume
        self.volume_line: QtWidgets.QLineEdit = QtWidgets.QLineEdit()
        self.volume_line.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.volume_line.setPlaceholderText("volume")
        self.volume_line.setAlignment(Qt.AlignCenter)
        self.volume_line.setClearButtonEnabled(True)
        self.volume_line.setValidator(double_validator)
        volume_minus_button = QtWidgets.QPushButton("-")
        volume_plus_button = QtWidgets.QPushButton("+")
        volume_minus_button.clicked.connect(self.volume_minus_clicked)
        volume_plus_button.clicked.connect(self.volume_plus_clicked)

        self.reduce_only_checkbox: QtWidgets.QCheckBox = QtWidgets.QCheckBox("reduce only")
        self.reduce_only_checkbox.setEnabled(False)
        # volume layout
        volume_layout: QtWidgets.QGridLayout = QtWidgets.QGridLayout()
        volume_layout.addWidget(volume_minus_button, 0, 0, 1, 1)
        volume_layout.addWidget(self.volume_line, 0, 1, 1, 2)
        volume_layout.addWidget(volume_plus_button, 0, 3, 1, 1)
        volume_layout.addWidget(self.reduce_only_checkbox, 1, 0, 1, 2)

        # buy sell button
        buy_button: QtWidgets.QPushButton = QtWidgets.QPushButton("buy")
        sell_button: QtWidgets.QPushButton = QtWidgets.QPushButton("sell")

        red_color: str = "rgb(228,95,97)"
        green_color: str = "rgb(92,199,135)"
        buy_button.setStyleSheet(f"background-color:{green_color}")
        sell_button.setStyleSheet(f"background-color:{red_color}")

        buy_button.clicked.connect(self.send_order)
        sell_button.clicked.connect(self.send_order)

        buy_sell_button_layout = QtWidgets.QHBoxLayout()
        buy_sell_button_layout.addWidget(buy_button)
        buy_sell_button_layout.addSpacing(10)
        buy_sell_button_layout.addWidget(sell_button)

        cancel_all_button_button: QtWidgets.QPushButton = QtWidgets.QPushButton("cancel all orders")
        cancel_all_button_button.clicked.connect(self.cancel_all_orders_clicked)
        cancel_order_layout = QtWidgets.QHBoxLayout()
        cancel_order_layout.addWidget(cancel_all_button_button)

        configs_layout = QtWidgets.QHBoxLayout()
        all_config_button: QtWidgets.QPushButton = QtWidgets.QPushButton("all configs")
        add_config_button: QtWidgets.QPushButton = QtWidgets.QPushButton("add config")
        all_config_button.clicked.connect(self.all_configs_button_clicked)
        add_config_button.clicked.connect(self.add_config_button_clicked)
        configs_layout.addWidget(all_config_button)
        configs_layout.addSpacing(10)
        configs_layout.addWidget(add_config_button)

        grid: QtWidgets.QGridLayout = QtWidgets.QGridLayout()
        grid.addWidget(QtWidgets.QLabel("vt_symbol"), 0, 0, 1, 1)
        grid.addWidget(QtWidgets.QLabel("symbol"), 1, 0, 1, 1)
        grid.addWidget(QtWidgets.QLabel("order type"), 2, 0, 1, 1)
        grid.addLayout(price_layout, 3, 0, 1, 3)
        grid.addLayout(volume_layout, 4, 0, 1, 3)

        grid.addWidget(self.vt_symbol_line, 0, 1, 1, 1)
        grid.addWidget(self.symbol_line, 1, 1, 1, 1)
        grid.addLayout(order_type_layout, 2, 1, 1, 1)
        grid.addWidget(self.price_line, 3, 1, 1, 1)
        grid.addWidget(self.volume_line, 4, 1, 1, 1)
        grid.addLayout(buy_sell_button_layout, 5, 0, 1, 3)

        grid.addLayout(QtWidgets.QHBoxLayout(), 6, 0, 1, 3)
        grid.addLayout(cancel_order_layout, 7, 0, 1, 3)
        grid.addLayout(configs_layout, 8, 0,1, 3)

        self.bp1_label: MyLabel = self.create_label(green_color)
        self.bp2_label: MyLabel = self.create_label(green_color)
        self.bp3_label: MyLabel = self.create_label(green_color)
        self.bp4_label: MyLabel = self.create_label(green_color)
        self.bp5_label: MyLabel = self.create_label(green_color)

        self.bv1_label: MyLabel = self.create_label(green_color, alignment=QtCore.Qt.AlignRight)
        self.bv2_label: MyLabel = self.create_label(green_color, alignment=QtCore.Qt.AlignRight)
        self.bv3_label: MyLabel = self.create_label(green_color, alignment=QtCore.Qt.AlignRight)
        self.bv4_label: MyLabel = self.create_label(green_color, alignment=QtCore.Qt.AlignRight)
        self.bv5_label: MyLabel = self.create_label(green_color, alignment=QtCore.Qt.AlignRight)

        self.ap1_label: MyLabel = self.create_label(red_color)
        self.ap2_label: MyLabel = self.create_label(red_color)
        self.ap3_label: MyLabel = self.create_label(red_color)
        self.ap4_label: MyLabel = self.create_label(red_color)
        self.ap5_label: MyLabel = self.create_label(red_color)

        self.av1_label: MyLabel = self.create_label(red_color, alignment=QtCore.Qt.AlignRight)
        self.av2_label: MyLabel = self.create_label(red_color, alignment=QtCore.Qt.AlignRight)
        self.av3_label: MyLabel = self.create_label(red_color, alignment=QtCore.Qt.AlignRight)
        self.av4_label: MyLabel = self.create_label(red_color, alignment=QtCore.Qt.AlignRight)
        self.av5_label: MyLabel = self.create_label(red_color, alignment=QtCore.Qt.AlignRight)

        self.bp1_label.clicked.connect(self.update_price)
        self.bp2_label.clicked.connect(self.update_price)
        self.bp3_label.clicked.connect(self.update_price)
        self.bp4_label.clicked.connect(self.update_price)
        self.bp5_label.clicked.connect(self.update_price)

        self.ap1_label.clicked.connect(self.update_price)
        self.ap2_label.clicked.connect(self.update_price)
        self.ap3_label.clicked.connect(self.update_price)
        self.ap4_label.clicked.connect(self.update_price)
        self.ap5_label.clicked.connect(self.update_price)

        self.lp_label: MyLabel = self.create_label()
        self.return_label: MyLabel = self.create_label(alignment=QtCore.Qt.AlignRight)

        form: QtWidgets.QFormLayout = QtWidgets.QFormLayout()
        form.addRow(self.ap5_label, self.av5_label)
        form.addRow(self.ap4_label, self.av4_label)
        form.addRow(self.ap3_label, self.av3_label)
        form.addRow(self.ap2_label, self.av2_label)
        form.addRow(self.ap1_label, self.av1_label)
        form.addRow(self.lp_label, self.return_label)
        form.addRow(self.bp1_label, self.bv1_label)
        form.addRow(self.bp2_label, self.bv2_label)
        form.addRow(self.bp3_label, self.bv3_label)
        form.addRow(self.bp4_label, self.bv4_label)
        form.addRow(self.bp5_label, self.bv5_label)

        # Overall layout
        vbox: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout()
        vbox.addLayout(grid)
        vbox.addLayout(form)
        self.setLayout(vbox)

    def create_label(
            self,
            color: str = "",
            alignment: Qt.AlignmentFlag = QtCore.Qt.AlignLeft
    ) -> MyLabel:
        """
        Create label with certain font color.
        """
        label: MyLabel = MyLabel()
        if color:
            label.setStyleSheet(f"color:{color}")
        label.setAlignment(alignment)
        return label

    def register_event(self) -> None:
        """"""
        self.signal_tick.connect(self.process_tick_event)
        self.event_engine.register(EVENT_TICK, self.signal_tick.emit)

    def process_tick_event(self, event: Event) -> None:
        """"""
        tick: TickData = event.data
        if tick.vt_symbol != self.vt_symbol:
            return

        self.lp_label.setText(str(round_to(Decimal(str(tick.last_price)), self.contract.pricetick)))
        self.bp1_label.setText(str(round_to(Decimal(str(tick.bid_price_1)), self.contract.pricetick)))
        self.bv1_label.setText(str(tick.bid_volume_1))

        self.ap1_label.setText(str(round_to(Decimal(str(tick.ask_price_1)), self.contract.pricetick)))
        self.av1_label.setText(str(tick.ask_volume_1))

        if tick.pre_close:
            r: float = (tick.last_price / tick.pre_close - 1) * 100
            self.return_label.setText(f"{r:.2f}%")

        if tick.bid_price_2:
            self.bp2_label.setText(str(round_to(Decimal(str(tick.bid_price_2)), self.contract.pricetick)))
            self.bv2_label.setText(str(tick.bid_volume_2))
            self.ap2_label.setText(str(round_to(Decimal(str(tick.ask_price_2)), self.contract.pricetick)))
            self.av2_label.setText(str(tick.ask_volume_2))

            self.bp3_label.setText(str(round_to(Decimal(str(tick.bid_price_3)), self.contract.pricetick)))
            self.bv3_label.setText(str(tick.bid_volume_3))
            self.ap3_label.setText(str(round_to(Decimal(str(tick.ask_price_3)), self.contract.pricetick)))
            self.av3_label.setText(str(tick.ask_volume_3))

            self.bp4_label.setText(str(round_to(Decimal(str(tick.bid_price_4)), self.contract.pricetick)))
            self.bv4_label.setText(str(tick.bid_volume_4))
            self.ap4_label.setText(str(round_to(Decimal(str(tick.ask_price_4)), self.contract.pricetick)))
            self.av4_label.setText(str(tick.ask_volume_4))

            self.bp5_label.setText(str(round_to(Decimal(str(tick.bid_price_5)), self.contract.pricetick)))
            self.bv5_label.setText(str(tick.bid_volume_5))
            self.ap5_label.setText(str(round_to(Decimal(str(tick.ask_price_5)), self.contract.pricetick)))
            self.av5_label.setText(str(tick.ask_volume_5))

    def set_vt_symbol(self) -> None:
        """
        Set the tick depth data to monitor by vt_symbol.
        """
        vt_symbol: str = str(self.vt_symbol_line.text())
        self.vt_symbol_line.clearFocus()

        if not vt_symbol:
            return None

        if vt_symbol == self.vt_symbol:
            return None

        contract: ContractData = self.main_engine.get_contract(vt_symbol)
        if not contract:
            return None

        symbol, exchange_value = extract_vt_symbol(vt_symbol)
        self.vt_symbol = vt_symbol
        self.reduce_only_checkbox.setChecked(False)
        if contract.product == Product.SPOT:
            self.reduce_only_checkbox.setEnabled(False)
        else:
            self.reduce_only_checkbox.setEnabled(True)

        # Update name line widget and clear all labels
        self.contract = contract
        self.symbol_line.setText(contract.name)
        gateway_name: str = contract.gateway_name

        self.clear_label_text()
        self.volume_line.setText("")
        self.price_line.setText("")

        # Subscribe tick data
        req: SubscribeRequest = SubscribeRequest(
            symbol=symbol, exchange=Exchange(exchange_value)
        )

        self.main_engine.subscribe(req, gateway_name)

    def clear_label_text(self) -> None:
        """
        Clear text on all labels.
        """
        self.lp_label.setText("")
        self.return_label.setText("")

        self.bv1_label.setText("")
        self.bv2_label.setText("")
        self.bv3_label.setText("")
        self.bv4_label.setText("")
        self.bv5_label.setText("")

        self.av1_label.setText("")
        self.av2_label.setText("")
        self.av3_label.setText("")
        self.av4_label.setText("")
        self.av5_label.setText("")

        self.bp1_label.setText("")
        self.bp2_label.setText("")
        self.bp3_label.setText("")
        self.bp4_label.setText("")
        self.bp5_label.setText("")

        self.ap1_label.setText("")
        self.ap2_label.setText("")
        self.ap3_label.setText("")
        self.ap4_label.setText("")
        self.ap5_label.setText("")

    def send_order(self) -> None:
        """
        Send new order manually.
        """
        button: QtWidgets.QPushButton = self.sender()
        if button.text() == 'buy':
            direction = Direction.LONG
        else:
            direction = Direction.SHORT

        vt_symbol: str = str(self.vt_symbol_line.text())
        if not vt_symbol:
            QtWidgets.QMessageBox.critical(self, "send order failed", "pls input vt_symbol")
            return None

        volume_text: str = str(self.volume_line.text())
        if not volume_text:
            QtWidgets.QMessageBox.critical(self, "send order failed", "pls input volume")
            return None

        volume: Decimal = Decimal(volume_text)
        price_text: str = str(self.price_line.text())

        if self.order_type == OrderType.TAKER:
            price = Decimal("0")
        elif not price_text:
            QtWidgets.QMessageBox.critical(self, "send order failed", "pls input price")
            return None
        else:
            price = Decimal(price_text)

        symbol, exchange = extract_vt_symbol(vt_symbol)
        check =self.reduce_only_checkbox.isChecked()
        if check:
            offset = Offset.CLOSE
        else:
            offset = Offset.OPEN

        req: OrderRequest = OrderRequest(
            symbol=symbol,
            exchange=exchange,
            direction=direction,
            type=self.order_type,
            volume=volume,
            price=price,
            offset=offset,
            reference="trader"
        )

        gateway_name: str = self.contract.gateway_name
        self.main_engine.send_order(req, gateway_name)

    def change_order_type(self):
        radio_button: QtWidgets.QRadioButton = self.sender()
        text = radio_button.text()
        if text == 'limit':
            self.order_type = OrderType.LIMIT
            self.price_line.setEnabled(True)
        elif text == 'maker':
            self.order_type = OrderType.MAKER
            self.price_line.setEnabled(True)
        elif text == 'taker':
            self.order_type = OrderType.TAKER
            self.price_line.setEnabled(False)

    def price_minus_clicked(self) -> None:
        try:
            value = self.price_line.text()
            if not value:
                value = "0"

            price = Decimal(value)
            if self.contract:
                price = price - self.contract.pricetick
            if price >= 0:
                price = round_to(price, self.contract.pricetick)
                self.price_line.setText(str(price))
            else:
                self.price_line.setText("0")

        except Exception as error:
            self.price_line.setText("0")

    def price_plus_clicked(self) -> None:
        try:
            value = self.price_line.text()
            if not value:
                value = "0"

            price = Decimal(value)
            if self.contract:
                price = price + self.contract.pricetick
            if price >= 0:
                price = round_to(price, self.contract.pricetick)
                self.price_line.setText(str(price))
            else:
                self.price_line.setText("0")

        except Exception as error:
            self.price_line.setText("0")

    def volume_minus_clicked(self) -> None:
        try:
            value = self.volume_line.text()
            if not value:
                value = "0"

            vol = Decimal(value)
            if self.contract:
                vol = vol - self.contract.min_volume
            if vol >= 0:
                vol = round_to(vol, self.contract.min_volume)
                self.volume_line.setText(str(vol))
            else:
                self.volume_line.setText("0")

        except Exception as error:
            self.volume_line.setText("0")

    def volume_plus_clicked(self) -> None:
        try:
            value = self.volume_line.text()
            if not value:
                value = "0"

            vol = Decimal(value)
            if self.contract:
                vol = vol + self.contract.min_volume
                vol = round_to(vol, self.contract.min_volume)
                self.volume_line.setText(str(vol))
            else:
                self.volume_line.setText("0")
        except Exception as error:
            self.volume_line.setText("0")

    def cancel_all_orders_clicked(self) -> None:
        """
        Cancel all active orders.
        """
        order_list: List[OrderData] = self.main_engine.get_all_active_orders()
        for order in order_list:
            req: CancelRequest = order.create_cancel_request()
            self.main_engine.cancel_order(req, order.gateway_name)

    def all_configs_button_clicked(self) -> None:
        dialog = QuickTraderDialog()
        dialog.exec_()

    def add_config_button_clicked(self) -> None:
        dialog = QuickTraderConfigDialog()
        dialog.exec()

    def update_with_cell(self, cell: BaseCell) -> None:
        """"""
        data = cell.get_data()
        if isinstance(data, TickData) or isinstance(data, PositionData):
            self.symbol_line.setText(data.symbol)
            self.vt_symbol_line.setText(data.vt_symbol)
            self.set_vt_symbol()

            if isinstance(data, PositionData):
                d: PositionData = data
                self.volume_line.setText(str(abs(data.volume)))

    def update_price(self, price_str) -> None:
        if price_str:
            self.price_line.setText(price_str)


class ActiveOrderMonitor(OrderMonitor):
    """
    Monitor which shows active order only.
    """

    def process_event(self, event) -> None:
        """
        Hides the row if order is not active.
        """
        super(ActiveOrderMonitor, self).process_event(event)

        order: OrderData = event.data
        row_cells: dict = self.cells[order.vt_orderid]
        row: int = self.row(row_cells["volume"])

        if order.is_active():
            self.showRow(row)
        else:
            self.hideRow(row)


class ContractManager(QtWidgets.QWidget):
    """
    Query contract data available to trade in system.
    """

    headers: Dict[str, str] = {
        "vt_symbol": "vt_symbol",
        "symbol": "symbol",
        "exchange": "exchange",
        "name": "name",
        "product": "product",
        "size": "size",
        "pricetick": "price_tick",
        "min_volume": "min_volume",
        "gateway_name": "gateway",
    }

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine) -> None:
        super().__init__()

        self.main_engine: MainEngine = main_engine
        self.event_engine: EventEngine = event_engine

        self.init_ui()

    def init_ui(self) -> None:
        """"""
        self.setWindowTitle("query contract")
        self.resize(1000, 600)

        self.filter_line: QtWidgets.QLineEdit = QtWidgets.QLineEdit()
        self.filter_line.setPlaceholderText("pls input symbol or exchange，leave empty will query all contracts")

        self.button_show: QtWidgets.QPushButton = QtWidgets.QPushButton("query")
        self.button_show.clicked.connect(self.show_contracts)

        labels: list = []
        for name, display in self.headers.items():
            label: str = f"{display}"  # f"{display}\n{name}"
            labels.append(label)

        self.contract_table: QtWidgets.QTableWidget = QtWidgets.QTableWidget()
        self.contract_table.setColumnCount(len(self.headers))
        self.contract_table.setHorizontalHeaderLabels(labels)
        self.contract_table.verticalHeader().setVisible(False)
        self.contract_table.setEditTriggers(self.contract_table.NoEditTriggers)
        self.contract_table.setAlternatingRowColors(True)

        hbox: QtWidgets.QHBoxLayout = QtWidgets.QHBoxLayout()
        hbox.addWidget(self.filter_line)
        hbox.addWidget(self.button_show)

        vbox: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout()
        vbox.addLayout(hbox)
        vbox.addWidget(self.contract_table)

        self.setLayout(vbox)

    def show_contracts(self) -> None:
        """
        Show contracts by symbol
        """
        flt: str = str(self.filter_line.text())

        all_contracts: List[ContractData] = self.main_engine.get_all_contracts()
        if flt:
            contracts: List[ContractData] = [
                contract for contract in all_contracts if flt in contract.vt_symbol
            ]
        else:
            contracts: List[ContractData] = all_contracts

        self.contract_table.clearContents()
        self.contract_table.setRowCount(len(contracts))

        for row, contract in enumerate(contracts):
            for column, name in enumerate(self.headers.keys()):
                value = getattr(contract, name)
                if isinstance(value, Enum):
                    cell: EnumCell = EnumCell(value, contract)
                else:
                    cell: BaseCell = BaseCell(value, contract)
                self.contract_table.setItem(row, column, cell)

        self.contract_table.resizeColumnsToContents()


class AboutDialog(QtWidgets.QDialog):
    """
    Information about the trading platform.
    """

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine) -> None:
        """"""
        super().__init__()

        self.main_engine: MainEngine = main_engine
        self.event_engine: EventEngine = event_engine

        self.init_ui()

    def init_ui(self) -> None:
        """"""
        self.setWindowTitle("About Howtrader")

        from ... import __version__ as vnpy_version

        text: str = f"""
            Fork from vnpy
            License：MIT
            Github：www.github.com/51bitquant/howtrader

            Python - {platform.python_version()}
            PySide6 - {importlib_metadata.version("pyside6")}
            NumPy - {importlib_metadata.version("numpy")}
            pandas - {importlib_metadata.version("pandas")}
            """

        label: QtWidgets.QLabel = QtWidgets.QLabel()
        label.setText(text)
        label.setMinimumWidth(500)

        vbox: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout()
        vbox.addWidget(label)
        self.setLayout(vbox)


class QuickTraderDialog(QtWidgets.QDialog):
    """
    display configs
    """
    def __init__(self):
        """"""
        super(QuickTraderDialog, self).__init__()

        self.init_ui()

    def init_ui(self) -> None:
        """"""
        self.setWindowTitle("QuickTrader")
        self.setMinimumWidth(880)

        table = QtWidgets.QTableWidget()

        table.horizontalHeader().setFixedHeight(50)
        table.setEditTriggers(QtWidgets.QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        table.verticalHeader().setVisible(False)

        del_btn = QtWidgets.QPushButton('delete')
        del_btn.clicked.connect(self.del_action)
        cancel_btn = QtWidgets.QPushButton('cancel')
        cancel_btn.clicked.connect(self.close)

        hbox = QtWidgets.QHBoxLayout()

        hbox.addWidget(del_btn)
        hbox.addWidget(cancel_btn)

        vbox = QtWidgets.QVBoxLayout()
        vbox.addWidget(table)
        vbox.addLayout(hbox)

        headers = ['hotkey', 'buy/sell', 'volume_option', 'volume', 'base_price', '+/-', 'over_price_value', 'over_price_option']
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)

        table.setRowCount(len(QUICK_TRADER_SETTINGS.keys()))

        index = 0
        for key in QUICK_TRADER_SETTINGS.keys():

            data = QUICK_TRADER_SETTINGS.get(key, {})
            if not isinstance(data, dict):
                continue

            buy_sell = data.get('direction')
            volume_option = data.get('volume_option')
            volume = data.get('volume')
            price = data.get('price')
            add_minus = data.get('add_minus')
            over_price_value =  data.get('over_price_value')
            over_price_option = data.get('over_price_option')

            table.setItem(index, 0, QtWidgets.QTableWidgetItem(key))
            table.setItem(index, 1, QtWidgets.QTableWidgetItem(buy_sell))
            table.setItem(index, 2, QtWidgets.QTableWidgetItem(volume_option))
            table.setItem(index, 3, QtWidgets.QTableWidgetItem(volume))
            table.setItem(index, 4, QtWidgets.QTableWidgetItem(price))
            table.setItem(index, 5, QtWidgets.QTableWidgetItem(add_minus))
            table.setItem(index, 6, QtWidgets.QTableWidgetItem(over_price_value))
            table.setItem(index, 7, QtWidgets.QTableWidgetItem(over_price_option))
            index += 1

        if len(QUICK_TRADER_SETTINGS.keys()) > 0:
            # default selected is 0 row
            table.selectRow(0)

        self.table = table
        self.setLayout(vbox)

    def del_action(self) -> None:
        row = self.table.currentIndex().row()
        if row >= 0:
            key = self.table.item(row, 0).text()

            if QUICK_TRADER_SETTINGS.get(key, None):
                del QUICK_TRADER_SETTINGS[key]
                save_json('quick_trader_setting.json', QUICK_TRADER_SETTINGS)
                self.table.removeRow(row)

    def cancel_action(self) -> None:
        """
        Get setting value from line edits and update global setting file.
        """
        self.accept()


class QuickTraderConfigDialog(QtWidgets.QDialog):
    """
    Quick Trader Dialog
    """

    def __init__(self):
        """"""
        super(QuickTraderConfigDialog, self).__init__()
        self.init_ui()

    def init_ui(self) -> None:
        """"""
        self.setWindowTitle("QuickTrader")
        self.setMinimumWidth(800)

        grid_layout = QtWidgets.QGridLayout()

        # create the elements.
        hotkey_label: QtWidgets.QLabel = QtWidgets.QLabel("Hotkey")

        buy_sell_label: QtWidgets.QLabel = QtWidgets.QLabel("Buy/Sell")
        self.buy_sell_combo: QtWidgets.QComboBox  = QtWidgets.QComboBox()
        self.buy_sell_combo.addItems(['buy', 'sell'])
        price_label = QtWidgets.QLabel('Price')
        volume_label = QtWidgets.QLabel('Volume')

        confirm_btn = QtWidgets.QPushButton("Confirm")
        cancel_btn = QtWidgets.QPushButton("Cancel")
        confirm_btn.clicked.connect(self.confirm_action)
        cancel_btn.clicked.connect(self.cancel_action)

        self.hotkey_combo:QtWidgets.QComboBox  = QtWidgets.QComboBox()

        keys = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']
        for item in QUICK_TRADER_SETTINGS.keys():
            if keys.__contains__(item):
                keys.remove(item)

        self.hotkey_combo.addItems(keys)

        self.base_price_combo = QtWidgets.QComboBox()
        self.base_price_combo.addItems(['bid_price_1', 'bid_price_2', 'bid_price_3', 'bid_price_4', 'bid_price_5',
                              'ask_price_1', 'ask_price_2', 'ask_price_3', 'ask_price_4', 'ask_price_5'])

        double_validator: QtGui.QDoubleValidator = QtGui.QDoubleValidator()
        double_validator.setBottom(0)

        self.price_add_minus_combo: QtWidgets.QComboBox = QtWidgets.QComboBox()
        self.price_add_minus_combo.addItems(["+", "-"])
        self.over_price_line_edit = QtWidgets.QLineEdit()
        self.over_price_line_edit.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.over_price_line_edit.setValidator(double_validator)
        self.over_price_combo = QtWidgets.QComboBox()
        self.over_price_combo.addItems(['min_price', '% of price'])

        self.volume_combox = QtWidgets.QComboBox()
        self.volume_combox.addItems(['fixed_volume', '% of position'])
        self.volume_line_edit = QtWidgets.QLineEdit()
        self.volume_line_edit.setValidator(double_validator)
        self.volume_line_edit.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        grid_layout.addWidget(hotkey_label, 0, 0)
        grid_layout.addWidget(self.hotkey_combo, 0, 1)

        grid_layout.addWidget(buy_sell_label, 1, 0)
        grid_layout.addWidget(self.buy_sell_combo, 1, 1)

        grid_layout.addWidget(price_label, 2, 0)
        grid_layout.addWidget(self.base_price_combo, 2, 1)
        grid_layout.addWidget(self.price_add_minus_combo, 2, 2)
        grid_layout.addWidget(self.over_price_line_edit,2, 3)
        grid_layout.addWidget(self.over_price_combo, 2, 4)

        grid_layout.addWidget(volume_label, 3, 0)
        grid_layout.addWidget(self.volume_combox, 3, 1)
        grid_layout.addWidget(self.volume_line_edit, 3, 2)

        ## confirm and cancel
        horizontal_layout = QtWidgets.QHBoxLayout()
        horizontal_layout.addStretch(1)
        horizontal_layout.addWidget(confirm_btn)
        horizontal_layout.addSpacing(20)
        horizontal_layout.addWidget(cancel_btn)
        horizontal_layout.addStretch(1)

        grid_layout.addLayout(horizontal_layout, 4, 2)
        self.setLayout(grid_layout)

    def confirm_action(self):

        hotkey_value = self.hotkey_combo.currentText()
        direction = self.buy_sell_combo.currentText()
        price = self.base_price_combo.currentText()
        add_minus = self.price_add_minus_combo.currentText()
        over_price_value = self.over_price_line_edit.text()
        over_price_option = self.over_price_combo.currentText()
        if not over_price_value:
            over_price_value = "0"

        volume_option = self.volume_combox.currentText()
        volume = self.volume_line_edit.text()
        if not volume:
            volume = "0"

        QUICK_TRADER_SETTINGS[hotkey_value] = {
            "direction": direction,
            "price": price,
            "add_minus": add_minus,
            "over_price_value": over_price_value,
            "over_price_option": over_price_option,
            "volume_option": volume_option,
            "volume": volume
        }

        save_json('quick_trader_setting.json', QUICK_TRADER_SETTINGS)
        self.accept()

    def cancel_action(self):
        self.accept()

class GlobalDialog(QtWidgets.QDialog):
    """
    Start connection of a certain gateway.
    """

    def __init__(self) -> None:
        """"""
        super().__init__()

        self.widgets: Dict[str, Any] = {}

        self.init_ui()

    def init_ui(self) -> None:
        """"""
        self.setWindowTitle("global configs")
        self.setMinimumWidth(800)

        settings: dict = copy(SETTINGS)
        settings.update(load_json(SETTING_FILENAME))

        # Initialize line edits and form layout based on setting.
        form: QtWidgets.QFormLayout = QtWidgets.QFormLayout()

        for field_name, field_value in settings.items():
            field_type: type = type(field_value)
            widget: QtWidgets.QLineEdit = QtWidgets.QLineEdit(str(field_value))

            form.addRow(f"{field_name} <{field_type.__name__}>", widget)
            self.widgets[field_name] = (widget, field_type)

        button: QtWidgets.QPushButton = QtWidgets.QPushButton("confirm")
        button.clicked.connect(self.update_setting)
        form.addRow(button)

        scroll_widget: QtWidgets.QWidget = QtWidgets.QWidget()
        scroll_widget.setLayout(form)

        scroll_area: QtWidgets.QScrollArea = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(scroll_widget)

        vbox: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout()
        vbox.addWidget(scroll_area)
        self.setLayout(vbox)

    def update_setting(self) -> None:
        """
        Get setting value from line edits and update global setting file.
        """
        settings: dict = {}
        for field_name, tp in self.widgets.items():
            widget, field_type = tp
            value_text: str = widget.text()

            if field_type == bool:
                if value_text == "True":
                    field_value: bool = True
                else:
                    field_value: bool = False
            else:
                field_value = field_type(value_text)

            settings[field_name] = field_value

        QtWidgets.QMessageBox.information(
            self,
            "Note",
            "Editting the global configs requires to restart the software！",
            QtWidgets.QMessageBox.Ok
        )

        save_json(SETTING_FILENAME, settings)
        self.accept()
