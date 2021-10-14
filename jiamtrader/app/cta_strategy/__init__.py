from pathlib import Path

from jiamtrader.trader.app import BaseApp
from jiamtrader.trader.constant import Direction
from jiamtrader.trader.object import TickData, BarData, TradeData, OrderData
from jiamtrader.trader.utility import BarGenerator, ArrayManager

from .base import APP_NAME, StopOrder
from .engine import CtaEngine
from .template import CtaTemplate, CtaSignal, TargetPosTemplate


class CtaStrategyApp(BaseApp):
    """"""

    app_name = APP_NAME
    app_module = __module__
    app_path = Path(__file__).parent
    display_name = "CTA策略"
    engine_class = CtaEngine
    widget_name = "CtaManager"
    icon_name = "cta.ico"
