from howtrader.app.tradingview.template import TVTemplate
from howtrader.app.tradingview.engine import TVEngine
from howtrader.trader.object import TickData, TradeData, OrderData


class SimpleTVStrategy(TVTemplate):
    """the limit order Strategy"""

    author: str = "51bitquant"

    trade_volume: float = 0

    parameters: list = ["trade_volume"]
    def __init__(
            self,
            tv_engine: TVEngine,
            strategy_name: str,
            tv_id:str,
            vt_symbol: str,
            setting: dict,
    ) -> None:
        """"""
        super().__init__(tv_engine, strategy_name, tv_id, vt_symbol, setting)

    def on_init(self) -> None:
        """
        Callback when strategy is inited.
        """
        self.write_log("on init")

    def on_start(self) -> None:
        """
        Callback when strategy is started.
        """

    def on_stop(self):
        """
        Callback when strategy is stopped.
        """
        self.write_log("strategy stop")

    def on_tick(self, tick: TickData) -> None:
        """
        Callback of new tick data update.
        """
        pass

    def on_trade(self, trade: TradeData) -> None:
        """
        Callback of new trade data update.
        """
        pass

    def on_signal(self, signal: dict) -> None:
        pass

    def on_order(self, order: OrderData) -> None:
        """
        Callback of new order data update.
        """
        pass
