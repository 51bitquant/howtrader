"""
1. 只支持单币种保证金模式
2. 只支持全仓模式
3. 只支持单向持仓模式

"""

import base64
import decimal
from decimal import Decimal
import hashlib
import hmac
import json
import sys
import time
from copy import copy
from datetime import datetime, timedelta
from urllib.parse import urlencode
from typing import Any, Dict, List, Set
from types import TracebackType

from howtrader.trader.constant import (
    Direction,
    Exchange,
    Interval,
    Offset,
    OrderType,
    Product,
    Status
)
from howtrader.trader.gateway import BaseGateway
from howtrader.trader.object import (
    AccountData,
    BarData,
    CancelRequest,
    ContractData,
    HistoryRequest,
    OrderData,
    OrderRequest,
    PositionData,
    SubscribeRequest,
    OrderQueryRequest,
    TickData,
    TradeData
)

from howtrader.api.rest import RestClient, Request, Response
from howtrader.api.websocket import WebsocketClient
from howtrader.trader.constant import LOCAL_TZ
from howtrader.trader.event import EVENT_TIMER
from howtrader.event import Event, EventEngine
from howtrader.trader.setting import SETTINGS

REST_HOST: str = "https://www.okx.com"
PUBLIC_WEBSOCKET_HOST: str = "wss://ws.okx.com:8443/ws/v5/public"
PRIVATE_WEBSOCKET_HOST: str = "wss://ws.okx.com:8443/ws/v5/private"
TEST_PUBLIC_WEBSOCKET_HOST: str = "wss://wspap.okx.com:8443/ws/v5/public?brokerId=9999"
TEST_PRIVATE_WEBSOCKET_HOST: str = "wss://wspap.okx.com:8443/ws/v5/private?brokerId=9999"

# Order status mapping
STATUS_OKX2VT: Dict[str, Status] = {
    "live": Status.NOTTRADED,
    "partially_filled": Status.PARTTRADED,
    "filled": Status.ALLTRADED,
    "canceled": Status.CANCELLED
}

# order type mapping.
ORDERTYPE_OKX2VT: Dict[str, OrderType] = {
    "limit": OrderType.LIMIT,
    "fok": OrderType.FOK,
    "ioc": OrderType.FAK,
    "market": OrderType.TAKER,
    "post_only": OrderType.MAKER,
}
ORDERTYPE_VT2OKX: Dict[OrderType, str] = {v: k for k, v in ORDERTYPE_OKX2VT.items()}

# order side mapping.
DIRECTION_OKX2VT: Dict[str, Direction] = {
    "buy": Direction.LONG,
    "sell": Direction.SHORT
}
DIRECTION_VT2OKX: Dict[Direction, str] = {v: k for k, v in DIRECTION_OKX2VT.items()}

# interval/timeframe mapping.
INTERVAL_VT2OKX: Dict[Interval, str] = {
    Interval.MINUTE: "1m",
    Interval.HOUR: "1H",
    Interval.DAILY: "1D",
}

# product mapping.
PRODUCT_OKX2VT: Dict[str, Product] = {
    "SPOT": Product.SPOT,   # spot
    "SWAP": Product.FUTURES,  # swap
    "FUTURES": Product.FUTURES,  # futures
    # "MARGIN": Product.SPOT,  # margin
}
PRODUCT_VT2OKX: Dict[Product, str] = {v: k for k, v in PRODUCT_OKX2VT.items()}

# symbol/instrument mapping.
symbol_contract_map: Dict[str, ContractData] = {}

# local order set
local_orderids: Set[str] = set()


