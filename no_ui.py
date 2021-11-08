import sys
from time import sleep
from datetime import datetime, time
from logging import INFO

from jiamtrader.event import EventEngine
from jiamtrader.trader.setting import SETTINGS
from jiamtrader.trader.engine import MainEngine

from jiamtrader.gateway.binance import BinanceSpotGateway
from jiamtrader.gateway.binance import BinanceUsdtGateway
from jiamtrader.gateway.huobi import HuobiSpotGateway
from jiamtrader.app.cta_strategy import CtaStrategyApp
from jiamtrader.app.cta_strategy.base import EVENT_CTA_LOG


SETTINGS["log.active"] = True
SETTINGS["log.level"] = INFO
SETTINGS["log.console"] = True


binances_setting = {
        "key": "BH8dPZ2GNBqIWUwhGRmT9vGOq01SZlQ9BfDluqu5xcLAzyoXi8smWmPuGghOBAgi",
        "secret": "YkqX0EARMqBZW8H5lRWadHH6HJZCOykMGuglki4NwsMnrkbCbdVRoZ81eWgwNcR0",
        "会话数": 3,
        "服务器": "REAL",
        "合约模式": "正向",
        "代理地址": "",
        "代理端口": 0,
    }
binance_setting = {
        "key": "BH8dPZ2GNBqIWUwhGRmT9vGOq01SZlQ9BfDluqu5xcLAzyoXi8smWmPuGghOBAgi",
        "secret": "YkqX0EARMqBZW8H5lRWadHH6HJZCOykMGuglki4NwsMnrkbCbdVRoZ81eWgwNcR0",
        "会话数": 3,
        "服务器": "REAL",
        "合约模式": "正向",
        "代理地址": "",
        "代理端口": 0,
    }

def run():
    """
    Running in the child process.
    """
    SETTINGS["log.file"] = True

    event_engine = EventEngine()  # 初始化事件引擎
    main_engine = MainEngine(event_engine)  # 初始化主引擎
    main_engine.add_gateway(BinanceSpotGateway)  # 加载币安现货的网关
    main_engine.add_gateway(BinanceUsdtGateway)  # 加载币安现货的网关
    #main_engine.add_gateway(HuobiSpotGateway)
    cta_engine = main_engine.add_app(CtaStrategyApp) #添加cta策略的app
    # 添加cta引擎, 实际上就是初始化引擎。
    main_engine.write_log("主引擎创建成功")
    log_engine = main_engine.get_engine("log")
    event_engine.register(EVENT_CTA_LOG, log_engine.process_log_event)
    main_engine.write_log("注册日志事件监听")
    # 连接到交易所
    #main_engine.connect(binances_setting, "HUOBI_SPOT")
    main_engine.connect(binance_setting, "BINANCE_SPOT")
    main_engine.connect(binances_setting, "BINANCE_USDT")
    main_engine.write_log("连接BINANCESPOT接口")

    sleep(10) # 稍作等待策略启动完成。

    cta_engine.init_engine()
    # 启动引擎 --> 实际上是处理CTA策略要准备的事情，加载策略
    # 具体加载的策略来自于配置文件howtrader/cta_strategy_settings.json
    # 仓位信息来自于howtrader/cta_strategy_data.json
    main_engine.write_log("CTA策略初始化完成")

    # cta_engine.add_strategy() # 类似于我们在UI界面添加策略的操作类似
    #cta_engine.add_strategy('DemoChannelStrategy', {})
    #cta_engine.add_strategy('Class11SimpleStrategy', 'btcusdt_spot', 'btcusdt.BINANCE', {})
    #  在配置文件有这个配置信息就不需要手动添加。
    cta_engine.init_all_strategies() # 初始化所有的策略, 具体启动的哪些策略是来自于配置文件的
    # cta_engine.add_strategy() # 类似于我们在UI界面添加策略的操作类似
    # cta_engine.add_strategy('Class11SimpleStrategy', 'bnbusdt_spot', 'bnbusdt.BINANCE', {})
    #  在配置文件有这个配置信息就不需要手动添加。

    sleep(5)  # 预留足够的时间让策略去初始化.
    main_engine.write_log("CTA策略全部初始化")

    cta_engine.start_all_strategies()  # 开启所有的策略.
    main_engine.write_log("CTA策略全部启动")

    while True:
        sleep(10)

if __name__ == "__main__":
    run()
# shell nohub