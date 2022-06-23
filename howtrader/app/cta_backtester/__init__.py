from pathlib import Path

from howtrader.trader.app import BaseApp

from .engine import BacktesterEngine, APP_NAME


class CtaBacktesterApp(BaseApp):
    """"""

    app_name: str = APP_NAME
    app_module: str = __module__
    app_path: Path = Path(__file__).parent
    display_name: str = "CTA回测"
    engine_class: BacktesterEngine = BacktesterEngine
    widget_name: str = "BacktesterManager"
    icon_name: str = str(app_path.joinpath("ui", "backtester.ico"))