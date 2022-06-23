from pathlib import Path

from howtrader.trader.app import BaseApp

from .engine import ChartWizardEngine, APP_NAME


class ChartWizardApp(BaseApp):
    """"""

    app_name: str = APP_NAME
    app_module: str = __module__
    app_path: Path = Path(__file__).parent
    display_name: str = "K线图表"
    engine_class: ChartWizardEngine = ChartWizardEngine
    widget_name: str = "ChartWizardWidget"
    icon_name: str = str(app_path.joinpath("ui", "cw.ico"))