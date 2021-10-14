from jiamtrader.event import EventEngine

from jiamtrader.trader.engine import MainEngine
from jiamtrader.trader.ui import MainWindow, create_qapp

from jiamtrader.gateway.binance import BinanceUsdtGateway  # 合约
from jiamtrader.gateway.binance import BinanceInverseGateway  # 反向合约
from jiamtrader.gateway.binance import BinanceSpotGateway  # 现货
from jiamtrader.gateway.bitmex import BitmexGateway  # bitmex

from jiamtrader.app.cta_strategy import CtaStrategyApp  # CTA策略
from jiamtrader.app.data_manager import DataManagerApp  # 数据管理, csv_data
from jiamtrader.app.data_recorder import DataRecorderApp  # 录行情数据
from jiamtrader.app.algo_trading import AlgoTradingApp  # 算法交易
from jiamtrader.app.cta_backtester import CtaBacktesterApp  # 回测研究
from jiamtrader.app.risk_manager import RiskManagerApp  # 风控管理
from jiamtrader.app.spread_trading import SpreadTradingApp  # 价差交易


def main():
    """"""

    qapp = create_qapp()

    event_engine = EventEngine()

    main_engine = MainEngine(event_engine)

    main_engine.add_gateway(BinanceInverseGateway)
    main_engine.add_gateway(BinanceSpotGateway)
    main_engine.add_gateway(BinanceUsdtGateway)
    main_engine.add_gateway(BitmexGateway)
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

     BTCUSDT, BTCUSDT
    """

    main()

