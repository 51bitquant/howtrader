from datetime import datetime
from threading import Thread
from typing import List

from howtrader.event import Event, EventEngine
from howtrader.trader.engine import BaseEngine, MainEngine
from howtrader.trader.constant import Interval
from howtrader.trader.object import BarData, HistoryRequest, ContractData
from howtrader.trader.utility import extract_vt_symbol
from howtrader.trader.database import get_database, BaseDatabase

APP_NAME: str = "ChartWizard"

EVENT_CHART_HISTORY: str = "eChartHistory"


class ChartWizardEngine(BaseEngine):
    """
    For running chartWizard.
    """

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine) -> None:
        """"""
        super().__init__(main_engine, event_engine, APP_NAME)
        self.database: BaseDatabase = get_database()

    def query_history(
        self,
        vt_symbol: str,
        interval: Interval,
        start: datetime,
        end: datetime
    ) -> None:
        """"""
        thread: Thread = Thread(
            target=self._query_history,
            args=[vt_symbol, interval, start, end]
        )
        thread.start()

    def _query_history(
        self,
        vt_symbol: str,
        interval: Interval,
        start: datetime,
        end: datetime
    ) -> None:
        """"""
        symbol, exchange = extract_vt_symbol(vt_symbol)

        req: HistoryRequest = HistoryRequest(
            symbol=symbol,
            exchange=exchange,
            interval=interval,
            start=start,
            end=end
        )

        contract: ContractData = self.main_engine.get_contract(vt_symbol)
        if contract:
            if contract.history_data:
                data: List[BarData] = self.main_engine.query_history(req, contract.gateway_name)
        else:
            data: List[BarData] = self.database.load_bar_data(
                symbol,
                exchange,
                interval,
                start,
                end
            )

        event: Event = Event(EVENT_CHART_HISTORY, data)
        self.event_engine.put(event)
