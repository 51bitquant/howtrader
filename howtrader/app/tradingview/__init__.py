from pathlib import Path

from howtrader.trader.app import BaseApp

from .engine import TVEngine, APP_NAME


class TradingViewApp(BaseApp):
    """"""

    app_name = APP_NAME
    app_module = __module__
    app_path = Path(__file__).parent
    display_name = "Tradingview"
    engine_class = TVEngine
    widget_name = "TVManager"
    icon_name = str(app_path.joinpath("ui", "tv.ico"))