"""
1. only support one-way Mode position

"""

import urllib
import hashlib
import hmac
import time
from copy import copy
from datetime import datetime, timedelta
from enum import Enum
from threading import Lock
from typing import Any, Dict, List, Tuple
import pytz
from decimal import Decimal

from requests.exceptions import SSLError
from howtrader.trader.constant import (
    Direction,
    Exchange,
    Product,
    Status,
    OrderType,
    Interval
)
from howtrader.trader.gateway import BaseGateway
from howtrader.trader.object import (
    TickData,
    OrderData,
    TradeData,
    AccountData,
    OrderQueryRequest,
    KlineRequest,
    ContractData,
    PositionData,
    BarData,
    OrderRequest,
    CancelRequest,
    SubscribeRequest,
    HistoryRequest
)
from howtrader.trader.event import EVENT_TIMER
from howtrader.event import Event, EventEngine

from howtrader.api.rest import Request, RestClient, Response
from howtrader.api.websocket import WebsocketClient

# Asia/Shanghai timezone
CHINA_TZ = pytz.timezone("Asia/Shanghai")

# rest api host
F_REST_HOST: str = "https://fapi.binance.com"

# ws api host
F_WEBSOCKET_TRADE_HOST: str = "wss://fstream.binance.com/ws/"
F_WEBSOCKET_DATA_HOST: str = "wss://fstream.binance.com/stream"


# Order status map
STATUS_BINANCES2VT: Dict[str, Status] = {
    "NEW": Status.NOTTRADED,
    "PARTIALLY_FILLED": Status.PARTTRADED,
    "FILLED": Status.ALLTRADED,
    "CANCELED": Status.CANCELLED,
    "REJECTED": Status.REJECTED,
    "EXPIRED": Status.CANCELLED
}

# order type map
ORDERTYPE_VT2BINANCES: Dict[OrderType, Tuple[str, str]] = {
    OrderType.LIMIT: ("LIMIT", "GTC"),
    OrderType.MARKET: ("MARKET", "GTC"),
    OrderType.FAK: ("LIMIT", "IOC"),
    OrderType.FOK: ("LIMIT", "FOK"),
}
ORDERTYPE_BINANCES2VT: Dict[Tuple[str, str], OrderType] = {v: k for k, v in ORDERTYPE_VT2BINANCES.items()}

# sell/buy direction map
DIRECTION_VT2BINANCES: Dict[Direction, str] = {
    Direction.LONG: "BUY",
    Direction.SHORT: "SELL"
}
DIRECTION_BINANCES2VT: Dict[str, Direction] = {v: k for k, v in DIRECTION_VT2BINANCES.items()}

# data time frame map
INTERVAL_VT2BINANCES: Dict[Interval, str] = {
    Interval.MINUTE: "1m",
    Interval.HOUR: "1h",
    Interval.DAILY: "1d",
}

# time delta map
TIMEDELTA_MAP: Dict[Interval, timedelta] = {
    Interval.MINUTE: timedelta(minutes=1),
    Interval.HOUR: timedelta(hours=1),
    Interval.DAILY: timedelta(days=1),
}

# contract symbol map
symbol_contract_map: Dict[str, ContractData] = {}


# signature
class Security(Enum):
    NONE: int = 0
    SIGNED: int = 1
    API_KEY: int = 2


