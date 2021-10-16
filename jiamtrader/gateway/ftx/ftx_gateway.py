import json
import time
import hmac
from copy import copy
from enum import Enum
from threading import Lock
from datetime import timezone, datetime, timedelta
import pytz
from typing import Any, Dict, List

from jiamtrader.event.engine import EventEngine
from jiamtrader.trader.gateway import BaseGateway
from jiamtrader.trader.constant import (
    Interval,
    Status,
    Direction,
    Exchange
)
from jiamtrader.trader.object import (
    AccountData,
    CancelRequest,
    OrderRequest,
    PositionData,
    SubscribeRequest,
    OrderType,
    OrderData,
    ContractData,
    Product,
    TickData,
    TradeData,
    HistoryRequest,
    BarData
)
from jiamtrader.trader.event import EVENT_TIMER

from jiamtrader.api.rest import Request, RestClient, Response
from jiamtrader.api.websocket import WebsocketClient


# 中国时区
CHINA_TZ = pytz.timezone("Asia/Shanghai")

# REST API地址
REST_HOST: str = "https://ftx.com"

# Websocket API地址
WEBSOCKET_HOST: str = "wss://ftx.com/ws/"

# 委托类型映射
ORDERTYPE_VT2FTX = {
    OrderType.LIMIT: "limit",
    OrderType.MARKET: "market"
}

ORDERTYPE_FTX2VT = {v: k for k, v in ORDERTYPE_VT2FTX.items()}

# 买卖方向映射
DIRECTION_VT2FTX = {
    Direction.LONG: "buy",
    Direction.SHORT: "sell",
    Direction.NET: "net"
}

DIRECTION_FTX2VT = {v: k for k, v in DIRECTION_VT2FTX.items()}

# 商品类型映射
PRODUCTTYPE_VT2FTX = {
    Product.FUTURES: "future",
    Product.SPOT: "spot"
}

PRODUCTTYPE_FTX2VT = {v: k for k, v in PRODUCTTYPE_VT2FTX.items()}

# 窗口长度映射
WINDOW_VT2FTX = {
    Interval.MINUTE: 60,
    Interval.HOUR: 3600,
    Interval.DAILY: 86400,
    Interval.WEEKLY: 604800
}

WINDOW_FTX2VT = {v: k for k, v in WINDOW_VT2FTX.items()}

# 历史数据长度限制映射
LMIMIT_VT2FTX = {
    Interval.MINUTE: 950,
    Interval.HOUR: 1400,
    Interval.DAILY: 1400,
    Interval.WEEKLY: 1400
}

# 合约数据全局缓存字典
symbol_contract_map: Dict[str, ContractData] = {}


# 鉴权类型
class Security(Enum):
    NONE: int = 0
    SIGNED: int = 1


class OrderBook:
    """用于维护orderbook"""

    def __init__(self):
        """"""
        self.bids = []
        self.asks = []
        self.bid_dict = {}
        self.ask_dict = {}

    def init(self, bid: List[List], ask: List[List]) -> List[List]:
        """初始化"""
        for i in bid:
            self.bids.append(float(i[0]))
            self.bid_dict[i[0]] = float(i[1])
        self.bids.sort(reverse=True)

        for i in ask:
            self.asks.append(float(i[0]))
            self.ask_dict[i[0]] = float(i[1])
        self.asks.sort(reverse=False)

        p: List[List] = []
        q: List[List] = []
        for i in range(5):
            p.append([self.bids[i], self.bid_dict[self.bids[i]]])
            q.append([self.asks[i], self.ask_dict[self.asks[i]]])

        return {"bid": p, "ask": q}

    def bid_add(self, bid: List[List]) -> None:
        """添加bid"""
        if len(bid) > 0:
            for i in bid:
                if float(i[1]) == 0:
                    if float(i[0]) in self.bids:
                        self.bids.remove(float(i[0]))
                        self.bid_dict.pop(float(i[0]))
                else:
                    if float(i[0]) not in self.bids:
                        self.bids.append(float(i[0]))
                    self.bid_dict[float(i[0])] = float(i[1])
            self.bids.sort(reverse=True)

    def ask_add(self, ask: List[List]) -> None:
        """添加ask"""
        if len(ask) > 0:
            for i in ask:
                if float(i[1]) == 0:
                    if float(i[0]) in self.asks:
                        self.asks.remove(float(i[0]))
                        self.ask_dict.pop(float(i[0]))
                else:
                    if float(i[0]) not in self.asks:
                        self.asks.append(float(i[0]))
                    self.ask_dict[float(i[0])] = float(i[1])
            self.asks.sort(reverse=False)

    def add(self, bid: List[List], ask: List[List]) -> List[List]:
        """添加bid和ask"""
        self.bid_add(bid)
        self.ask_add(ask)

        p: List[List] = []
        q: List[List] = []
        for i in range(5):
            p.append([self.bids[i], self.bid_dict[self.bids[i]]])
            q.append([self.asks[i], self.ask_dict[self.asks[i]]])

        return {"bid": p, "ask": q}


