from typing import Dict, List, TYPE_CHECKING, Optional

from howtrader.trader.object import TickData, TradeData, ContractData
from howtrader.trader.constant import Direction

if TYPE_CHECKING:
    from .engine import PortfolioEngine


class ContractResult:
    """"""

    def __init__(
        self,
        engine: "PortfolioEngine",
        reference: str,
        vt_symbol: str,
        open_pos: float = 0
    ) -> None:
        """"""
        super().__init__()

        self.engine: "PortfolioEngine" = engine

        self.reference: str = reference
        self.vt_symbol: str = vt_symbol

        self.open_pos: float = open_pos
        self.last_pos: float = open_pos

        self.trading_pnl: float = 0
        self.holding_pnl: float = 0
        self.total_pnl: float = 0

        self.trades: Dict[str, TradeData] = {}
        self.new_trades: List[TradeData] = []

        self.long_volume: float = 0
        self.short_volume: float = 0
        self.long_cost: float = 0
        self.short_cost: float = 0

    def update_trade(self, trade: TradeData) -> None:
        """"""
        # 过滤重复成交
        if trade.vt_tradeid in self.trades:
            return
        self.trades[trade.vt_tradeid] = trade
        self.new_trades.append(trade)

        if trade.direction == Direction.LONG:
            self.last_pos += float(trade.volume)
        else:
            self.last_pos -= float(trade.volume)

    def calculate_pnl(self) -> None:
        """"""
        vt_symbol: str = self.vt_symbol

        contract: Optional[ContractData] = self.engine.get_contract(vt_symbol)
        tick: Optional[TickData] = self.engine.get_tick(vt_symbol)
        if not contract or not tick:
            return

        last_price: float = tick.last_price
        size: float = float(contract.size)

        # 计算新成交额
        for trade in self.new_trades:
            trade_volume: float = float(trade.volume)
            trade_cost: float = float(trade.price) * float(trade_volume) * size

            if trade.direction == Direction.LONG:
                self.long_cost += trade_cost
                self.long_volume += trade_volume
            else:
                self.short_cost += trade_cost
                self.short_volume += float(trade_volume)

        self.new_trades.clear()

        # 计算成交利润
        long_value: float = self.long_volume * last_price * size
        long_pnl: float = long_value - self.long_cost

        shrot_value: float = self.short_volume * last_price * size
        short_pnl: float = self.short_cost - shrot_value

        self.trading_pnl = long_pnl + short_pnl

        # 计算未实现利润和总利润
        self.holding_pnl = (last_price - tick.pre_close) * self.open_pos * size
        self.total_pnl = self.holding_pnl + self.trading_pnl


class PortfolioResult:
    """"""

    def __init__(self, reference: str) -> None:
        """"""
        super().__init__()

        self.reference: str = reference
        self.trading_pnl: float = 0
        self.holding_pnl: float = 0
        self.total_pnl: float = 0

    def clear_pnl(self) -> None:
        """"""
        self.trading_pnl = 0
        self.holding_pnl = 0
        self.total_pnl = 0