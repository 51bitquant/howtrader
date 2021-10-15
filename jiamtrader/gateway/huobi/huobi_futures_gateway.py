import json
from copy import copy
from datetime import datetime, timedelta
from typing import Dict, List, Any, Set
from collections import defaultdict

from jiamtrader.event import EventEngine
from jiamtrader.api.websocket import WebsocketClient
from jiamtrader.trader.constant import (
    Direction,
    Offset,
    Exchange,
    Product,
    Status,
    OrderType,
    Interval
)
from jiamtrader.trader.gateway import BaseGateway
from jiamtrader.trader.object import (
    TickData,
    OrderData,
    TradeData,
    BarData,
    AccountData,
    PositionData,
    ContractData,
    OrderRequest,
    CancelRequest,
    SubscribeRequest,
    HistoryRequest
)
from .huobi_apibase import _split_url, generate_datetime, create_signature, CHINA_TZ, HuobiWebsocketApiBase


# 实盘REST API地址
REST_HOST: str = "https://api.hbdm.com"

# 实盘Websocket API地址
WEBSOCKET_DATA_HOST: str = "wss://www.hbdm.com/ws"
WEBSOCKET_TRADE_HOST: str = "wss://api.hbdm.com/notification"

# 委托状态映射
STATUS_HUOBIF2VT: Dict[str, Status] = {
    3: Status.NOTTRADED,
    4: Status.PARTTRADED,
    5: Status.CANCELLED,
    6: Status.ALLTRADED,
    7: Status.CANCELLED,
}

# 委托类型映射
ORDERTYPE_VT2HUOBIF: Dict[OrderType, Any] = {
    OrderType.MARKET: "opponent",
    OrderType.LIMIT: "limit",
    OrderType.FOK: "fok",
    OrderType.FAK: "ioc"
}
ORDERTYPE_HUOBIF2VT: Dict[Any, OrderType] = {v: k for k, v in ORDERTYPE_VT2HUOBIF.items()}
ORDERTYPE_HUOBIF2VT[1] = OrderType.LIMIT
ORDERTYPE_HUOBIF2VT[3] = OrderType.MARKET
ORDERTYPE_HUOBIF2VT[4] = OrderType.MARKET
ORDERTYPE_HUOBIF2VT[5] = OrderType.STOP
ORDERTYPE_HUOBIF2VT[6] = OrderType.LIMIT
ORDERTYPE_HUOBIF2VT["lightning"] = OrderType.MARKET
ORDERTYPE_HUOBIF2VT["optimal_5"] = OrderType.MARKET
ORDERTYPE_HUOBIF2VT["optimal_10"] = OrderType.MARKET
ORDERTYPE_HUOBIF2VT["optimal_20"] = OrderType.MARKET

# 买卖方向映射
DIRECTION_VT2HUOBIF: Dict[Direction, str] = {
    Direction.LONG: "buy",
    Direction.SHORT: "sell",
}
DIRECTION_HUOBIF2VT: Dict[str, Direction] = {v: k for k, v in DIRECTION_VT2HUOBIF.items()}

# 开平方向映射
OFFSET_VT2HUOBIF: Dict[Offset, str] = {
    Offset.OPEN: "open",
    Offset.CLOSE: "close",
}
OFFSET_HUOBIF2VT: Dict[str, Offset] = {v: k for k, v in OFFSET_VT2HUOBIF.items()}

# 数据频率映射
INTERVAL_VT2HUOBIF: Dict[Interval, str] = {
    Interval.MINUTE: "1min",
    Interval.HOUR: "60min",
    Interval.DAILY: "1day"
}

# 时间间隔映射
TIMEDELTA_MAP: Dict[Interval, timedelta] = {
    Interval.MINUTE: timedelta(minutes=1),
    Interval.HOUR: timedelta(hours=1),
    Interval.DAILY: timedelta(days=1),
}

# 合约类型映射
CONTRACT_TYPE_MAP: Dict[str, str] = {
    "this_week": "CW",
    "next_week": "NW",
    "quarter": "CQ",
    "next_quarter": "NQ"
}