class FtxGateway(BaseGateway):
    """vn.py用于对接FTX的交易接口"""

    default_setting: Dict[str, Any] = {
        "key": "",
        "secret": "",
        "代理地址": "",
        "代理端口": 0,
    }

    exchanges: Exchange = [Exchange.FTX]

    def __init__(self, event_engine: EventEngine, gateway_name: str = "FTX") -> None:
        """构造函数"""
        super().__init__(event_engine, gateway_name)

        self.ws_api: "FtxWebsocketApi" = FtxWebsocketApi(self)
        self.rest_api: "FtxRestApi" = FtxRestApi(self)

        self.orders: Dict[str, OrderData] = {}
        self.order_id: Dict[str, str] = {}

    def connect(self, setting: dict) -> None:
        """连接交易接口"""
        key: str = setting["key"]
        secret: str = setting["secret"]
        proxy_host: str = setting["代理地址"]
        proxy_port: int = setting["代理端口"]

        self.rest_api.connect(key, secret, proxy_host, proxy_port)
        self.ws_api.connect(key, secret, proxy_host, proxy_port)

        self.init_ping()

    def subscribe(self, req: SubscribeRequest) -> None:
        """订阅行情"""
        self.ws_api.subscribe(req)

    def unsubscribe(self, req: SubscribeRequest) -> None:
        """取消行情订阅"""
        self.ws_api.unsubscribe(req)

    def send_order(self, req: OrderRequest) -> None:
        """委托下单"""
        return self.rest_api.send_order(req)

    def cancel_order(self, req: CancelRequest) -> None:
        """委托撤单"""
        self.rest_api.cancel_order(req)

    def query_account(self) -> None:
        """查询资金"""
        self.rest_api.query_account()

    def query_position(self) -> None:
        """查询持仓"""
        self.rest_api.query_position()

    def query_orders(self) -> None:
        """查询未成交委托"""
        self.rest_api.query_order()

    def on_order(self, order: OrderData) -> None:
        """推送委托数据"""
        self.orders[order.orderid] = copy(order)
        super().on_order(order)

    def get_order(self, orderid: str) -> OrderData:
        """查询委托数据"""
        return self.orders.get(orderid, None)

    def query_history(self, req: HistoryRequest) -> List[BarData]:
        """查询历史数据"""
        return self.rest_api.query_history(req)

    def query_price(self, symbol: str) -> List:
        """查询高开低收价格"""
        return self.rest_api.query_price(symbol)

    def close(self) -> None:
        """关闭连接"""
        self.rest_api.stop()
        self.ws_api.stop()

    def process_timer_event(self, event) -> None:
        """定时事件处理"""
        self.count += 1
        if self.count < 15:
            return
        self.count = 0
        self.ws_api.ping()

    def init_ping(self) -> None:
        """初始化心跳"""
        self.count: int = 0
        self.event_engine.register(EVENT_TIMER, self.process_timer_event)


