import sys

from howtrader.event import EventEngine, Event
from howtrader.trader.engine import MainEngine
from howtrader.trader.ui import QtWidgets, QtCore
from howtrader.trader.utility import load_json, save_json
from ..engine import APP_NAME, TVEngine, EVENT_TV_LOG, EVENT_TV_STRATEGY
from howtrader.trader.ui import QtCore, QtGui, QtWidgets
from howtrader.trader.ui.widget import (
    MsgCell,
    TimeCell,
    BaseMonitor
)


class TVManager(QtWidgets.QWidget):
    """"""
    setting_filename: str = "tv_setting.json"
    signal_log: QtCore.Signal = QtCore.Signal(Event)
    signal_strategy: QtCore.Signal = QtCore.Signal(Event)

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine) -> None:
        super(TVManager, self).__init__()

        self.main_engine: MainEngine = main_engine
        self.event_engine: EventEngine = event_engine
        self.tv_engine: TVEngine = main_engine.get_engine(APP_NAME)
        self.managers: StrategyManager = {}

        self.init_ui()
        self.register_event()
        self.tv_engine.init_engine()
        self.update_class_combo()

    def init_ui(self) -> None:
        """"""
        self.setWindowTitle("TradingView")

        # Create widgets
        self.class_combo: QtWidgets.QComboBox = QtWidgets.QComboBox()

        add_button: QtWidgets.QPushButton = QtWidgets.QPushButton("Add Strategy")
        add_button.clicked.connect(self.add_strategy)

        init_button: QtWidgets.QPushButton = QtWidgets.QPushButton("Init All Strategies")
        init_button.clicked.connect(self.tv_engine.init_all_strategies)

        start_button: QtWidgets.QPushButton = QtWidgets.QPushButton("Start All Strategies")
        start_button.clicked.connect(self.tv_engine.start_all_strategies)

        stop_button: QtWidgets.QPushButton = QtWidgets.QPushButton("Stop All Strategies")
        stop_button.clicked.connect(self.tv_engine.stop_all_strategies)

        clear_button: QtWidgets.QPushButton = QtWidgets.QPushButton("Clear Logs")
        clear_button.clicked.connect(self.clear_log)

        self.scroll_layout: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout()
        self.scroll_layout.addStretch()
        scroll_widget: QtWidgets.QWidget = QtWidgets.QWidget()
        scroll_widget.setLayout(self.scroll_layout)

        scroll_area: QtWidgets.QScrollArea = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(scroll_widget)

        self.log_monitor: LogMonitor = LogMonitor(self.main_engine, self.event_engine)

        # Set layout
        hbox1: QtWidgets.QHBoxLayout = QtWidgets.QHBoxLayout()
        hbox1.addWidget(self.class_combo)
        hbox1.addWidget(add_button)
        hbox1.addStretch()
        hbox1.addWidget(init_button)
        hbox1.addWidget(start_button)
        hbox1.addWidget(stop_button)
        hbox1.addWidget(clear_button)

        grid: QtWidgets.QGridLayout = QtWidgets.QGridLayout()


        grid.addWidget(scroll_area, 0,0)
        grid.addWidget(self.log_monitor, 0, 1)

        vbox: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout()
        vbox.addLayout(hbox1)
        vbox.addLayout(grid)

        self.setLayout(vbox)

    def update_class_combo(self) -> None:
        """"""
        names = self.tv_engine.get_all_strategy_class_names()
        names.sort()
        self.class_combo.addItems(names)

    def register_event(self) -> None:
        """"""
        self.signal_strategy.connect(self.process_strategy_event)

        self.event_engine.register(
            EVENT_TV_STRATEGY, self.signal_strategy.emit
        )

    def process_strategy_event(self, event) -> None:
        """
        Update strategy status onto its monitor.
        """
        data = event.data
        strategy_name: str = data["strategy_name"]

        if strategy_name in self.managers:
            manager: StrategyManager = self.managers[strategy_name]
            manager.update_data(data)
        else:
            manager: StrategyManager = StrategyManager(self, self.tv_engine, data)
            self.scroll_layout.insertWidget(0, manager)
            self.managers[strategy_name] = manager

    def remove_strategy(self, strategy_name) -> None:
        """"""
        manager: StrategyManager = self.managers.pop(strategy_name)
        manager.deleteLater()

    def add_strategy(self) -> None:
        """"""
        class_name: str = str(self.class_combo.currentText())
        if not class_name:
            return

        parameters: dict = self.tv_engine.get_strategy_class_parameters(class_name)
        editor: SettingEditor = SettingEditor(parameters, class_name=class_name)
        n: int = editor.exec_()

        if n == editor.Accepted:
            setting: dict = editor.get_setting()
            vt_symbol: str = setting.pop("vt_symbol")
            strategy_name: str = setting.pop("strategy_name")
            tv_id: str = setting.pop("tv_id")

            self.tv_engine.add_strategy(
                class_name, strategy_name, tv_id, vt_symbol, setting
            )

    def clear_log(self) -> None:
        """"""
        self.log_monitor.setRowCount(0)

    def show(self) -> None:
        """"""
        self.showMaximized()



