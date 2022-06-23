from pathlib import Path

from howtrader.trader.app import BaseApp

from .engine import RiskEngine, APP_NAME


class RiskManagerApp(BaseApp):
    """"""
    app_name = APP_NAME
    app_module = __module__
    app_path = Path(__file__).parent
    display_name = "交易风控"
    engine_class = RiskEngine
    widget_name = "RiskManager"
    icon_name = str(app_path.joinpath("ui", "rm.ico"))