# 合约类型全局缓存字典
symbol_type_map: Dict[str, str] = {}


class HuobiFuturesGateway(BaseGateway):
    """
    vn.py用于对接火币交割合约账户的交易接口。
    """

    default_setting: Dict[str, str] = {
        "key": "",
        "secret": "",
        "代理地址": "",
        "代理端口": "",
    }

    exchanges: Exchange = [Exchange.HUOBI]

    def __init__(self, event_engine: EventEngine, gateway_name: str = "HUOBI_FUTURES") -> None:
        """构造函数"""
        super().__init__(event_engine, gateway_name)

        self.rest_api: "HuobiFuturesRestApi" = HuobiFuturesRestApi(self)
        self.trade_ws_api: "HuobiFuturesTradeWebsocketApi" = HuobiFuturesTradeWebsocketApi(self)
        self.market_ws_api: "HuobiFuturesDataWebsocketApi" = HuobiFuturesDataWebsocketApi(self)

    def connect(self, setting: dict) -> None:
        """连接交易接口"""
        key: str = setting["key"]
        secret: str = setting["secret"]
        proxy_host: str = setting["代理地址"]
        proxy_port: str = setting["代理端口"]

        if proxy_port.isdigit():
            proxy_port = int(proxy_port)
        else:
            proxy_port = 0

        self.rest_api.connect(key, secret, proxy_host, proxy_port)
        self.trade_ws_api.connect(key, secret, proxy_host, proxy_port)
        self.market_ws_api.connect(key, secret, proxy_host, proxy_port)

    def subscribe(self, req: SubscribeRequest) -> None:
        """订阅行情"""
        self.market_ws_api.subscribe(req)

    def send_order(self, req: OrderRequest) -> str:
        """委托下单"""
        return self.rest_api.send_order(req)

    def cancel_order(self, req: CancelRequest) -> None:
        """委托撤单"""
        self.rest_api.cancel_order(req)

    def query_account(self) -> None:
        """查询资金"""
        pass

    def query_position(self) -> None:
        """查询持仓"""
        pass

    def query_history(self, req: HistoryRequest):
        """查询历史数据"""
        return self.rest_api.query_history(req)

    def close(self) -> None:
        """关闭连接"""
        self.rest_api.stop()
        self.trade_ws_api.stop()
        self.market_ws_api.stop()


