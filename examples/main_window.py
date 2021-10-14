
from jiamtrader.event import EventEngine

from jiamtrader.trader.engine import MainEngine
from jiamtrader.trader.ui import MainWindow, create_qapp

from jiamtrader.gateway.binance import BinanceGateway
from jiamtrader.gateway.binances import BinancesGateway


from jiamtrader.app.cta_strategy import CtaStrategyApp
from jiamtrader.app.data_manager import DataManagerApp
from jiamtrader.app.data_recorder import DataRecorderApp
from jiamtrader.app.algo_trading import AlgoTradingApp
from jiamtrader.app.cta_backtester import CtaBacktesterApp
from jiamtrader.app.risk_manager import RiskManagerApp
from jiamtrader.app.spread_trading import SpreadTradingApp

def main():
    """"""

    qapp = create_qapp()

    event_engine = EventEngine()

    main_engine = MainEngine(event_engine)

    main_engine.add_gateway(BinanceGateway)
    main_engine.add_gateway(BinancesGateway)
    main_engine.add_app(CtaStrategyApp)
    main_engine.add_app(CtaBacktesterApp)
    main_engine.add_app(DataManagerApp)
    main_engine.add_app(AlgoTradingApp)
    main_engine.add_app(DataRecorderApp)
    main_engine.add_app(RiskManagerApp)
    main_engine.add_app(SpreadTradingApp)

    main_window = MainWindow(main_engine, event_engine)
    main_window.showMaximized()

    qapp.exec()


if __name__ == "__main__":
    """
     jiamtrader main window demo
     jiamtrader 的图形化界面
     
     we have binance gate way, which is for spot, while the binances gateway is for contract or futures.
     the difference between the spot and future is their symbol is just different. Spot uses the lower case for symbol, 
     while the futures use the upper cases.
     
     币安的接口有现货和合约接口之分。 他们之间的区别是通过交易对来区分的。现货用小写，合约用大写。 btcusdt.BINANCE 是现货的symbol,
     BTCUSDT.BINANCE合约的交易对。 BTCUSD.BINANCE是合约的币本位保证金的交易对.
    """

    main()