from typing import TYPE_CHECKING

from howtrader.trader.constant import Direction
from howtrader.trader.object import (TickData, OrderData, TradeData)
from howtrader.trader.utility import round_to

from .template import SpreadAlgoTemplate
from .base import SpreadData

if TYPE_CHECKING:
    from .engine import SpreadAlgoEngine


class SpreadTakerAlgo(SpreadAlgoTemplate):
    """"""
    algo_name = "SpreadTaker"

    def __init__(
        self,
        algo_engine: "SpreadAlgoEngine",
        algoid: str,
        spread: SpreadData,
        direction: Direction,
        price: float,
        volume: float,
        payup: int,
        interval: int,
        lock: bool,
        extra: dict
    ):
        """"""
        super().__init__(
            algo_engine,
            algoid,
            spread,
            direction,
            price,
            volume,
            payup,
            interval,
            lock,
            extra
        )

    def on_tick(self, tick: TickData):
        """"""
        # Return if there are any existing orders
        if not self.is_order_finished():
            return

        # Hedge if active leg is not fully hedged
        if not self.is_hedge_finished():
            self.hedge_passive_legs()
            return

        # Return if tick not inited
        if not self.spread.bid_volume or not self.spread.ask_volume:
            return

        # Otherwise check if should take active leg
        if self.direction == Direction.LONG:
            if self.spread.ask_price <= self.price:
                self.take_active_leg()
        else:
            if self.spread.bid_price >= self.price:
                self.take_active_leg()

    def on_order(self, order: OrderData):
        """"""
        # Only care active leg order update
        if order.vt_symbol != self.spread.active_leg.vt_symbol:
            return

        # Do nothing if still any existing orders
        if not self.is_order_finished():
            return

        # Hedge passive legs if necessary
        if not self.is_hedge_finished():
            self.hedge_passive_legs()

    def on_trade(self, trade: TradeData):
        """"""
        pass

    def on_interval(self):
        """"""
        if not self.is_order_finished():
            self.cancel_all_order()

    def take_active_leg(self):
        """"""
        active_symbol = self.spread.active_leg.vt_symbol

        # Calculate spread order volume of new round trade
        spread_volume_left = self.target - self.traded

        if self.direction == Direction.LONG:
            spread_order_volume = self.spread.ask_volume
            spread_order_volume = min(spread_order_volume, spread_volume_left)
        else:
            spread_order_volume = -self.spread.bid_volume
            spread_order_volume = max(spread_order_volume, spread_volume_left)

        # Calculate active leg order volume
        leg_order_volume = self.spread.calculate_leg_volume(
            active_symbol,
            spread_order_volume
        )

        # Check active leg volume left
        active_volume_target = self.spread.calculate_leg_volume(
            active_symbol,
            self.target
        )
        active_volume_traded = self.leg_traded[active_symbol]
        active_volume_left = active_volume_target - active_volume_traded

        # Limit order volume to total volume left of the active leg
        if active_volume_left > 0:
            leg_order_volume = min(leg_order_volume, active_volume_left)
        else:
            leg_order_volume = max(leg_order_volume, active_volume_left)

        # Send active leg order
        self.send_leg_order(
            active_symbol,
            leg_order_volume
        )

    def hedge_passive_legs(self):
        """
        Send orders to hedge all passive legs.
        """
        # Calcualte spread volume to hedge
        active_leg = self.spread.active_leg
        active_traded = self.leg_traded[active_leg.vt_symbol]
        active_traded = round_to(active_traded, self.spread.min_volume)

        hedge_volume = self.spread.calculate_spread_volume(
            active_leg.vt_symbol,
            active_traded
        )

        # Calculate passive leg target volume and do hedge
        for leg in self.spread.passive_legs:
            passive_traded = self.leg_traded[leg.vt_symbol]
            passive_traded = round_to(passive_traded, self.spread.min_volume)

            passive_target = self.spread.calculate_leg_volume(
                leg.vt_symbol,
                hedge_volume
            )

            leg_order_volume = passive_target - passive_traded
            if leg_order_volume:
                self.send_leg_order(leg.vt_symbol, leg_order_volume)

    def send_leg_order(self, vt_symbol: str, leg_volume: float):
        """"""
        leg = self.spread.legs[vt_symbol]
        leg_tick = self.get_tick(vt_symbol)
        leg_contract = self.get_contract(vt_symbol)

        if leg_volume > 0:
            price = leg_tick.ask_price_1 + leg_contract.pricetick * self.payup
            self.send_order(leg.vt_symbol, price, abs(leg_volume), Direction.LONG)
        elif leg_volume < 0:
            price = leg_tick.bid_price_1 - leg_contract.pricetick * self.payup
            self.send_order(leg.vt_symbol, price, abs(leg_volume), Direction.SHORT)