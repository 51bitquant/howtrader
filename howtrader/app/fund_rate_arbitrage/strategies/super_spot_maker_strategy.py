from howtrader.app.fund_rate_arbitrage import (
    FundRateArbitrageTemplate,
    FundRateEngine,
    TickData,
    TradeData,
    OrderData
)

from howtrader.trader.object import PremiumIndexData, AccountData, PositionData, ContractData, Status

from howtrader.trader.event import EVENT_TIMER, EVENT_ACCOUNT, EVENT_FUND_RATE_DATA, EVENT_POSITION
from howtrader.event import Event
from typing import Optional
from howtrader.trader.utility import floor_to


"""
## 策略参数说明

1. strategy_name : 策略的名称，随便取一个名字，多个策略的时候，要取不同的名字

2. spot_vt_symbol: 现货的交易对，交易对小写.BINANCE, 如: btcusdt.BINANCE,
   ethbusd.BINANCE
3. future_vt_symbol: 合约的交易对, 交易对大写.BINANCE, 如:BTCUSDT.BINANCE,
   ETHUSDT.BINANCE, UNIUSDT.BINANCE
   
4. spot_trade_asset: 需要交易现货的币种名称, 如果交易的是BTCUSDT,
   那么就填写BTC,如果是ETHUSDT, 那么就写ETH, 这里要全部大写。
 
5. spot_quote_asset: 计价的资产名称，如果你现货交易的是btcbusd,
   那么这里写BUSD, 如果是btcusdt, 这里填写USDT
 
6. initial_target_pos: 要对冲的最大的目标数量,
   如果你写10，就是要现货要买10个币，如果资金不够，就不会继续下单，满足条件的时候，会尽可能下单到这个数量。
   
7. trade_max_usd_every_time:
   每次最多下单多少个USDT/BUSD的订单，会根据盘口数量来选择下单数量，但是也会参考这个。防止对冲滑点过大。
   
8. slippage_tolerance_pct: 滑点的承受百分比,
   主要是maker成交后，会下taker单，默认0.03,
   就是万三的滑点，就是下一个超价的限价单去尽可能保证对冲的时效性。
   
9. open_spread_ptc: 大于多少的时候下单 0.1，表示的0.1%,
   就是盘口价差大于0.1%的时候才开启套利。
   
10. open_rate_pct:
    资金费率大于多少的时候，才开始套利。要满足价差和资金费率的值才开仓，0.1，表示0.1%
    
11. close_spread_ptc: 要平仓的价差，如果价差缩小到一定程度的时候，会考虑平仓。

12. close_rate_pct:
    资金费率小于某个百分比的时候，会平仓。但是要同时满足价差和资金费率。
    
13. close_before_liquidation_pct: 在爆仓价格/现在价格-1
    小于一定百分比的时候回平仓合约, 如果爆仓价格是1000，
    如果你写0.5，那就是在价格大于995的时候会平仓合约。
    
14. timer_interval: 挂单多久不成交会撤单.
   

如果需要平仓，可以把initial_target_pos设置为零
"""

