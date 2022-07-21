from time import sleep
from logging import INFO

from howtrader.event import EventEngine
from howtrader.trader.setting import SETTINGS
from howtrader.trader.engine import MainEngine, LogEngine

from howtrader.gateway.binance import BinanceSpotGateway, BinanceUsdtGateway, BinanceInverseGateway
from howtrader.app.cta_strategy import CtaStrategyApp, CtaEngine
from howtrader.app.cta_strategy.base import EVENT_CTA_LOG
from howtrader.event import Event
from howtrader.trader.event import EVENT_TV_SIGNAL, EVENT_TV_LOG
from howtrader.app.tradingview import TradingViewApp, TVEngine
from threading import Thread
import json
from flask import Flask, request

# create global event_engine
event_engine: EventEngine = EventEngine()
passphrase = SETTINGS.get("passphrase", "")
port = SETTINGS.get("port", 9999)

app = Flask(__name__)


@app.route('/', methods=['GET'])
def welcome():
    return "Hi, this is tv server!"


@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = json.loads(request.data)
        # print(data)
        if data.get('passphrase', None) != passphrase:
            return {"status": "failure", "msg": "passphrase is incorrect"}
        del data['passphrase']  # del it for safety.
        event: Event = Event(type=EVENT_TV_SIGNAL, data=data)
        event_engine.put(event)
        return {"status": "success", "msg": ""}
    except Exception as error:
        return {"status": "error", "msg": str(error)}


def start_tv_server():
    app.run(host="127.0.0.1", port=port)

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

    main_engine: MainEngine = MainEngine(event_engine)
    main_engine.add_gateway(BinanceUsdtGateway)
    tv_engine: TVEngine = main_engine.add_app(TradingViewApp)
    main_engine.write_log("setup main engine")

    log_engine: LogEngine  = main_engine.get_engine("log")
    event_engine.register(EVENT_TV_LOG, log_engine.process_log_event)
    main_engine.write_log("register event listener")

    main_engine.connect(usdt_gateway_setting, "BINANCE_USDT") # BINANCE_SPOT, BINANCE_INVERSE
    main_engine.write_log("connect binance usdt gate way")

    sleep(10)

    ##  cta engine if you need.
    # cta_engine: CtaEngine = main_engine.add_app(CtaStrategyApp)
    # cta_engine.init_engine()
    # main_engine.write_log("set up cta engine")
    #
    # cta_engine.init_all_strategies()
    # sleep(60)   # Leave enough time to complete strategy initialization
    # main_engine.write_log("init cta strategies")
    #
    # cta_engine.start_all_strategies()
    # main_engine.write_log("start cta strategies")

    # tv strategies.
    tv_engine.init_engine()
    main_engine.write_log("set up tv engine")

    tv_engine.init_all_strategies()  # init all strategies.
    sleep(60) # # Leave enough time to complete strategy initialization
    main_engine.write_log("init tv strategies")


    tv_engine.start_all_strategies()
    main_engine.write_log("start all tv strategies")

    t1 = Thread(target=start_tv_server)
    t1.daemon = True
    t1.start()

    while True:
        sleep(10)

if __name__ == "__main__":
    run()
