import re
import urllib
import pytz
import base64
import json
import zlib
import hashlib
import hmac
from typing import Dict
from datetime import datetime
from jiamtrader.trader.gateway import BaseGateway
from jiamtrader.api.websocket import WebsocketClient

# 中国时区
CHINA_TZ = pytz.timezone("Asia/Shanghai")


class HuobiWebsocketApiBase(WebsocketClient):
    """火币Websocket APIBase"""

    def __init__(self, gateway) -> None:
        """构造函数"""
        super().__init__()

        self.gateway: BaseGateway = gateway
        self.gateway_name: str = gateway.gateway_name

        self.key: str = ""
        self.secret: str = ""
        self.sign_host: str = ""
        self.path: str = ""

    def connect(
        self,
        key: str,
        secret: str,
        url: str,
        proxy_host: str,
        proxy_port: int
    ) -> None:
        """连接Websocket频道"""
        self.key = key
        self.secret = secret

        host, path = _split_url(url)
        self.sign_host = host
        self.path = path

        self.init(url, proxy_host, proxy_port)
        self.start()

    def login(self, v2: bool = False) -> int:
        """用户登录"""
        if v2:
            params: dict = create_signature_v2(
                self.key,
                "GET",
                self.sign_host,
                self.path,
                self.secret
            )

            req: dict = {
                "action": "req",
                "ch": "auth",
                "params": params
            }

            return self.send_packet(req)
        else:
            params: dict = {
                "op": "auth",
                "type": "api"
            }
            params.update(
                create_signature(
                    self.key,
                    "GET",
                    self.sign_host,
                    self.path,
                    self.secret
                )
            )
            return self.send_packet(params)

    def on_login(self, packet: dict) -> None:
        """用户登录回报"""
        pass

    @staticmethod
    def unpack_data(data) -> json.JSONDecoder:
        """"""
        if isinstance(data, bytes):
            buf = zlib.decompress(data, 31)
        else:
            buf = data

        return json.loads(buf)

    def on_packet(self, packet: dict) -> None:
        """推送数据回报"""
        if "ping" in packet:
            req: dict = {"pong": packet["ping"]}
            self.send_packet(req)
        elif "op" in packet and packet["op"] == "ping":
            req: dict = {
                "op": "pong",
                "ts": packet["ts"]
            }
            self.send_packet(req)
        elif "op" in packet and packet["op"] == "auth":
            return self.on_login()
        elif "action" in packet and packet["action"] == "ping":
            req: dict = {
                "action": "pong",
                "ts": packet["data"]["ts"]
            }
            self.send_packet(req)
        elif "action" in packet and packet["action"] == "req":
            return self.on_login(packet)
        elif "err-msg" in packet:
            return self.on_error_msg(packet)
        else:
            self.on_data(packet)

    def on_data(self, packet: dict) -> None:
        """"""
        print("data : {}".format(packet))

    def on_error_msg(self, packet: dict) -> None:
        """推送错误信息回报"""
        msg: str = packet["err-msg"]
        if msg == "invalid pong":
            return

        self.gateway.write_log(packet["err-msg"])


def _split_url(url) -> str:
    """
    将url拆分为host和path
    :return: host, path
    """
    result = re.match(r"\w+://([^/]*)(.*)", url)
    if result:
        return result.group(1), result.group(2)


def create_signature(
    api_key: str,
    method: str,
    host: str,
    path: str,
    secret_key: str,
    get_params=None
) -> Dict[str, str]:
    """
    创建Rest接口签名
    """
    sorted_params: list = [
        ("AccessKeyId", api_key),
        ("SignatureMethod", "HmacSHA256"),
        ("SignatureVersion", "2"),
        ("Timestamp", datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"))
    ]

    if get_params:
        sorted_params.extend(list(get_params.items()))
        sorted_params = list(sorted(sorted_params))
    encode_params = urllib.parse.urlencode(sorted_params)

    payload: list = [method, host, path, encode_params]
    payload: str = "\n".join(payload)
    payload: str = payload.encode(encoding="UTF8")

    secret_key: str = secret_key.encode(encoding="UTF8")

    digest: bytes = hmac.new(secret_key, payload, digestmod=hashlib.sha256).digest()
    signature: bytes = base64.b64encode(digest)

    params: dict = dict(sorted_params)
    params["Signature"] = signature.decode("UTF8")
    return params


def create_signature_v2(
    api_key: str,
    method: str,
    host: str,
    path: str,
    secret_key: str,
    get_params=None
) -> Dict[str, str]:
    """
    创建WebSocket接口签名
    """
    sorted_params: list = [
        ("accessKey", api_key),
        ("signatureMethod", "HmacSHA256"),
        ("signatureVersion", "2.1"),
        ("timestamp", datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"))
    ]

    if get_params:
        sorted_params.extend(list(get_params.items()))
        sorted_params = list(sorted(sorted_params))
    encode_params = urllib.parse.urlencode(sorted_params)

    payload: list = [method, host, path, encode_params]
    payload: str = "\n".join(payload)
    payload: str = payload.encode(encoding="UTF8")

    secret_key: str = secret_key.encode(encoding="UTF8")

    digest: bytes = hmac.new(secret_key, payload, digestmod=hashlib.sha256).digest()
    signature: bytes = base64.b64encode(digest)

    params: dict = dict(sorted_params)
    params["authType"] = "api"
    params["signature"] = signature.decode("UTF8")
    return params


def generate_datetime(timestamp: float) -> datetime:
    """生成时间"""
    dt: datetime = datetime.fromtimestamp(timestamp)
    dt: datetime = CHINA_TZ.localize(dt)
    return dt
