from howtrader.app.cta_strategy import (
    CtaTemplate,
    StopOrder,
    TickData,
    BarData,
    TradeData,
    OrderData,
    BarGenerator,
    ArrayManager,
)
import pandas as pd
import pandas_ta as ta

class AtrRsiStrategy(CtaTemplate):
    """"""

    author = "51bitquant"

    atr_length = 26
    atr_ma_length = 6
    rsi_length = 15
    rsi_entry = 16
    trailing_percent = 0.3
    trading_money = 10000

    trading_size = 0
    atr_value = 0
    atr_ma = 0
    rsi_value = 0
    rsi_buy = 0
    rsi_sell = 0
    intra_trade_high = 0
    intra_trade_low = 0

    parameters = ["atr_length", "atr_ma_length", "rsi_length",
                  "rsi_entry", "trailing_percent", "fixed_size"]
    variables = ["trading_size", "atr_value", "atr_ma", "rsi_value", "rsi_buy", "rsi_sell"]

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super(AtrRsiStrategy, self).__init__(
            cta_engine, strategy_name, vt_symbol, setting
        )
        self.bg = BarGenerator(self.on_bar, 15, self.on_15min_bar)
        self.am = ArrayManager()

    def on_init(self):
        """
        Callback when strategy is inited.
        """
        self.write_log("策略初始化")

        self.rsi_buy = 50 + self.rsi_entry
        self.rsi_sell = 50 - self.rsi_entry

        self.load_bar(10)

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

    def on_tick(self, tick: TickData):
        """
        Callback of new tick data update.
        """
        self.bg.update_tick(tick)

    def on_bar(self, bar: BarData):
        """
        Callback of new bar data update.
        """
        self.bg.update_bar(bar)


    def on_15min_bar(self, bar: BarData):
        self.cancel_all()

        am = self.am
        am.update_bar(bar)
        if not am.inited:
            return

        high = pd.Series(am.close_array)
        low = pd.Series(am.low_array)
        close = pd.Series(am.close_array)

        atr_array = ta.atr(high, low, close, self.atr_length)
        self.atr_value = atr_array.iloc[-1]

        self.atr_ma =  ta.sma(atr_array, self.atr_ma_length).iloc[-1]
        self.rsi_value = ta.rsi(close, self.rsi_length).iloc[-1]

        if self.pos == 0:
            self.intra_trade_high = bar.high_price
            self.intra_trade_low = bar.low_price

            self.trading_size = self.trading_money/bar.close_price
            if self.atr_value > self.atr_ma:
                if self.rsi_value > self.rsi_buy:
                    self.buy(bar.close_price + 5, self.trading_size)
                elif self.rsi_value < self.rsi_sell:
                    self.short(bar.close_price - 5, self.trading_size)

        elif self.pos > 0:
            self.intra_trade_high = max(self.intra_trade_high, bar.high_price)
            self.intra_trade_low = bar.low_price

            long_stop = self.intra_trade_high * \
                        (1 - self.trailing_percent / 100)
            self.sell(long_stop, abs(self.pos), stop=True)

        elif self.pos < 0:
            self.intra_trade_low = min(self.intra_trade_low, bar.low_price)
            self.intra_trade_high = bar.high_price

            short_stop = self.intra_trade_low * \
                         (1 + self.trailing_percent / 100)
            self.cover(short_stop, abs(self.pos), stop=True)


    def on_order(self, order: OrderData):
        """
        Callback of new order data update.
        """
        pass

    def on_trade(self, trade: TradeData):
        """
        Callback of new trade data update.
        """
        self.put_event()

    def on_stop_order(self, stop_order: StopOrder):
        """
        Callback of stop order update.
        """
        pass
