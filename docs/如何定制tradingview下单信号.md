
# 如何定制tradingview下单信号

howtrader 的模块 tradingview，默认是只有 long/short/exit 三个信号，
long是代表做多，如果是有空单，会先平空单，再继续下多单，如果没有仓位，就下多单。
short是代表做空，如果有多单，会先平多单，然后下空单，如果没有多单，就下空单。exit是代表出场，如果没有仓位那么，就不处理，
如果是有多单，就值平多单，如果有空单就只平空单。


我们来看一个简单的tradingview中的pine语言的例子：

```pine

if longCondition
    strategy.entry('L', strategy.long, comment='long')
if shortCongdition
    strategy.entry('S', strategy.short, comment='short')

per(pcnt) =>
    strategy.position_size != 0 ? math.round(pcnt / 100 * strategy.position_avg_price / syminfo.mintick) : float(na)

stoploss = input.float(title=' stop loss', defval=4, minval=0.01)

los = per(stoploss)

q = input.int(title=' qty percent', defval=100, minval=1)

tp = input.float(title=' Take profit', defval=1.6, minval=0.01)
tpMaMacd = input.float(title=' Take profit', defval=2.6, minval=0.01)


strategy.exit('tp', qty_percent=q, profit=per(tp), loss=los, comment="exit")

```

针对上面的策略，可以使用howtrader/app/tradingview/strategies/BestLimitTVStrategy.py中的策略代码。我们可以看下代码。



如果你的策略代码并不是这样简单的信号，可能有加仓，减仓等各种操作，比如下面的这个pine代码。

```pine

if long
    strategy.entry("l_1", strategy.long, comment="l_1")  //有多头信号的时候， 同时开两个多头仓位， 数量为指定，你可以在howtrader中设置，或者在tradingview中设置，如果不设置就通过资金来计算得到的。
    strategy.entry("l_2", strategy.long, comment="l_2")  

if short
    strategy.entry("s_1", strategy.short, comment="s_1") // //有空头信号的时候， 同时开两个空头仓位
    strategy.entry("s_2", strategy.short, comment="s_2")



strategy.exit("tp-1_l", "l_1", profit = (abs((last_open_longCondition * (1+(tp/100)))-last_open_longCondition)/syminfo.mintick), loss = (abs((last_open_longCondition * (1-(sl/100)))-last_open_longCondition)/syminfo.mintick), comment="tp-1_l")
strategy.exit("tp-2_l", "l_2", profit = (abs((last_open_longCondition * (1+(tp2/100)))-last_open_longCondition)/syminfo.mintick), loss = (abs((last_open_longCondition * (1-(sl/100)))-last_open_longCondition)/syminfo.mintick), comment="tp-2_l")

strategy.exit("tp-1_s", "s_1", profit = (abs((last_open_shortCondition * (1-(tp/100)))-last_open_shortCondition)/syminfo.mintick), loss = (abs((last_open_shortCondition * (1+(sl/100)))-last_open_shortCondition)/syminfo.mintick), comment="tp-1_s")
strategy.exit("tp-2_s", "s_2", profit = (abs((last_open_shortCondition * (1-(tp2/100)))-last_open_shortCondition)/syminfo.mintick),loss = (abs((last_open_shortCondition * (1+(sl/100)))-last_open_shortCondition)/syminfo.mintick ), comment="tp-2_s")


if ATR_L_STOP
    strategy.close_all(comment="exit")  // 就是止损，全部出场.

if ATR_S_STOP
    strategy.close_all(comment="exit")  // 就是止损，全部出场.
    
```

这里给大家实现两种方案，大家可以参考，然后定制自己的策略信号。


直接市价单成交的代码：