class OkxGateway(BaseGateway):
    """
    howtrader OKX gateway
    """

    default_name = "OKX"

    default_setting: Dict[str, Any] = {
        "key": "",
        "secret": "",
        "passphrase": "",
        "proxy_host": "",
        "proxy_port": 0,
        "server": ["REAL", "TEST"]
    }

    exchanges: Exchange = [Exchange.OKX]

    def __init__(self, event_engine: EventEngine, gateway_name: str = "OKX") -> None:
        super().__init__(event_engine, gateway_name)

        self.rest_api: "OkxRestApi" = OkxRestApi(self)
        self.ws_public_api: "OkxWebsocketPublicApi" = OkxWebsocketPublicApi(self)
        self.ws_private_api: "OkxWebsocketPrivateApi" = OkxWebsocketPrivateApi(self)

        self.orders: Dict[str, OrderData] = {}
        self.get_server_time_interval: int = 0

    def connect(self, setting: dict) -> None:
        """connect to OKX"""
        key: str = setting["key"]
        secret: str = setting["secret"]
        passphrase: str = setting["passphrase"]
        server: str = setting["server"]

        if not setting["proxy_host"] and isinstance(setting["proxy_host"], str):
            proxy_host: str = setting["proxy_host"]
        else:
            proxy_host: str = ""

        try:
            proxy_port: int = int(setting["proxy_port"])
        except ValueError:
            proxy_port: int = 0

        self.rest_api.connect(
            key,
            secret,
            passphrase,
            proxy_host,
            proxy_port,
            server
        )
        self.ws_public_api.connect(
            proxy_host,
            proxy_port,
            server
        )
        self.ws_private_api.connect(
            key,
            secret,
            passphrase,
            proxy_host,
            proxy_port,
            server
        )

        self.event_engine.unregister(EVENT_TIMER, self.process_timer_event)
        self.event_engine.register(EVENT_TIMER, self.process_timer_event)

    def process_timer_event(self, event: Event) -> None:
        """process the server time update."""
        self.get_server_time_interval += 1
        if self.get_server_time_interval >= SETTINGS.get('update_server_time_interval', 300):
            self.rest_api.query_time()
            self.get_server_time_interval = 0

    def subscribe(self, req: SubscribeRequest) -> None:
        """subscribe to market data."""
        self.ws_public_api.subscribe(req)

    def send_order(self, req: OrderRequest) -> str:
        """send order through private websocket."""
        return self.ws_private_api.send_order(req)

    def query_order(self, req: OrderQueryRequest) -> None:
        """query order status, you can get the order status in on_order method"""
        self.rest_api.query_order(req)

    def cancel_order(self, req: CancelRequest) -> None:
        """cancel order through private websocket."""
        self.ws_private_api.cancel_order(req)

    def query_account(self) -> None:
        """query account."""
        pass

    def query_position(self) -> None:
        """query position."""
        pass

    def query_history(self, req: HistoryRequest) -> List[BarData]:
        """query history kline/candles"""
        return self.rest_api.query_history(req)

    def close(self) -> None:
        """close api"""
        self.rest_api.stop()
        self.ws_public_api.stop()
        self.ws_private_api.stop()

    def on_order(self, order: OrderData) -> None:
        """on order update"""
        last_order: OrderData = self.get_order(order.orderid)
        if not last_order:
            self.orders[order.orderid] = order
            super().on_order(copy(order))

        else:
            traded: Decimal = order.traded - last_order.traded
            if traded < 0:  # filter the order is not in sequence
                return None

            if traded > 0:
                trade: TradeData = TradeData(
                    symbol=order.symbol,
                    exchange=order.exchange,
                    orderid=order.orderid,
                    direction=order.direction,
                    price=order.traded_price,
                    volume=traded,
                    datetime=order.update_time,
                    gateway_name=self.gateway_name,
                )

                super().on_trade(trade)

            if traded == 0 and order.status == last_order.status:
                return None

            self.orders[order.orderid] = order
            super().on_order(copy(order))

    def get_order(self, orderid: str) -> OrderData:
        """get order."""
        return self.orders.get(orderid, None)


