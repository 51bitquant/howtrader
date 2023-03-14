# HowTrader

[中文文档](./README-CN.md)


What does Howtrader means? It means how to be a trader, especially a
quant trader.

HowTrader crypto quantitative trading framework, and was forked from
VNPY, so the core codes、functions and useages are pretty similar to
VNPY, but would be more easy to install and use. By the way, Howtrader
fixes some bugs, add more functions and strategies to framework. We
extend the TradingView signals and grid strategies to Howtrader and more
codes.


## Howtrader VS VNPY
1. some classes' definition are pretty different: for OrderData
   、TradeData、ContractData, we replace float with Decimal to meet the
   precision, theses classes are defined in howtrader.trader.object
   module.
  
2. on_order and on_trade update sequence are different: in VNPY, ，the
   on_order is always updated before the on_trade if the order was
   traded. And in the cta strategy, the self.pos(the position data) was
   calculated in the on_trade callback. So if we want to get the latest
   self.pos value, we may need to define a variable to calculate the
   latest position data. To solve this issue, we push the on_trade
   before the on_order callback. check out the code to find out the
   details: 
   ``` python
       
       def on_order(self, order: OrderData) -> None:
        """on order update"""
        order.update_time = generate_datetime(time.time() * 1000)
        last_order: OrderData = self.get_order(order.orderid)
        if not last_order:
            self.orders[order.orderid] = copy(order)
            super().on_order(copy(order))

        else:
            traded: Decimal = order.traded - last_order.traded
            if traded < 0: # filter the order is not in sequence
                return None

            if traded > 0:
                trade: TradeData = TradeData(
                    symbol=order.symbol,
                    exchange=order.exchange,
                    orderid=order.orderid,
                    direction=order.direction,
                    price=order.price,
                    volume=traded,
                    datetime=order.update_time,
                    gateway_name=self.gateway_name,
                )

                super().on_trade(trade)

            if traded == 0 and order.status == last_order.status:
                return None

            self.orders[order.orderid] = copy(order)
            super().on_order(copy(order))

    def get_order(self, orderid: str) -> OrderData:
        """get order by order id"""
        return self.orders.get(orderid, None)
   
   ```

3. gateways are different: solve issues like disconnecting from
   exchange, and reconnecting.

4. TradingView app to receive other 3rd party signals and algo trading
   strategies, checkout the module: howtrader.app.tradingview


## Installation