class HuobiFuturesRestApi(RestClient):
    """火币交割合约REST API"""

    def __init__(self, gateway: HuobiFuturesGateway) -> None:
        """构造函数"""
        super().__init__()

        self.gateway: HuobiFuturesGateway = gateway
        self.gateway_name: str = gateway.gateway_name

        self.host: str = ""
        self.key: str = ""
        self.secret: str = ""
        self.account_id: str = ""

        self.order_count: int = 0
        self.currencies: Set[str] = set()

    def sign(self, request: Request) -> Request:
        """生成火币签名"""
        request.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.71 Safari/537.36"
        }
        params_with_signature = create_signature(
            self.key,
            request.method,
            self.host,
            request.path,
            self.secret,
            request.params
        )
        request.params = params_with_signature

        if request.method == "POST":
            request.headers["Content-Type"] = "application/json"

            if request.data:
                request.data = json.dumps(request.data)

        return request

    def connect(
        self,
        key: str,
        secret: str,
        proxy_host: str,
        proxy_port: int
    ) -> None:
        """连接REST服务器"""
        self.key = key
        self.secret = secret
        self.host, _ = _split_url(REST_HOST)

        self.init(REST_HOST, proxy_host, proxy_port)
        self.start()

        self.gateway.write_log("REST API启动成功")

        self.query_contract()

    def query_order(self) -> None:
        """查询未成交委托"""
        for currency in self.currencies:
            data = {"symbol": currency}

            self.add_request(
                method="POST",
                path="/api/v1/contract_openorders",
                callback=self.on_query_order,
                data=data,
                extra=currency
            )

    def query_contract(self) -> None:
        """查询合约信息"""
        self.add_request(
            method="GET",
            path="/api/v1/contract_contract_info",
            callback=self.on_query_contract
        )

    def query_history(self, req: HistoryRequest) -> List[BarData]:
        """查询历史数据"""
        history: List[BarData] = []
        count: int = 1999
        start: datetime = req.start
        time_delta: timedelta = TIMEDELTA_MAP[req.interval]

        # 合约名转换
        contract_type: str = symbol_type_map.get(req.symbol, "")
        buf: List[str] = [i for i in req.symbol if not i.isdigit()]
        symbol: str = "".join(buf)

        ws_contract_type: str = CONTRACT_TYPE_MAP[contract_type]
        ws_symbol: str = f"{symbol}_{ws_contract_type}"

        while True:
            # 计算结束时间
            end: datetime = start + time_delta * count

            # 创建查询参数
            params: dict = {
                "symbol": ws_symbol,
                "period": INTERVAL_VT2HUOBIF[req.interval],
                "from": int(start.timestamp()),
                "to": int(end.timestamp())
            }

            resp: Response = self.request(
                "GET",
                "/market/history/kline",
                params=params
            )

            # 如果请求失败则终止循环
            if resp.status_code // 100 != 2:
                msg: str = f"获取历史数据失败，状态码：{resp.status_code}，信息：{resp.text}"
                self.gateway.write_log(msg)
                break
            else:
                data: dict = resp.json()
                if not data:
                    msg: str = f"获取历史数据为空"
                    self.gateway.write_log(msg)
                    break

                buf: List[BarData] = []
                for d in data["data"]:
                    bar: BarData = BarData(
                        symbol=req.symbol,
                        exchange=req.exchange,
                        datetime=generate_datetime(d["id"]),
                        interval=req.interval,
                        volume=d["vol"],
                        open_price=d["open"],
                        high_price=d["high"],
                        low_price=d["low"],
                        close_price=d["close"],
                        gateway_name=self.gateway_name
                    )
                    buf.append(bar)

                history.extend(buf)

                begin: datetime = buf[0].datetime
                end: datetime = buf[-1].datetime
                msg: str = f"获取历史数据成功，{req.symbol} - {req.interval.value}，{begin} - {end}"
                self.gateway.write_log(msg)

                # 更新开始时间
                start: datetime = bar.datetime

                # 如果收到了最后一批数据则终止循环
                if len(buf) < count:
                    break

        return history

    def new_orderid(self) -> str:
        """生成本地委托号"""
        prefix: str = datetime.now().strftime("%Y%m%d%H%M%S")

        self.order_count += 1
        suffix: str = str(self.order_count).rjust(6, "0")

        orderid: str = prefix[2:] + suffix
        return orderid

    def send_order(self, req: OrderRequest) -> str:
        """委托下单"""
        orderid: str = self.new_orderid()
        order: OrderData = req.create_order_data(
            orderid,
            self.gateway_name
        )
        order.datetime = datetime.now(CHINA_TZ)

        data: dict = {
            "contract_code": req.symbol,
            "client_order_id": int(orderid),
            "price": req.price,
            "volume": int(req.volume),
            "direction": DIRECTION_VT2HUOBIF.get(req.direction, ""),
            "offset": OFFSET_VT2HUOBIF.get(req.offset, ""),
            "order_price_type": ORDERTYPE_VT2HUOBIF.get(req.type, ""),
            "lever_rate": 20
        }

        self.add_request(
            method="POST",
            path="/api/v1/contract_order",
            callback=self.on_send_order,
            data=data,
            extra=order,
            on_error=self.on_send_order_error,
            on_failed=self.on_send_order_failed
        )

        self.gateway.on_order(order)
        return order.vt_orderid

    def cancel_order(self, req: CancelRequest) -> None:
        """委托撤单"""
        buf: List[str] = [i for i in req.symbol if not i.isdigit()]

        data: dict = {
            "symbol": "".join(buf),
        }

        orderid: int = int(req.orderid)
        if orderid > 1000000:
            data["client_order_id"] = orderid
        else:
            data["order_id"] = orderid

        self.add_request(
            method="POST",
            path="/api/v1/contract_cancel",
            callback=self.on_cancel_order,
            on_failed=self.on_cancel_order_failed,
            data=data,
            extra=req
        )

    def on_query_order(self, data: dict, request: Request) -> None:
        """未成交委托查询回报"""
        if self.check_error(data, "查询活动委托"):
            return

        for d in data["data"]["orders"]:
            if d["client_order_id"]:
                orderid: int = d["client_order_id"]
            else:
                orderid: int = d["order_id"]

            order: OrderData = OrderData(
                orderid=orderid,
                symbol=d["contract_code"],
                exchange=Exchange.HUOBI,
                price=d["price"],
                volume=d["volume"],
                type=ORDERTYPE_HUOBIF2VT[d["order_price_type"]],
                direction=DIRECTION_HUOBIF2VT[d["direction"]],
                offset=OFFSET_HUOBIF2VT[d["offset"]],
                traded=d["trade_volume"],
                status=STATUS_HUOBIF2VT[d["status"]],
                datetime=generate_datetime(d["created_at"] / 1000),
                gateway_name=self.gateway_name,
            )
            self.gateway.on_order(order)

        self.gateway.write_log(f"{request.extra}活动委托信息查询成功")

    def on_query_contract(self, data: dict, request: Request) -> None:
        """合约信息查询回报"""
        if self.check_error(data, "查询合约"):
            return

        for d in data["data"]:
            self.currencies.add(d["symbol"])

            contract: ContractData = ContractData(
                symbol=d["contract_code"],
                exchange=Exchange.HUOBI,
                name=d["contract_code"],
                pricetick=d["price_tick"],
                size=int(d["contract_size"]),
                min_volume=1,
                product=Product.FUTURES,
                history_data=True,
                gateway_name=self.gateway_name,
            )
            self.gateway.on_contract(contract)

            symbol_type_map[contract.symbol] = d["contract_type"]

        self.gateway.write_log("合约信息查询成功")

        self.query_order()

    def on_send_order(self, data: dict, request: Request) -> None:
        """委托下单回报"""
        order: OrderData = request.extra

        if self.check_error(data, "委托"):
            order.status = Status.REJECTED
            self.gateway.on_order(order)

    def on_send_order_failed(self, status_code: str, request: Request) -> None:
        """委托下单失败服务器报错回报"""
        order: OrderData = request.extra
        order.status = Status.REJECTED
        self.gateway.on_order(order)

        msg: str = f"委托失败，状态码：{status_code}，信息：{request.response.text}"
        self.gateway.write_log(msg)

    def on_send_order_error(
        self, exception_type: type, exception_value: Exception, tb, request: Request
    ) -> None:
        """委托下单回报函数报错回报"""
        order: OrderData = request.extra
        order.status = Status.REJECTED
        self.gateway.on_order(order)

        if not issubclass(exception_type, ConnectionError):
            self.on_error(exception_type, exception_value, tb, request)

    def on_cancel_order(self, data: dict, request: Request) -> None:
        """委托撤单回报"""
        self.check_error(data, "撤单")

    def on_cancel_order_failed(self, status_code: str, request: Request) -> None:
        """委托撤单失败服务器报错回报"""
        msg: str = f"撤单失败，状态码：{status_code}，信息：{request.response.text}"
        self.gateway.write_log(msg)

    def on_error(
        self, exception_type: type, exception_value: Exception, tb, request: Request
    ) -> None:
        """请求触发异常的回调"""
        msg: str = f"触发异常，状态码：{exception_type}，信息：{exception_value}"
        self.gateway.write_log(msg)

        super().on_error(exception_type, exception_value, tb, request)

    def check_error(self, data: dict, func: str = "") -> bool:
        """回报状态检查"""
        if data["status"] != "error":
            return False

        error_code: int = data["err_code"]
        error_msg: str = data["err_msg"]

        self.gateway.write_log(f"{func}请求出错，代码：{error_code}，信息：{error_msg}")
        return True


