from typing import Tuple, Dict
from functools import partial
from datetime import datetime, timedelta

from pytz import all_timezones

from howtrader.trader.ui import QtWidgets, QtCore
from howtrader.trader.engine import MainEngine, EventEngine
from howtrader.trader.constant import Interval, Exchange
from howtrader.trader.database import DB_TZ

from ..engine import APP_NAME, ManagerEngine


class ManagerWidget(QtWidgets.QWidget):
    """"""

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine):
        """"""
        super().__init__()

        self.engine: ManagerEngine = main_engine.get_engine(APP_NAME)

        self.tree_items: Dict[Tuple, QtWidgets.QTreeWidgetItem] = {}

        self.init_ui()

    def init_ui(self) -> None:
        """"""
        self.setWindowTitle("Data Manager")

        self.init_tree()
        self.init_table()
        self.init_child()

        refresh_button = QtWidgets.QPushButton("refresh")
        refresh_button.clicked.connect(self.refresh_tree)

        import_button = QtWidgets.QPushButton("import data")
        import_button.clicked.connect(self.import_data)

        update_button = QtWidgets.QPushButton("update data")
        update_button.clicked.connect(self.update_data)

        download_button = QtWidgets.QPushButton("download data")
        download_button.clicked.connect(self.download_data)

        hbox1 = QtWidgets.QHBoxLayout()
        hbox1.addWidget(refresh_button)
        hbox1.addStretch()
        hbox1.addWidget(import_button)
        hbox1.addWidget(update_button)
        hbox1.addWidget(download_button)

        hbox2 = QtWidgets.QHBoxLayout()
        hbox2.addWidget(self.tree)
        hbox2.addWidget(self.table)

        vbox = QtWidgets.QVBoxLayout()
        vbox.addLayout(hbox1)
        vbox.addLayout(hbox2)

        self.setLayout(vbox)

    def init_tree(self) -> None:
        """"""
        labels = [
            "data",
            "vt_symbol",
            "symbol",
            "exchange",
            "data length",
            "start datetime",
            "end datetime",
            "",
            "",
            ""
        ]

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setColumnCount(len(labels))
        self.tree.setHeaderLabels(labels)

    def init_child(self) -> None:
        """"""
        self.minute_child = QtWidgets.QTreeWidgetItem()
        self.minute_child.setText(0, "Minute KLine")
        self.tree.addTopLevelItem(self.minute_child)

        self.hour_child = QtWidgets.QTreeWidgetItem(self.tree)
        self.hour_child.setText(0, "Hour KLine")
        self.tree.addTopLevelItem(self.hour_child)

        self.daily_child = QtWidgets.QTreeWidgetItem(self.tree)
        self.daily_child.setText(0, "Day KLine")
        self.tree.addTopLevelItem(self.daily_child)

    def init_table(self) -> None:
        """"""
        labels = [
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "turnover",
            "open_interest"
        ]

        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(len(labels))
        self.table.setHorizontalHeaderLabels(labels)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QtWidgets.QHeaderView.ResizeToContents
        )

    def clear_tree(self) -> None:
        """"""
        for key, item in self.tree_items.items():
            interval = key[2]

            if interval == Interval.MINUTE.value:
                self.minute_child.removeChild(item)
            elif interval == Interval.HOUR.value:
                self.hour_child.removeChild(item)
            else:
                self.daily_child.removeChild(item)

        self.tree_items.clear()

    def refresh_tree(self) -> None:
        """"""
        self.clear_tree()

        overviews = self.engine.get_bar_overview()

        #sort by symbol
        overviews.sort(key=lambda x: x.symbol)

        for overview in overviews:
            key = (overview.symbol, overview.exchange, overview.interval)
            item = self.tree_items.get(key, None)

            if not item:
                item = QtWidgets.QTreeWidgetItem()
                self.tree_items[key] = item

                item.setText(1, f"{overview.symbol}.{overview.exchange.value}")
                item.setText(2, overview.symbol)
                item.setText(3, overview.exchange.value)

                if overview.interval == Interval.MINUTE:
                    self.minute_child.addChild(item)
                elif overview.interval == Interval.HOUR:
                    self.hour_child.addChild(item)
                else:
                    self.daily_child.addChild(item)

                output_button = QtWidgets.QPushButton("export")
                output_func = partial(
                    self.output_data,
                    overview.symbol,
                    overview.exchange,
                    overview.interval,
                    overview.start,
                    overview.end
                )
                output_button.clicked.connect(output_func)

                show_button = QtWidgets.QPushButton("show")
                show_func = partial(
                    self.show_data,
                    overview.symbol,
                    overview.exchange,
                    overview.interval,
                    overview.start,
                    overview.end
                )
                show_button.clicked.connect(show_func)

                delete_button = QtWidgets.QPushButton("delete")
                delete_func = partial(
                    self.delete_data,
                    overview.symbol,
                    overview.exchange,
                    overview.interval
                )
                delete_button.clicked.connect(delete_func)

                self.tree.setItemWidget(item, 7, show_button)
                self.tree.setItemWidget(item, 8, output_button)
                self.tree.setItemWidget(item, 9, delete_button)

            item.setText(4, str(overview.count))
            item.setText(5, overview.start.strftime("%Y-%m-%d %H:%M:%S"))
            item.setText(6, overview.end.strftime("%Y-%m-%d %H:%M:%S"))

        self.minute_child.setExpanded(True)
        self.hour_child.setExpanded(True)
        self.daily_child.setExpanded(True)

    def import_data(self) -> None:
        """"""
        dialog = ImportDialog()
        n = dialog.exec_()
        if n != dialog.Accepted:
            return

        file_path = dialog.file_edit.text()
        symbol = dialog.symbol_edit.text()
        exchange = dialog.exchange_combo.currentData()
        interval = dialog.interval_combo.currentData()
        tz_name = dialog.tz_combo.currentText()
        datetime_head = dialog.datetime_edit.text()
        open_head = dialog.open_edit.text()
        low_head = dialog.low_edit.text()
        high_head = dialog.high_edit.text()
        close_head = dialog.close_edit.text()
        volume_head = dialog.volume_edit.text()
        turnover_head = dialog.turnover_edit.text()
        open_interest_head = dialog.open_interest_edit.text()
        datetime_format = dialog.format_edit.text()

        start, end, count = self.engine.import_data_from_csv(
            file_path,
            symbol,
            exchange,
            interval,
            tz_name,
            datetime_head,
            open_head,
            high_head,
            low_head,
            close_head,
            volume_head,
            turnover_head,
            open_interest_head,
            datetime_format
        )

        msg = f"\
        load CSV file\n\
        symbol: {symbol}\n\
        exchange: {exchange.value}\n\
        interval: {interval.value}\n\
        start: {start}\n\
        end: {end}\n\
        count: {count}\n\
        "
        QtWidgets.QMessageBox.information(self, "loading success！", msg)

    def output_data(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval,
        start: datetime,
        end: datetime
    ) -> None:
        """"""
        # Get output date range
        dialog = DateRangeDialog(start, end)
        n = dialog.exec_()
        if n != dialog.Accepted:
            return
        start, end = dialog.get_date_range()

        # Get output file path
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "export_data",
            "",
            "CSV(*.csv)"
        )
        if not path:
            return

        result = self.engine.output_data_to_csv(
            path,
            symbol,
            exchange,
            interval,
            start,
            end
        )

        if not result:
            QtWidgets.QMessageBox.warning(
                self,
                "export failed！",
                "the file was open by other software, pls close the software then try again."
            )

    def show_data(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval,
        start: datetime,
        end: datetime
    ) -> None:
        """"""
        # Get output date range
        dialog = DateRangeDialog(start, end)
        n = dialog.exec_()
        if n != dialog.Accepted:
            return
        start, end = dialog.get_date_range()

        bars = self.engine.load_bar_data(
            symbol,
            exchange,
            interval,
            start,
            end
        )

        self.table.setRowCount(0)
        self.table.setRowCount(len(bars))

        for row, bar in enumerate(bars):
            self.table.setItem(row, 0, DataCell(bar.datetime.strftime("%Y-%m-%d %H:%M:%S")))
            self.table.setItem(row, 1, DataCell(str(bar.open_price)))
            self.table.setItem(row, 2, DataCell(str(bar.high_price)))
            self.table.setItem(row, 3, DataCell(str(bar.low_price)))
            self.table.setItem(row, 4, DataCell(str(bar.close_price)))
            self.table.setItem(row, 5, DataCell(str(bar.volume)))
            self.table.setItem(row, 6, DataCell(str(bar.turnover)))
            self.table.setItem(row, 7, DataCell(str(bar.open_interest)))

    def delete_data(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval
    ) -> None:
        """"""
        n = QtWidgets.QMessageBox.warning(
            self,
            "confirm",
            f"Are you sure to delete all the data? {symbol} {exchange.value} {interval.value}",
            QtWidgets.QMessageBox.Ok,
            QtWidgets.QMessageBox.Cancel
        )

        if n == QtWidgets.QMessageBox.Cancel:
            return

        count = self.engine.delete_bar_data(
            symbol,
            exchange,
            interval
        )

        QtWidgets.QMessageBox.information(
            self,
            "delete success",
            f"already delete the data: {symbol} {exchange.value} {interval.value}, total count:{count}",
            QtWidgets.QMessageBox.Ok
        )

    def update_data(self) -> None:
        """"""
        overviews = self.engine.get_bar_overview()
        total = len(overviews)
        count = 0

        dialog = QtWidgets.QProgressDialog(
            "updating the historical datas",
            "cancel",
            0,
            100
        )
        dialog.setWindowTitle("update progress")
        dialog.setWindowModality(QtCore.Qt.WindowModal)
        dialog.setValue(0)

        for overview in overviews:
            if dialog.wasCanceled():
                break

            self.engine.download_bar_data(
                overview.symbol,
                overview.exchange,
                overview.interval,
                overview.end
            )
            count += 1
            progress = int(round(count / total * 100, 0))
            dialog.setValue(progress)

        dialog.close()

    def download_data(self) -> None:
        """"""
        dialog = DownloadDialog(self.engine)
        dialog.exec_()

    def show(self) -> None:
        """"""
        self.showMaximized()


