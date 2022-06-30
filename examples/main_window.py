
from howtrader.event import EventEngine

from howtrader.trader.engine import MainEngine
from howtrader.trader.ui import MainWindow, create_qapp

from howtrader.gateway.binance import BinanceSpotGateway, BinanceUsdtGateway, BinanceInverseGateway

from howtrader.app.cta_strategy import CtaStrategyApp
from howtrader.app.data_manager import DataManagerApp
from howtrader.app.data_recorder import DataRecorderApp
from howtrader.app.algo_trading import AlgoTradingApp
from howtrader.app.risk_manager import RiskManagerApp
from howtrader.app.spread_trading import SpreadTradingApp

def main():
    """"""

    qapp = create_qapp()

    event_engine = EventEngine()

    main_engine = MainEngine(event_engine)

    main_engine.add_gateway(BinanceSpotGateway)
    main_engine.add_gateway(BinanceUsdtGateway)
    main_engine.add_gateway(BinanceInverseGateway)
    main_engine.add_app(CtaStrategyApp)
    main_engine.add_app(DataManagerApp)
    # main_engine.add_app(AlgoTradingApp)
    main_engine.add_app(DataRecorderApp)
    # main_engine.add_app(RiskManagerApp)
    # main_engine.add_app(SpreadTradingApp)

    main_window = MainWindow(main_engine, event_engine)
    main_window.showMaximized()

    qapp.exec()


if __name__ == "__main__":

    main()