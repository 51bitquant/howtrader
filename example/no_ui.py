import sys
from time import sleep
from datetime import datetime, time
from logging import INFO

from howtrader.event import EventEngine
from howtrader.trader.setting import SETTINGS
from howtrader.trader.engine import MainEngine

from howtrader.gateway.binances import BinancesGateway
from howtrader.app.cta_strategy import CtaStrategyApp
from howtrader.app.cta_strategy.base import EVENT_CTA_LOG


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


def run():
    """
    Running in the child process.
    """
    SETTINGS["log.file"] = True

    event_engine = EventEngine()
    main_engine = MainEngine(event_engine)
    main_engine.add_gateway(BinancesGateway)
    cta_engine = main_engine.add_app(CtaStrategyApp)
    main_engine.write_log("主引擎创建成功")

    log_engine = main_engine.get_engine("log")
    event_engine.register(EVENT_CTA_LOG, log_engine.process_log_event)
    main_engine.write_log("注册日志事件监听")

    main_engine.connect(binances_setting, "BINANCES")
    main_engine.write_log("连接BINANCES接口")

    sleep(10)

    cta_engine.init_engine()
    main_engine.write_log("CTA策略初始化完成")

    cta_engine.init_all_strategies()
    sleep(60)   # Leave enough time to complete strategy initialization
    main_engine.write_log("CTA策略全部初始化")

    cta_engine.start_all_strategies()
    main_engine.write_log("CTA策略全部启动")

    while True:
        sleep(10)

if __name__ == "__main__":
    run()