class BinanceUsdtGateway(BaseGateway):
    """
    Binance USDT/BUSD future gateway
    """

    default_name: str = "BINANCE_USDT"

    default_setting: Dict[str, Any] = {
        "key": "",
        "secret": "",
        "proxy_host": "",
        "proxy_port": 0,
    }

    exchanges: Exchange = [Exchange.BINANCE]

    def __init__(self, event_engine: EventEngine, gateway_name: str) -> None:
        """init"""
        super().__init__(event_engine, gateway_name)

        self.trade_ws_api: "BinanceUsdtTradeWebsocketApi" = BinanceUsdtTradeWebsocketApi(self)
        self.market_ws_api: "BinanceUsdtDataWebsocketApi" = BinanceUsdtDataWebsocketApi(self)
        self.rest_api: "BinanceUsdtRestApi" = BinanceUsdtRestApi(self)

        self.orders: Dict[str, OrderData] = {}

    def connect(self, setting: dict) -> None:
        """connect exchange api"""
        key: str = setting["key"]
        secret: str = setting["secret"]

        if isinstance(setting["proxy_host"], str):
            proxy_host: str = setting["proxy_host"]
        else:
            proxy_host: str = ""

        if isinstance(setting["proxy_port"], int):
            proxy_port: int = setting["proxy_port"]
        else:
            proxy_port: int = 0

        self.rest_api.connect(key, secret, proxy_host, proxy_port)
        self.market_ws_api.connect(proxy_host, proxy_port)

        self.event_engine.register(EVENT_TIMER, self.process_timer_event)

    def subscribe(self, req: SubscribeRequest) -> None:
        """subscribe data"""
        self.market_ws_api.subscribe(req)

    def send_order(self, req: OrderRequest) -> str:
        """send/place order"""
        return self.rest_api.send_order(req)

    def cancel_order(self, req: CancelRequest) -> None:
        """cancel order"""
        self.rest_api.cancel_order(req)

    def query_order(self, req: OrderQueryRequest) -> None:
        """query order status, you can get the order status in on_order method"""
        self.rest_api.query_order(req)

    def query_account(self) -> None:
        """query account"""
        self.rest_api.query_account()

    def query_position(self) -> None:
        """query position"""
        self.rest_api.query_position()

    def query_kline(self, req: KlineRequest) -> None:
        pass

    def query_history(self, req: HistoryRequest) -> List[BarData]:
        """query historical kline data"""
        return self.rest_api.query_history(req)

    def close(self) -> None:
        """close api connection"""
        self.rest_api.stop()
        self.trade_ws_api.stop()
        self.market_ws_api.stop()

    def process_timer_event(self, event: Event) -> None:
        """process the listen key update"""
        self.rest_api.keep_user_stream()

    def on_order(self, order: OrderData) -> None:
        """on order update"""
        order.update_time = generate_datetime(time.time() * 1000)
        super().on_order(copy(order))
        last_order: OrderData = self.get_order(order.orderid)
        if not last_order:
            self.orders[order.orderid] = copy(order)
        else:
            traded: Decimal = order.traded - last_order.traded
            if traded >= 0:
                self.orders[order.orderid] = copy(order)

            if traded > 0:
                trade: TradeData = TradeData(
                    symbol=order.symbol,
                    exchange=order.exchange,
                    orderid=order.orderid,
                    direction=order.direction,
                    price=order.price,
                    volume=traded,
                    datetime=order.update_time,
                    gateway_name=self.gateway_name,
                )

                super().on_trade(trade)

    def get_order(self, orderid: str) -> OrderData:
        """get order by order id"""
        return self.orders.get(orderid, None)