class DataCell(QtWidgets.QTableWidgetItem):
    """"""

    def __init__(self, text: str = ""):
        super().__init__(text)

        self.setTextAlignment(QtCore.Qt.AlignCenter)


class DateRangeDialog(QtWidgets.QDialog):
    """"""

    def __init__(self, start: datetime, end: datetime, parent=None):
        """"""
        super().__init__(parent)

        self.setWindowTitle("Choose 选择数据区间")

        self.start_edit = QtWidgets.QDateEdit(
            QtCore.QDate(
                start.year,
                start.month,
                start.day
            )
        )
        self.end_edit = QtWidgets.QDateEdit(
            QtCore.QDate(
                end.year,
                end.month,
                end.day
            )
        )

        button = QtWidgets.QPushButton("confirm")
        button.clicked.connect(self.accept)

        form = QtWidgets.QFormLayout()
        form.addRow("start datetime", self.start_edit)
        form.addRow("end datetime", self.end_edit)
        form.addRow(button)

        self.setLayout(form)

    def get_date_range(self) -> Tuple[datetime, datetime]:
        """"""
        start = self.start_edit.dateTime().toPython()
        end = self.end_edit.dateTime().toPython() + timedelta(days=1)
        return start, end


class ImportDialog(QtWidgets.QDialog):
    """"""

    def __init__(self, parent=None):
        """"""
        super().__init__()

        self.setWindowTitle("import data from csv file")
        self.setFixedWidth(300)

        self.setWindowFlags(
            (self.windowFlags() | QtCore.Qt.CustomizeWindowHint)
            & ~QtCore.Qt.WindowMaximizeButtonHint)

        file_button = QtWidgets.QPushButton("select file")
        file_button.clicked.connect(self.select_file)

        load_button = QtWidgets.QPushButton("confirm")
        load_button.clicked.connect(self.accept)

        self.file_edit = QtWidgets.QLineEdit()
        self.symbol_edit = QtWidgets.QLineEdit()

        self.exchange_combo = QtWidgets.QComboBox()
        for i in Exchange:
            self.exchange_combo.addItem(str(i.name), i)

        self.interval_combo = QtWidgets.QComboBox()
        for i in Interval:
            if i != Interval.TICK:
                self.interval_combo.addItem(str(i.name), i)

        self.tz_combo = QtWidgets.QComboBox()
        self.tz_combo.addItems(all_timezones)
        self.tz_combo.setCurrentIndex(self.tz_combo.findText("Asia/Shanghai"))

        self.datetime_edit = QtWidgets.QLineEdit("open_time")
        self.open_edit = QtWidgets.QLineEdit("open")
        self.high_edit = QtWidgets.QLineEdit("high")
        self.low_edit = QtWidgets.QLineEdit("low")
        self.close_edit = QtWidgets.QLineEdit("close")
        self.volume_edit = QtWidgets.QLineEdit("volume")
        self.turnover_edit = QtWidgets.QLineEdit("turnover")
        self.open_interest_edit = QtWidgets.QLineEdit("open_interest")

        self.format_edit = QtWidgets.QLineEdit("%Y-%m-%d %H:%M:%S")

        info_label = QtWidgets.QLabel("contract info")
        info_label.setAlignment(QtCore.Qt.AlignCenter)

        head_label = QtWidgets.QLabel("columns info")
        head_label.setAlignment(QtCore.Qt.AlignCenter)

        format_label = QtWidgets.QLabel("format info")
        format_label.setAlignment(QtCore.Qt.AlignCenter)

        form = QtWidgets.QFormLayout()
        form.addRow(file_button, self.file_edit)
        form.addRow(QtWidgets.QLabel())
        form.addRow(info_label)
        form.addRow("symbol", self.symbol_edit)
        form.addRow("exchange", self.exchange_combo)
        form.addRow("interval", self.interval_combo)
        form.addRow("timezone", self.tz_combo)
        form.addRow(QtWidgets.QLabel())
        form.addRow(head_label)
        form.addRow("open_time", self.datetime_edit)
        form.addRow("open", self.open_edit)
        form.addRow("high", self.high_edit)
        form.addRow("low", self.low_edit)
        form.addRow("close", self.close_edit)
        form.addRow("volume", self.volume_edit)
        form.addRow("turnover", self.turnover_edit)
        form.addRow("open_interest", self.open_interest_edit)
        form.addRow(QtWidgets.QLabel())
        form.addRow(format_label)
        form.addRow("datetime format", self.format_edit)
        form.addRow(QtWidgets.QLabel())
        form.addRow(load_button)

        self.setLayout(form)

    def select_file(self):
        """"""
        result: str = QtWidgets.QFileDialog.getOpenFileName(
            self, filter="CSV (*.csv)")
        filename = result[0]
        if filename:
            self.file_edit.setText(filename)


