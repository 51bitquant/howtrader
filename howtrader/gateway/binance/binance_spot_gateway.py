import urllib
import hashlib
import hmac
import time
from copy import copy
from datetime import datetime, timedelta
from enum import Enum
from threading import Lock
from typing import Any, Dict, List
from decimal import Decimal
import pandas as pd
import numpy as np
import json

from requests.exceptions import SSLError
from howtrader.trader.constant import (
    Direction,
    Exchange,
    Product,
    Status,
    OrderType,
    Interval,
)
from howtrader.trader.gateway import BaseGateway
from howtrader.trader.object import (
    TickData,
    OrderData,
    TradeData,
    OrderQueryRequest,
    AccountData,
    ContractData,
    BarData,
    OrderRequest,
    CancelRequest,
    SubscribeRequest,
    HistoryRequest,
    OriginalKlineData
)
from howtrader.trader.event import EVENT_TIMER
from howtrader.event import Event, EventEngine
from howtrader.api.rest import RestClient, Request, Response
from howtrader.api.websocket import WebsocketClient
from howtrader.trader.constant import LOCAL_TZ

# REST API HOST
REST_HOST: str = "https://api.binance.com"

# Websocket API HOST
WEBSOCKET_TRADE_HOST: str = "wss://stream.binance.com:9443/ws/"
WEBSOCKET_DATA_HOST: str = "wss://stream.binance.com:9443/stream"


# order status mapping
STATUS_BINANCE2VT: Dict[str, Status] = {
    "NEW": Status.NOTTRADED,
    "PARTIALLY_FILLED": Status.PARTTRADED,
    "FILLED": Status.ALLTRADED,
    "CANCELED": Status.CANCELLED,
    "REJECTED": Status.REJECTED,
    "EXPIRED": Status.CANCELLED
}

# order type mapping
ORDERTYPE_VT2BINANCE: Dict[OrderType, str] = {
    OrderType.LIMIT: "LIMIT",
    OrderType.TAKER: "MARKET",
    OrderType.MAKER: "LIMIT_MAKER",
}
ORDERTYPE_BINANCE2VT: Dict[str, OrderType] = {v: k for k, v in ORDERTYPE_VT2BINANCE.items()}

# order direction mapping
DIRECTION_VT2BINANCE: Dict[Direction, str] = {
    Direction.LONG: "BUY",
    Direction.SHORT: "SELL"
}
DIRECTION_BINANCE2VT: Dict[str, Direction] = {v: k for k, v in DIRECTION_VT2BINANCE.items()}

# data timeframe mapping
INTERVAL_VT2BINANCE: Dict[Interval, str] = {
    Interval.MINUTE: "1m",
    Interval.MINUTE_3: "3m",
    Interval.MINUTE_5: "5m",
    Interval.MINUTE_15: "15",
    Interval.MINUTE_30: "30m",
    Interval.HOUR: "1h",
    Interval.HOUR_2: "2h",
    Interval.HOUR_4: "4h",
    Interval.HOUR_6: "6h",
    Interval.HOUR_8: "8h",
    Interval.HOUR_12: "12h",
    Interval.DAILY: "1d",
    Interval.DAILY_3: "3d",
    Interval.WEEKLY: "1w",
    Interval.MONTH: "1M"
}

# time delta mapping
TIMEDELTA_MAP: Dict[Interval, timedelta] = {
    Interval.MINUTE: timedelta(minutes=1),
    Interval.HOUR: timedelta(hours=1),
    Interval.DAILY: timedelta(days=1),
}

# contract mapping
symbol_contract_map: Dict[str, ContractData] = {}


# security for private api
class Security(Enum):
    NONE = 0
    SIGNED = 1
    API_KEY = 2


