# howtrader项目下面的配置文件讲解

运行main_window.py文件，该文件代码如下：

```
from howtrader.event import EventEngine, Event
from howtrader.trader.event import EVENT_TV_SIGNAL
from howtrader.trader.engine import MainEngine
from howtrader.trader.ui import MainWindow, create_qapp
from howtrader.trader.setting import SETTINGS
from howtrader.gateway.binance import BinanceUsdtGateway, BinanceSpotGateway, BinanceInverseGateway

from howtrader.app.cta_strategy import CtaStrategyApp
# from howtrader.app.data_manager import DataManagerApp
# from howtrader.app.data_recorder import DataRecorderApp
# from howtrader.app.algo_trading import AlgoTradingApp
# from howtrader.app.risk_manager import RiskManagerApp
# from howtrader.app.spread_trading import SpreadTradingApp
from howtrader.app.tradingview import TradingViewApp
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


def main():
    """"""
    qapp = create_qapp()
    main_engine = MainEngine(event_engine)

    main_engine.add_gateway(BinanceSpotGateway)
    main_engine.add_gateway(BinanceUsdtGateway)
    main_engine.add_gateway(BinanceInverseGateway)
    main_engine.add_app(CtaStrategyApp)
    main_engine.add_app(TradingViewApp)

    # if you don't use
    # main_engine.add_app(DataManagerApp)
    # main_engine.add_app(AlgoTradingApp)
    # main_engine.add_app(DataRecorderApp)
    # main_engine.add_app(RiskManagerApp)
    # main_engine.add_app(SpreadTradingApp)

    main_window = MainWindow(main_engine, event_engine)
    main_window.showMaximized()

    t1 = Thread(target=start_tv_server)
    t1.daemon = True
    t1.start()

    qapp.exec()


if __name__ == "__main__":

    main()


```

它会在项目下面创建一个howtrader的文件夹，该文件夹里面会包含一些配置文件和日志文件等信息。这里展开讲解一下。

- vt_setting.json: 项目的配置文件，完整的配置信息如下: 

```
"font.family": "",
    "font.size": 12,

    "log.active": True,
    "log.level": CRITICAL,
    "log.console": True,
    "log.file": True,

    "email.server": "smtp.qq.com",
    "email.port": 465,
    "email.username": "",
    "email.password": "",
    "email.sender": "",
    "email.receiver": "",

    "update_interval": 600,
    "passphrase": "howtrader",  # tv passphrase
    "port": 9999, # tv server port

    "datafeed.name": "",
    "datafeed.username": "",
    "datafeed.password": "",

    "database.timezone": get_localzone_name(),
    "database.name": "sqlite",
    "database.database": "database.db",
    "database.host": "",
    "database.port": 0,
    "database.user": "",
    "database.password": ""

```
你可以修改其中的任何一项信息，修改后，会修改项目中的相应配置，具体原始配置是在howtrader/trader/setting.py文件里面。

- database.db 文件: 是数据库文件，你爬取的数据会存放在该文件下面。

- connect_binance_spot.json: 连接币安现货的api配置

- connect_binance_usdt.json: 连接币安u本位合约的api配置

- connect_binance_inverse.json: 连接币安币本位合约的api配置

- tv_strategy_setting.json: tradingview或者第三方信号的策略配置信息

- tv_strategy_data.json:
  tradingview或者第三方信号的仓位等缓存信息，如果你交易所的仓位信息清空了，记得把该文件删除，不然仓位信息是对应不上的。
  
- cta_strategy_setting.json: CTA策略的配置信息

- cta_strategy_data.json:
  CTA策略的仓位等缓存信息，如果你清仓了，或者修改了参数啥的，可以把该文件删除，不然仓位数据等信息对应不上。
  
 
  

