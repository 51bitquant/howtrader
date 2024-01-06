from pathlib import Path

from howtrader.trader.app import BaseApp
from howtrader.trader.constant import Direction
from howtrader.trader.object import TickData,TradeData, OrderData

from .base import APP_NAME
from .engine import FundRateEngine
from .template import FundRateArbitrageTemplate


class FundRateArbitrageApp(BaseApp):
    """"""

    app_name = APP_NAME
    app_module = __module__
    app_path = Path(__file__).parent
    display_name = "资金费率套利"
    engine_class = FundRateEngine
    widget_name = "FundRateManager"
    icon_name = "fund_rate.ico"