class FtxRestApi(RestClient):
    """FTX的REST API"""

    def __init__(self, gateway: FtxGateway) -> None:
        """构造函数"""
        super().__init__()

        self.gateway: FtxGateway = gateway
        self.gateway_name: str = gateway.gateway_name

        self.ws_api: FtxWebsocketApi = self.gateway.ws_api

        # 保存用户登陆信息
        self.key: str = ""
        self.secret: str = ""

        # 确保生成的orderid不发生冲突
        self.order_count: int = 1_000_000
        self.order_count_lock: Lock = Lock()
        self.connect_time: int = 0

    def sign(self, request: Request) -> Request:
        """生成FTX签名"""
        # 获取鉴权类型并将其从data中删除
        security = request.data["security"]
        request.data.pop("security")

        if security == Security.NONE:
            request.data = None
            return request

        if security == Security.SIGNED:
            timestamp = int(time.time() * 1000)
            signature_payload = f'{timestamp}{request.method}{request.path}'

            if request.data:
                request.data = json.dumps(request.data)
                signature_payload += request.data
            signature_payload = signature_payload.encode()
            signature = hmac.new(self.secret, signature_payload, 'sha256').hexdigest()

            if request.headers is None:
                request.headers = {'Content-Type': 'application/json'}

            request.headers['FTX-KEY'] = self.key
            request.headers['FTX-SIGN'] = signature
            request.headers['FTX-TS'] = str(timestamp)

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
        self.secret = secret.encode()
        self.proxy_port = proxy_host
        self.proxy_host = proxy_port

        self.connect_time = (
            int(datetime.now().strftime("%y%m%d%H%M%S")) * self.order_count
        )

        self.init(REST_HOST, self.proxy_host, self.proxy_port)
        self.start()

        self.gateway.write_log("REST API启动成功")

        self.query_account()
        self.query_position()
        self.query_order()
        self.query_contract()

    def query_account(self) -> None:
        """查询资金"""
        data: dict = {"security": Security.SIGNED}

        path: str = "/api/wallet/balances"

        self.add_request(
            method="GET",
            path=path,
            callback=self.on_query_account,
            data=data
        )

    def query_position(self) -> None:
        """查询持仓"""
        data: dict = {"security": Security.SIGNED}

        path: str = "/api/positions"

        self.add_request(
            method="GET",
            path=path,
            callback=self.on_query_position,
            data=data
        )

    def query_order(self) -> None:
        """查询未成交委托"""
        data: dict = {"security": Security.SIGNED}

        path: str = "/api/orders"

        self.add_request(
            method="GET",
            path=path,
            callback=self.on_query_order,
            data=data
        )

    def query_contract(self) -> None:
        """查询合约信息"""
        data: dict = {"security": Security.NONE}

        path: str = "/api/markets"

        self.add_request(
            method="GET",
            path=path,
            callback=self.on_query_contract,
            data=data
        )

    def _new_order_id(self) -> int:
        """生成本地委托号"""
        with self.order_count_lock:
            self.order_count += 1
            return self.order_count

    def send_order(self, req: OrderRequest) -> str:
        """委托下单"""
        # 生成本地委托号
        orderid: str = str(self.connect_time + self._new_order_id())

        # 推送提交中事件
        order: OrderData = req.create_order_data(
            orderid,
            self.gateway_name
        )
        self.gateway.on_order(order)

        data: dict = {
            "market": req.symbol.upper(),
            "side": DIRECTION_VT2FTX[req.direction],
            "price": str(req.price),
            "size": str(req.volume),
            "type": ORDERTYPE_VT2FTX[req.type],
            "reduceOnly": False,
            "ioc": False,
            "postOnly": False,
            "clientId": orderid,
            "rejectOnPriceBand": False,
            "security": Security.SIGNED
        }

        self.add_request(
            method="POST",
            path="/api/orders",
            callback=self.on_send_order,
            data=data,
            extra=order,
            on_error=self.on_send_order_error,
            on_failed=self.on_send_order_failed
        )

        return order.vt_orderid

    def cancel_order(self, req: CancelRequest) -> None:
        """委托撤单"""
        data: dict = {"security": Security.SIGNED}

        path: str = "/api/orders/by_client_id/" + req.orderid

        order: OrderData = self.gateway.get_order(req.orderid)

        self.add_request(
            method="DELETE",
            path=path,
            callback=self.on_cancel_order,
            data=data,
            on_failed=self.on_cancel_failed,
            extra=order
        )

    def on_query_account(self, data: dict, request: Request) -> None:
        """资金查询回报"""
        for asset in data["result"]:
            account: AccountData = AccountData(
                accountid=asset["coin"],
                balance=asset["total"],
                gateway_name=self.gateway_name
            )
            account.available = asset["free"]
            account.frozen = account.balance - account.available

            if account.balance:
                self.gateway.on_account(account)

        self.gateway.write_log("账户资金查询成功")

    def on_query_position(self, data: dict, request: Request) -> None:
        """持仓查询回报"""
        for d in data["result"]:
            position: PositionData = PositionData(
                symbol=d["future"],
                exchange=Exchange.FTX,
                direction=DIRECTION_FTX2VT["net"],
                volume=float(d["netSize"]),
                price=0,
                pnl=float(d["unrealizedPnl"]),
                gateway_name=self.gateway_name,
            )

            self.gateway.on_position(position)

        self.gateway.write_log("持仓信息查询成功")

    def on_query_order(self, data: dict, request: Request) -> None:
        """未成交委托查询回报"""
        for d in data["result"]:
            # 先判断订单状态
            current_status = d["status"]
            size = d["size"]
            filled_size = d["filledSize"]
            remaining_size = d["remainingSize"]
            if current_status == "new":
                status = Status.NOTTRADED
            elif (current_status == "open") & (filled_size == 0):
                status = Status.NOTTRADED
            elif (current_status == "open") & (size != filled_size):
                status = Status.PARTTRADED
            elif (current_status == "closed") & ((size != filled_size)):
                status = Status.CANCELLED
            elif (remaining_size == 0) & (size == filled_size):
                status = Status.ALLTRADED
            else:
                status = "other status"

            order: OrderData = OrderData(
                orderid=d["clientId"],
                symbol=d["market"],
                exchange=Exchange.FTX,
                price=float(d["price"]),
                volume=float(d["size"]),
                type=ORDERTYPE_FTX2VT[d["type"]],
                direction=DIRECTION_FTX2VT[d["side"]],
                traded=d["filledSize"],
                status=status,
                datetime=change_datetime(d["createdAt"]),
                gateway_name=self.gateway_name,
            )
            self.gateway.on_order(order)

        self.gateway.write_log("委托信息查询成功")

    def on_query_contract(self, data: dict, request: Request):
        """合约信息查询回报"""
        for d in data["result"]:
            contract: ContractData = ContractData(
                symbol=d["name"],
                exchange=Exchange.FTX,
                name=d["name"],
                pricetick=d["priceIncrement"],
                size=1,
                min_volume=d["sizeIncrement"],
                product=PRODUCTTYPE_FTX2VT[d["type"]],
                net_position=True,
                history_data=True,
                gateway_name=self.gateway_name,
            )
            self.gateway.on_contract(contract)

            symbol_contract_map[contract.symbol] = contract

        self.gateway.write_log("合约信息查询成功")

    def on_send_order(self, data: dict, request: Request) -> None:
        """委托下单回报"""
        pass

    def on_send_order_error(
        self, exception_type: type, exception_value: Exception, tb, request: Request
    ) -> None:
        """委托下单回报函数报错回报"""
        order: OrderData = request.extra
        order.status = Status.REJECTED
        self.gateway.on_order(order)

        if not issubclass(exception_type, ConnectionError):
            self.on_error(exception_type, exception_value, tb, request)

    def on_send_order_failed(self, status_code: str, request: Request) -> None:
        """委托下单失败服务器报错回报"""
        order: OrderData = request.extra
        order.status = Status.REJECTED
        self.gateway.on_order(order)

        msg: str = f"委托失败，状态码：{status_code}，信息：{request.response.text}"
        self.gateway.write_log(msg)

    def on_cancel_order(self, status_code: str, request: Request) -> None:
        """委托撤单回报"""
        pass

    def on_cancel_failed(self, status_code: str, request: Request):
        """撤单回报函数报错回报"""
        if request.extra:
            order = request.extra
            order.status = Status.REJECTED
            self.gateway.on_order(order)

        msg = f"撤单失败，状态码：{status_code}，信息：{request.response.text}"
        self.gateway.write_log(msg)

    def query_history(self, req: HistoryRequest) -> List[BarData]:
        """查询历史数据"""
        history: List[BarData] = []
        limit: int = LMIMIT_VT2FTX[req.interval]

        start: int = int(datetime.timestamp(req.start))
        end: int = int(datetime.timestamp(req.end))

        tmp_start = max(start, end - WINDOW_VT2FTX[req.interval] * limit)

        buf: List[BarData] = None

        while True:
            params = {
                "resolution": WINDOW_VT2FTX[req.interval],
                "start_time": tmp_start,
                "end_time": end
            }

            path = f"/api/markets/{req.symbol}/candles?"

            resp: Response = self.request(
                "GET",
                path,
                data={"security": Security.NONE},
                params=params
            )

            # 如果请求失败则终止循环
            if resp.status_code // 100 != 2:
                msg: str = f"获取历史数据失败，状态码：{resp.status_code}，信息：{resp.text}"
                self.gateway.write_log(msg)
                break
            else:
                data: dict = resp.json()
                # 整个时间段内都未有数据，终止循环
                if (not data["result"]) and (buf is None):
                    stop_time = datetime.utcfromtimestamp(tmp_start)
                    msg: str = f"获取历史数据为空，开始时间：{stop_time}"
                    self.gateway.write_log(msg)
                    break
                # 剩下的时间端内不再有数据，终止循环
                elif (not data["result"]) and (buf is not None):
                    msg: str = "获取历史数据完成"
                    self.gateway.write_log(msg)
                    break

                buf: List[BarData] = []

                for his_data in data["result"]:
                    bar = BarData(
                        symbol=req.symbol,
                        exchange=req.exchange,
                        datetime=datetime.utcfromtimestamp(his_data["time"] / 1000),
                        interval=req.interval,
                        volume=his_data["volume"],
                        open_price=his_data["open"],
                        high_price=his_data["high"],
                        low_price=his_data["low"],
                        close_price=his_data["close"],
                        gateway_name=self.gateway_name
                    )
                    buf.append(bar)

                begin: datetime = buf[0].datetime
                end: datetime = buf[-1].datetime

                history.extend(buf)

                msg: str = f"获取历史数据成功，{req.symbol} - {req.interval.value}，{begin} - {end}"
                self.gateway.write_log(msg)

                # 最后一段查询结束后终止
                if tmp_start == start:
                    msg: str = "获取历史数据完成"
                    self.gateway.write_log(msg)
                    break

                # 更新下一个时间段
                end = tmp_start
                tmp_start = max(start, end - WINDOW_VT2FTX[req.interval] * limit)

        return history

    def query_price(self, symbol: str) -> List:
        """查询当天高开低收"""
        start = datetime.timestamp(datetime.now() - timedelta(days=1))
        params = {
            "resolution": 86400,
            "start_time": start
        }
        path = f"/api/markets/{symbol}/candles?"

        resp = self.request(
            "GET",
            path,
            data={"security": Security.NONE},
            params=params
        )
        data = resp.json()

        return data["result"][0]["open"], data["result"][0]["high"], data["result"][0]["low"], data["result"][0]["close"]