class OkxRestApi(RestClient):
    """OKX rest api..."""

    def __init__(self, gateway: OkxGateway) -> None:
        super().__init__()

        self.gateway: OkxGateway = gateway
        self.gateway_name: str = gateway.gateway_name

        self.key: str = ""
        self.secret: str = ""
        self.passphrase: str = ""
        self.simulated: bool = False
        self.time_offset_ms: float = 0

    def sign(self, request: Request) -> Request:
        """signature"""

        now: datetime = datetime.utcnow()
        now = now - timedelta(milliseconds=self.time_offset_ms)
        timestamp: str = now.isoformat("T", "milliseconds") + "Z"
        request.data = json.dumps(request.data)

        if request.params:
            path: str = request.path + "?" + urlencode(request.params)
        else:
            path: str = request.path

        msg: str = timestamp + request.method + path + request.data
        signature: bytes = generate_signature(msg, self.secret)

        # request headers for private api
        request.headers = {
            "OK-ACCESS-KEY": self.key,
            "OK-ACCESS-SIGN": signature.decode(),
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json"
        }

        if self.simulated:
            request.headers["x-simulated-trading"] = "1"

        return request

    def connect(
        self,
        key: str,
        secret: str,
        passphrase: str,
        proxy_host: str,
        proxy_port: int,
        server: str
    ) -> None:
        """connect rest api"""
        self.key = key
        self.secret = secret.encode()
        self.passphrase = passphrase
        self.connect_time = int(datetime.now().strftime("%y%m%d%H%M%S"))

        if server == "TEST":
            self.simulated = True

        self.init(REST_HOST, proxy_host, proxy_port)
        self.start()
        self.gateway.write_log("starting rest api")

        self.query_time()
        self.query_open_orders()
        self.query_instrument()
        self.set_position_mode()

    def set_position_mode(self) -> None:
        self.add_request(
            "POST",
            "/api/v5/account/set-position-mode",
            data={"posMode": "net_mode"},
            callback=self.on_position_mode)

    def on_position_mode(self, packet: dict, request: Request):
        pass

    def query_open_orders(self) -> None:
        """query open orders"""
        self.add_request(
            "GET",
            "/api/v5/trade/orders-pending",
            callback=self.on_query_open_orders,
        )

    def query_time(self) -> None:
        """query server time"""
        self.add_request(
            "GET",
            "/api/v5/public/time",
            callback=self.on_query_time
        )

    def query_order(self, req: OrderQueryRequest) -> None:
        params = {
            "instId": req.symbol
        }

        if req.orderid in local_orderids:
            params["clOrdId"] = req.orderid
        else:
            params["ordId"] = req.orderid

        self.add_request(
            "GET",
            "/api/v5/trade/order",
            params=params,
            callback=self.on_query_order,
        )

    def on_query_order(self, packet: dict, request: Request) -> None:
        # print("query order by restapi: ")
        # print(packet)

        order_datas = packet.get('data', [])
        for order_info in order_datas:
            order: OrderData = parse_order_data(
                order_info,
                self.gateway_name
            )
            self.gateway.on_order(order)

        self.gateway.write_log("query order successfully.")

    def on_query_open_orders(self, packet: dict, request: Request) -> None:
        """on query open orders successfully callback"""
        order_datas = packet.get('data', [])
        for order_info in order_datas:
            order: OrderData = parse_order_data(
                order_info,
                self.gateway_name
            )
            self.gateway.on_order(order)

        self.gateway.write_log("query open orders successfully.")

    def query_instrument(self) -> None:
        """query symbols/instruments"""
        for inst_type in PRODUCT_OKX2VT.keys():
            self.add_request(
                "GET",
                "/api/v5/public/instruments",
                callback=self.on_query_instrument,
                params={"instType": inst_type}
            )

    def on_query_time(self, packet: dict, request: Request) -> None:
        server_ts: float = float(packet["data"][0]["ts"])
        local_ts: float = float(time.time() * 1000)
        self.time_offset_ms: float = local_ts - server_ts

        server_dt: datetime = datetime.fromtimestamp(server_ts / 1000)
        local_dt: datetime = datetime.fromtimestamp(local_ts/1000)
        msg: str = f"server time: {server_dt}, local time: {local_dt}"
        self.gateway.write_log(msg)

    def on_query_instrument(self, packet: dict, request: Request) -> None:
        """on query symbols/instruments"""
        data: list = packet["data"]
        for d in data:
            symbol: str = d["instId"]
            product: Product = PRODUCT_OKX2VT[d["instType"]]
            net_position: bool = True

            if not d["ctMult"]:
                size: Decimal = Decimal("1")
            else:
                size: Decimal = Decimal(d["ctMult"])

            contract: ContractData = ContractData(
                symbol=symbol,
                exchange=Exchange.OKX,
                name=symbol,
                product=product,
                size=size,
                pricetick=Decimal(d["tickSz"]),  # price
                min_volume=Decimal(d["lotSz"]),  # volume precision
                min_size=Decimal(d["minSz"]),
                history_data=True,
                net_position=net_position,
                gateway_name=self.gateway_name,
            )

            symbol_contract_map[contract.symbol] = contract
            self.gateway.on_contract(contract)

        if len(data):
            self.gateway.write_log(f"query {d['instType']} market contract successfully.")

    def on_error(
        self,
        exception_type: type,
        exception_value: Exception,
        tb: TracebackType,
        request: Request
    ) -> None:
        """exception callback"""
        msg: str = f"exception, code: {exception_type}, msg: {exception_value}"
        self.gateway.write_log(msg)

        sys.stderr.write(
            self.exception_detail(exception_type, exception_value, tb, request)
        )

    def query_history(self, req: HistoryRequest) -> List[BarData]:
        """query kline/candles data"""
        buf: Dict[datetime, BarData] = {}
        end_time: str = str(int(req.end.timestamp()//60) * 60 * 1000)
        start_ts: int = int(req.start.timestamp()//60) * 60 * 1000  # ts in millisecond
        path: str = "/api/v5/market/candles"

        while True:
            params: dict = {
                "instId": req.symbol,
                "bar": INTERVAL_VT2OKX[req.interval],
                "limit": 300,
                "after": end_time
            }

            resp: Response = self.request(
                "GET",
                path,
                params=params
            )

            if resp.status_code // 100 != 2:
                msg = f"request failed，code：{resp.status_code} msg：{resp.text}"
                self.gateway.write_log(msg)
                break
            else:
                data: dict = resp.json()

                if not data["data"]:
                    m = data["msg"]
                    msg = f"request historical candles failed: {m}"
                    self.gateway.write_log(msg)
                    break

                for bar_list in data["data"]:
                    ts, o, h, l, c, vol, _, _, confirmed = bar_list
                    if confirmed:
                        dt = parse_timestamp(ts)
                        bar: BarData = BarData(
                            symbol=req.symbol,
                            exchange=req.exchange,
                            datetime=dt,
                            interval=req.interval,
                            volume=float(vol),
                            open_price=float(o),
                            high_price=float(h),
                            low_price=float(l),
                            close_price=float(c),
                            gateway_name=self.gateway_name
                        )
                        buf[bar.datetime] = bar

                begin: str = data["data"][-1][0]
                end: str = data["data"][0][0]
                end_time = begin
                msg: str = f"request historical candles，{req.symbol} - {req.interval.value}，{parse_timestamp(begin)}" \
                           f" - {parse_timestamp(end)}"
                self.gateway.write_log(msg)
                if int(begin) < start_ts:
                    break

        index: List[datetime] = list(buf.keys())
        index.sort()
        history: List[BarData] = [buf[i] for i in index]
        return history


class OkxWebsocketPublicApi(WebsocketClient):
    def __init__(self, gateway: OkxGateway) -> None:
        super().__init__()
        self.gateway: OkxGateway = gateway
        self.gateway_name: str = gateway.gateway_name

        self.subscribed: Dict[str, SubscribeRequest] = {}
        self.ticks: Dict[str, TickData] = {}

        self.callbacks: Dict[str, callable] = {
            "tickers": self.on_ticker,
            "books5": self.on_depth
        }

    def connect(
        self,
        proxy_host: str,
        proxy_port: int,
        server: str
    ) -> None:
        self.receive_timeout = 60
        if server == "REAL":
            # ping interval should be less than 30
            self.init(host=PUBLIC_WEBSOCKET_HOST, proxy_host=proxy_host, proxy_port=proxy_port, ping_interval=20)
        else:
            self.init(host=TEST_PUBLIC_WEBSOCKET_HOST, proxy_host=proxy_host, proxy_port=proxy_port, ping_interval=20)

        self.start()

    def subscribe(self, req: SubscribeRequest) -> None:
        """subscribe market data"""
        self.subscribed[req.vt_symbol] = req

        tick: TickData = TickData(
            symbol=req.symbol,
            exchange=req.exchange,
            name=req.symbol,
            datetime=datetime.now(LOCAL_TZ),
            gateway_name=self.gateway_name,
        )
        self.ticks[req.symbol] = tick

        args: list = []
        for channel in ["tickers", "books5"]:
            args.append({
                "channel": channel,
                "instId": req.symbol
            })

        req: dict = {
            "op": "subscribe",
            "args": args
        }
        self.send_packet(req)

    def on_connected(self) -> None:
        self.gateway.write_log("OKX Websocket Public API connected")

        for req in list(self.subscribed.values()):
            self.subscribe(req)

    def on_disconnected(self) -> None:
        self.gateway.write_log("OKX Websocket Public API disconnected")

    def on_packet(self, packet: dict) -> None:
        if "event" in packet:
            event: str = packet["event"]
            if event == "subscribe":
                return
            elif event == "error":
                code: str = packet["code"]
                msg: str = packet["msg"]
                self.gateway.write_log(f"Websocket Public API Exception, code：{code}, msg：{msg}")
        else:
            channel: str = packet["arg"]["channel"]
            callback: callable = self.callbacks.get(channel, None)

            if callback:
                data: list = packet["data"]
                callback(data)

    def on_error(self, exception_type: type, exception_value: Exception, tb) -> None:
        """on error"""
        msg: str = f"public channels raise exceptions, type: {exception_type}, msg: {exception_value}"
        self.gateway.write_log(msg)

        sys.stderr.write(
            self.exception_detail(exception_type, exception_value, tb)
        )

    def on_ticker(self, data: list) -> None:
        """on tick"""
        for d in data:
            tick: TickData = self.ticks[d["instId"]]
            tick.last_price = float(d["last"])
            tick.open_price = float(d["open24h"])
            tick.high_price = float(d["high24h"])
            tick.low_price = float(d["low24h"])
            tick.volume = float(d["vol24h"])

    def on_depth(self, data: list) -> None:
        """on depth/orderbook"""
        for d in data:
            tick: TickData = self.ticks[d["instId"]]
            bids: list = d["bids"]
            asks: list = d["asks"]

            for n in range(min(5, len(bids))):
                price, volume, _, _ = bids[n]
                tick.__setattr__("bid_price_%s" % (n + 1), float(price))
                tick.__setattr__("bid_volume_%s" % (n + 1), float(volume))

            for n in range(min(5, len(asks))):
                price, volume, _, _ = asks[n]
                tick.__setattr__("ask_price_%s" % (n + 1), float(price))
                tick.__setattr__("ask_volume_%s" % (n + 1), float(volume))

            tick.datetime = parse_timestamp(d["ts"])
            self.gateway.on_tick(copy(tick))


class OkxWebsocketPrivateApi(WebsocketClient):
    """account websocket"""

    def __init__(self, gateway: OkxGateway) -> None:
        super().__init__()

        self.gateway: OkxGateway = gateway
        self.gateway_name: str = gateway.gateway_name

        self.key: str = ""
        self.secret: str = ""
        self.passphrase: str = ""

        self.reqid: int = 0
        self.order_count: int = 0
        self.connect_time: int = 0

        self.callbacks: Dict[str, callable] = {
            "login": self.on_login,
            "orders": self.on_order,
            "account": self.on_account,
            "positions": self.on_position,
            "order": self.on_send_order,
            "cancel-order": self.on_cancel_order,
            "error": self.on_api_error
        }

        self.reqid_order_map: Dict[str, OrderData] = {}

    def connect(
        self,
        key: str,
        secret: str,
        passphrase: str,
        proxy_host: str,
        proxy_port: int,
        server: str
    ) -> None:
        self.key = key
        self.secret = secret.encode()
        self.passphrase = passphrase

        self.connect_time = int(datetime.now().strftime("%y%m%d%H%M%S"))
        self.receive_timeout = 60
        if server == "REAL":
            # ping interval should be less than 30
            self.init(host=PRIVATE_WEBSOCKET_HOST, proxy_host=proxy_host, proxy_port=proxy_port, ping_interval=20)
        else:
            self.init(host=TEST_PRIVATE_WEBSOCKET_HOST, proxy_host=proxy_host, proxy_port=proxy_port, ping_interval=20)

        self.start()

    def on_connected(self) -> None:
        """connected callback"""
        self.gateway.write_log("Websocket Private API connected")
        self.login()

    def on_disconnected(self) -> None:
        """disconnected callback"""
        self.gateway.write_log("Websocket Private API disconnected")

    def on_packet(self, packet: dict) -> None:
        """"""
        if "event" in packet:
            cb_name: str = packet["event"]
        elif "op" in packet:
            cb_name: str = packet["op"]
        else:
            cb_name: str = packet.get("arg", {}).get("channel", "")

        callback: callable = self.callbacks.get(cb_name, None)
        if callback:
            callback(packet)

    def on_error(self, exception_type: type, exception_value: Exception, tb) -> None:
        """on error callback"""
        msg: str = f"private websocket exception, type: {exception_type}, msg: {exception_value}"
        self.gateway.write_log(msg)

        sys.stderr.write(
            self.exception_detail(exception_type, exception_value, tb)
        )

    def on_api_error(self, packet: dict) -> None:
        """on api error event"""
        code: str = packet.get("code", "")
        msg: str = packet.get("msg", "")
        self.gateway.write_log(f"Websocket Private API request failed, code: {code}, msg: {msg}")

    def on_login(self, packet: dict) -> None:
        """"""
        if packet.get("code", None) == '0':
            self.gateway.write_log("Websocket Private API login successfully.")
            self.subscribe_topic()
        else:
            self.gateway.write_log("Websocket Private API login failed.")

    def on_order(self, packet: dict) -> None:
        """on order"""
        data: list = packet.get("data", [])
        for d in data:
            order: OrderData = parse_order_data(d, self.gateway_name)
            if order.type == OrderType.TAKER and order.status == Status.ALLTRADED and d.get("fillSz") == "0":
                order.traded = order.volume

            self.gateway.on_order(order)

            # if d["fillSz"] == "0":
            #     return None
            # # 这里处理的数据不对，需要进行处理....
            # # 将成交数量四舍五入到正确精度
            # trade_volume: float = float(d["fillSz"])
            # contract: ContractData = symbol_contract_map.get(order.symbol, None)
            # if contract:
            #     trade_volume = round_to(trade_volume, contract.min_volume)
            #
            # trade: TradeData = TradeData(
            #     symbol=order.symbol,
            #     exchange=order.exchange,
            #     orderid=order.orderid,
            #     tradeid=d["tradeId"],
            #     direction=order.direction,
            #     offset=order.offset,
            #     price=float(d["fillPx"]),
            #     volume=trade_volume,
            #     datetime=parse_timestamp(d["uTime"]),
            #     gateway_name=self.gateway_name,
            # )
            # self.gateway.on_trade(trade)

    def on_account(self, packet: dict) -> None:
        """on account update"""

        account: list = packet.get("data", [])
        if len(account) == 0:
            return None

        buf: dict = account[0]
        for detail in buf["details"]:
            account: AccountData = AccountData(
                accountid=detail["ccy"],
                balance=float(detail["eq"]),
                gateway_name=self.gateway_name,
            )

            account.available = float(detail["availEq"]) if len(detail["availEq"]) != 0 else 0.0
            account.frozen = account.balance - account.available
            self.gateway.on_account(account)

    def on_position(self, packet: dict) -> None:
        """on position."""
        data: list = packet.get("data", [])
        for d in data:
            symbol: str = d["instId"]
            pos: float = float(d.get("pos", "0"))
            price: float = get_float_value(d, "avgPx")
            pnl: float = get_float_value(d, "upl")

            position: PositionData = PositionData(
                symbol=symbol,
                exchange=Exchange.OKX,
                direction=Direction.NET,
                volume=pos,
                price=price,
                pnl=pnl,
                gateway_name=self.gateway_name,
            )
            self.gateway.on_position(position)

    def on_send_order(self, packet: dict) -> None:
        """on send order"""
        data: list = packet.get("data", [])
        if packet.get("code", None) != "0":
            if not data:
                order: OrderData = copy(self.reqid_order_map.get(packet["id"], None))
                if order:
                    order.status = Status.REJECTED
                    self.gateway.on_order(order)
                return None

        for d in data:
            code: str = d.get("sCode", None)
            if code == "0":
                return None

            orderid: str = d.get("clOrdId", "")
            if not orderid:
                orderid: str = d.get("ordId", "")

            order: OrderData = copy(self.gateway.get_order(orderid))
            msg: str = d.get("sMsg", "")

            if order:
                order.status = Status.REJECTED
                order.rejected_reason = msg
                self.gateway.on_order(order)

            self.gateway.write_log(f"send order failed, code: {code}, msg: {msg}")

    def on_cancel_order(self, packet: dict) -> None:
        """on cancel order."""
        # print("on cancel the order")
        # print(packet)
        if packet["code"] != "0":
            code: str = packet.get("code", "")
            msg: str = packet.get("msg", "")
            self.gateway.write_log(f"cancel order failed, code: {code}, msg: {msg}")
            return None

        data: list = packet.get("data", [])
        for d in data:
            if d.get('sCode', "") == "0":
                return None

            msg: str = d["sMsg"]
            self.gateway.write_log(f"cancel order failed, code: {d['sCode']}, msg: {msg}")

    def login(self) -> None:
        """login to private websocket channel."""
        now: float = time.time()
        now = now - self.gateway.rest_api.time_offset_ms/1000
        timestamp: str = str(now)
        msg: str = timestamp + "GET" + "/users/self/verify"
        signature: bytes = generate_signature(msg, self.secret)

        okx_req: dict = {
            "op": "login",
            "args":
            [
                {
                    "apiKey": self.key,
                    "passphrase": self.passphrase,
                    "timestamp": timestamp,
                    "sign": signature.decode("utf-8")
                }
            ]
        }
        self.send_packet(okx_req)

    def subscribe_topic(self) -> None:
        """subscribe orders/account/positions after login success."""
        okx_req: dict = {
            "op": "subscribe",
            "args": [
                {
                    "channel": "orders",
                    "instType": "ANY"
                },
                {
                    "channel": "account"
                },
                {
                    "channel": "positions",
                    "instType": "ANY"
                },
            ]
        }
        self.send_packet(okx_req)

    def send_order(self, req: OrderRequest) -> str:
        """send order"""
        if req.type not in ORDERTYPE_VT2OKX:
            self.gateway.write_log(f"send order failed，order type: {req.type.value} unsupported")
            return ""

        contract: ContractData = symbol_contract_map.get(req.symbol, None)
        if not contract:
            self.gateway.write_log(f"send order failed, trading symbol not found: {req.symbol}")
            return ""

        self.order_count += 1
        count_str = str(self.order_count).rjust(6, "0")
        orderid = f"{self.connect_time}{count_str}"

        args: dict = {
            "instId": req.symbol,
            "clOrdId": orderid,
            "side": DIRECTION_VT2OKX[req.direction],
            "ordType": ORDERTYPE_VT2OKX[req.type],
            "px": str(req.price),
            "sz": str(req.volume)
        }

        if contract.product == Product.SPOT:
            args["tdMode"] = "cash"
        else:
            args["tdMode"] = "cross"

        self.reqid += 1
        okx_req: dict = {
            "id": str(self.reqid),
            "op": "order",
            "args": [args]
        }
        self.send_packet(okx_req)

        order: OrderData = req.create_order_data(orderid, self.gateway_name)
        self.reqid_order_map[str(self.reqid)] = order
        self.gateway.on_order(order)
        return order.vt_orderid

    def cancel_order(self, req: CancelRequest) -> None:
        """cancel order"""
        args: dict = {"instId": req.symbol}

        if req.orderid in local_orderids:
            args["clOrdId"] = req.orderid
        else:
            args["ordId"] = req.orderid

        self.reqid += 1
        okx_req: dict = {
            "id": str(self.reqid),
            "op": "cancel-order",
            "args": [args]
        }
        self.send_packet(okx_req)


def generate_signature(msg: str, secret_key: str) -> bytes:
    """生成签名"""
    return base64.b64encode(hmac.new(secret_key, msg.encode(), hashlib.sha256).digest())


def generate_timestamp() -> str:
    now: datetime = datetime.utcnow()
    timestamp: str = now.isoformat("T", "milliseconds")
    return timestamp + "Z"


def parse_timestamp(timestamp: str) -> datetime:
    try:
        ts = float(timestamp)
        dt: datetime = datetime.fromtimestamp(ts / 1000)
        return dt.replace(tzinfo=LOCAL_TZ)
    except ValueError:
        return datetime.now(tz=LOCAL_TZ)


def get_float_value(data: dict, key: str) -> float:
    """utility for get float value from empty str"""
    data_str: str = data.get(key, "")
    if not data_str:
        return 0.0
    try:
        return float(data_str)
    except ValueError:
        return 0.0


def parse_decimal(value: str) -> Decimal:
    try:
        return Decimal(value)
    except decimal.InvalidOperation:
        return Decimal("0")


def parse_order_data(data: dict, gateway_name: str) -> OrderData:
    """parse order data into OrderData"""
    order_id: str = data["clOrdId"]
    if order_id:
        local_orderids.add(order_id)
    else:
        order_id: str = data["ordId"]

    order: OrderData = OrderData(
        symbol=data["instId"],
        exchange=Exchange.OKX,
        type=ORDERTYPE_OKX2VT[data.get("ordType", "limit")],
        orderid=order_id,
        direction=DIRECTION_OKX2VT[data["side"]],
        offset=Offset.NONE,
        traded=parse_decimal(data.get("accFillSz")),
        price=parse_decimal(data.get("px")),
        volume=parse_decimal(data.get("sz")),
        traded_price=parse_decimal(data.get("avgPx")),
        datetime=parse_timestamp(data.get("cTime")),
        update_time=parse_timestamp(data.get("uTime")),
        status=STATUS_OKX2VT[data.get("state", "canceled")],
        gateway_name=gateway_name,
    )
    return order