class BinanceUsdtRestApi(RestClient):
    """Binance USDT/BUSD future rest api"""

    def __init__(self, gateway: BinanceUsdtGateway) -> None:
        """init"""
        super().__init__()

        self.gateway: BinanceUsdtGateway = gateway
        self.gateway_name: str = gateway.gateway_name

        self.trade_ws_api: BinanceUsdtTradeWebsocketApi = self.gateway.trade_ws_api

        self.key: str = ""
        self.secret: str = ""

        self.user_stream_key: str = ""
        self.keep_alive_count: int = 0
        self.recv_window: int = 5000
        self.time_offset: int = 0

        self.order_count: int = 1_000_000
        self.order_count_lock: Lock = Lock()
        self.connect_time: int = 0

    def sign(self, request: Request) -> Request:
        """generate signature for private api"""
        security: Security = request.data["security"]
        if security == Security.NONE:
            request.data = None
            return request

        if request.params:
            path: str = request.path + "?" + urllib.parse.urlencode(request.params)
        else:
            request.params = dict()
            path: str = request.path

        if security == Security.SIGNED:
            timestamp: int = int(time.time() * 1000)

            if self.time_offset > 0:
                timestamp -= abs(self.time_offset)
            elif self.time_offset < 0:
                timestamp += abs(self.time_offset)

            request.params["timestamp"] = timestamp

            query: str = urllib.parse.urlencode(sorted(request.params.items()))
            signature: bytes = hmac.new(self.secret, query.encode(
                "utf-8"), hashlib.sha256).hexdigest()

            query += "&signature={}".format(signature)
            path: str = request.path + "?" + query

        request.path = path
        request.params = {}
        request.data = {}

        # request headers
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "X-MBX-APIKEY": self.key,
            "Connection": "close"
        }

        if security in [Security.SIGNED, Security.API_KEY]:
            request.headers = headers

        return request

    def connect(
            self,
            key: str,
            secret: str,
            proxy_host: str,
            proxy_port: int
    ) -> None:
        """connect rest api"""
        self.key = key
        self.secret = secret.encode()
        self.proxy_port = proxy_port
        self.proxy_host = proxy_host

        self.connect_time = (
                int(datetime.now().strftime("%y%m%d%H%M%S")) * self.order_count
        )

        self.init(F_REST_HOST, proxy_host, proxy_port)

        self.start()

        self.gateway.write_log("start connecting rest api")

        self.query_time()
        self.query_account()
        self.query_position()
        self.query_orders()
        self.query_contract()
        self.start_user_stream()

    def query_time(self) -> None:
        """query server time"""
        data: dict = {
            "security": Security.NONE
        }

        path: str = "/fapi/v1/time"

        self.add_request(
            "GET",
            path,
            callback=self.on_query_time,
            data=data
        )

    def query_account(self) -> None:
        """query account data"""
        data: dict = {"security": Security.SIGNED}

        path: str = "/fapi/v1/account"

        self.add_request(
            method="GET",
            path=path,
            callback=self.on_query_account,
            data=data
        )

    def query_position(self) -> None:
        """query position"""
        data: dict = {"security": Security.SIGNED}

        path: str = "/fapi/v2/positionRisk"

        self.add_request(
            method="GET",
            path=path,
            callback=self.on_query_position,
            data=data
        )

    def query_order(self, req: OrderQueryRequest) -> None:
        """query specific order with orderid"""
        data = {
            "security": Security.SIGNED
        }

        params = {
            "symbol": req.symbol,
            "origClientOrderId": req.orderid
        }

        path = "/fapi/v1/order"

        self.add_request(
            method="GET",
            path=path,
            callback=self.on_query_order,
            params=params,
            data=data,
            extra=req
        )

    def query_orders(self) -> None:
        """query open orders"""
        data: dict = {"security": Security.SIGNED}

        path: str = "/fapi/v1/openOrders"

        self.add_request(
            method="GET",
            path=path,
            callback=self.on_query_orders,
            data=data
        )

    def query_contract(self) -> None:
        """query contract detail or symbol detail"""
        data: dict = {
            "security": Security.NONE
        }

        path: str = "/fapi/v1/exchangeInfo"

        self.add_request(
            method="GET",
            path=path,
            callback=self.on_query_contract,
            data=data
        )

    def _new_order_id(self) -> int:
        """generate customized order id"""
        with self.order_count_lock:
            self.order_count += 1
            return self.order_count

    def send_order(self, req: OrderRequest) -> str:
        """send/place order"""
        orderid: str = "x-cLbi5uMH" + str(self.connect_time + self._new_order_id())

        # create OrderData object
        order: OrderData = req.create_order_data(
            orderid,
            self.gateway_name
        )
        self.gateway.on_order(order)

        data: dict = {
            "security": Security.SIGNED
        }

        # order request parameters
        params: dict = {
            "symbol": req.symbol,
            "side": DIRECTION_VT2BINANCES[req.direction],
            "quantity": req.volume,
            "newClientOrderId": orderid,
        }

        if req.type == OrderType.MARKET:
            params["type"] = "MARKET"
        else:
            order_type, time_condition = ORDERTYPE_VT2BINANCES[req.type]
            params["type"] = order_type
            params["timeInForce"] = time_condition
            params["price"] = req.price

        path: str = "/fapi/v1/order"

        self.add_request(
            method="POST",
            path=path,
            callback=self.on_send_order,
            data=data,
            params=params,
            extra=order,
            on_error=self.on_send_order_error,
            on_failed=self.on_send_order_failed
        )

        return order.vt_orderid

    def cancel_order(self, req: CancelRequest) -> None:
        """cancel order"""
        data: dict = {
            "security": Security.SIGNED
        }

        params: dict = {
            "symbol": req.symbol,
            "origClientOrderId": req.orderid
        }

        path: str = "/fapi/v1/order"

        order: OrderData = self.gateway.get_order(req.orderid)

        self.add_request(
            method="DELETE",
            path=path,
            callback=self.on_cancel_order,
            params=params,
            data=data,
            on_failed=self.on_cancel_failed,
            extra=order
        )

    def start_user_stream(self) -> None:
        """post listen key"""
        data: dict = {
            "security": Security.API_KEY
        }

        path: str = "/fapi/v1/listenKey"

        self.add_request(
            method="POST",
            path=path,
            callback=self.on_start_user_stream,
            on_failed=self.on_start_user_stream_failed,
            on_error=self.on_start_user_stream_eror,
            data=data
        )

    def keep_user_stream(self) -> None:
        """extend listenKey expire time"""
        self.keep_alive_count += 1
        if self.keep_alive_count < 1200:
            return None
        self.keep_alive_count = 0

        data: dict = {
            "security": Security.API_KEY
        }

        params: dict = {
            "listenKey": self.user_stream_key
        }

        path: str = "/fapi/v1/listenKey"

        self.add_request(
            method="PUT",
            path=path,
            callback=self.on_keep_user_stream,
            params=params,
            data=data,
            on_failed=self.on_keep_user_strea_failed,
            on_error=self.on_keep_user_stream_error
        )

    def on_query_time(self, data: dict, request: Request) -> None:
        """query server time callback"""
        local_time: int = int(time.time() * 1000)
        server_time: int = int(data["serverTime"])
        self.time_offset: int = local_time - server_time

    def on_query_account(self, data: dict, request: Request) -> None:
        """query account callback"""
        for asset in data["assets"]:
            account: AccountData = AccountData(
                accountid=asset["asset"],
                balance=float(asset["walletBalance"]),
                frozen=float(asset["maintMargin"]),
                gateway_name=self.gateway_name
            )

            # if account.balance:
            self.gateway.on_account(account)

        self.gateway.write_log("query account successfully")

    def on_query_position(self, data: list, request: Request) -> None:
        """query position callback"""
        for d in data:
            position: PositionData = PositionData(
                symbol=d["symbol"],
                exchange=Exchange.BINANCE,
                direction=Direction.NET,
                volume=float(d["positionAmt"]),
                price=float(d["entryPrice"]),
                pnl=float(d["unRealizedProfit"]),
                gateway_name=self.gateway_name,
            )

            # if position.volume:
            volume = d["positionAmt"]
            if '.' in volume:
                position.volume = float(d["positionAmt"])
            else:
                position.volume = int(d["positionAmt"])

            self.gateway.on_position(position)

        self.gateway.write_log("query position successfully")

    def on_query_order(self, data:dict, request: Request) -> None:

        key = (data["type"], data["timeInForce"])
        order_type = ORDERTYPE_BINANCES2VT.get(key, OrderType.LIMIT)
        # if not order_type:
        #     return
        order = OrderData(
            orderid=data["clientOrderId"],
            symbol=data["symbol"],
            exchange=Exchange.BINANCE,
            price=Decimal(str(data["price"])),
            volume=Decimal(str(data["origQty"])),
            type=order_type,
            direction=DIRECTION_BINANCES2VT[data["side"]],
            traded=Decimal(str(data["executedQty"])),
            status=STATUS_BINANCES2VT.get(data["status"], None),
            datetime=generate_datetime(data["time"]),
            gateway_name=self.gateway_name,
        )
        self.gateway.on_order(order)

        self.gateway.write_log("query order successfully")

    def on_query_orders(self, data: list, request: Request) -> None:
        """query open orders callback"""
        for d in data:
            key: Tuple[str, str] = (d["type"], d["timeInForce"])
            # order_type: OrderType = ORDERTYPE_BINANCES2VT.get(key, None)
            # if not order_type:
            #     continue
            order_type: OrderType = ORDERTYPE_BINANCES2VT.get(key, OrderType.LIMIT)

            order: OrderData = OrderData(
                orderid=d["clientOrderId"],
                symbol=d["symbol"],
                exchange=Exchange.BINANCE,
                price=Decimal(str(d["price"])),
                volume=Decimal(str(d["origQty"])),
                type=order_type,
                direction=DIRECTION_BINANCES2VT[d["side"]],
                traded=Decimal(str(d["executedQty"])),
                status=STATUS_BINANCES2VT.get(d["status"], Status.NOTTRADED),
                datetime=generate_datetime(d["time"]),
                gateway_name=self.gateway_name,
            )
            self.gateway.on_order(order)

        self.gateway.write_log("query open orders successfully")

    def on_query_contract(self, data: dict, request: Request) -> None:
        """query contract callback"""
        for d in data["symbols"]:
            base_currency: str = d["baseAsset"]
            quote_currency: str = d["quoteAsset"]
            name: str = f"{base_currency.upper()}/{quote_currency.upper()}"

            pricetick: Decimal = Decimal("1")
            min_volume: Decimal = Decimal("1")

            for f in d["filters"]:
                if f["filterType"] == "PRICE_FILTER":
                    pricetick = Decimal(str(f["tickSize"]))
                elif f["filterType"] == "LOT_SIZE":
                    min_volume = Decimal(str(f["stepSize"]))

            contract: ContractData = ContractData(
                symbol=d["symbol"],
                exchange=Exchange.BINANCE,
                name=name,
                pricetick=pricetick,
                size=Decimal("1"),
                min_volume=min_volume,
                product=Product.FUTURES,
                net_position=True,
                history_data=True,
                gateway_name=self.gateway_name,
            )
            self.gateway.on_contract(contract)

            symbol_contract_map[contract.symbol] = contract

        self.gateway.write_log("query contract successfully")

    def on_send_order(self, data: dict, request: Request) -> None:
        """send order callback"""
        pass

    def on_send_order_failed(self, status_code: str, request: Request) -> None:
        """send order failed callback"""
        order: OrderData = request.extra
        order.status = Status.REJECTED
        self.gateway.on_order(order)

        msg: str = f"send order failed，status code：{status_code}，msg：{request.response.text}"
        self.gateway.write_log(msg)

    def on_send_order_error(
            self, exception_type: type, exception_value: Exception, tb, request: Request
    ) -> None:
        """send order error callback"""
        order: OrderData = request.extra
        order.status = Status.REJECTED
        self.gateway.on_order(order)

        if not issubclass(exception_type, (ConnectionError, SSLError)):
            self.on_error(exception_type, exception_value, tb, request)

    def on_cancel_order(self, data: dict, request: Request) -> None:
        """cancel order callback"""
        pass

    def on_cancel_failed(self, status_code: str, request: Request) -> None:
        """cancel order failed callback"""
        if request.extra:
            order = request.extra
            order.status = Status.REJECTED
            self.gateway.on_order(order)

        msg = f"cancel order failed，status code：{status_code}，msg：{request.response.text}"
        self.gateway.write_log(msg)

    def on_start_user_stream(self, data: dict, request: Request) -> None:
        """query listenkey callback, then connect to trade ws """
        self.user_stream_key = data["listenKey"]
        self.keep_alive_count = 0

        url = F_WEBSOCKET_TRADE_HOST + self.user_stream_key

        self.trade_ws_api.connect(url, self.proxy_host, self.proxy_port)

    def on_start_user_stream_failed(self, status_code: str, request: Request):
        self.start_user_stream()

    def on_start_user_stream_error(self, exception_type: type, exception_value: Exception, tb, request: Request):
        self.start_user_stream()

    def on_keep_user_stream(self, data: dict, request: Request) -> None:
        """extend the listen key expire time"""
        pass

    def on_keep_user_strea_failed(self, status_code: str, request: Request):
        self.start_user_stream()

    def on_keep_user_stream_error(
            self, exception_type: type, exception_value: Exception, tb, request: Request
    ) -> None:
        """put the listen key failed"""
        self.start_user_stream()
        if not issubclass(exception_type, TimeoutError):
            self.on_error(exception_type, exception_value, tb, request)

    def query_history(self, req: HistoryRequest) -> List[BarData]:
        """query historical kline data"""
        history: List[BarData] = []
        limit: int = 1500

        start_time: int = int(datetime.timestamp(req.start))

        while True:
            # query parameters
            params: dict = {
                "symbol": req.symbol,
                "interval": INTERVAL_VT2BINANCES[req.interval],
                "limit": limit,
                "startTime": start_time * 1000
            }

            path: str = "/fapi/v1/klines"
            if req.end:
                end_time = int(datetime.timestamp(req.end))
                params["endTime"] = end_time * 1000  # convert the start time into milliseconds

            resp: Response = self.request(
                "GET",
                path=path,
                data={"security": Security.NONE},
                params=params
            )

            # will break the while loop if the request failed
            if resp.status_code // 100 != 2:
                msg: str = f"query historical kline data failed, status code：{resp.status_code}，msg：{resp.text}"
                self.gateway.write_log(msg)
                break
            else:
                data: dict = resp.json()
                if not data:
                    msg: str = f"historical kline data is empty, start time：{start_time}"
                    self.gateway.write_log(msg)
                    break

                buf: List[BarData] = []

                for row in data:
                    bar: BarData = BarData(
                        symbol=req.symbol,
                        exchange=req.exchange,
                        datetime=generate_datetime(row[0]),
                        interval=req.interval,
                        volume=float(row[5]),
                        turnover=float(row[7]),
                        open_price=float(row[1]),
                        high_price=float(row[2]),
                        low_price=float(row[3]),
                        close_price=float(row[4]),
                        gateway_name=self.gateway_name
                    )
                    buf.append(bar)

                begin: datetime = buf[0].datetime
                end: datetime = buf[-1].datetime

                history.extend(buf)
                msg: str = f"query historical kline data successfully, {req.symbol} - {req.interval.value}，{begin} - {end}"
                self.gateway.write_log(msg)

                # if the data len is less than limit, break the while loop
                if len(data) < limit:
                    break

                # update start time
                start_dt = bar.datetime + TIMEDELTA_MAP[req.interval]
                start_time = int(datetime.timestamp(start_dt))

        return history


