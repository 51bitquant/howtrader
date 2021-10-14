from pathlib import Path

from jiamtrader.trader.app import BaseApp
from jiamtrader.trader.constant import Direction
from jiamtrader.trader.object import TickData, BarData, TradeData, OrderData
from jiamtrader.trader.utility import BarGenerator, ArrayManager

from .base import APP_NAME
from .engine import StrategyEngine
from .template import StrategyTemplate
from .backtesting import BacktestingEngine


class PortfolioStrategyApp(BaseApp):
    """"""

    app_name = APP_NAME
    app_module = __module__
    app_path = Path(__file__).parent
    display_name = "组合策略"
    engine_class = StrategyEngine
    widget_name = "PortfolioStrategyManager"
    icon_name = "strategy.ico"