```python
from howtrader.app.tradingview.template import TVTemplate
from howtrader.app.tradingview.engine import TVEngine
from howtrader.trader.object import TickData, TradeData, OrderData, ContractData, Product
from typing import Optional
from howtrader.event import Event, EVENT_TIMER
from decimal import Decimal
from howtrader.trader.utility import round_to
from random import uniform
from howtrader.trader.object import Direction


class MyTVSimpleStrategy(TVTemplate):
    """自定义信号， 通过市价单去实现.

    self-customized signals and place order in market order
    """

    author: str = "51bitquant"

    # the order volume you want to trade, if you trade BTCUSDT, the volume is BTC amount, if you set zero, will use from TV or other signal.
    # 订单的数量，如果你是交易BTCUSDT, 这个数量是BTC的数量, 如果设置为零，那么交易使用会使用来自tradingview或则其他第三方的信号
    order_volume: float = 0.0

    # the price slippage for taker order, 0.5 means 0.5%
    max_slippage_percent: float = 0.5  # 0.5%

    parameters: list = ["order_volume", "max_slippage_percent"]

    def __init__(
            self,
            tv_engine: TVEngine,
            strategy_name: str,
            tv_id: str,
            vt_symbol: str,
            setting: dict,
    ) -> None:
        """"""
        super().__init__(tv_engine, strategy_name, tv_id, vt_symbol, setting)
        self.orders: list = []

        self.target_volume: Decimal = Decimal("0")  # trade volume target 需要交易的数量.
        self.traded_volume: Decimal = Decimal("0")  # have already traded volume 已经交易的数量
        self.direction: Optional[Direction] = None  #

        self.contract: Optional[ContractData] = tv_engine.main_engine.get_contract(vt_symbol)
        self.timer_count = 0
        self.signals = []  # store the signals.

    def on_init(self) -> None:
        """
        Callback when strategy is inited.
        """
        self.write_log("strategy inited")

    def on_start(self) -> None:
        """
        Callback when strategy is started.
        """
        self.write_log("strategy started")

    def on_stop(self):
        """
        Callback when strategy is stopped.
        """
        self.write_log("strategy stop")

    def on_tick(self, tick: TickData):
        """"""
        if not tick or tick.bid_price_1 <= 0 or not self.contract:
            return None

        self.timer_count += 1
        if self.timer_count < 3:
            return None

        self.timer_count = 0

        if len(self.orders) > 0:
            self.cancel_all()
            return None

        volume = self.target_volume - self.traded_volume

        if volume > self.contract.min_volume and volume * tick.bid_price_1 >= 10:  # 下单的价值要大于10USDT

            if self.direction == Direction.LONG:
                price = Decimal(tick.ask_price_1 * (1 + self.max_slippage_percent / 100))
                price = round_to(price, self.contract.pricetick)
                orderids = self.buy(price, volume)
                self.orders.extend(orderids)

            elif self.direction == Direction.SHORT:
                price = Decimal(tick.bid_price_1 * (1 - self.max_slippage_percent / 100))
                price = round_to(price, self.contract.pricetick)

                if self.contract.product == Product.FUTURES:  # for futures market
                    orderids = self.short(price, volume)
                    self.orders.extend(orderids)

                elif self.contract.product == Product.SPOT:  # for spot market
                    orderids = self.sell(price, volume)
                    self.orders.extend(orderids)

        else:
            self.traded_volume = Decimal("0")
            self.target_volume = Decimal("0")
            self.direction = None

            if len(self.signals) > 0:
                signal = self.signals.pop(0)
                self.resolve_signal(signal)

    def resolve_signal(self, signal: dict) -> None:
        action = signal.get('action', None)
        if action is None:
            self.write_log(f"current action is : {action}")
            return None

        action = action.lower()  # 把信号转成小写了。
        if self.contract is None:
            self.write_log('contract is None, did you connect to the exchange?')
            return None

        if self.order_volume > 0:
            v = str(self.order_volume)
            volume = round_to(Decimal(v), self.contract.min_volume)
        else:
            v = signal.get('volume', None)
            if v is None:
                self.write_log("missing volume from signal for placing order volume.")
                return None

            volume = round_to(Decimal(str(v)), self.contract.min_volume)

        volume = abs(volume)
        self.traded_volume = Decimal("0")

        if action == 'l_1':
            if self.pos < 0:
                self.target_volume = volume + abs(self.pos)
            else:
                self.target_volume = volume
            self.direction = Direction.LONG

        elif action == 'l_2':
            self.target_volume = volume
            self.direction = Direction.LONG

        elif action == 's_1':
            if self.pos > 0:
                self.target_volume = volume + self.pos
            else:
                self.target_volume = volume
            self.direction = Direction.SHORT

        elif action == 's_2':
            self.target_volume = volume
            self.direction = Direction.SHORT

        elif action == 'tp_1_l':

            if self.pos > 0:
                if self.pos >= volume:
                    self.target_volume = volume
                    self.direction = Direction.SHORT
                else:
                    self.target_volume = self.pos
                    self.direction = Direction.SHORT

        elif action == 'tp_2_l':
            if self.pos > 0:
                self.target_volume = self.pos
                self.direction = Direction.SHORT

        elif action == 'tp_1_s':
            if self.pos < 0:
                if abs(self.pos) >= volume:
                    self.target_volume = volume
                    self.direction = Direction.LONG

                else:
                    self.target_volume = abs(self.pos)
                    self.direction = Direction.LONG

        elif action == 'tp_2_s':
            if self.pos < 0:
                self.target_volume = abs(self.pos)
                self.direction = Direction.LONG

        elif action == 'exit':
            if abs(self.pos) < self.contract.min_volume:
                self.write_log(f"ignore exit signal, current pos: {self.pos}")
                return None

            self.target_volume = abs(self.pos)
            if self.pos > 0:
                self.direction = Direction.SHORT
            else:
                self.direction = Direction.LONG
        else:
            pass
            # extend your signal here.

    def on_signal(self, signal: dict) -> None:
        """
        the signal contains
        """
        self.write_log(f"received signal: {signal}")
        self.signals.append(signal)

    def on_order(self, order: OrderData) -> None:
        """
        Callback of new order data update.
        """
        if not order.is_active():
            try:
                # if order is not active, then remove it from self.orders
                self.orders.remove(order.vt_orderid)

            except Exception:
                pass

    def on_trade(self, trade: TradeData):
        """"""
        self.traded_volume += trade.volume

        if self.traded_volume >= self.target_volume:
            self.write_log(
                f"signal trading finished: traded_volume：{self.traded_volume}，target_volume：{self.target_volume}")
            self.traded_volume = Decimal("0")
            self.target_volume = Decimal("0")
            self.direction = None



```