class BinanceSpotGateway(BaseGateway):
    """
    binance spot gateway for howtrader
    """

    default_name: str = "BINANCE_SPOT"

    default_setting: Dict[str, Any] = {
        "key": "",
        "secret": "",
        "proxy_host": "",
        "proxy_port": 0
    }

    exchanges: Exchange = [Exchange.BINANCE]

    def __init__(self, event_engine: EventEngine, gateway_name: str) -> None:
        """init"""
        super().__init__(event_engine, gateway_name)

        self.trade_ws_api: "BinanceSpotTradeWebsocketApi" = BinanceSpotTradeWebsocketApi(self)
        self.market_ws_api: "BinanceSpotDataWebsocketApi" = BinanceSpotDataWebsocketApi(self)
        self.rest_api: "BinanceSpotRestAPi" = BinanceSpotRestAPi(self)

        self.orders: Dict[str, OrderData] = {}
        self.get_server_time_interval: int = 0

    def connect(self, setting: dict):
        """connect binance api"""
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

        self.event_engine.unregister(EVENT_TIMER, self.process_timer_event)
        self.event_engine.register(EVENT_TIMER, self.process_timer_event)

    def subscribe(self, req: SubscribeRequest) -> None:
        """subscribe market data"""
        self.market_ws_api.subscribe(req)

    def send_order(self, req: OrderRequest) -> str:
        """place order"""
        return self.rest_api.send_order(req)

    def cancel_order(self, req: CancelRequest) -> None:
        """cancel order"""
        self.rest_api.cancel_order(req)

    def query_account(self) -> None:
        """query account data"""
        self.rest_api.query_account()

    def query_position(self) -> None:
        """query position, not available for spot gateway"""
        pass

    def query_order(self, req: OrderQueryRequest) -> None:
        self.rest_api.query_order(req)

    def query_history(self, req: HistoryRequest) -> List[BarData]:
        """query historical kline data"""
        return self.rest_api.query_history(req)

    def query_latest_kline(self, req: HistoryRequest) -> None:
        self.rest_api.query_latest_kline(req)

    def close(self) -> None:
        """close connection from exchange server"""
        self.rest_api.stop()
        self.trade_ws_api.stop()
        self.market_ws_api.stop()

    def process_timer_event(self, event: Event) -> None:
        """process timer event, for updating the listen key"""
        self.rest_api.keep_user_stream()
        self.get_server_time_interval += 1
        if self.get_server_time_interval >= 300:  # get the server time for every five miute
            self.rest_api.query_time()
            self.get_server_time_interval = 0

    def on_order(self, order: OrderData) -> None:
        """on order, order update"""
        order.update_time = generate_datetime(time.time() * 1000)
        last_order: OrderData = self.get_order(order.orderid)
        if not last_order:
            self.orders[order.orderid] = order
            super().on_order(copy(order))

        else:
            traded: Decimal = order.traded - last_order.traded
            if traded < 0: # filter the order is not in sequence
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
        """get order by orderid"""
        return self.orders.get(orderid, None)