class SuperSpotMakerStrategy(FundRateArbitrageTemplate):
    """
    现货挂maker单，合约taker单.
    """
    author = "bitquant"

    spot_trade_asset: str = "BTC"  # 现货资产
    spot_quote_asset: str = "BUSD"  # 计价的资产

    initial_target_pos: float = 0.0  # 目标对冲的数量
    trade_max_usd_every_time = 100  # 每次交易的最大数量
    slippage_tolerance_pct: float = 0.03 #
    open_spread_pct: float = 0.01  # 价差
    open_rate_pct:float = 0.02 # 资金费率

    close_spread_pct: float = 0.0
    close_rate_pct: float = 0.0
    close_before_liquidation_pct: float = 0.5  # 在爆仓前减仓, 每次减仓1000刀价值的仓位.
    timer_interval: int = 15  # 轮询的周期，单位为秒

    parameters = ["spot_trade_asset", "spot_quote_asset", "initial_target_pos",
                  "trade_max_usd_every_time", "slippage_tolerance_pct",
                  "open_spread_pct", "open_rate_pct",
                  "close_spread_pct", "close_rate_pct",
                  "close_before_liquidation_pct",
                  "timer_interval"]

    current_spread: float = 0
    current_rate: float = 0
    spot_trade_vol:float = 0
    spot_quote_vol: float = 0
    future_vol: float = 0
    liquid_price:float = 0
    reduce_future_pos:bool = False
    close_pos:bool = False
    insufficient:bool = False

    variables = ["current_spread", "spot_trade_vol", "spot_quote_vol",  "future_vol", "liquid_price", "reduce_future_pos", "close_pos", "insufficient"]

    def __init__(self, fund_rate_engine: FundRateEngine, strategy_name: str, spot_vt_symbol:str, future_vt_symbol:str, setting:dict):
        """"""
        super().__init__(fund_rate_engine, strategy_name, spot_vt_symbol,future_vt_symbol, setting)

        self.timer_count = 0

        self.spot_tick: Optional[TickData] = None
        self.future_tick: Optional[TickData] = None

        self.spot_trade_account: Optional[AccountData] = None
        self.spot_quote_account: Optional[AccountData] = None
        self.future_position: Optional[PositionData] = None

        self.premium_index_data: Optional[PremiumIndexData] = None
        self.future_contract: Optional[ContractData] = None
        self.spot_contract: Optional[ContractData] = None

        self.insufficient: bool = False

        # 这个参数是固定的.
        self.min_trade_amount = 11  # 最小的交易金额，防止出现下单错误, 以usdt/busd计算.

        self.close_pos = False
        self.reduce_future_pos = False

        self.orders = []  # 对冲的单子.

    def on_init(self):
        """
        Callback when strategy is inited.
        """
        self.write_log("策略初始化")

    def on_start(self):
        """
        Callback when strategy is started.
        """

        # 重新等待熟练来自交易所初始化这些值.

        self.write_log("策略启动")
        # 订阅现货的资产信息. BINANCE.资产名, 或者BINANCES.资产名

        self.insufficient: bool = False
        # 重新初始化值
        self.current_spread = 0
        self.current_rate = 0
        self.spot_trade_vol = 0
        self.spot_quote_vol = 0
        self.future_vol = 0
        self.liquid_price = 0  # 爆仓的价格.

        self.close_pos = False
        self.reduce_future_pos = False

        self.spot_tick: Optional[TickData] = None
        self.future_tick: Optional[TickData] = None

        self.spot_trade_account: Optional[AccountData] = None
        self.spot_quote_account: Optional[AccountData] = None
        self.future_position: Optional[PositionData] = None

        self.premium_index_data: Optional[PremiumIndexData] = None

        self.future_contract = self.get_contract(self.future_vt_symbol)
        self.spot_contract = self.get_contract(self.spot_vt_symbol)


        self.fund_rate_engine.event_engine.register(EVENT_ACCOUNT + f"BINANCE.{self.spot_trade_asset.upper()}",
                                                    self.process_account_event)

        self.fund_rate_engine.event_engine.register(EVENT_ACCOUNT + f"BINANCE.{self.spot_quote_asset.upper()}",
                                                    self.process_account_event)

        self.fund_rate_engine.event_engine.register(EVENT_TIMER, self.process_timer_event)
        ## 注册合约的资金费率.
        self.fund_rate_engine.event_engine.register(EVENT_FUND_RATE_DATA + self.future_vt_symbol,
                                                    self.process_fund_rate_data_event)
        self.fund_rate_engine.event_engine.register(EVENT_POSITION + self.future_vt_symbol, self.process_position_event)

    def on_stop(self):
        """
        Callback when strategy is stopped.
        """
        self.write_log("策略停止")

        # 取消订阅资产.
        self.fund_rate_engine.event_engine.unregister(EVENT_ACCOUNT + f"BINANCE.{self.spot_trade_asset.upper()}",
                                                    self.process_account_event)

        self.fund_rate_engine.event_engine.unregister(EVENT_ACCOUNT + f"BINANCE.{self.spot_quote_asset.upper()}",
                                                      self.process_account_event)


        self.fund_rate_engine.event_engine.unregister(EVENT_TIMER, self.process_timer_event)
        ## 注册合约的资金费率.
        self.fund_rate_engine.event_engine.unregister(EVENT_FUND_RATE_DATA + self.future_vt_symbol,
                                                    self.process_fund_rate_data_event)
        self.fund_rate_engine.event_engine.unregister(EVENT_POSITION + self.future_vt_symbol, self.process_position_event)

    def process_fund_rate_data_event(self, event: Event):
        self.premium_index_data: PremiumIndexData = event.data

    def process_timer_event(self, event: Event) -> None:

        self.timer_count += 1
        self.put_event()
        if self.timer_count < self.timer_interval:
            return None

        self.cancel_all()
        self.timer_count = 0  # 重置timer


    def on_tick(self, tick: TickData):
        """
        Callback of new tick data update.
        """
        if tick.vt_symbol == self.spot_vt_symbol:
            self.spot_tick = tick

        elif tick.vt_symbol == self.future_vt_symbol:
            self.future_tick = tick

        # 如果没有行情数据就不会处理.
        if not self.spot_contract:
            print("spot_contract为空")
            return

        if not self.future_contract:
            print("future_contract为空")
            return

        if not self.spot_tick:
            print("spot_tick为空")
            return
        if not self.future_tick:
            print("future_tick为空")
            return

        if not self.premium_index_data:
            print("资金费率为空")
            return

        if not self.spot_trade_account:
            print("现货资产为空")
            return

        if not self.spot_quote_account:
            print("现货U资产为空")
            return

        if not self.future_position:
            print("合约仓位为空")
            return

        if not self.trading:
            return

        # 如果之前有订单，就不会下单.
        if len(self.orders) > 0:
            return

        self.timer_count = 0


        ################################################# 处理仓位不相等的情况.
        if self.future_position.volume >= self.future_contract.min_volume:
            print(f"合约仓位为多头，全部清仓数量: {self.future_position.volume}")
            ids = self.sell(self.future_vt_symbol, self.future_tick.bid_price_1 * (1 - self.slippage_tolerance_pct/100),
                       abs(self.future_position.volume))
            self.orders.extend(ids)
            return None

        # 合约触发减仓后，就要开始处理现货减仓了.
        if self.reduce_future_pos:
            delta_vol = self.spot_trade_account.balance - abs(self.future_position.volume)

            vol = min(delta_vol, self.spot_trade_account.balance)  # 要求这个数必须是正数.
            if vol * self.spot_tick.bid_price_1 >= self.min_trade_amount:

                ids = self.sell(self.spot_vt_symbol, self.spot_tick.bid_price_1 * (1 - self.slippage_tolerance_pct/100), vol)
                self.orders.extend(ids)
                print(f"触发减仓信息, 需要卖出现货: {self.spot_trade_account.balance}, {self.future_position.volume}, {delta_vol}")
                return None

        # 防止爆仓的处理.
        if self.liquid_price > 0 and abs(self.future_position.volume) >= self.future_contract.min_volume:
            # 有仓位且爆仓价格存在的时候

            if self.future_tick.bid_price_1 <= 0:
                return
            liquid = (self.liquid_price / self.future_tick.bid_price_1 - 1) * 100

            if liquid < self.close_before_liquidation_pct:
                print(f"爆仓价格：{self.liquid_price}, 当前价格:{self.future_tick.bid_price_1}, 百分比:{liquid}, 临界值: {self.close_before_liquidation_pct}")
                cover_price = self.future_tick.ask_price_1 * (1 + self.slippage_tolerance_pct / 100)

                vol = abs(self.future_position.volume) * 0.1  # 每次减仓10%
                vol = floor_to(vol, self.future_contract.min_volume)
                if vol <= 10 * self.future_contract.min_volume:
                    vol = abs(self.future_position.volume)

                ids = self.cover(self.future_vt_symbol, cover_price, vol)
                self.orders.extend(ids)
                print(f"下减仓单了，防止爆仓: {round(cover_price, 3)}@{vol}, orders: {self.orders}")
                return None

        # 处理合约的仓位和现货仓位相等.
        delta_vol = self.spot_trade_account.balance - abs(self.future_position.volume)

        # print(f"现货仓位:{self.spot_trade_account.balance}, 合约仓位: {self.future_position.volume}, delta: {delta_vol}")
        if abs(delta_vol) * self.spot_tick.bid_price_1 >= self.min_trade_amount and abs(delta_vol) >= self.future_contract.min_volume:
            print(f"现货仓位:{self.spot_trade_account.balance}, 合约仓位: {self.future_position.volume}, delta: {delta_vol}")

            if delta_vol > 0:

                if not self.insufficient:
                    vol = floor_to(delta_vol, self.future_contract.min_volume)
                    if vol >= self.future_contract.min_volume:
                        ids = self.short(self.future_vt_symbol,
                                         self.future_tick.bid_price_1 * (1 - self.slippage_tolerance_pct / 100), vol)
                        self.orders.extend(ids)
                        print(f"合约对冲做空：{self.future_tick.bid_price_1}@{vol}, orders: {self.orders}")
                        return None

                else:

                    self.initial_target_pos = abs(self.future_position.volume)
                    self.write_log(f"合约保证金不够，停止对冲了")

            elif delta_vol < 0:

                vol = floor_to(abs(delta_vol), self.future_contract.min_volume)
                left_vol = abs(self.future_position.volume) - vol

                # 看看剩余的数量是不是比较小，如果太小了，就一起把它给平仓了。
                if left_vol >= self.future_contract.min_volume and left_vol * self.future_tick.ask_price_1 < self.min_trade_amount:
                    vol = abs(self.future_position.volume)

                if vol >= self.future_contract.min_volume:

                    ids = self.cover(self.future_vt_symbol,
                                     self.future_tick.ask_price_1 * (1 + self.slippage_tolerance_pct / 100),
                                     vol)
                    self.orders.extend(ids)

                    print(f"合约对冲做多：{self.future_tick.ask_price_1}@{vol}, orders: {self.orders}")

                    return None

        ##############################################################

        if self.spot_tick.bid_price_1 <= 0:
            return

        self.current_spread = round((self.future_tick.bid_price_1 / self.spot_tick.bid_price_1 - 1) * 100, 3)
        self.current_rate = self.premium_index_data.lastFundingRate

        # print(f"current_spread: {self.current_spread}, current_rate: {self.current_rate}")

        if self.current_spread <= self.close_spread_pct and self.current_rate <= self.close_rate_pct:

            trade_amount = self.spot_trade_account.balance

            trade_vol = floor_to(self.trade_max_usd_every_time / self.spot_tick.bid_price_1,
                                 self.spot_contract.min_volume)

            trade_vol = min(self.future_tick.ask_volume_1, trade_vol, abs(trade_amount))

            if trade_vol * self.spot_tick.ask_price_1 >= self.min_trade_amount:
                ids = self.sell(self.spot_vt_symbol, self.spot_tick.ask_price_1, abs(trade_vol), limit_maker=True)
                self.orders.extend(ids)
                print(f"价差和资金费率变小，让程序减仓. 价差:{self.current_spread} <= {self.close_spread_pct},  "
                      f"费率: {self.current_rate} <= {self.close_rate_pct}, 现货减仓：{self.spot_tick.ask_price_1}@{trade_vol}, orders: {self.orders}")
                self.close_pos = True

            else:
                self.close_pos = False

            return None

        buy_amount = self.initial_target_pos - self.spot_trade_account.balance  # 3-3.45

        if buy_amount > 0:
            if self.reduce_future_pos:
                return
            # 如果发生减仓的话就不进行开仓了。
            if self.current_spread < self.open_spread_pct or self.current_rate < self.open_rate_pct:
                print(
                    f"价差和资金费率不满足开仓条件, 当前价差->{self.current_spread}, 预设:{self.open_spread_pct},  费率: 当前->{self.current_rate}, 预设:{self.open_rate_pct}")
                return None

            trade_value = min(self.spot_quote_account.balance, self.trade_max_usd_every_time)

            trade_vol = floor_to(trade_value / self.spot_tick.bid_price_1, self.spot_contract.min_volume)

            trade_vol = min(self.future_tick.bid_volume_1, trade_vol, buy_amount)
            trade_vol = floor_to(trade_vol, self.spot_contract.min_volume)

            if trade_vol * self.spot_tick.bid_price_1 >= self.min_trade_amount and trade_vol >= self.future_contract.min_volume:
                ids = self.buy(self.spot_vt_symbol, self.spot_tick.bid_price_1, trade_vol, limit_maker=True)
                self.orders.extend(ids)

                print(f"下现货买单:{self.spot_tick.bid_price_1}@{trade_vol}, orders: {self.orders}")

            else:
                print(f"不满足下单条件, 下单数量: {trade_vol}, 合约要求的最小下单数量: {self.future_contract.min_volume}")

        elif buy_amount < 0:

            if abs(buy_amount) * self.spot_tick.ask_price_1 >= self.min_trade_amount:
                trade_vol = floor_to(self.trade_max_usd_every_time / self.spot_tick.bid_price_1,
                                     self.spot_contract.min_volume)

                vol = min(self.future_tick.ask_volume_1, trade_vol, abs(buy_amount), self.spot_trade_account.balance)
                vol = floor_to(vol, self.spot_contract.min_volume)

                if vol * self.spot_tick.ask_price_1 >= self.min_trade_amount and vol >= self.future_contract.min_volume:

                    ids = self.sell(self.spot_vt_symbol, self.spot_tick.ask_price_1, vol, limit_maker=True)
                    self.orders.extend(ids)
                    self.close_pos = True  # 设置它是平仓.
                    print(f"下现货卖单：{self.spot_tick.ask_price_1}@{vol}, orders: {self.orders}")
            else:
                self.close_pos = False

        else:
            self.close_pos = False

    def on_order(self, order: OrderData):
        """
        Callback of new order data update.
        """

        if not order.is_active():
            if order.vt_orderid in self.orders:
                self.orders.remove(order.vt_orderid)

        if order.status == Status.REJECTED:
            self.write_log(f"{order.vt_symbol}: {order.failed_order_msg}")

            if 'insufficient' in order.failed_order_msg:
                if order.vt_symbol == self.future_vt_symbol:
                    self.insufficient = True

    def on_trade(self, trade: TradeData):
        """
        Callback of new trade data update.
        """

    def process_account_event(self, event: Event):
        account: AccountData = event.data
        if account.accountid == self.spot_trade_asset:
            self.spot_trade_account = account
            self.spot_trade_vol = self.spot_trade_account.balance

        elif account.accountid == self.spot_quote_asset:
            self.spot_quote_account = account
            self.spot_quote_vol = self.spot_quote_account.balance

        if self.spot_trade_account and self.spot_quote_account:
            print(f"{self.spot_trade_asset}资产:{self.spot_trade_account.balance}, {self.spot_quote_asset}资产:{self.spot_quote_account.balance}")

        self.put_event()

    def process_position_event(self, event: Event):
        self.future_position: PositionData = event.data

        delta = self.future_position.volume - self.future_vol

        # print(f"合约现在仓位: {self.future_position.volume}, 上一次仓位: {self.future_vol}, delta: {delta}")

        if self.future_contract and delta >= self.future_contract.min_volume:
            if not self.close_pos:
                self.initial_target_pos = abs(self.future_position.volume)
                print(f"减仓后的目标仓位: {self.initial_target_pos}")
                self.reduce_future_pos = True

        self.future_vol = self.future_position.volume

        if self.future_position.volume < 0:
            if self.future_position.liquidation_price > 0:
                self.liquid_price = self.future_position.liquidation_price
        else:
            self.liquid_price = 0

        # print(f"当前的爆仓价: {self.liquid_price}")

        self.put_event()

    def get_contract(self, vt_symbol: str) -> ContractData:
        """"""
        return self.fund_rate_engine.get_contract(vt_symbol)


