from pathlib import Path

from howtrader.trader.app import BaseApp

from .engine import RecorderEngine, APP_NAME


class DataRecorderApp(BaseApp):
    """"""

    app_name: str = APP_NAME
    app_module: str = __module__
    app_path: Path = Path(__file__).parent
    display_name: str = "行情记录"
    engine_class: RecorderEngine = RecorderEngine
    widget_name: str = "RecorderManager"
    icon_name: str = str(app_path.joinpath("ui", "recorder.ico"))