class BinanceUsdtTradeWebsocketApi(WebsocketClient):
    """binance usdt/busd trade ws api"""

    def __init__(self, gateway: BinanceUsdtGateway) -> None:
        super().__init__()

        self.gateway: BinanceUsdtGateway = gateway
        self.gateway_name: str = gateway.gateway_name

    def connect(self, url: str, proxy_host: str, proxy_port: int) -> None:
        """connect binance usdt/busd future trade ws"""
        self.init(url, proxy_host, proxy_port)
        self.start()

    def on_connected(self) -> None:
        """trade ws connected"""
        self.gateway.write_log("trade ws connected")

    def on_packet(self, packet: dict) -> None:
        """receive data from ws"""
        if packet["e"] == "ACCOUNT_UPDATE":
            self.on_account(packet)
        elif packet["e"] == "ORDER_TRADE_UPDATE":
            self.on_order(packet)
        elif packet['e'] == 'listenKeyExpired':
            self.gateway.rest_api.start_user_stream()

    def on_account(self, packet: dict) -> None:
        """account data update"""
        for acc_data in packet["a"]["B"]:
            account: AccountData = AccountData(
                accountid=acc_data["a"],
                balance=float(acc_data["wb"]),
                frozen=float(acc_data["wb"]) - float(acc_data["cw"]),
                gateway_name=self.gateway_name
            )

            self.gateway.on_account(account)

        for pos_data in packet["a"]["P"]:
            if pos_data["ps"] == "BOTH":
                volume = pos_data["pa"]
                if '.' in volume:
                    volume = float(volume)
                else:
                    volume = int(volume)

                position: PositionData = PositionData(
                    symbol=pos_data["s"],
                    exchange=Exchange.BINANCE,
                    direction=Direction.NET,
                    volume=volume,
                    price=float(pos_data["ep"]),
                    pnl=float(pos_data["cr"]),
                    gateway_name=self.gateway_name,
                )

                self.gateway.on_position(position)

    def on_order(self, packet: dict) -> None:
        """order update"""
        ord_data: dict = packet["o"]
        key: Tuple[str, str] = (ord_data["o"], ord_data["f"])
        # order_type: OrderType = ORDERTYPE_BINANCES2VT.get(key, None)
        # if not order_type:
        #     return
        order_type: OrderType = ORDERTYPE_BINANCES2VT.get(key, OrderType.LIMIT)

        order: OrderData = OrderData(
            symbol=ord_data["s"],
            exchange=Exchange.BINANCE,
            orderid=str(ord_data["c"]),
            type=order_type,
            direction=DIRECTION_BINANCES2VT[ord_data["S"]],
            price=Decimal(str(ord_data["p"])),
            volume=Decimal(str(ord_data["q"])),
            traded=Decimal(str(ord_data["z"])),
            status=STATUS_BINANCES2VT[ord_data["X"]],
            datetime=generate_datetime(packet["E"]),
            gateway_name=self.gateway_name
        )

        self.gateway.on_order(order)

        # 将成交数量四舍五入到正确精度
        # trade_volume: float = float(ord_data["l"])
        # contract: ContractData = symbol_contract_map.get(order.symbol, None)
        # if contract:
        #     trade_volume = round_to(trade_volume, contract.min_volume)
        #
        # if not trade_volume:
        #     return
        #
        # trade: TradeData = TradeData(
        #     symbol=order.symbol,
        #     exchange=order.exchange,
        #     orderid=order.orderid,
        #     tradeid=ord_data["t"],
        #     direction=order.direction,
        #     price=float(ord_data["L"]),
        #     volume=trade_volume,
        #     datetime=generate_datetime(ord_data["T"]),
        #     gateway_name=self.gateway_name,
        # )
        # self.gateway.on_trade(trade)


