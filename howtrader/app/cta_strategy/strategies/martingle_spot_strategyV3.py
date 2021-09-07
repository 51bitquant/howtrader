from howtrader.app.cta_strategy import (
    CtaTemplate,
    StopOrder,
    TickData,
    BarData,
    TradeData,
    OrderData
)

from howtrader.app.cta_strategy.engine import CtaEngine
from howtrader.trader.event import EVENT_TIMER
from howtrader.event import Event
from howtrader.trader.object import Status, Direction, Interval, ContractData, AccountData
from howtrader.app.cta_strategy import BarGenerator

from typing import Optional, Union, Tuple
import numpy as np
import talib
from howtrader.trader.event import EVENT_CONTRACT, EVENT_ACCOUNT


class MyArrayManager(object):
    """
    For:
    1. time series container of bar data
    2. calculating technical indicator value
    """

    def __init__(self, size: int = 100):
        """Constructor"""
        self.count: int = 0
        self.size: int = size
        self.inited: bool = False

        self.open_array: np.ndarray = np.zeros(size)
        self.high_array: np.ndarray = np.zeros(size)
        self.low_array: np.ndarray = np.zeros(size)
        self.close_array: np.ndarray = np.zeros(size)
        self.volume_array: np.ndarray = np.zeros(size)
        self.open_interest_array: np.ndarray = np.zeros(size)

    def update_bar(self, bar: BarData) -> None:
        """
        Update new bar data into array manager.
        """
        self.count += 1
        if not self.inited and self.count >= self.size:
            self.inited = True

        self.open_array[:-1] = self.open_array[1:]
        self.high_array[:-1] = self.high_array[1:]
        self.low_array[:-1] = self.low_array[1:]
        self.close_array[:-1] = self.close_array[1:]
        self.volume_array[:-1] = self.volume_array[1:]
        self.open_interest_array[:-1] = self.open_interest_array[1:]

        self.open_array[-1] = bar.open_price
        self.high_array[-1] = bar.high_price
        self.low_array[-1] = bar.low_price
        self.close_array[-1] = bar.close_price
        self.volume_array[-1] = bar.volume
        self.open_interest_array[-1] = bar.open_interest

    @property
    def open(self) -> np.ndarray:
        """
        Get open price time series.
        """
        return self.open_array

    @property
    def high(self) -> np.ndarray:
        """
        Get high price time series.
        """
        return self.high_array

    @property
    def low(self) -> np.ndarray:
        """
        Get low price time series.
        """
        return self.low_array

    @property
    def close(self) -> np.ndarray:
        """
        Get close price time series.
        """
        return self.close_array

    @property
    def volume(self) -> np.ndarray:
        """
        Get trading volume time series.
        """
        return self.volume_array

    @property
    def open_interest(self) -> np.ndarray:
        """
        Get trading volume time series.
        """
        return self.open_interest_array

    def sma(self, n: int, array: bool = False) -> Union[float, np.ndarray]:
        """
        Simple moving average.
        """
        result = talib.SMA(self.close, n)
        if array:
            return result
        return result[-1]

    def ema(self, n: int, array: bool = False) -> Union[float, np.ndarray]:
        """
        Exponential moving average.
        """
        result = talib.EMA(self.close, n)
        if array:
            return result
        return result[-1]

    def kama(self, n: int, array: bool = False) -> Union[float, np.ndarray]:
        """
        KAMA.
        """
        result = talib.KAMA(self.close, n)
        if array:
            return result
        return result[-1]

    def wma(self, n: int, array: bool = False) -> Union[float, np.ndarray]:
        """
        WMA.
        """
        result = talib.WMA(self.close, n)
        if array:
            return result
        return result[-1]

    def apo(
            self,
            fast_period: int,
            slow_period: int,
            matype: int = 0,
            array: bool = False
    ) -> Union[float, np.ndarray]:
        """
        APO.
        """
        result = talib.APO(self.close, fast_period, slow_period, matype)
        if array:
            return result
        return result[-1]

    def cmo(self, n: int, array: bool = False) -> Union[float, np.ndarray]:
        """
        CMO.
        """
        result = talib.CMO(self.close, n)
        if array:
            return result
        return result[-1]

    def mom(self, n: int, array: bool = False) -> Union[float, np.ndarray]:
        """
        MOM.
        """
        result = talib.MOM(self.close, n)
        if array:
            return result
        return result[-1]

    def ppo(
            self,
            fast_period: int,
            slow_period: int,
            matype: int = 0,
            array: bool = False
    ) -> Union[float, np.ndarray]:
        """
        PPO.
        """
        result = talib.PPO(self.close, fast_period, slow_period, matype)
        if array:
            return result
        return result[-1]

    def roc(self, n: int, array: bool = False) -> Union[float, np.ndarray]:
        """
        ROC.
        """
        result = talib.ROC(self.close, n)
        if array:
            return result
        return result[-1]

    def rocr(self, n: int, array: bool = False) -> Union[float, np.ndarray]:
        """
        ROCR.
        """
        result = talib.ROCR(self.close, n)
        if array:
            return result
        return result[-1]

    def rocp(self, n: int, array: bool = False) -> Union[float, np.ndarray]:
        """
        ROCP.
        """
        result = talib.ROCP(self.close, n)
        if array:
            return result
        return result[-1]

    def rocr_100(self, n: int, array: bool = False) -> Union[float, np.ndarray]:
        """
        ROCR100.
        """
        result = talib.ROCR100(self.close, n)
        if array:
            return result
        return result[-1]

    def trix(self, n: int, array: bool = False) -> Union[float, np.ndarray]:
        """
        TRIX.
        """
        result = talib.TRIX(self.close, n)
        if array:
            return result
        return result[-1]

    def std(self, n: int, nbdev: int = 1, array: bool = False) -> Union[float, np.ndarray]:
        """
        Standard deviation.
        """
        result = talib.STDDEV(self.close, n, nbdev)
        if array:
            return result
        return result[-1]

    def obv(self, array: bool = False) -> Union[float, np.ndarray]:
        """
        OBV.
        """
        result = talib.OBV(self.close, self.volume)
        if array:
            return result
        return result[-1]

    def cci(self, n: int, array: bool = False) -> Union[float, np.ndarray]:
        """
        Commodity Channel Index (CCI).
        """
        result = talib.CCI(self.high, self.low, self.close, n)
        if array:
            return result
        return result[-1]

    def atr(self, n: int, array: bool = False) -> Union[float, np.ndarray]:
        """
        Average True Range (ATR).
        """
        result = talib.ATR(self.high, self.low, self.close, n)
        if array:
            return result
        return result[-1]

    def natr(self, n: int, array: bool = False) -> Union[float, np.ndarray]:
        """
        NATR.
        """
        result = talib.NATR(self.high, self.low, self.close, n)
        if array:
            return result
        return result[-1]

    def rsi(self, n: int, array: bool = False) -> Union[float, np.ndarray]:
        """
        Relative Strenght Index (RSI).
        """
        result = talib.RSI(self.close, n)
        if array:
            return result
        return result[-1]

    def macd(
            self,
            fast_period: int,
            slow_period: int,
            signal_period: int,
            array: bool = False
    ) -> Union[
        Tuple[np.ndarray, np.ndarray, np.ndarray],
        Tuple[float, float, float]
    ]:
        """
        MACD.
        """
        macd, signal, hist = talib.MACD(
            self.close, fast_period, slow_period, signal_period
        )
        if array:
            return macd, signal, hist
        return macd[-1], signal[-1], hist[-1]

    def adx(self, n: int, array: bool = False) -> Union[float, np.ndarray]:
        """
        ADX.
        """
        result = talib.ADX(self.high, self.low, self.close, n)
        if array:
            return result
        return result[-1]

    def adxr(self, n: int, array: bool = False) -> Union[float, np.ndarray]:
        """
        ADXR.
        """
        result = talib.ADXR(self.high, self.low, self.close, n)
        if array:
            return result
        return result[-1]

    def dx(self, n: int, array: bool = False) -> Union[float, np.ndarray]:
        """
        DX.
        """
        result = talib.DX(self.high, self.low, self.close, n)
        if array:
            return result
        return result[-1]

    def minus_di(self, n: int, array: bool = False) -> Union[float, np.ndarray]:
        """
        MINUS_DI.
        """
        result = talib.MINUS_DI(self.high, self.low, self.close, n)
        if array:
            return result
        return result[-1]

    def plus_di(self, n: int, array: bool = False) -> Union[float, np.ndarray]:
        """
        PLUS_DI.
        """
        result = talib.PLUS_DI(self.high, self.low, self.close, n)
        if array:
            return result
        return result[-1]

    def willr(self, n: int, array: bool = False) -> Union[float, np.ndarray]:
        """
        WILLR.
        """
        result = talib.WILLR(self.high, self.low, self.close, n)
        if array:
            return result
        return result[-1]

    def ultosc(
            self,
            time_period1: int = 7,
            time_period2: int = 14,
            time_period3: int = 28,
            array: bool = False
    ) -> Union[float, np.ndarray]:
        """
        Ultimate Oscillator.
        """
        result = talib.ULTOSC(self.high, self.low, self.close, time_period1, time_period2, time_period3)
        if array:
            return result
        return result[-1]

    def trange(self, array: bool = False) -> Union[float, np.ndarray]:
        """
        TRANGE.
        """
        result = talib.TRANGE(self.high, self.low, self.close)
        if array:
            return result
        return result[-1]

    def boll(
            self,
            n: int,
            dev: float,
            array: bool = False
    ) -> Union[
        Tuple[np.ndarray, np.ndarray],
        Tuple[float, float]
    ]:
        """
        Bollinger Channel.
        """
        mid = self.sma(n, array)
        std = self.std(n, 1, array)

        up = mid + std * dev
        down = mid - std * dev

        return up, down

    def keltner(
            self,
            n: int,
            dev: float,
            array: bool = False
    ) -> Union[
        Tuple[np.ndarray, np.ndarray],
        Tuple[float, float]
    ]:
        """
        Keltner Channel.
        """
        mid = self.sma(n, array)
        atr = self.atr(n, array)

        up = mid + atr * dev
        down = mid - atr * dev

        return up, down

    def donchian(
            self, n: int, array: bool = False
    ) -> Union[
        Tuple[np.ndarray, np.ndarray],
        Tuple[float, float]
    ]:
        """
        Donchian Channel.
        """
        up = talib.MAX(self.high, n)
        down = talib.MIN(self.low, n)

        if array:
            return up, down
        return up[-1], down[-1]

    def aroon(
            self,
            n: int,
            array: bool = False
    ) -> Union[
        Tuple[np.ndarray, np.ndarray],
        Tuple[float, float]
    ]:
        """
        Aroon indicator.
        """
        aroon_down, aroon_up = talib.AROON(self.high, self.low, n)

        if array:
            return aroon_up, aroon_down
        return aroon_up[-1], aroon_down[-1]

    def aroonosc(self, n: int, array: bool = False) -> Union[float, np.ndarray]:
        """
        Aroon Oscillator.
        """
        result = talib.AROONOSC(self.high, self.low, n)

        if array:
            return result
        return result[-1]

    def minus_dm(self, n: int, array: bool = False) -> Union[float, np.ndarray]:
        """
        MINUS_DM.
        """
        result = talib.MINUS_DM(self.high, self.low, n)

        if array:
            return result
        return result[-1]

    def plus_dm(self, n: int, array: bool = False) -> Union[float, np.ndarray]:
        """
        PLUS_DM.
        """
        result = talib.PLUS_DM(self.high, self.low, n)

        if array:
            return result
        return result[-1]

    def mfi(self, n: int, array: bool = False) -> Union[float, np.ndarray]:
        """
        Money Flow Index.
        """
        result = talib.MFI(self.high, self.low, self.close, self.volume, n)
        if array:
            return result
        return result[-1]

    def ad(self, array: bool = False) -> Union[float, np.ndarray]:
        """
        AD.
        """
        result = talib.AD(self.high, self.low, self.close, self.volume)
        if array:
            return result
        return result[-1]

    def adosc(
            self,
            fast_period: int,
            slow_period: int,
            array: bool = False
    ) -> Union[float, np.ndarray]:
        """
        ADOSC.
        """
        result = talib.ADOSC(self.high, self.low, self.close, self.volume, fast_period, slow_period)
        if array:
            return result
        return result[-1]

    def bop(self, array: bool = False) -> Union[float, np.ndarray]:
        """
        BOP.
        """
        result = talib.BOP(self.open, self.high, self.low, self.close)

        if array:
            return result
        return result[-1]