the framework depends on pandas, Numpy libraries, so we higly recommend
you to install [Anaconda](https://www.anaconda.com/products/distribution).

1. Install Anaconda, the Anaconda download website is
   [here](https://www.anaconda.com/products/distribution), remember to
   click "Add Conda to System Path" in the process of Anaconda
   Installation. If you forget to do so, you might need to unistall and
   reinstall the Anaconda, or just search how to add conda to you system
   path, if you encounter the problem of "not found conda command".
   
   If you already install the anaconda before, you can simply update
   your conda by runing the following command:
   > conda update conda
   
   > conda update anaconda

2. install git 

Install git is pretty simple, just download git from
[https://git-scm.com/downloads], then install it, remember to add git to
your system path. If you're using MacOX, git was integrated into the
system, so you may not need to install git.
3. create virtual env by conda
> conda create -n mytrader python==3.9

mytrader is the name of your virtual env, if you have the mytrader
virtual env before and the version is not 3.9, you can unistall it by
following command:

> conda remove -n mytrader --all

if you encounter an error, you may need to deactivate the mytrader by
the command:
> conda deactivate 

then remove it:
> conda remove -n mytrader --all

4. activate your virtual env:
> conda activate mytrader

5. install howtrader

run the command: 
> pip install git+https://github.com/51bitquant/howtrader.git

if you want to update to the latest version, use the command:
> > pip install git+https://github.com/51bitquant/howtrader.git -U 

if encounter the failure of installation TA-Lib, checkout the next step.

## Install TA-Lib

If you can't install the howtrader in Window system, the main reason may
be the TA-Lib, here we go in to the detail of installing TA-Lib:

1. open this url in your browser:[https://www.lfd.uci.edu/~gohlke/pythonlibs/#ta-lib](https://www.lfd.uci.edu/~gohlke/pythonlibs/#ta-lib)

2. search ta-lib in the website and download the TA-Lib.whl file: here
   we found the TA_Lib‑0.4.24‑cp39‑cp39‑win_amd64.whl in the website and
   we click download, for the TA_Lib-0.4.24, it means TA-Lib version is
   0.4.24， cp39 is the python version is 3.9， amd64 your system
   version is 64 bit, choose the right one and download it.

3. change your directory to your TA-Lib folder, and remember to activate
   your virtual env to mytrader(if you use mytrader as your vitrual
   env), then execute the following command: 
   
> pip install TA_Lib‑0.4.24‑cp39‑cp39‑win_amd64.whl

## how-to-use

create a python proejct, and create a main.py file,and set your
project's interpreter to the mytrader(the virtual env you just create
and config).

then copy and paste the following code to main.py and run it, and you
will see a howtrader folder beside the main.py, the howtrader folder
contains the configs data(like exchange api key)、 your strategy
settings and datas etc.

``` python


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


## how-to-crawl binance kline data

howdtrader use sliqte database as default, and also support mongodb and
mysql if you want to use it. If you want to use other database, you can
change the configuration in howtrader/vt_setting.json, here is the full
configuration key, you can just config the corresponding values.

```dict
{
    "font.family": "", # set font family if display error
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

    "order_update_interval": 600, # securing correct orders' status by synchronizing/updating orders through rest api
    "update_server_time_interval": 300,  # sync with server time
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
}


```

to crawl the Binance exchange kline data for backtesting, you just need
to create a crawl_data.py file, just in the main.py directory. copy and
paste the following codes:

```
"""
use the binance api to crawl data then save into the sqlite database.

"""

import pandas as pd
import time
from datetime import datetime
import requests
import pytz
from howtrader.trader.database import get_database, BaseDatabase

pd.set_option('expand_frame_repr', False)  #
from howtrader.trader.object import BarData, Interval, Exchange

BINANCE_SPOT_LIMIT = 1000
BINANCE_FUTURE_LIMIT = 1500

from howtrader.trader.constant import LOCAL_TZ

from threading import Thread
database: BaseDatabase = get_database()

def generate_datetime(timestamp: float) -> datetime:
    """
    :param timestamp:
    :return:
    """
    dt = datetime.fromtimestamp(timestamp / 1000)
    dt = LOCAL_TZ.localize(dt)
    return dt


def get_binance_data(symbol: str, exchange: str, start_time: str, end_time: str):
    """
    crawl binance exchange data
    :param symbol: BTCUSDT.
    :param exchange: spot、usdt_future, inverse_future.
    :param start_time: format :2020-1-1 or 2020-01-01 year-month-day
    :param end_time: format: 2020-1-1 or 2020-01-01 year-month-day
    :param gate_way the gateway name for binance is:BINANCE_SPOT, BINANCE_USDT, BINANCE_INVERSE
    :return:
    """

    api_url = ''
    save_symbol = symbol
    gateway = "BINANCE_USDT"
    if exchange == 'spot':
        print("spot")
        limit = BINANCE_SPOT_LIMIT
        save_symbol = symbol.lower()
        gateway = 'BINANCE_SPOT'
        api_url = f'https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1m&limit={limit}'

    elif exchange == 'usdt_future':
        print('usdt_future')
        limit = BINANCE_FUTURE_LIMIT
        gateway = "BINANCE_USDT"
        api_url = f'https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=1m&limit={limit}'

    elif exchange == 'inverse_future':
        print("inverse_future")
        limit = BINANCE_FUTURE_LIMIT
        gateway = "BINANCE_INVERSE"
        f'https://dapi.binance.com/dapi/v1/klines?symbol={symbol}&interval=1m&limit={limit}'

    else:
        raise Exception('the exchange name should be one of ：spot, usdt_future, inverse_future')

    start_time = int(datetime.strptime(start_time, '%Y-%m-%d').timestamp() * 1000)
    end_time = int(datetime.strptime(end_time, '%Y-%m-%d').timestamp() * 1000)

    while True:
        try:
            print(start_time)
            url = f'{api_url}&startTime={start_time}'
            print(url)
            datas = requests.get(url=url, timeout=10, proxies=proxies).json()

            """
            [
                [
                    1591258320000,      // open time
                    "9640.7",           // open price
                    "9642.4",           // highest price
                    "9640.6",           // lowest price
                    "9642.0",           // close price(latest price if the kline is not close)
                    "206",              // volume
                    1591258379999,      // close time
                    "2.13660389",       // turnover
                    48,                 // trade count 
                    "119",              // buy volume
                    "1.23424865",       //  buy turnover
                    "0"                 // ignore
                ]

            """

            buf = []

            for row in datas:
                bar: BarData = BarData(
                    symbol=save_symbol,
                    exchange=Exchange.BINANCE,
                    datetime=generate_datetime(row[0]),
                    interval=Interval.MINUTE,
                    volume=float(row[5]),
                    turnover=float(row[7]),
                    open_price=float(row[1]),
                    high_price=float(row[2]),
                    low_price=float(row[3]),
                    close_price=float(row[4]),
                    gateway_name=gateway
                )
                buf.append(bar)

            database.save_bar_data(buf)

            # exit the loop, if close time is greater than the current time
            if (datas[-1][0] > end_time) or datas[-1][6] >= (int(time.time() * 1000) - 60 * 1000):
                break

            start_time = datas[-1][0]

        except Exception as error:
            print(error)
            time.sleep(10)


def download_spot(symbol):
    """
    download binance spot data, config your start date and end date(format: year-month-day)
    :return:
    """
    t1 = Thread(target=get_binance_data, args=(symbol, 'spot', "2018-1-1", "2018-6-1"))
    t2 = Thread(target=get_binance_data, args=(symbol, 'spot', "2018-6-1", "2018-12-1"))

    t3 = Thread(target=get_binance_data, args=(symbol, 'spot', "2018-12-1", "2019-6-1"))
    t4 = Thread(target=get_binance_data, args=(symbol, 'spot', "2019-6-1", "2019-12-1"))

    t5 = Thread(target=get_binance_data, args=(symbol, 'spot', "2019-12-1", "2020-6-1"))
    t6 = Thread(target=get_binance_data, args=(symbol, 'spot', "2020-6-1", "2020-12-1"))

    t7 = Thread(target=get_binance_data, args=(symbol, 'spot', "2020-12-1", "2021-6-1"))
    t8 = Thread(target=get_binance_data, args=(symbol, 'spot', "2021-6-1", "2021-12-1"))
    t9 = Thread(target=get_binance_data, args=(symbol, 'spot', "2021-12-1", "2022-6-28"))

    t1.start()
    t2.start()
    t3.start()
    t4.start()
    t5.start()
    t6.start()
    t7.start()
    t8.start()
    t9.start()

    t1.join()
    t2.join()
    t3.join()
    t4.join()
    t5.join()
    t6.join()
    t7.join()
    t8.join()
    t9.join()


def download_future(symbol):
    """
    download binance future data, config your start date and end date(format: year-month-day)
    :return:

    """

    t1 = Thread(target=get_binance_data, args=(symbol, 'usdt_future', "2020-1-1", "2020-6-1"))
    t2 = Thread(target=get_binance_data, args=(symbol, 'usdt_future', "2020-6-1", "2020-12-1"))
    t3 = Thread(target=get_binance_data, args=(symbol, 'usdt_future', "2020-12-1", "2021-6-1"))
    t4 = Thread(target=get_binance_data, args=(symbol, 'usdt_future', "2021-6-1", "2021-12-1"))
    t5 = Thread(target=get_binance_data, args=(symbol, 'usdt_future', "2021-12-1", "2022-6-28"))

    t1.start()
    t2.start()
    t3.start()
    t4.start()
    t5.start()

    t1.join()
    t2.join()
    t3.join()
    t4.join()
    t5.join()



if __name__ == '__main__':

    """
    read the code before run it. the software crawl the binance data then save into the sqlite database.
    you may need to change the start date and end date.
    """

    # proxy_host , if you can directly connect to the binance exchange, then set it to None or empty string ""，如果没有你就设置为 None 或者空的字符串 "",
    # you can use the command  ping api.binance.com to check whether your network work well: 你可以在终端运行 ping api.binance.com 查看你的网络是否正常。
    proxy_host = "127.0.0.1"  # set it to your proxy_host 如果没有就设置为"", 如果有就设置为你的代理主机如：127.0.0.1
    proxy_port = 1087  # set it to your proxy_port  设置你的代理端口号如: 1087, 没有你修改为0,但是要保证你能访问api.binance.com这个主机。

    proxies = None
    if proxy_host and proxy_port:
        proxy = f'http://{proxy_host}:{proxy_port}'
        proxies = {'http': proxy, 'https': proxy}

    download_future(symbol="BTCUSDT")  # crawl usdt_future data. 下载合约的数据

    download_spot(symbol="BTCUSDT") # crawl binance spot data.




```

if you want to change start date or end date, you check out the codes.
And the data will be stored in howtrader/database.db file.


## backtesting

for backtesting, here is the example. vt_symbol format like
BTCUSDT.BINANCE, the first part is symbol, and other part is exchange
name. Howtrader uses lower case for spot market, and upper case for
future market.

```
from howtrader.app.cta_strategy.backtesting import BacktestingEngine, OptimizationSetting
from howtrader.trader.object import Interval
from datetime import datetime
from strategies.atr_rsi_strategy import AtrRsiStrategy  # import your strategy.

engine = BacktestingEngine()
engine.set_parameters(
    vt_symbol="BTCUSDT.BINANCE",
    interval=Interval.MINUTE,
    start=datetime(2020, 1, 1),
    end=datetime(2020, 5, 1),
    rate=4/10000,
    slippage=0,
    size=1,
    pricetick=0.01,
    capital=1000000,
)

engine.add_strategy(AtrRsiStrategy, {})


engine.load_data()
engine.run_backtesting()
df = engine.calculate_result()
engine.calculate_statistics()
engine.show_chart()

setting = OptimizationSetting()
setting.set_target("sharpe_ratio")
setting.add_parameter("atr_length", 3, 39, 1)
setting.add_parameter("atr_ma_length", 10, 30, 1)

result = engine.run_ga_optimization(setting)  # optimization result
print(result) # you can print the result.


```

for more example codes, checkout the examples:
[https://github.com/51bitquant/howtrader/tree/main/examples](https://github.com/51bitquant/howtrader/tree/main/examples)

## material codes:

you can check out my github profile: [https:github.com/51bitquant](https:github.com/51bitquant)

howtrader course_codes: [https://github.com/51bitquant/course_codes](https://github.com/51bitquant/course_codes)

## Contact
Twitter: 51bitquant.eth

discord-community:
[https://discord.gg/fgySfwG9eJ](https://discord.gg/fgySfwG9eJ)

Binance Invite Link: 
[https://www.binancezh.pro/cn/futures/ref/51bitquant](https://www.binancezh.pro/cn/futures/ref/51bitquant)

 
 
 
 

 

 
 
 
 