class StrategyManager(QtWidgets.QFrame):
    """
    Manager for a strategy
    """

    def __init__(
        self, tv_manager: TVManager, tv_engine: TVEngine, data: dict
    ) -> None:
        """"""
        super(StrategyManager, self).__init__()

        self.tv_manager: TVManager = tv_manager
        self.tv_engine: TVEngine = tv_engine
        self.strategy_name: str = data["strategy_name"]
        self._data: dict = data

        self.init_ui()

    def init_ui(self) -> None:
        """"""
        self.setFixedHeight(300)
        self.setFrameShape(self.Box)
        self.setLineWidth(1)

        self.init_button: QtWidgets.QPushButton = QtWidgets.QPushButton("Init Strategy")
        self.init_button.clicked.connect(self.init_strategy)

        self.start_button: QtWidgets.QPushButton = QtWidgets.QPushButton("Start Strategy")
        self.start_button.clicked.connect(self.start_strategy)
        self.start_button.setEnabled(False)

        self.stop_button: QtWidgets.QPushButton = QtWidgets.QPushButton("Stop Strategy")
        self.stop_button.clicked.connect(self.stop_strategy)
        self.stop_button.setEnabled(False)

        self.edit_button: QtWidgets.QPushButton = QtWidgets.QPushButton("Edit Strategy")
        self.edit_button.clicked.connect(self.edit_strategy)

        self.remove_button: QtWidgets.QPushButton = QtWidgets.QPushButton("Remove Strategy")
        self.remove_button.clicked.connect(self.remove_strategy)

        strategy_name: str = self._data["strategy_name"]
        vt_symbol: str = self._data["vt_symbol"]
        class_name: str = self._data["class_name"]
        tv_id: str = self._data['tv_id']
        author: str = self._data["author"]

        label_text: str = (
            f"{strategy_name} - {vt_symbol} - {tv_id} ({class_name} by {author})"
        )
        label: QtWidgets.QLabel = QtWidgets.QLabel(label_text)
        label.setAlignment(QtCore.Qt.AlignCenter)

        self.parameters_monitor: DataMonitor = DataMonitor(self._data["parameters"])
        self.variables_monitor: DataMonitor = DataMonitor(self._data["variables"])

        hbox: QtWidgets.QHBoxLayout = QtWidgets.QHBoxLayout()
        hbox.addWidget(self.init_button)
        hbox.addWidget(self.start_button)
        hbox.addWidget(self.stop_button)
        hbox.addWidget(self.edit_button)
        hbox.addWidget(self.remove_button)

        vbox: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout()
        vbox.addWidget(label)
        vbox.addLayout(hbox)
        vbox.addWidget(self.parameters_monitor)
        vbox.addWidget(self.variables_monitor)
        self.setLayout(vbox)

    def update_data(self, data: dict) -> None:
        """"""
        self._data = data

        self.parameters_monitor.update_data(data["parameters"])
        self.variables_monitor.update_data(data["variables"])

        # Update button status
        variables: list = data["variables"]
        inited: bool = variables["inited"]
        trading: bool = variables["trading"]

        if not inited:
            return
        self.init_button.setEnabled(False)

        if trading:
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self.edit_button.setEnabled(False)
            self.remove_button.setEnabled(False)
        else:
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.edit_button.setEnabled(True)
            self.remove_button.setEnabled(True)

    def init_strategy(self) -> None:
        """"""
        self.tv_engine.init_strategy(self.strategy_name)

    def start_strategy(self) -> None:
        """"""
        self.tv_engine.start_strategy(self.strategy_name)

    def stop_strategy(self) -> None:
        """"""
        self.tv_engine.stop_strategy(self.strategy_name)

    def edit_strategy(self) -> None:
        """"""
        strategy_name: str = self._data["strategy_name"]

        parameters: dict = self.tv_engine.get_strategy_parameters(strategy_name)
        editor: SettingEditor = SettingEditor(parameters, strategy_name=strategy_name)
        n: int = editor.exec_()

        if n == editor.Accepted:
            setting: dict = editor.get_setting()
            self.tv_engine.edit_strategy(strategy_name, setting)

    def remove_strategy(self) -> None:
        """"""
        result: bool = self.tv_engine.remove_strategy(self.strategy_name)

        # Only remove strategy gui manager if it has been removed from engine
        if result:
            self.tv_manager.remove_strategy(self.strategy_name)