class HuobiFuturesTradeWebsocketApi(HuobiWebsocketApiBase):
    """火币交割合约交易Websocket API"""

    def __init__(self, gateway: HuobiFuturesGateway):
        """构造函数"""
        super().__init__(gateway)

        self.positions: Dict[str, PositionData] = defaultdict(dict)

    def connect(
        self,
        key: str,
        secret: str,
        proxy_host: str,
        proxy_port: int
    ) -> None:
        """连接Websocket交易频道"""
        super().connect(
            key,
            secret,
            WEBSOCKET_TRADE_HOST,
            proxy_host,
            proxy_port
        )

    def subscribe(self) -> None:
        """订阅委托和资金、持仓推送"""
        req: dict = {
            "op": "sub",
            "topic": f"orders.*"
        }
        self.send_packet(req)

        req: dict = {
            "op": "sub",
            "topic": f"accounts.*"
        }
        self.send_packet(req)

        req: dict = {
            "op": "sub",
            "topic": f"positions.*"
        }
        self.send_packet(req)

    def on_connected(self) -> None:
        """连接成功回报"""
        self.gateway.write_log("交易Websocket API连接成功")
        self.login()

    def on_login(self) -> None:
        """登录成功回报"""
        self.gateway.write_log("交易Websocket API登录成功")
        self.subscribe()

    def on_data(self, packet: dict) -> None:
        """推送数据回报"""
        op: str = packet.get("op", None)
        if op != "notify":
            return

        topic: str = packet["topic"]
        if "orders" in topic:
            self.on_order(packet)
        elif "accounts" in topic:
            self.on_account(packet)
        elif "positions" in topic:
            self.on_position(packet)

    def on_order(self, data: dict) -> None:
        """委托更新推送"""
        if data["client_order_id"]:
            orderid = data["client_order_id"]
        else:
            orderid = data["order_id"]

        order: OrderData = OrderData(
            symbol=data["contract_code"],
            exchange=Exchange.HUOBI,
            orderid=orderid,
            type=ORDERTYPE_HUOBIF2VT[data["order_price_type"]],
            direction=DIRECTION_HUOBIF2VT[data["direction"]],
            offset=OFFSET_HUOBIF2VT[data["offset"]],
            price=data["price"],
            volume=data["volume"],
            traded=data["trade_volume"],
            status=STATUS_HUOBIF2VT[data["status"]],
            datetime=generate_datetime(data["created_at"] / 1000),
            gateway_name=self.gateway_name
        )
        self.gateway.on_order(order)

        # 成交事件推送
        trades: list = data["trade"]
        if not trades:
            return

        for d in trades:
            trade: TradeData = TradeData(
                symbol=order.symbol,
                exchange=Exchange.HUOBI,
                orderid=order.orderid,
                tradeid=str(d["id"]),
                direction=order.direction,
                offset=order.offset,
                price=d["trade_price"],
                volume=d["trade_volume"],
                datetime=generate_datetime(d["created_at"] / 1000),
                gateway_name=self.gateway_name,
            )
            self.gateway.on_trade(trade)

    def on_account(self, data: dict) -> None:
        """资金更新推送"""
        if not data:
            return

        for d in data["data"]:
            account: AccountData = AccountData(
                accountid=d["symbol"],
                balance=d["margin_balance"],
                frozen=d["margin_frozen"],
                gateway_name=self.gateway_name
            )

            self.gateway.on_account(account)

    def on_position(self, data: dict) -> None:
        """持仓更新推送"""
        if not data:
            return

        for d in data["data"]:
            key: str = f"{d['contract_code']}_{d['direction']}"
            position: PositionData = self.positions.get(key, None)

            if not position:
                position: PositionData = PositionData(
                    symbol=d["contract_code"],
                    exchange=Exchange.HUOBI,
                    direction=DIRECTION_HUOBIF2VT[d["direction"]],
                    gateway_name=self.gateway_name
                )
                self.positions[key] = position

            position.volume = d["volume"]
            position.frozen = d["frozen"]
            position.price = d["cost_hold"]
            position.pnl = d["profit"]

        for position in self.positions.values():
            self.gateway.on_position(position)


