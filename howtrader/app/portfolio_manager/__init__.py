from pathlib import Path

from howtrader.trader.app import BaseApp

from .engine import PortfolioEngine, APP_NAME


class PortfolioManagerApp(BaseApp):
    """"""
    app_name = APP_NAME
    app_module = __module__
    app_path = Path(__file__).parent
    display_name = "Portfolio Manager"
    engine_class = PortfolioEngine
    widget_name = "PortfolioManager"
    icon_name = str(app_path.joinpath("ui", "portfolio.ico"))