class FtxWebsocketApi(WebsocketClient):
    """FTX交易Websocket API"""

    def __init__(self, gateway: FtxGateway) -> None:
        """构造函数"""
        super().__init__()

        self.gateway: FtxGateway = gateway
        self.gateway_name: str = gateway.gateway_name

        self.subscribed: Dict[str, SubscribeRequest] = {}
        self.orderbook: Dict[str, OrderBook] = {}
        self.holc: Dict[str, Dict] = {}

        self.start_time = datetime.utcnow().date()
        self.count = 0

    def connect(
        self,
        api_key: str,
        api_secret_key: str,
        proxy_host: str,
        proxy_port: int
    ) -> None:
        """连接Websocket交易频道"""
        self.api_key = api_key
        self.api_secret_key = api_secret_key
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.init(WEBSOCKET_HOST, self.proxy_host, self.proxy_port)
        self.start()

        self.gateway.write_log("行情Websocket API启动成功")

    def on_connected(self) -> None:
        """连接成功回报"""
        self.gateway.write_log("行情Websocket API连接刷新")

        self.ping()
        self.authenticate(self.api_key, self.api_secret_key)

        for req in list(self.subscribed.values()):
            self.resubscribe(req)

        self.subscribe_private_channels()

    def on_disconnected(self) -> None:
        """"""
        self.gateway.write_log("行情Websocket 连接断开")

    def authenticate(
        self,
        api_key: str,
        api_secret_key: str
    ) -> None:
        """登陆私人频道"""
        timestamp: int = int(time.time() * 1000)
        signature_payload = f'{timestamp}websocket_login'.encode()
        signature: str = hmac.new(api_secret_key.encode(), signature_payload, 'sha256').hexdigest()
        auth = {
            'args': {'key': api_key,
                     'sign': signature,
                     'time': timestamp},
            'op': 'login'
        }
        self.send_packet(auth)

    def subscribe(self, req: SubscribeRequest) -> None:
        """订阅行情"""
        if req.symbol not in symbol_contract_map:
            self.gateway.write_log(f"找不到该合约代码{req.symbol}")
            return

        if req.vt_symbol in self.subscribed:
            return

        self.holc[req.symbol] = {}
        self.holc[req.symbol]["start_time"] = datetime.utcnow().date().day
        self.holc[req.symbol]["open"], self.holc[req.symbol]["high"], self.holc[req.symbol]["low"], self.holc[req.symbol]["close"] = self.gateway.query_price(req.symbol)

        self.subscribed[req.vt_symbol] = req
        subscribe_ticker = {'op': 'subscribe', 'channel': 'ticker', 'market': req.symbol}
        self.send_packet(subscribe_ticker)
        subscribe_orderbook = {'op': 'subscribe', 'channel': 'orderbook', 'market': req.symbol}
        self.send_packet(subscribe_orderbook)

    def unsubscribe(self, req: SubscribeRequest) -> None:
        """取消订阅行情"""
        if req.symbol not in symbol_contract_map:
            self.gateway.write_log(f"找不到该合约代码{req.symbol}")
            return

        if req.vt_symbol in self.subscribed:
            self.subscribed.pop(req.vt_symbol)
            unsubscribe_ticker = {'op': 'unsubscribe', 'channel': 'ticker', 'market': req.symbol}
            self.send_packet(unsubscribe_ticker)
            unsubscribe_orderbook = {'op': 'unsubscribe', 'channel': 'orderbook', 'market': req.symbol}
            self.send_packet(unsubscribe_orderbook)

            # 释放该合约缓存数据
            symbol = req.vt_symbol.split(".")[0]
            self.orderbook.pop(symbol)
            self.holc.pop(symbol)

    def resubscribe(self, req: SubscribeRequest) -> None:
        """重连后订阅行情"""
        if req.symbol not in symbol_contract_map:
            self.gateway.write_log(f"找不到该合约代码{req.symbol}")
            return

        self.subscribed[req.vt_symbol] = req
        subscribe_ticker = {'op': 'subscribe', 'channel': 'ticker', 'market': req.symbol}
        self.send_packet(subscribe_ticker)
        subscribe_orderbook = {'op': 'subscribe', 'channel': 'orderbook', 'market': req.symbol}
        self.send_packet(subscribe_orderbook)

    def subscribe_private_channels(self) -> None:
        """订阅个人orders和fills行情"""
        self.send_packet({'op': 'subscribe', 'channel': 'fills'})
        self.send_packet({'op': 'subscribe', 'channel': 'orders'})

    def ping(self) -> None:
        """发送心跳"""
        self.send_packet({'op': 'ping'})

    def update_holc(self, symbol) -> None:
        """更新订阅代码的holc"""
        if symbol in self.subscribed.keys():
            self.holc[symbol]["open"], self.holc[symbol]["high"], self.holc[symbol]["low"], self.holc[symbol]["close"] = self.gateway.query_price(symbol)

    def on_packet(self, packet: Any) -> None:
        """推送数据回报"""
        # 更新推送
        if packet["type"] == "update":
            channel = packet["channel"]

            if channel == "ticker":
                symbol = packet["market"]
                self.holc[symbol]["last_price"] = packet["data"]["last"]
                tm_mday = time.gmtime(packet["data"]["time"]).tm_mday

                if self.holc[symbol]["start_time"] == tm_mday:
                    if self.holc[symbol]["last_price"] > self.holc[symbol]["high"]:
                        self.holc[symbol]["high"] = self.holc[symbol]["last_price"]
                    if self.holc[symbol]["last_price"] < self.holc[symbol]["low"]:
                        self.holc[symbol]["low"] = self.holc[symbol]["last_price"]
                else:
                    self.holc[symbol]["start_time"] = tm_mday
                    self.update_holc(symbol)

            elif channel == "orderbook":
                symbol = packet["market"]
                orderbook = self.orderbook[symbol].add(packet["data"]["bids"], packet["data"]["asks"])
                tick: TickData = TickData(
                    gateway_name=self.gateway_name,
                    symbol=symbol,
                    exchange=Exchange.FTX,
                    datetime=generate_datetime(packet["data"]["time"]),

                    name="FTX",
                    volume=0,
                    open_price=self.holc[symbol]["open"],
                    high_price=self.holc[symbol]["high"],
                    low_price=self.holc[symbol]["low"],
                    last_price=self.holc[symbol]["last_price"],

                    bid_price_1=orderbook["bid"][0][0],
                    bid_volume_1=orderbook["bid"][0][1],
                    bid_price_2=orderbook["bid"][1][0],
                    bid_volume_2=orderbook["bid"][1][1],
                    bid_price_3=orderbook["bid"][2][0],
                    bid_volume_3=orderbook["bid"][2][1],
                    bid_price_4=orderbook["bid"][3][0],
                    bid_volume_4=orderbook["bid"][3][1],
                    bid_price_5=orderbook["bid"][4][0],
                    bid_volume_5=orderbook["bid"][4][1],
                    ask_price_1=orderbook["ask"][0][0],
                    ask_volume_1=orderbook["ask"][0][1],
                    ask_price_2=orderbook["ask"][1][0],
                    ask_volume_2=orderbook["ask"][1][1],
                    ask_price_3=orderbook["ask"][2][0],
                    ask_volume_3=orderbook["ask"][2][1],
                    ask_price_4=orderbook["ask"][3][0],
                    ask_volume_4=orderbook["ask"][3][1],
                    ask_price_5=orderbook["ask"][4][0],
                    ask_volume_5=orderbook["ask"][4][1],
                )
                if tick.last_price:
                    self.gateway.on_tick(copy(tick))

            elif channel == "trades":
                pass

            elif channel == "fills":
                d = packet["data"]
                trade: TradeData = TradeData(
                    symbol=d["market"],
                    exchange=Exchange.FTX,
                    orderid=self.gateway.order_id[d["orderId"]],
                    tradeid=d["tradeId"],
                    direction=DIRECTION_FTX2VT[d["side"]],
                    price=float(d["price"]),
                    volume=float(d["size"]),
                    datetime=change_datetime(d["time"]),
                    gateway_name=self.gateway_name,
                )
                self.gateway.on_trade(trade)
                self.gateway.query_position()
                self.gateway.query_account()

            elif channel == "orders":
                d = packet["data"]
                current_status = d["status"]
                size = d["size"]
                filled_size = d["filledSize"]
                remaining_size = d["remainingSize"]
                if current_status == "new":
                    status = Status.NOTTRADED
                elif (current_status == "open") & (filled_size == 0):
                    status = Status.NOTTRADED
                elif (current_status == "open") & (size != filled_size):
                    status = Status.PARTTRADED
                elif (current_status == "closed") & ((size != filled_size)):
                    status = Status.CANCELLED
                elif (remaining_size == 0) & (size == filled_size):
                    status = Status.ALLTRADED
                else:
                    status = "other status"

                order: OrderData = OrderData(
                    orderid=d["clientId"],
                    symbol=d["market"],
                    exchange=Exchange.FTX,
                    price=float(d["price"]),
                    volume=float(d["size"]),
                    type=ORDERTYPE_FTX2VT[d["type"]],
                    direction=DIRECTION_FTX2VT[d["side"]],
                    traded=d["filledSize"],
                    status=status,
                    datetime=change_datetime(d["createdAt"]),
                    gateway_name=self.gateway_name,
                )
                self.gateway.order_id[d["id"]] = d["clientId"]
                self.gateway.on_order(order)

            else:
                print(packet)

        # 初始推送
        elif packet["type"] == "partial":
            channel = packet["channel"]
            if channel == "orderbook":
                symbol = packet['market']
                self.orderbook[symbol] = OrderBook()
                orderbook = self.orderbook[symbol].init(packet["data"]["bids"], packet["data"]["asks"])
                tick: TickData = TickData(
                    gateway_name=self.gateway_name,
                    symbol=symbol,
                    exchange=Exchange.FTX,
                    datetime=generate_datetime(packet["data"]["time"]),

                    name="FTX",
                    volume=0,
                    open_price=self.holc[symbol]["open"],
                    high_price=self.holc[symbol]["high"],
                    low_price=self.holc[symbol]["low"],
                    last_price=self.holc[symbol]["last_price"],

                    bid_price_1=orderbook["bid"][0][0],
                    bid_volume_1=orderbook["bid"][0][1],
                    bid_price_2=orderbook["bid"][1][0],
                    bid_volume_2=orderbook["bid"][1][1],
                    bid_price_3=orderbook["bid"][2][0],
                    bid_volume_3=orderbook["bid"][2][1],
                    bid_price_4=orderbook["bid"][3][0],
                    bid_volume_4=orderbook["bid"][3][1],
                    bid_price_5=orderbook["bid"][4][0],
                    bid_volume_5=orderbook["bid"][4][1],

                    ask_price_1=orderbook["ask"][0][0],
                    ask_volume_1=orderbook["ask"][0][1],
                    ask_price_2=orderbook["ask"][1][0],
                    ask_volume_2=orderbook["ask"][1][1],
                    ask_price_3=orderbook["ask"][2][0],
                    ask_volume_3=orderbook["ask"][2][1],
                    ask_price_4=orderbook["ask"][3][0],
                    ask_volume_4=orderbook["ask"][3][1],
                    ask_price_5=orderbook["ask"][4][0],
                    ask_volume_5=orderbook["ask"][4][1],

                )
                if tick.last_price:
                    self.gateway.on_tick(copy(tick))

            else:
                print(packet)

        else:
            print(packet)


def change_datetime(created_time: str) -> datetime:
    """更改时区"""
    created_time = datetime.strptime(created_time[:-6], "%Y-%m-%dT%H:%M:%S.%f")
    created_time = created_time.replace(tzinfo=timezone.utc)
    created_time = created_time.astimezone(pytz.timezone(str(CHINA_TZ)))
    return created_time


def generate_datetime(timestamp: float) -> datetime:
    """生成时间"""
    dt: datetime = datetime.fromtimestamp(timestamp)
    dt: datetime = CHINA_TZ.localize(dt)
    return dt