class DownloadDialog(QtWidgets.QDialog):
    """"""

    def __init__(self, engine: ManagerEngine, parent=None):
        """"""
        super().__init__()

        self.engine = engine

        self.setWindowTitle("download historical datas")
        self.setFixedWidth(300)

        self.setWindowFlags(
            (self.windowFlags() | QtCore.Qt.CustomizeWindowHint)
            & ~QtCore.Qt.WindowMaximizeButtonHint)

        self.symbol_edit = QtWidgets.QLineEdit()

        self.exchange_combo = QtWidgets.QComboBox()
        for i in Exchange:
            self.exchange_combo.addItem(str(i.name), i)

        self.interval_combo = QtWidgets.QComboBox()
        for i in Interval:
            self.interval_combo.addItem(str(i.name), i)

        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=3 * 365)

        self.start_date_edit = QtWidgets.QDateEdit(
            QtCore.QDate(
                start_dt.year,
                start_dt.month,
                start_dt.day
            )
        )

        button = QtWidgets.QPushButton("download")
        button.clicked.connect(self.download)

        form = QtWidgets.QFormLayout()
        form.addRow("symbol", self.symbol_edit)
        form.addRow("exchange", self.exchange_combo)
        form.addRow("interval", self.interval_combo)
        form.addRow("start datetime", self.start_date_edit)
        form.addRow(button)

        self.setLayout(form)

    def download(self):
        """"""
        symbol = self.symbol_edit.text()
        exchange = Exchange(self.exchange_combo.currentData())
        interval = Interval(self.interval_combo.currentData())

        start_date = self.start_date_edit.date()
        start = datetime(start_date.year(), start_date.month(), start_date.day())
        start = DB_TZ.localize(start)

        if interval == Interval.TICK:
            count = self.engine.download_tick_data(symbol, exchange, start)
        else:
            count = self.engine.download_bar_data(symbol, exchange, interval, start)
        QtWidgets.QMessageBox.information(self, "download is over", f"total count: {count}")