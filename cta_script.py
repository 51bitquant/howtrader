import sys
from time import sleep
from datetime import datetime, time
from logging import INFO

from howtrader.event import EventEngine
from howtrader.trader.setting import SETTINGS
from howtrader.trader.engine import MainEngine, LogEngine

from howtrader.gateway.binance import BinanceSpotGateway, BinanceUsdtGateway
from howtrader.app.cta_strategy import CtaStrategyApp, CtaEngine
from howtrader.app.cta_strategy.base import EVENT_CTA_LOG


SETTINGS["log.active"] = True
SETTINGS["log.level"] = INFO
SETTINGS["log.console"] = True


usdt_gateway_setting = {
        "key": "",
        "secret": "",
        "proxy_host": "",
        "proxy_port": 0,
    }

def run():
    """
    Running in the child process.
    """
    SETTINGS["log.file"] = True

    event_engine = EventEngine()
    main_engine: MainEngine = MainEngine(event_engine)
    main_engine.add_gateway(BinanceUsdtGateway)
    cta_engine: CtaEngine = main_engine.add_app(CtaStrategyApp)
    main_engine.write_log("setup main engine")

    log_engine: LogEngine  = main_engine.get_engine("log")
    event_engine.register(EVENT_CTA_LOG, log_engine.process_log_event)
    main_engine.write_log("register event listener")

    main_engine.connect(usdt_gateway_setting, "BINANCE_USDT")
    main_engine.write_log("connect binance usdt gate way")

    sleep(10)

    cta_engine.init_engine()
    main_engine.write_log("set up cta engine")

    cta_engine.init_all_strategies()
    sleep(60)   # Leave enough time to complete strategy initialization
    main_engine.write_log("init cta strategies")

    cta_engine.start_all_strategies()
    main_engine.write_log("start cta strategies")

    while True:
        sleep(10)

if __name__ == "__main__":
    run()