class BinanceUsdtDataWebsocketApi(WebsocketClient):
    """Binance usdt/busd Data ws"""

    def __init__(self, gateway: BinanceUsdtGateway) -> None:
        """"""
        super().__init__()

        self.gateway: BinanceUsdtGateway = gateway
        self.gateway_name: str = gateway.gateway_name

        self.ticks: Dict[str, TickData] = {}
        self.reqid: int = 0

    def connect(
            self,
            proxy_host: str,
            proxy_port: int,
    ) -> None:
        """connect market data ws"""
        self.init(F_WEBSOCKET_DATA_HOST, proxy_host, proxy_port)
        self.start()

    def on_connected(self) -> None:
        """data ws connected"""
        self.gateway.write_log("data ws connected")

        # re-subscribe data
        if self.ticks:
            channels = []
            for symbol in self.ticks.keys():
                channels.append(f"{symbol}@ticker")
                channels.append(f"{symbol}@depth5")

            req: dict = {
                "method": "SUBSCRIBE",
                "params": channels,
                "id": self.reqid
            }
            self.send_packet(req)

    def subscribe(self, req: SubscribeRequest) -> None:
        """subscribe data"""
        if req.symbol in self.ticks:
            return

        if req.symbol not in symbol_contract_map:
            self.gateway.write_log(f"symbol is not found: {req.symbol}")
            return

        self.reqid += 1

        # init Tick object
        tick: TickData = TickData(
            symbol=req.symbol,
            name=symbol_contract_map[req.symbol].name,
            exchange=Exchange.BINANCE,
            datetime=datetime.now(CHINA_TZ),
            gateway_name=self.gateway_name,
        )
        self.ticks[req.symbol.lower()] = tick

        channels = [
            f"{req.symbol.lower()}@ticker",
            f"{req.symbol.lower()}@depth5"
        ]

        req: dict = {
            "method": "SUBSCRIBE",
            "params": channels,
            "id": self.reqid
        }
        self.send_packet(req)

    def on_packet(self, packet: dict) -> None:
        """received the subscribe data"""
        stream: str = packet.get("stream", None)

        if not stream:
            return

        data: dict = packet["data"]

        symbol, channel = stream.split("@")
        tick: TickData = self.ticks[symbol]

        if channel == "ticker":
            tick.volume = float(data['v'])
            tick.turnover = float(data['q'])
            tick.open_price = float(data['o'])
            tick.high_price = float(data['h'])
            tick.low_price = float(data['l'])
            tick.last_price = float(data['c'])
            tick.datetime = generate_datetime(float(data['E']))
        else:
            bids: list = data["b"]
            for n in range(min(5, len(bids))):
                price, volume = bids[n]
                tick.__setattr__("bid_price_" + str(n + 1), float(price))
                tick.__setattr__("bid_volume_" + str(n + 1), float(volume))

            asks: list = data["a"]
            for n in range(min(5, len(asks))):
                price, volume = asks[n]
                tick.__setattr__("ask_price_" + str(n + 1), float(price))
                tick.__setattr__("ask_volume_" + str(n + 1), float(volume))

        if tick.last_price:
            tick.localtime = datetime.now()
            self.gateway.on_tick(copy(tick))


def generate_datetime(timestamp: float) -> datetime:
    """generate time"""
    dt: datetime = datetime.fromtimestamp(timestamp / 1000)
    dt: datetime = CHINA_TZ.localize(dt)
    return dt