class HuobiFuturesDataWebsocketApi(HuobiWebsocketApiBase):
    """火币交割合约行情Websocket API"""

    def __init__(self, gateway: HuobiFuturesGateway):
        """构造函数"""
        super().__init__(gateway)

        self.ticks: Dict[str, TickData] = {}
        self.subscribed: Dict[str, SubscribeRequest] = {}

    def connect(
        self,
        key: str,
        secret: str,
        proxy_host: str,
        proxy_port: int
    ) -> None:
        """连接Websocket行情频道"""
        super().connect(
            key,
            secret,
            WEBSOCKET_DATA_HOST,
            proxy_host,
            proxy_port
        )

    def on_connected(self) -> None:
        """连接成功回报"""
        self.gateway.write_log("行情Websocket API连接成功")

        for req in list(self.subscribed.values()):
            self.subscribe(req)

    def subscribe(self, req: SubscribeRequest) -> None:
        """订阅行情"""
        contract_type = symbol_type_map.get(req.symbol, "")
        if not contract_type:
            return

        # 缓存订阅记录
        self.subscribed[req.vt_symbol] = req

        buf: list = [i for i in req.symbol if not i.isdigit()]
        symbol: str = "".join(buf)

        ws_contract_type: str = CONTRACT_TYPE_MAP[contract_type]
        ws_symbol: str = f"{symbol}_{ws_contract_type}"

        # 创建TICK对象
        tick: TickData = TickData(
            symbol=req.symbol,
            name=req.symbol,
            exchange=Exchange.HUOBI,
            datetime=datetime.now(CHINA_TZ),
            gateway_name=self.gateway_name,
        )
        self.ticks[ws_symbol] = tick

        req_dict: dict = {
            "sub": f"market.{ws_symbol}.depth.step0"
        }
        self.send_packet(req_dict)

        req_dict: dict = {
            "sub": f"market.{ws_symbol}.detail"
        }
        self.send_packet(req_dict)

    def on_data(self, packet: dict) -> None:
        """推送数据回报"""
        channel: str = packet.get("ch", None)
        if channel:
            if "depth.step" in channel:
                self.on_market_depth(packet)
            elif "detail" in channel:
                self.on_market_detail(packet)
        elif "err_code" in packet:
            code: int = packet["err_code"]
            msg: str = packet["err_msg"]
            self.gateway.write_log(f"错误代码：{code}, 错误信息：{msg}")

    def on_market_depth(self, data: dict) -> None:
        """行情深度推送 """
        ws_symbol: str = data["ch"].split(".")[1]
        tick: TickData = self.ticks[ws_symbol]
        tick.datetime = generate_datetime(data["ts"] / 1000)

        tick_data: dict = data["tick"]
        if "bids" not in tick_data or "asks" not in tick_data:
            return

        bids: list = tick_data["bids"]
        for n in range(min(5, len(bids))):
            price, volume = bids[n]
            tick.__setattr__("bid_price_" + str(n + 1), float(price))
            tick.__setattr__("bid_volume_" + str(n + 1), float(volume))

        asks: list = tick_data["asks"]
        for n in range(min(5, len(asks))):
            price, volume = asks[n]
            tick.__setattr__("ask_price_" + str(n + 1), float(price))
            tick.__setattr__("ask_volume_" + str(n + 1), float(volume))

        if tick.last_price:
            tick.localtime = datetime.now()
            self.gateway.on_tick(copy(tick))

    def on_market_detail(self, data: dict) -> None:
        """市场细节推送"""
        ws_symbol: str = data["ch"].split(".")[1]
        tick: TickData = self.ticks[ws_symbol]
        tick.datetime = generate_datetime(data["ts"] / 1000)

        tick_data = data["tick"]
        tick.open_price = tick_data["open"]
        tick.high_price = tick_data["high"]
        tick.low_price = tick_data["low"]
        tick.last_price = tick_data["close"]
        tick.volume = tick_data["vol"]

        if tick.bid_price_1:
            tick.localtime = datetime.now()
            self.gateway.on_tick(copy(tick))