最优限价单策略代码：


```python
from howtrader.app.tradingview.template import TVTemplate
from howtrader.app.tradingview.engine import TVEngine
from howtrader.trader.object import TickData, TradeData, OrderData, ContractData, Product
from typing import Optional
from howtrader.event import Event, EVENT_TIMER
from decimal import Decimal
from howtrader.trader.utility import round_to
from random import uniform
from howtrader.trader.object import Direction

class MyTVBestLimitStrategy(TVTemplate):
    """Place Best Limit order for TV strategy for multi signals

    split a large order to small order, and use best limit price to place order automatically until it filled. For more detail, read the codes below.

    使用最优价格(买一/卖一)去下限价单，把大单拆成小单，不断去循环下单，直到下单完成。
    """

    author: str = "51bitquant"

    # the order volume you want to trade, if you trade BTCUSDT, the volume is BTC amount, if you set zero, will use from TV or other signal.
    # 订单的数量，如果你是交易BTCUSDT, 这个数量是BTC的数量, 如果设置为零，那么交易使用会使用来自tradingview或则其他第三方的信号
    order_volume: float = 0.0

    # place max order volume per order 单次最大的下单数量.
    min_volume_per_order: float = 0.0
    max_volume_per_order: float = 0.0

    parameters: list = ["order_volume","min_volume_per_order", "max_volume_per_order"]

    def __init__(
            self,
            tv_engine: TVEngine,
            strategy_name: str,
            tv_id:str,
            vt_symbol: str,
            setting: dict,
    ) -> None:
        """"""
        super().__init__(tv_engine, strategy_name, tv_id, vt_symbol, setting)
        self.last_tick: Optional[TickData] = None
        self.orders: list = []
        self.order_price: float = 0

        self.target_volume: Decimal = Decimal("0") # trade volume target 需要交易的数量.
        self.traded_volume: Decimal = Decimal("0") # have already traded volume 已经交易的数量
        self.direction: Optional[Direction] = None #

        self.contract: Optional[ContractData] = tv_engine.main_engine.get_contract(vt_symbol)

        self.signals = []  # store the signals.

    def on_init(self) -> None:
        """
        Callback when strategy is inited.
        """
        self.write_log("strategy inited")

    def on_start(self) -> None:
        """
        Callback when strategy is started.
        """
        self.write_log("strategy started")

    def on_stop(self):
        """
        Callback when strategy is stopped.
        """
        self.write_log("strategy stop")

    def on_tick(self, tick: TickData):
        """"""
        self.last_tick = tick

        if self.direction == Direction.LONG:
            if len(self.orders) == 0:
                self.buy_best_limit()
            elif self.order_price != self.last_tick.bid_price_1:
                self.cancel_all()
        elif self.direction == Direction.SHORT:
            if len(self.orders) == 0:
                self.sell_best_limit()
            elif self.order_price != self.last_tick.ask_price_1:
                self.cancel_all()
        else:
            if len(self.signals) > 0:
                signal = self.signals.pop(0)
                self.resolve_signal(signal)

    def resolve_signal(self, signal: dict) -> None:
        action = signal.get('action', None)
        if action is None:
            self.write_log(f"current action is : {action}")
            return None

        action = action.lower()  # 把信号转成小写了。
        if self.contract is None:
            self.write_log('contract is None, did you connect to the exchange?')
            return None

        if self.order_volume > 0:
            v = str(self.order_volume)
            volume = round_to(Decimal(v), self.contract.min_volume)
        else:
            v = signal.get('volume', None)
            if v is None:
                self.write_log("missing volume from signal for placing order volume.")
                return None

            volume = round_to(Decimal(str(v)), self.contract.min_volume)

        volume = abs(volume)
        self.traded_volume = Decimal("0")

        if action == 'l_1':
            if self.pos < 0:
                self.target_volume = volume + abs(self.pos)
            else:
                self.target_volume = volume
            self.direction = Direction.LONG

        elif action == 'l_2':
            self.target_volume = volume
            self.direction = Direction.LONG

        elif action == 's_1':
            if self.pos > 0:
                self.target_volume = volume + self.pos
            else:
                self.target_volume = volume
            self.direction = Direction.SHORT

        elif action == 's_2':
            self.target_volume = volume
            self.direction = Direction.SHORT

        elif action == 'tp_1_l':

            if self.pos > 0:
                if self.pos >= volume:
                    self.target_volume = volume
                    self.direction = Direction.SHORT
                else:
                    self.target_volume = self.pos
                    self.direction = Direction.SHORT

        elif action == 'tp_2_l':
            if self.pos > 0:
                self.target_volume = self.pos
                self.direction = Direction.SHORT

        elif action == 'tp_1_s':
            if self.pos < 0:
                if abs(self.pos) >= volume:
                    self.target_volume = volume
                    self.direction = Direction.LONG

                else:
                    self.target_volume = abs(self.pos)
                    self.direction = Direction.LONG

        elif action == 'tp_2_s':
            if self.pos < 0:
                self.target_volume = abs(self.pos)
                self.direction = Direction.LONG

        elif action == 'exit':
            if abs(self.pos) < self.contract.min_volume:
                self.write_log(f"ignore exit signal, current pos: {self.pos}")
                return None

            self.target_volume = abs(self.pos)
            if self.pos > 0:
                self.direction = Direction.SHORT
            else:
                self.direction = Direction.LONG
        else:
            pass
            # extend your signal here.

    def on_signal(self, signal: dict) -> None:
        """
        the signal contains
        """
        self.write_log(f"received signal: {signal}")
        self.signals.append(signal)

    def on_order(self, order: OrderData) -> None:
        """
        Callback of new order data update.
        """
        if not order.is_active():
            try:
            # if order is not active, then remove it from self.orders
                self.orders.remove(order.vt_orderid)
                self.order_price = 0
            except Exception:
                pass

    def on_trade(self, trade: TradeData):
        """"""
        self.traded_volume += trade.volume

        if self.traded_volume >= self.target_volume:
            self.write_log(f"algo trading finished: traded_volume：{self.traded_volume}，target_volume：{self.target_volume}")
            self.traded_volume = Decimal("0")
            self.target_volume = Decimal("0")
            self.direction = None

    def buy_best_limit(self) -> None:
        """"""
        volume_left = self.target_volume - self.traded_volume
        rand_volume = self.generate_rand_volume()
        order_volume = min(rand_volume, volume_left)
        order_volume = round_to(order_volume, self.contract.min_volume)
        if order_volume < self.contract.min_volume or order_volume < 0:
            return None

        self.order_price = self.last_tick.bid_price_1
        orderids = self.buy(Decimal(str(self.order_price)), order_volume)
        self.orders.extend(orderids)

    def sell_best_limit(self) -> None:
        """"""
        volume_left = self.target_volume - self.traded_volume
        rand_volume = self.generate_rand_volume()
        order_volume = min(rand_volume, volume_left)
        order_volume = round_to(order_volume, self.contract.min_volume)
        if order_volume < self.contract.min_volume or order_volume < 0:
            return None

        self.order_price = self.last_tick.ask_price_1
        if self.contract.product == Product.SPOT:
            orderids = self.sell(Decimal(str(self.order_price)), Decimal(order_volume))
            self.orders.extend(orderids)
        elif self.contract.product == Product.FUTURES:
            orderids = self.short(Decimal(str(self.order_price)), Decimal(order_volume))
            self.orders.extend(orderids)

    def generate_rand_volume(self):
        """"""
        rand_volume = uniform(self.min_volume_per_order, self.max_volume_per_order)
        return Decimal(str(rand_volume))


```

