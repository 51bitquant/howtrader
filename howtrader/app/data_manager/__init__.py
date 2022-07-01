from pathlib import Path

from howtrader.trader.app import BaseApp
from .engine import APP_NAME, ManagerEngine


class DataManagerApp(BaseApp):
    """"""

    app_name = APP_NAME
    app_module = __module__
    app_path = Path(__file__).parent
    display_name = "Data Manager"
    engine_class = ManagerEngine
    widget_name = "ManagerWidget"
    icon_name = str(app_path.joinpath("ui", "manager.ico"))