class MartingleSpotStrategyV3(CtaTemplate):
    """
    1. 马丁策略.
    币安邀请链接: https://www.binancezh.pro/cn/futures/ref/51bitquant
    币安合约邀请码：51bitquant

    ## 策略思路

    1. 挑选1小时涨幅超过2.6%的币，或者4小涨幅超过4.6%的币, 然后入场
    2. 利润超过1%，且最高价回调1%后平仓，当然你可以选择自己的参数
    3. 如果入场后，没有利润，价格继续下跌。那么入场价格下跌5%后，采用马丁策略加仓。

    """
    author = "51bitquant"

    # 策略的核心参数.
    initial_trading_value = 200  # 首次开仓价值 1000USDT.
    trading_value_multiplier = 2  # 加仓的比例.
    max_increase_pos_count = 5  # 最大的加仓次数

    hour_pump_pct = 0.026  # 小时的上涨百分比
    four_hour_pump_pct = 0.046  # 四小时的上涨百分比.
    high_close_change_pct = 0.03  # 最高价/收盘价 -1, 防止上引线过长.
    increase_pos_when_dump_pct = 0.05  # 价格下跌 5%就继续加仓.
    exit_profit_pct = 0.01  # 出场平仓百分比 1%
    exit_pull_back_pct = 0.01  # 最高价回调超过1%，且利润超过1% 就出场.
    trading_fee = 0.00075  # 交易手续费

    # 变量
    avg_price = 0.0  # 当前持仓的平均价格.
    last_entry_price = 0.0  # 上一次入场的价格.
    entry_highest_price = 0.0
    current_pos = 0.0  # 当前的持仓的数量.
    current_increase_pos_count = 0  # 当前的加仓的次数.
    total_profit = 0  # 统计总的利润.

    parameters = ["initial_trading_value", "trading_value_multiplier", "max_increase_pos_count",
                  "hour_pump_pct", "four_hour_pump_pct", "high_close_change_pct", "increase_pos_when_dump_pct",
                  "exit_profit_pct",
                  "exit_pull_back_pct", "trading_fee"]

    variables = ["avg_price", "last_entry_price", "entry_highest_price", "current_pos", "current_increase_pos_count",
                 "total_profit"]

    def __init__(self, cta_engine: CtaEngine, strategy_name, vt_symbol, setting):
        """"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)

        self.last_filled_order: Optional[OrderData, None] = None
        self.tick: Optional[TickData, None] = None
        self.contract: Optional[ContractData, None] = None
        self.account: Optional[AccountData, None] = None

        self.bg_1hour = BarGenerator(self.on_bar, 1, on_window_bar=self.on_1hour_bar, interval=Interval.HOUR)  # 1hour
        self.bg_4hour = BarGenerator(self.on_bar, 4, on_window_bar=self.on_4hour_bar, interval=Interval.HOUR)  # 4hour

        # self.cta_engine.event_engine.register(EVENT_ACCOUNT + 'BINANCE.币名称', self.process_acccount_event)
        # self.cta_engine.event_engine.register(EVENT_ACCOUNT + "BINANCE.USDT", self.process_account_event)

        self.buy_orders = []  # 买单id列表。
        self.sell_orders = []  # 卖单id列表。
        self.min_notional = 11  # 最小的交易金额.

    def on_init(self):
        """
        Callback when strategy is inited.
        """
        self.write_log("策略初始化")
        self.load_bar(3)  # 加载3天的数据.

    def on_start(self):
        """
        Callback when strategy is started.
        """
        self.write_log("策略启动")

    def on_stop(self):
        """
        Callback when strategy is stopped.
        """
        self.write_log("策略停止")

    # def process_account_event(self, event: Event):
    #     self.account: AccountData = event.data
    #     if self.account:
    #         print(
    #             f"self.account: available{self.account.available}, balance:{self.account.balance}, frozen: {self.account.frozen}")

    def on_tick(self, tick: TickData):
        """
        Callback of new tick data update.
        """
        if tick.bid_price_1 > 0 and tick.ask_price_1 > 0:
            self.bg_1hour.update_tick(tick)
            self.bg_4hour.update_tick(tick)

    def on_bar(self, bar: BarData):
        """
        Callback of new bar data update.
        """
        if self.entry_highest_price > 0:
            self.entry_highest_price = max(bar.high_price, self.entry_highest_price)

        if self.current_pos * bar.close_price >= self.min_notional:

            if len(self.sell_orders) <= 0 < self.avg_price:
                # 有利润平仓的时候
                # 清理掉其他买单.

                profit_percent = bar.close_price / self.avg_price - 1
                profit_pull_back_pct = self.entry_highest_price / bar.close_price - 1
                if profit_percent >= self.exit_profit_pct and profit_pull_back_pct >= self.exit_pull_back_pct:
                    self.cancel_all()
                    orderids = self.sell(bar.close_price, abs(self.current_pos))
                    self.sell_orders.extend(orderids)

            if len(self.buy_orders) <= 0:
                # 考虑加仓的条件: 1） 当前有仓位,且仓位值要大于11USDTyi以上，2）加仓的次数小于最大的加仓次数，3）当前的价格比上次入场的价格跌了一定的百分比。

                dump_down_pct = self.last_entry_price / bar.close_price - 1

                if self.current_increase_pos_count <= self.max_increase_pos_count and dump_down_pct >= self.increase_pos_when_dump_pct:
                    # ** 表示的是乘方.
                    self.cancel_all()  # 清理其他卖单.

                    increase_pos_value = self.initial_trading_value * self.trading_value_multiplier ** self.current_increase_pos_count
                    price = bar.close_price
                    vol = increase_pos_value / price
                    orderids = self.buy(price, vol)
                    self.buy_orders.extend(orderids)

        self.bg_1hour.update_bar(bar)
        self.bg_4hour.update_bar(bar)

        self.put_event()

    def on_1hour_bar(self, bar: BarData):

        close_change_pct = bar.close_price / bar.open_price - 1  # 收盘价涨了多少.
        high_change_pct = bar.high_price / bar.close_price - 1  # 计算上引线

        # 回调一定比例的时候.
        if self.current_pos * bar.close_price < self.min_notional:
            # 每次下单要大于等于10USDT, 为了简单设置11USDT.
            if close_change_pct >= self.hour_pump_pct and high_change_pct < self.high_close_change_pct and len(
                    self.buy_orders) == 0:
                # 这里没有仓位.
                # 重置当前的数据.
                self.cancel_all()
                self.current_increase_pos_count = 0
                self.avg_price = 0
                self.entry_highest_price = 0.0

                price = bar.close_price
                vol = self.initial_trading_value / price
                orderids = self.buy(price, vol)
                self.buy_orders.extend(orderids)  # 以及已经下单的orderids.

    def on_4hour_bar(self, bar: BarData):
        close_change_pct = bar.close_price / bar.open_price - 1  # 收盘价涨了多少.
        high_change_pct = bar.high_price / bar.close_price - 1  # 计算上引线

        # 回调一定比例的时候.
        if self.current_pos * bar.close_price < self.min_notional:
            # 每次下单要大于等于10USDT, 为了简单设置11USDT.
            if close_change_pct >= self.four_hour_pump_pct and high_change_pct < self.high_close_change_pct and len(
                    self.buy_orders) == 0:
                # 这里没有仓位.
                # 重置当前的数据.
                self.cancel_all()
                self.current_increase_pos_count = 0
                self.avg_price = 0
                self.entry_highest_price = 0.0

                price = bar.close_price
                vol = self.initial_trading_value / price
                orderids = self.buy(price, vol)
                self.buy_orders.extend(orderids)  # 以及已经下单的orderids.

    def on_order(self, order: OrderData):
        """
        Callback of new order data update.
        """
        if order.status == Status.ALLTRADED:
            if order.direction == Direction.LONG:
                # 买单成交.
                self.current_increase_pos_count += 1
                self.last_entry_price = order.price  # 记录上一次成绩的价格.
                self.entry_highest_price = order.price

        if not order.is_active():
            if order.vt_orderid in self.sell_orders:
                self.sell_orders.remove(order.vt_orderid)

            elif order.vt_orderid in self.buy_orders:
                self.buy_orders.remove(order.vt_orderid)

        self.put_event()  # 更新UI使用.

    def on_trade(self, trade: TradeData):
        """
        Callback of new trade data update.
        """
        if trade.direction == Direction.LONG:
            total = self.avg_price * self.current_pos + trade.price * trade.volume
            self.current_pos += trade.volume

            self.avg_price = total / self.current_pos
        elif trade.direction == Direction.SHORT:
            self.current_pos -= trade.volume

            # 计算统计下总体的利润.
            profit = (trade.price - self.avg_price) * trade.volume
            total_fee = trade.volume * trade.price * 2 * self.trading_fee
            self.total_profit += profit - total_fee

        self.put_event()

    def on_stop_order(self, stop_order: StopOrder):
        """
        Callback of stop order update.
        """
        pass
