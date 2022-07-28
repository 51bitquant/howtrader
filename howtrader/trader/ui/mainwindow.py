"""
Implements main window of the trading platform.
"""

from types import ModuleType
import webbrowser
from functools import partial
from importlib import import_module
from typing import Callable, Dict, List, Tuple

import howtrader
from howtrader.event import EventEngine
from decimal import Decimal
from .qt import QtCore, QtGui, QtWidgets
from .widget import (
    TickMonitor,
    OrderMonitor,
    TradeMonitor,
    PositionMonitor,
    AccountMonitor,
    LogMonitor,
    ActiveOrderMonitor,
    ConnectDialog,
    ContractManager,
    TradingWidget,
    AboutDialog,
    GlobalDialog
)
from ..engine import MainEngine, BaseApp
from ..utility import get_icon_path, TRADER_DIR, round_to, floor_to, extract_vt_symbol
from ..setting import QUICK_TRADER_SETTINGS
from howtrader.trader.object import ContractData, OrderRequest, Direction, OrderType, Offset, TickData, PositionData, Product


class MainWindow(QtWidgets.QMainWindow):
    """
    Main window of the trading platform.
    """

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine) -> None:
        """"""
        super().__init__()

        self.main_engine: MainEngine = main_engine
        self.event_engine: EventEngine = event_engine

        self.window_title: str = f"Howtrader - {howtrader.__version__}   [{TRADER_DIR}]"

        self.widgets: Dict[str, QtWidgets.QWidget] = {}

        self.init_ui()

    def init_ui(self) -> None:
        """"""
        self.setWindowTitle(self.window_title)
        self.init_dock()
        self.init_toolbar()
        self.init_menu()
        # self.load_window_setting("custom")

    def init_dock(self) -> None:
        """"""
        self.trading_widget, trading_dock = self.create_dock(
            TradingWidget, "Trading", QtCore.Qt.LeftDockWidgetArea
        )
        tick_widget, tick_dock = self.create_dock(
            TickMonitor, "Ticks", QtCore.Qt.RightDockWidgetArea
        )
        order_widget, order_dock = self.create_dock(
            OrderMonitor, "All Orders", QtCore.Qt.RightDockWidgetArea
        )
        active_widget, active_dock = self.create_dock(
            ActiveOrderMonitor, "Active Orders", QtCore.Qt.RightDockWidgetArea
        )
        trade_widget, trade_dock = self.create_dock(
            TradeMonitor, "Trades", QtCore.Qt.RightDockWidgetArea
        )
        log_widget, log_dock = self.create_dock(
            LogMonitor, "Logs", QtCore.Qt.RightDockWidgetArea
        )
        account_widget, account_dock = self.create_dock(
            AccountMonitor, "Accounts", QtCore.Qt.RightDockWidgetArea
        )
        position_widget, position_dock = self.create_dock(
            PositionMonitor, "Positions", QtCore.Qt.RightDockWidgetArea
        )

        self.tabifyDockWidget(order_dock, active_dock)
        self.tabifyDockWidget(active_dock,trade_dock)

        self.tabifyDockWidget(account_dock, position_dock)
        self.tabifyDockWidget(position_dock, log_dock)

        self.save_window_setting("default")

        tick_widget.itemDoubleClicked.connect(self.trading_widget.update_with_cell)
        position_widget.itemDoubleClicked.connect(self.trading_widget.update_with_cell)

    def init_menu(self) -> None:
        """"""
        bar: QtWidgets.QMenuBar = self.menuBar()
        bar.setNativeMenuBar(False)     # for mac and linux

        # System menu
        sys_menu: QtWidgets.QMenu = bar.addMenu("exchanges")

        gateway_names: list = self.main_engine.get_all_gateway_names()
        for name in gateway_names:
            func: Callable = partial(self.connect, name)
            self.add_action(
                sys_menu,
                f"Connect {name}",
                get_icon_path(__file__, "connect.ico"),
                func
            )

        sys_menu.addSeparator()

        self.add_action(
            sys_menu,
            "exit",
            get_icon_path(__file__, "exit.ico"),
            self.close
        )

        # App menu
        app_menu: QtWidgets.QMenu = bar.addMenu("apps")

        all_apps: List[BaseApp] = self.main_engine.get_all_apps()
        for app in all_apps:
            ui_module: ModuleType = import_module(app.app_module + ".ui")
            widget_class: QtWidgets.QWidget = getattr(ui_module, app.widget_name)

            func: Callable = partial(self.open_widget, widget_class, app.app_name)

            self.add_action(app_menu, app.display_name, app.icon_name, func, True)

        # Global setting editor
        action: QtGui.QAction = QtWidgets.QAction("configs", self)
        action.triggered.connect(self.edit_global_setting)
        bar.addAction(action)

        # Help menu
        help_menu: QtWidgets.QMenu = bar.addMenu("help")

        self.add_action(
            help_menu,
            "query contract",
            get_icon_path(__file__, "contract.ico"),
            partial(self.open_widget, ContractManager, "contract"),
            True
        )

        self.add_action(
            help_menu,
            "restore window",
            get_icon_path(__file__, "restore.ico"),
            self.restore_window_setting
        )

        # self.add_action(
        #     help_menu,
        #     "测试邮件",
        #     get_icon_path(__file__, "email.ico"),
        #     self.send_test_email
        # )
        #
        # self.add_action(
        #     help_menu,
        #     "社区论坛",
        #     get_icon_path(__file__, "forum.ico"),
        #     self.open_forum,
        #     True
        # )

        self.add_action(
            help_menu,
            "about",
            get_icon_path(__file__, "about.ico"),
            partial(self.open_widget, AboutDialog, "about"),
        )

    def init_toolbar(self) -> None:
        """"""
        self.toolbar: QtWidgets.QToolBar = QtWidgets.QToolBar(self)
        self.toolbar.setObjectName("toolbar")
        self.toolbar.setFloatable(False)
        self.toolbar.setMovable(False)

        # Set button size
        w: int = 40
        size = QtCore.QSize(w, w)
        self.toolbar.setIconSize(size)

        # Set button spacing
        self.toolbar.layout().setSpacing(10)

        self.addToolBar(QtCore.Qt.LeftToolBarArea, self.toolbar)

    def add_action(
        self,
        menu: QtWidgets.QMenu,
        action_name: str,
        icon_name: str,
        func: Callable,
        toolbar: bool = False
    ) -> None:
        """"""
        icon: QtGui.QIcon = QtGui.QIcon(icon_name)

        action: QtGui.QAction = QtWidgets.QAction(action_name, self)
        action.triggered.connect(func)
        action.setIcon(icon)

        menu.addAction(action)

        if toolbar:
            self.toolbar.addAction(action)

    def create_dock(
        self,
        widget_class: QtWidgets.QWidget,
        name: str,
        area: int
    ) -> Tuple[QtWidgets.QWidget, QtWidgets.QDockWidget]:
        """
        Initialize a dock widget.
        """
        widget: QtWidgets.QWidget = widget_class(self.main_engine, self.event_engine)

        dock: QtWidgets.QDockWidget = QtWidgets.QDockWidget(name)
        dock.setWidget(widget)
        dock.setObjectName(name)
        dock.setFeatures(dock.DockWidgetFloatable | dock.DockWidgetMovable)
        self.addDockWidget(area, dock)
        return widget, dock

    def connect(self, gateway_name: str) -> None:
        """
        Open connect dialog for gateway connection.
        """
        dialog: ConnectDialog = ConnectDialog(self.main_engine, gateway_name)
        dialog.exec_()

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """
        Call main engine close function before exit.
        """
        reply = QtWidgets.QMessageBox.question(
            self,
            "exit",
            "confirm exit？",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )

        if reply == QtWidgets.QMessageBox.Yes:
            for widget in self.widgets.values():
                widget.close()
            # self.save_window_setting("custom")

            self.main_engine.close()

            event.accept()
        else:
            event.ignore()

    def open_widget(self, widget_class: QtWidgets.QWidget, name: str) -> None:
        """
        Open contract manager.
        """
        widget: QtWidgets.QWidget = self.widgets.get(name, None)
        if not widget:
            widget = widget_class(self.main_engine, self.event_engine)
            self.widgets[name] = widget

        if isinstance(widget, QtWidgets.QDialog):
            widget.exec_()
        else:
            widget.show()

    def save_window_setting(self, name: str) -> None:
        """
        Save current window size and state by trader path and setting name.
        """
        settings: QtCore.QSettings = QtCore.QSettings(self.window_title, name)
        settings.setValue("state", self.saveState())
        settings.setValue("geometry", self.saveGeometry())

    def load_window_setting(self, name: str) -> None:
        """
        Load previous window size and state by trader path and setting name.
        """
        settings: QtCore.QSettings = QtCore.QSettings(self.window_title, name)
        state = settings.value("state")
        geometry = settings.value("geometry")

        if isinstance(state, QtCore.QByteArray):
            self.restoreState(state)
            self.restoreGeometry(geometry)

    def restore_window_setting(self) -> None:
        """
        Restore window to default setting.
        """
        self.load_window_setting("default")
        self.showMaximized()

    def send_test_email(self) -> None:
        """
        Sending a test email.
        """
        self.main_engine.send_email("Howtrader", "testing")

    def open_forum(self) -> None:
        """
        """
        webbrowser.open("https://www.vnpy.com/forum/")

    def edit_global_setting(self) -> None:
        """
        """
        dialog: GlobalDialog = GlobalDialog()
        dialog.exec_()

    def keyReleaseEvent(self, key_event: QtGui.QKeyEvent):
        if isinstance(self.trading_widget, TradingWidget):
            vt_symbol: str = self.trading_widget.vt_symbol
            if not vt_symbol:
                return None
        else:
            return None

        if key_event.key() == QtCore.Qt.Key_Z:
            # Z key.
            order_list = self.main_engine.get_all_active_orders()
            for order in order_list:
                req = order.create_cancel_request()
                self.main_engine.cancel_order(req, order.gateway_name)

            self.main_engine.write_log("Press Z key: cancel all orders")
            return None

        keys = {QtCore.Qt.Key_0: "0",
                QtCore.Qt.Key_1: "1",
                QtCore.Qt.Key_2: "2",
                QtCore.Qt.Key_3: "3",
                QtCore.Qt.Key_4: "4",
                QtCore.Qt.Key_5: "5",
                QtCore.Qt.Key_6: "6",
                QtCore.Qt.Key_7: "7",
                QtCore.Qt.Key_8: "8",
                QtCore.Qt.Key_9: "9"
                }

        key = keys.get(key_event.key(), None)
        if not key:
            return None

        options = QUICK_TRADER_SETTINGS.get(key, None)

        if options:
            direction = options.get('direction')
            price = options.get('price')
            over_price_value = float(options.get('over_price_value'))
            over_price_option = options.get('over_price_option')
            volume_option = options.get('volume_option')
            volume = options.get('volume')
            add_minus = options.get('add_minus')

            contract: ContractData = self.main_engine.get_contract(vt_symbol)

            if not contract:
                return

            if direction == "buy":
                direction = Direction.LONG
            else:
                direction = Direction.SHORT

            order_type = OrderType.LIMIT
            offset = Offset.OPEN

            tick: TickData = self.main_engine.get_tick(vt_symbol)
            tick_price = getattr(tick, price)
            if tick_price <= 0 or not tick_price:
                self.main_engine.write_log("Tick price is incorrect.")
                return None

            if over_price_option == "min_price":
                if add_minus == '+':
                    order_price = tick_price + float(over_price_value) * float(contract.pricetick)
                else:
                    order_price = tick_price - float(over_price_value) * float(contract.pricetick)

            else:  # percent
                if add_minus == '+':
                    order_price = tick_price * (1 + float(over_price_value)/100)
                else:
                    order_price = tick_price * (1 - float(over_price_value)/100)

            order_price = round_to(Decimal(str(order_price)), contract.pricetick)

            if volume_option == "fixed_volume":
                volume = Decimal(volume)
            else: # % of the position
                if contract.product == Product.SPOT:
                    self.main_engine.write_log(f"Position is not available for Spot market.")
                    return None

                if not contract.net_position:
                    self.main_engine.write_log(f"Not support Position.")
                    return None

                position_id: str = f"{vt_symbol}.{Direction.NET.value}"
                position: PositionData = self.main_engine.get_position(position_id)

                if position:
                    volume = abs(position.volume) * float(volume) / 100
                    volume = floor_to(volume, contract.min_volume)
                else:
                    self.main_engine.write_log(f"Position is None")
                    return None

            symbol, exchange = extract_vt_symbol(vt_symbol)

            req = OrderRequest(
                symbol=symbol,
                exchange=exchange,
                direction=direction,
                type=order_type,
                offset=offset,
                volume=volume,
                price=order_price,
                reference="QuickTrader"
            )

            self.main_engine.send_order(req, contract.gateway_name)