class BinanceSpotRestAPi(RestClient):
    """binance spot rest api"""

    def __init__(self, gateway: BinanceSpotGateway) -> None:
        """init"""
        super().__init__()

        self.gateway: BinanceSpotGateway = gateway
        self.gateway_name: str = gateway.gateway_name

        self.trade_ws_api: BinanceSpotTradeWebsocketApi = self.gateway.trade_ws_api

        self.key: str = ""
        self.secret: str = ""

        self.user_stream_key: str = ""
        self.keep_alive_count: int = 0
        self.keep_alive_failed_count: int = 0
        self.recv_window: int = 5000
        self.time_offset: int = 0

        self.order_count: int = 1_000_000
        self.order_count_lock: Lock = Lock()
        self.connect_time: int = 0

    def sign(self, request: Request) -> Request:
        """signature for private api"""
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
                int(datetime.now(LOCAL_TZ).strftime("%y%m%d%H%M%S")) * self.order_count
        )

        self.init(REST_HOST, proxy_host, proxy_port)

        self.start()

        self.gateway.write_log("start connecting rest api")

        self.query_contract()
        self.query_time()
        self.query_account()
        self.query_orders()
        self.start_user_stream()

    def query_time(self) -> None:
        """query time"""
        data: dict = {
            "security": Security.NONE
        }
        path: str = "/api/v3/time"

        self.add_request(
            "GET",
            path,
            callback=self.on_query_time,
            on_failed=self.on_query_time_failed,
            on_error=self.on_query_time_error,
            data=data
        )

    def query_account(self) -> None:
        """query account"""
        data: dict = {"security": Security.SIGNED}

        self.add_request(
            method="GET",
            path="/api/v3/account",
            callback=self.on_query_account,
            data=data
        )

    def query_order(self, req: OrderQueryRequest) -> None:
        """
        query order with a specific orderid.
        :param req:
        :return:
        """
        data = {
            "security": Security.SIGNED
        }

        params = {
            "symbol": req.symbol.upper(),
            "origClientOrderId": req.orderid
        }

        self.add_request(
            method="GET",
            path="/api/v3/order",
            callback=self.on_query_order,
            params=params,
            data=data,
            extra=req
        )

    def query_orders(self) -> None:
        """query open orders"""
        data: dict = {"security": Security.SIGNED}

        self.add_request(
            method="GET",
            path="/api/v3/openOrders",
            callback=self.on_query_orders,
            data=data
        )


    def query_contract(self) -> None:
        """query contract detail or exchange info detail"""
        data: dict = {
            "security": Security.NONE
        }
        self.add_request(
            method="GET",
            path="/api/v3/exchangeInfo",
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

        orderid: str = "x-A6SIDXVS" + str(self.connect_time + self._new_order_id())

        # create order by OrderRequest
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
            "symbol": req.symbol.upper(),
            "side": DIRECTION_VT2BINANCE[req.direction],
            "type": ORDERTYPE_VT2BINANCE[req.type],
            "quantity": req.volume, # format(req.volume, "f")
            "newClientOrderId": orderid,
            "newOrderRespType": "RESULT"
        }

        if req.type == OrderType.LIMIT:
            params["timeInForce"] = "GTC"
            params["price"] = req.price
        elif req.type == OrderType.MAKER:
            params["price"] = req.price

        self.add_request(
            method="POST",
            path="/api/v3/order",
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
            "symbol": req.symbol.upper(),
            "origClientOrderId": req.orderid
        }

        order: OrderData = self.gateway.get_order(req.orderid)

        self.add_request(
            method="DELETE",
            path="/api/v3/order",
            callback=self.on_cancel_order,
            params=params,
            data=data,
            on_failed=self.on_cancel_order_failed,
            extra=order
        )

    def start_user_stream(self) -> None:
        """post listenKey"""
        data: dict = {
            "security": Security.API_KEY
        }

        self.add_request(
            method="POST",
            path="/api/v3/userDataStream",
            callback=self.on_start_user_stream,
            on_failed=self.on_start_user_stream_failed,
            on_error=self.on_start_user_stream_error,
            data=data
        )

    def keep_user_stream(self) -> None:
        """extend listenKey expire time """
        self.keep_alive_count += 1
        if self.keep_alive_count < 300:
            return None
        self.keep_alive_count = 0

        data: dict = {
            "security": Security.API_KEY
        }

        params: dict = {
            "listenKey": self.user_stream_key
        }

        self.add_request(
            method="PUT",
            path="/api/v3/userDataStream",
            callback=self.on_keep_user_stream,
            params=params,
            data=data,
            on_failed=self.on_keep_user_stream_failed,
            on_error=self.on_keep_user_stream_error
        )

    def on_query_time(self, data: dict, request: Request) -> None:
        """query server time callback"""
        local_time = int(time.time() * 1000)
        server_time = int(data["serverTime"])
        self.time_offset = local_time - server_time

    def on_query_time_failed(self, status_code: int, request: Request):
        self.query_time()

    def on_query_time_error(self, exception_type: type, exception_value: Exception, tb, request: Request) -> None:
        self.query_time()

    def on_query_account(self, data: dict, request: Request) -> None:
        """query account callback"""
        for account_data in data["balances"]:
            account: AccountData = AccountData(
                accountid=account_data["asset"],
                balance=float(account_data["free"]) + float(account_data["locked"]),
                frozen=float(account_data["locked"]),
                gateway_name=self.gateway_name
            )

            self.gateway.on_account(account)

        self.gateway.write_log("query account successfully")

    def on_query_order(self, data: dict, request: Request) -> None:

        traded = Decimal(data.get('executedQty', '0'))
        price = Decimal(data.get('price', '0'))
        traded_price = Decimal("0")
        if traded > 0:
            traded_quote = Decimal(data.get('cummulativeQuoteQty', '0'))
            traded_price = traded_quote/traded
        if price <= 0 < traded_price:
            price = traded_price

        order = OrderData(
            orderid=data["clientOrderId"],
            symbol=data["symbol"].lower(),
            exchange=Exchange.BINANCE,
            price=price,
            volume=Decimal(data["origQty"]),
            traded=traded,
            traded_price=traded_price,
            type=ORDERTYPE_BINANCE2VT.get(data["type"],OrderType.LIMIT),
            direction=DIRECTION_BINANCE2VT[data["side"]],
            status=STATUS_BINANCE2VT.get(data["status"], Status.NOTTRADED),
            datetime=generate_datetime(data["time"]),
            gateway_name=self.gateway_name,
        )
        self.gateway.on_order(order)

    def on_query_orders(self, datas: list, request: Request) -> None:
        """query open orders callback"""
        for data in datas:
            # filter the unsupported order type
            # if d["type"] not in ORDERTYPE_BINANCE2VT:
            #     continue
            price = Decimal(data.get("price", '0'))
            traded = Decimal(data.get('executedQty', '0'))
            traded_price = Decimal("0")
            if traded > 0:
                traded_quote = Decimal(data.get('cummulativeQuoteQty', '0'))
                traded_price = traded_quote / traded

            if price <= 0 < traded_price:
                price = traded_price

            order: OrderData = OrderData(
                orderid=data["clientOrderId"],
                symbol=data["symbol"].lower(),
                exchange=Exchange.BINANCE,
                price=price,
                volume=Decimal(data["origQty"]),
                traded=traded,
                traded_price=traded_price,
                type=ORDERTYPE_BINANCE2VT.get(data["type"], OrderType.LIMIT),
                direction=DIRECTION_BINANCE2VT[data["side"]],
                status=STATUS_BINANCE2VT.get(data["status"], Status.NOTTRADED),
                datetime=generate_datetime(data["time"]),
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
            min_notional: Decimal = Decimal("10")

            for f in d["filters"]:
                if f["filterType"] == "PRICE_FILTER":
                    tick = str(f["tickSize"]).rstrip("0")
                    pricetick = Decimal(tick)
                elif f["filterType"] == "LOT_SIZE":
                    step = str(f["stepSize"]).rstrip("0")
                    min_volume = Decimal(step)
                elif f.get('filterType') == 'MIN_NOTIONAL':
                    notional = str(f["minNotional"]).rstrip("0")
                    min_notional = Decimal(notional)

            contract: ContractData = ContractData(
                symbol=d["symbol"].lower(),
                exchange=Exchange.BINANCE,
                name=name,
                pricetick=pricetick,
                size=Decimal("1"),
                min_volume=min_volume,
                min_notional=min_notional,
                product=Product.SPOT,
                history_data=True,
                gateway_name=self.gateway_name,
            )
            self.gateway.on_contract(contract)

            symbol_contract_map[contract.symbol] = contract

        self.gateway.write_log("query contract successfully")

    def on_send_order(self, data: dict, request: Request) -> None:
        """send order callback"""
        if request.extra:
            order: OrderData = copy(request.extra)

            price = Decimal(data.get('price', '0'))
            traded = Decimal(data.get('executedQty', '0'))
            traded_price = Decimal("0")
            if traded > 0:
                traded_quote = Decimal(data.get('cummulativeQuoteQty', '0'))
                traded_price = traded_quote / traded

            if price <= 0 < traded_price:
                price = traded_price

            order.traded = traded
            order.traded_price = traded_price
            order.price = price
            order.status = STATUS_BINANCE2VT.get(data.get('status'), Status.NOTTRADED)
            self.gateway.on_order(order)

    def on_send_order_failed(self, status_code: int, request: Request) -> None:
        """send order failed callback"""
        self.failed_with_timestamp(request)
        if request.extra:
            order: OrderData = copy(request.extra)
            order.status = Status.REJECTED
            order.rejected_reason = request.response.text if request.response.text else ""
            self.gateway.on_order(order)

            msg: str = f"send order failed, orderid: {order.orderid}, status code：{status_code}, msg：{request.response.text}"
            self.gateway.write_log(msg)

    def on_send_order_error(
            self, exception_type: type, exception_value: Exception, tb, request: Request
    ) -> None:
        """send order error callback"""
        if request.extra:
            order: OrderData = copy(request.extra)
            order.status = Status.REJECTED
            order.rejected_reason = "on_send_order_error"
            self.gateway.on_order(order)

        if not issubclass(exception_type, (ConnectionError, SSLError)):
            self.on_error(exception_type, exception_value, tb, request)

    def on_cancel_order(self, data: dict, request: Request) -> None:
        """cancel order callback"""
        if request.extra:
            order: OrderData = copy(request.extra)
            price = Decimal(data.get('price', '0'))
            traded = Decimal(data.get('executedQty', '0'))
            traded_price = Decimal("0")
            if traded > 0:
                traded_quote = Decimal(data.get('cummulativeQuoteQty', '0'))
                traded_price = traded_quote / traded

            if price <= 0 < traded_price:
                price = traded_price

            order.traded = traded
            order.price = price
            order.traded_price = traded_price
            order.status = STATUS_BINANCE2VT.get(data.get('status'), Status.CANCELLED)
            self.gateway.on_order(order)
        else:

            price = Decimal(data.get('price', '0'))
            traded = Decimal(data.get('executedQty', '0'))
            traded_price = Decimal("0")
            if traded > 0:
                traded_quote = Decimal(data.get('cummulativeQuoteQty', '0'))
                traded_price = traded_quote / traded

            if price <= 0 < traded_price:
                price = traded_price

            order: OrderData = OrderData(
                symbol=data.get("symbol").lower(),
                exchange=Exchange.BINANCE,
                orderid=data.get("clientOrderId"),
                type=ORDERTYPE_BINANCE2VT.get(data.get("type"), OrderType.LIMIT),
                direction=DIRECTION_BINANCE2VT.get(data.get("side")),
                price=price,
                volume=Decimal(data.get('origQty')),
                traded=traded,
                traded_price=traded_price,
                status=STATUS_BINANCE2VT.get(data.get('status'), Status.CANCELLED),
                gateway_name=self.gateway_name
            )

            self.gateway.on_order(order)


    def on_cancel_order_failed(self, status_code: int, request: Request) -> None:
        """cancel order failed callback"""
        self.failed_with_timestamp(request)
        orderid = ""
        if request.extra:
            order:OrderData = copy(request.extra)
            orderid = order.orderid
            # order.status = Status.REJECTED
            # self.gateway.on_order(copy(order))
            req: OrderQueryRequest = order.create_query_request()
            self.query_order(req)

        msg = f"cancel order failed, orderid: {orderid}, status code: {status_code}, msg：{request.response.text}"
        self.gateway.write_log(msg)

    def on_start_user_stream(self, data: dict, request: Request) -> None:
        """query listen key callback, we connect the account ws"""
        self.user_stream_key = data["listenKey"]
        self.keep_alive_count = 0

        url = WEBSOCKET_TRADE_HOST + self.user_stream_key

        self.trade_ws_api.connect(url, self.proxy_host, self.proxy_port)

    def on_start_user_stream_failed(self, status_code: int, request: Request):
        self.failed_with_timestamp(request)
        self.start_user_stream()

    def on_start_user_stream_error(self, exception_type: type, exception_value: Exception, tb, request: Request):
        self.start_user_stream()

    def on_keep_user_stream(self, data: dict, request: Request) -> None:
        """extend the listen key expire time"""
        self.keep_alive_failed_count = 0

    def on_keep_user_stream_failed(self, status_code: int, request: Request):
        self.failed_with_timestamp(request)
        self.keep_alive_failed_count += 1
        if self.keep_alive_failed_count <= 3:
            self.keep_alive_count = 1200000
            self.keep_user_stream()
        else:
            self.keep_alive_failed_count = 0
            self.start_user_stream()

    def on_keep_user_stream_error(
            self, exception_type: type, exception_value: Exception, tb, request: Request
    ) -> None:
        """put the listen key failed"""

        self.keep_alive_failed_count += 1
        if self.keep_alive_failed_count <= 3:
            self.keep_alive_count = 1200000
            self.keep_user_stream()
        else:
            self.keep_alive_failed_count = 0
            self.start_user_stream()

        if not issubclass(exception_type, TimeoutError):
            self.on_error(exception_type, exception_value, tb, request)

    def query_latest_kline(self, req: HistoryRequest) -> None:

        interval = INTERVAL_VT2BINANCE.get(req.interval, None)
        if not interval:
            print(f"unsupport interval: {req.interval}")
            return None

        # end_time: int = int(datetime.timestamp(req.end))
        params: dict = {
            "symbol": req.symbol.upper(),
            "interval": interval,
            "limit": req.limit,
            # "endTime": end_time * 1000  # convert the start time into milliseconds
        }

        self.add_request(
            method="GET",
            path="/api/v3/klines",
            callback=self.on_query_latest_kline,
            params=params,
            data={"security": Security.NONE}
        )

    def on_query_latest_kline(self, datas:list, request: Request):
        if len(datas) > 0:
            df = pd.DataFrame(datas, dtype=np.float64,
                              columns=['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'turnover',
                                       'a2',
                                       'a3', 'a4', 'a5'])
            df = df[['open_time', 'open', 'high', 'low', 'close', 'volume', 'turnover']]
            df.set_index('open_time', inplace=True)
            df.index = pd.to_datetime(df.index, unit='ms') # + pd.Timedelta(hours=8) # use the utc time.

            symbol = request.params.get("symbol", "").lower()
            interval = Interval(request.params.get('interval'))
            kline_data = OriginalKlineData(
                symbol=symbol,
                exchange="BINANCE",
                interval=interval,
                klines=datas,
                kline_df=df
            )

            self.gateway.on_kline(kline_data)

    def query_history(self, req: HistoryRequest) -> List[BarData]:
        """query historical kline data"""
        history: List[BarData] = []
        limit: int = 1000
        start_time: int = int(datetime.timestamp(req.start))

        while True:
            # query parameters
            params: dict = {
                "symbol": req.symbol.upper(),
                "interval": INTERVAL_VT2BINANCE[req.interval],
                "limit": limit,
                "startTime": start_time * 1000,  # convert the start time into milliseconds
            }

            if req.end:
                end_time: int = int(datetime.timestamp(req.end))
                params["endTime"] = end_time * 1000  # convert the start time into milliseconds

            resp: Response = self.request(
                "GET",
                "/api/v3/klines",
                data={"security": Security.NONE},
                params=params
            )

            # continue to query the data until failed
            if resp.status_code // 100 != 2:
                msg: str = f"query historical kline data failed，status code：{resp.status_code}，msg：{resp.text}"
                self.gateway.write_log(msg)
                break
            else:
                data: dict = resp.json()
                if not data:
                    msg: str = f"historical kline data is empty ，start time：{start_time}"
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

                history.extend(buf)

                begin: datetime = buf[0].datetime
                end: datetime = buf[-1].datetime
                msg: str = f"query historical kline data successfully，{req.symbol} - {req.interval.value}，{begin} - {end}"
                self.gateway.write_log(msg)

                # if the data len is less than limit, break the while loop
                if len(data) < limit:
                    break

                # update start time
                start_dt = bar.datetime + TIMEDELTA_MAP[req.interval]
                start_time = int(datetime.timestamp(start_dt))

        return history

    def failed_with_timestamp(self, request: Request):
        # request.response.text
        # -1021 INVALID_TIMESTAMP
        try:
            if request and request.response and request.response.text:
                resp = json.loads(request.response.text)
                if resp.get('code') == -1021:
                    self.query_time()
        except Exception:
            pass


class BinanceSpotTradeWebsocketApi(WebsocketClient):
    """Binance Spot trade ws api"""

    def __init__(self, gateway: BinanceSpotGateway) -> None:
        """init"""
        super().__init__()

        self.gateway: BinanceSpotGateway = gateway
        self.gateway_name = gateway.gateway_name

    def connect(self, url: str, proxy_host: str, proxy_port: int) -> None:
        """connect binance spot trade ws api"""
        self.init(url, proxy_host, proxy_port)
        self.start()

    def on_connected(self) -> None:
        """trade ws connected """
        self.gateway.write_log("trade ws connected")

    def on_packet(self, packet: dict) -> None:
        """receive data from ws"""
        if packet["e"] == "outboundAccountPosition":
            self.on_account(packet)
        elif packet["e"] == "executionReport":
            self.on_order(packet)

    def on_exit_loop(self):
        self.gateway.rest_api.start_user_stream()

    def on_account(self, packet: dict) -> None:
        """account data update"""
        for d in packet["B"]:
            account: AccountData = AccountData(
                accountid=d["a"],
                balance=float(d["f"]) + float(d["l"]),
                frozen=float(d["l"]),
                gateway_name=self.gateway_name
            )

            self.gateway.on_account(account)

    def on_order(self, packet: dict) -> None:
        """order update"""
        # filter unsupported order type
        # if packet["o"] not in ORDERTYPE_BINANCE2VT:
        #     return

        if packet["C"] == "":
            orderid: str = packet["c"]
        else:
            orderid: str = packet["C"]

        price = Decimal(packet["p"])
        traded_price = Decimal(packet.get("L", "0"))
        if price <= 0:
            price = traded_price

        order: OrderData = OrderData(
            symbol=packet["s"].lower(),
            exchange=Exchange.BINANCE,
            orderid=orderid,
            type=ORDERTYPE_BINANCE2VT.get(packet["o"], OrderType.LIMIT),
            direction=DIRECTION_BINANCE2VT[packet["S"]],
            price=price,
            volume=Decimal(packet["q"]),
            traded=Decimal(packet["z"]),
            traded_price=traded_price,
            status=STATUS_BINANCE2VT.get(packet["X"], Status.NOTTRADED),
            datetime=generate_datetime(packet["O"]),
            gateway_name=self.gateway_name
        )

        self.gateway.on_order(order)

class BinanceSpotDataWebsocketApi(WebsocketClient):
    """Binance spot market data ws"""

    def __init__(self, gateway: BinanceSpotGateway) -> None:
        """init"""
        super().__init__()

        self.gateway: BinanceSpotGateway = gateway
        self.gateway_name: str = gateway.gateway_name

        self.ticks: Dict[str, TickData] = {}
        self.reqid: int = 0

    def connect(self, proxy_host: str, proxy_port: int):
        """connect market data ws"""
        self.init(WEBSOCKET_DATA_HOST, proxy_host, proxy_port)

        self.start()

    def on_connected(self) -> None:
        """data ws connected"""
        self.gateway.write_log("data ws connected")

        # re-subscribe data.
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

        # init the tick Object
        tick: TickData = TickData(
            symbol=req.symbol,
            name=symbol_contract_map[req.symbol].name,
            exchange=Exchange.BINANCE,
            datetime=datetime.now(LOCAL_TZ),
            gateway_name=self.gateway_name,
        )
        self.ticks[req.symbol] = tick

        channels = [
            f"{req.symbol}@ticker",
            f"{req.symbol}@depth5"
        ]

        req: dict = {
            "method": "SUBSCRIBE",
            "params": channels,
            "id": self.reqid
        }
        self.send_packet(req)

    def on_packet(self, packet: dict) -> None:
        """receiving the subscribed data"""
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
            bids: list = data["bids"]
            for n in range(min(5, len(bids))):
                price, volume = bids[n]
                tick.__setattr__("bid_price_" + str(n + 1), float(price))
                tick.__setattr__("bid_volume_" + str(n + 1), float(volume))

            asks: list = data["asks"]
            for n in range(min(5, len(asks))):
                price, volume = asks[n]
                tick.__setattr__("ask_price_" + str(n + 1), float(price))
                tick.__setattr__("ask_volume_" + str(n + 1), float(volume))

        if tick.last_price:
            tick.localtime = datetime.now()
            self.gateway.on_tick(copy(tick))


def generate_datetime(timestamp: float) -> datetime:
    """generate datetime"""
    dt: datetime = datetime.fromtimestamp(timestamp / 1000)
    dt: datetime = LOCAL_TZ.localize(dt)
    return dt
