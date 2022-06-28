import sys
from time import sleep
from datetime import datetime, time
from logging import INFO

from howtrader.event import EventEngine
from howtrader.trader.setting import SETTINGS
from howtrader.trader.engine import MainEngine

from howtrader.gateway.binance import BinanceSpotGateway,BinanceUsdtGateway, BinanceInverseGateway
from howtrader.gateway.binance.binance_usdt_gateway import BinanceUsdtRestApi
from howtrader.trader.object import Exchange, Interval
from tzlocal import get_localzone_name
from howtrader.trader.object import HistoryRequest
from howtrader.trader.database import BaseDatabase, get_database

database: BaseDatabase = get_database()

from threading import Thread

SETTINGS["log.active"] = True
SETTINGS["log.level"] = INFO
SETTINGS["log.console"] = True

spot_gateway_setting = {
    "key": "",
    "secret": "",
    "proxy_host": "",
    "proxy_port": 0,
}

usdt_gateway_setting = {
    "key": "",
    "secret": "",
    "proxy_host": "",
    "proxy_port": 0
}

inverse_gateway_setting = {
    "key": "",
    "secret": "",
    "proxy_host": "",
    "proxy_port": 0
}


def request1():
    start = datetime(2020, 10, 1, tzinfo=get_localzone_name())
    end = datetime(2020, 10, 2, tzinfo=get_localzone_name())
    req = HistoryRequest(
        symbol=symbol,
        exchange=exchange,
        interval=interval,
        start=start,
        end=end
    )

    bars = gate_way.query_history(req)

    print(bars)
    if bars:
        database.save_bar_data(bars)

def request2():
    print("start2")
    start = datetime(2020, 11, 12, tzinfo=get_localzone_name())
    end = datetime(2020, 11, 13, tzinfo=get_localzone_name())
    req = HistoryRequest(
        symbol=symbol,
        exchange=exchange,
        interval=interval,
        start=start,
        end=end
    )

    bars = gate_way.query_history(req)
    print("start2_end", bars)
    if bars:
        database.save_bar_data(bars)


if __name__ == "__main__":
    """
        for crawling data from Binance exchange.
    """
    SETTINGS["log.file"] = True

    event_engine = EventEngine()
    main_engine = MainEngine(event_engine)
    main_engine.add_gateway(BinanceSpotGateway)  # spot
    main_engine.add_gateway(BinanceUsdtGateway)  # future
    main_engine.add_gateway(BinanceInverseGateway)  # future
    main_engine.connect(spot_gateway_setting, "BINANCE_SPOT")  # spot
    main_engine.connect(usdt_gateway_setting, "BINANCE_USDT")  # future
    main_engine.connect(inverse_gateway_setting, "BINANCE_INVERSE")  # Inverse future.
    sleep(3)

    main_engine.write_log("connect binance spot gateway")  # spot
    main_engine.write_log("connect binance future gateway") # future
    main_engine.write_log("connect binance inverse gateway")  # inverse
    gate_way = main_engine.get_gateway("BINANCE")  # spot
    # gate_way = main_engine.get_gateway("BINANCES")  # future
    print(gate_way)

    symbol = "btcusdt"  # spot for lower case while the future will be upper case.

    exchange = Exchange.BINANCE  # binance.
    interval = Interval.MINUTE  # minute

    t1 = Thread(target=request1)
    # t2 = Thread(target=request2)

    t1.start()
    # t2.start()




