## 如何在linux上运行howtrader

linux系统上，比如ubuntu等，一般都没有界面，这时候就没法用UI的方式运行了。解决办法就是用脚本的方式来运行。

用脚本的方式，可以参考以下代码， 这里以使用CTA策略app为讲解，创建一个main.py文件，然后复制粘贴以下代码：

```
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

```

这里要说明下:

```
usdt_gateway_setting = {
        "key": "",
        "secret": "",
        "proxy_host": "",
        "proxy_port": 0,
    }
```

这个是你连接交易所接口的apikey
配置信息。在启动前，你要把你的cta策略的配置信息放在howtrader文件夹，该文件夹在main.py方便属于同一个文件层级，如果你没有，可以手动创建一个:
> mkdir howtrader

你的cta策略配置文件，如果不知道如何创建，可以在window或者macOS通过UI的方式添加策略，然后再howtrader文件夹找到cta_strategy_setting.json文件，文件里面的内容就是策略的配置信息，样例如下：

```json
{
    "MATICUSDT": {
        "class_name": "FutureProfitGridStrategy",
        "vt_symbol": "MATICUSDT.BINANCE",
        "setting": {
            "class_name": "FutureProfitGridStrategy",
            "grid_step": 0.0005388,
            "profit_step": 0.0005388,
            "trading_size": 20.0,
            "max_pos": 28.0,
            "profit_orders_counts": 28,
            "trailing_stop_multiplier": 29.0,
            "stop_minutes": 360.0
        }
    }
}

```

最左边的key MATCUSDT是策略的名称，后面的{}策略相应配置信息，
class_name是该策略用的是哪个类，vt_symbol是交易对信息，.后面是交易所的名称，setting是策略中的参数。

另外说明的一点是，如果你之前的策略是用vnpy开发的，那么你要把从vnpy导入换成howtrader,
下单方法buy,sell, short, cover,
中的价格和数量，要用Decimal的类型，这主要是为了满足精度问题，不然类似SHIBUSDT的交易对没法交易。


## contact

如果你使用有问题，可以联系我，或者提issue.

Wechat: bitquant51

