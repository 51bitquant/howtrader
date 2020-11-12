""""""
from datetime import datetime
from threading import Thread

from howtrader.event import Event, EventEngine
from howtrader.trader.engine import BaseEngine, MainEngine
from howtrader.trader.constant import Interval
from howtrader.trader.object import HistoryRequest, ContractData


APP_NAME = "ChartWizard"

EVENT_CHART_HISTORY = "eChartHistory"


class ChartWizardEngine(BaseEngine):
    """"""

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine):
        """"""
        super().__init__(main_engine, event_engine, APP_NAME)


    def query_history(
        self,
        vt_symbol: str,
        interval: Interval,
        start: datetime,
        end: datetime
    ) -> None:
        """"""
        thread = Thread(
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
        contract: ContractData = self.main_engine.get_contract(vt_symbol)

        req = HistoryRequest(
            symbol=contract.symbol,
            exchange=contract.exchange,
            interval=interval,
            start=start,
            end=end
        )

        if contract.history_data:
            data = self.main_engine.query_history(req, contract.gateway_name)

            event = Event(EVENT_CHART_HISTORY, data)
            self.event_engine.put(event)