class DataMonitor(QtWidgets.QTableWidget):
    """
    Table monitor for parameters and variables.
    """

    def __init__(self, data: dict) -> None:
        """"""
        super(DataMonitor, self).__init__()

        self._data: dict = data
        self.cells: dict = {}

        self.init_ui()

    def init_ui(self) -> None:
        """"""
        labels: list = list(self._data.keys())
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

            cell: QtWidgets.QTableWidgetItem = QtWidgets.QTableWidgetItem(str(value))
            cell.setTextAlignment(QtCore.Qt.AlignCenter)

            self.setItem(0, column, cell)
            self.cells[name] = cell

    def update_data(self, data: dict) -> None:
        """"""
        for name, value in data.items():
            cell: QtWidgets.QTableWidgetItem = self.cells[name]
            cell.setText(str(value))


class LogMonitor(BaseMonitor):
    """
    Monitor for log data.
    """

    event_type: str = EVENT_TV_LOG
    data_key: str = ""
    sorting: bool = False

    headers: dict = {
        "time": {"display": "time", "cell": TimeCell, "update": False},
        "msg": {"display": "msg", "cell": MsgCell, "update": False},
    }

    def init_ui(self) -> None:
        """
        Stretch last column.
        """
        super(LogMonitor, self).init_ui()

        self.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.Stretch
        )

    def insert_new_row(self, data) -> None:
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
    ) -> None:
        """"""
        super(SettingEditor, self).__init__()

        self.parameters: dict = parameters
        self.strategy_name: str = strategy_name
        self.class_name: str = class_name

        self.edits: dict = {}

        self.init_ui()

    def init_ui(self) -> None:
        """"""
        form: QtWidgets.QFormLayout = QtWidgets.QFormLayout()

        # Add vt_symbol, name edit, tv_id if add new strategy
        if self.class_name:
            self.setWindowTitle(f"Add Strategy: {self.class_name}")
            button_text: str = "Confirm"
            parameters: dict = {"strategy_name": "", "tv_id": "", "vt_symbol": ""}
            parameters.update(self.parameters)
        else:
            self.setWindowTitle(f"Edit Parameters {self.strategy_name}")
            button_text: str = "Confirm"
            parameters: dict = self.parameters

        for name, value in parameters.items():
            type_: type = type(value)

            edit: QtWidgets.QLineEdit = QtWidgets.QLineEdit(str(value))
            if type_ is int:
                validator: QtGui.QIntValidator = QtGui.QIntValidator()
                edit.setValidator(validator)
            elif type_ is float:
                validator: QtGui.QDoubleValidator = QtGui.QDoubleValidator()
                edit.setValidator(validator)

            form.addRow(f"{name} {type_}", edit)

            self.edits[name] = (edit, type_)

        button: QtWidgets.QPushButton = QtWidgets.QPushButton(button_text)
        button.clicked.connect(self.accept)
        form.addRow(button)

        widget: QtWidgets.QWidget = QtWidgets.QWidget()
        widget.setLayout(form)

        scroll: QtWidgets.QScrollArea = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)

        vbox: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout()
        vbox.addWidget(scroll)
        self.setLayout(vbox)

    def get_setting(self) -> dict:
        """"""
        setting: dict = {}

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