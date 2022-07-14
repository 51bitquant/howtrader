## 如何在Window和MacOS上运行Howtrader

在运行前需要安装python环境，一般推荐安装anaconda, 然后创建一个python
3.9的版本。

假设你已经安装了anaconda, 你可以用 conda
来创建一个名为mytrader虚拟环境，当然名字随便取，是英文字母的就好。我们在命令行cmd(window)或者终端terminal(MacOS)中输入:

> conda create -n mytrader python==3.9

创建完成后，我们在cmd或终端中输入以下命令来激活mytrader虚拟环境(假设你也用mytrader作为虚拟环境的名称):
> conda activate mytrader

然后再终端中执行以下命令来安装howtrader:
> pip install git+https://github.com/51bitquant/howtrader.git

如果你想用TA-Lib来计算技术指标，可以安装下TA-Lib，具体安装步骤如下:

1. 打开该网址: [https://www.lfd.uci.edu/~gohlke/pythonlibs/#ta-lib](https://www.lfd.uci.edu/~gohlke/pythonlibs/#ta-lib)

2. 在网页中搜索ta-lib找到ta-lib的包:
   TA_Lib‑0.4.24‑cp39‑cp39‑win_amd64.whl,
   记得下载自己对应的python版本，TA_Lib-0.4.24, 是Ta-Lib版本为0.4.24，
   cp39就是python3.9版本， amd64就是64位的意思。

3. 切换到下载TA-Lib的文件目录，不然提示你找不到要安装的TA_Lib文件，最后通过命令行来安装：
   
> pip install TA_Lib‑0.4.24‑cp39‑cp39‑win_amd64.whl


安装howtrader和TA-Lib完成后，可以用创建个python项目，里面创建个main.py文件，复制和粘贴下面的代码：

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
        del data['passphrase'] # del it for safety.
        event:Event = Event(type=EVENT_TV_SIGNAL, data=data)
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

在运行前，记得设置该python项目的解析器为刚才创建的mytrader。然后运行main.py文件。

## 

## contact

如果你使用有问题，可以联系我，或者提issue.

Wechat: bitquant51

