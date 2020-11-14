import sys
from time import sleep
from datetime import datetime, time
from logging import INFO

from howtrader.event import EventEngine
from howtrader.trader.setting import SETTINGS
from howtrader.trader.engine import MainEngine

from howtrader.gateway.binances import BinancesGateway
from howtrader.gateway.binances.binances_gateway import BinancesRestApi
from howtrader.trader.object import Exchange, Interval
from tzlocal import get_localzone
from howtrader.trader.object import HistoryRequest
from howtrader.trader.database import database_manager
from threading import Thread


SETTINGS["log.active"] = True
SETTINGS["log.level"] = INFO
SETTINGS["log.console"] = True


binances_setting = {
        "key": "",
        "secret": "",
        "会话数": 3,
        "服务器": "REAL",
        "合约模式": "正向",
        "代理地址": "",
        "代理端口": 0,
    }


def request1():
    start = datetime(2020, 11, 13, tzinfo=get_localzone())
    end = datetime(2020, 11, 14, tzinfo=get_localzone())
    req = HistoryRequest(
        symbol=symbol,
        exchange=exchange,
        interval=Interval(interval),
        start=start,
        end=end
    )

    data = gate_way.query_history(req)

    if data:
        database_manager.save_bar_data(data)

def request2():
    start = datetime(2020, 11, 12, tzinfo=get_localzone())
    end = datetime(2020, 11, 13, tzinfo=get_localzone())
    req = HistoryRequest(
        symbol=symbol,
        exchange=exchange,
        interval=Interval(interval),
        start=start,
        end=end
    )

    data = gate_way.query_history(req)
    if data:
        database_manager.save_bar_data(data)


if __name__ == "__main__":

    SETTINGS["log.file"] = True

    event_engine = EventEngine()
    main_engine = MainEngine(event_engine)
    main_engine.add_gateway(BinancesGateway)

    main_engine.connect(binances_setting, "BINANCES")

    sleep(3)

    main_engine.write_log("连接BINANCES接口")

    gate_way = main_engine.get_gateway("BINANCES")

    print(gate_way)

    symbol = "BTCUSDT"

    exchange = Exchange.BINANCE  # binance.

    interval = Interval.MINUTE  # minute

    t1 = Thread(target=request1)
    t2 = Thread(target=request2)

    t1.start()
    t2.start()




