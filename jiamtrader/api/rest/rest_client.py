import sys
import traceback
from datetime import datetime
from typing import Any, Callable, Optional, Union, Type
from types import TracebackType, coroutine
from threading import Thread
from asyncio import (
    get_event_loop,
    set_event_loop,
    run_coroutine_threadsafe,
    AbstractEventLoop,
    Future
)
from json import loads

from aiohttp import ClientSession, ClientResponse


CALLBACK_TYPE = Callable[[dict, "Request"], None]
ON_FAILED_TYPE = Callable[[int, "Request"], None]
ON_ERROR_TYPE = Callable[[Type, Exception, TracebackType, "Request"], None]


class Request(object):
    """
    请求对象

    method: API的请求方法（GET, POST, PUT, DELETE, QUERY）
    path: API的请求路径（不包含根地址）
    callback: 请求成功的回调函数
    params: 请求表单的参数字典
    data: 请求主体数据，如果传入字典会被自动转换为json
    headers: 请求头部的字典
    on_failed: 请求失败的回调函数
    on_error: 请求异常的回调函数
    extra: 任意其他数据（用于回调时获取）
    """

    def __init__(
        self,
        method: str,
        path: str,
        params: dict,
        data: Union[dict, str, bytes],
        headers: dict,
        callback: CALLBACK_TYPE = None,
        on_failed: ON_FAILED_TYPE = None,
        on_error: ON_ERROR_TYPE = None,
        extra: Any = None,
    ):
        """"""
        self.method: str = method
        self.path: str = path
        self.callback: CALLBACK_TYPE = callback
        self.params: dict = params
        self.data: Union[dict, str, bytes] = data
        self.headers: dict = headers

        self.on_failed: ON_FAILED_TYPE = on_failed
        self.on_error: ON_ERROR_TYPE = on_error
        self.extra: Any = extra

        self.response: "Response" = None

    def __str__(self):
        """字符串表示"""
        if self.response is None:
            status_code = "terminated"
        else:
            status_code = self.response.status_code

        return (
            "request : {} {} because {}: \n"
            "headers: {}\n"
            "params: {}\n"
            "data: {}\n"
            "response:"
            "{}\n".format(
                self.method,
                self.path,
                status_code,
                self.headers,
                self.params,
                self.data,
                "" if self.response is None else self.response.text,
            )
        )


class Response:
    """结果对象"""

    def __init__(self, status_code: int, text: str) -> None:
        """"""
        self.status_code: int = status_code
        self.text: str = text

    def json(self) -> dict:
        """获取字符串对应的JSON格式数据"""
        data = loads(self.text)
        return data


class RestClient(object):
    """
    针对各类RestFul API的异步客户端

    * 重载sign方法来实现请求签名逻辑
    * 重载on_failed方法来实现请求失败的标准回调处理
    * 重载on_error方法来实现请求异常的标准回调处理
    """

    def __init__(self):
        """"""
        self.url_base: str = ""
        self.proxy: str = ""

        self.session: ClientSession = ClientSession(trust_env=True)
        self.loop: AbstractEventLoop = None

    def init(
        self,
        url_base: str,
        proxy_host: str = "",
        proxy_port: int = 0
    ) -> None:
        """传入REST API的根地址，初始化客户端"""
        self.url_base = url_base

        if proxy_host and proxy_port:
            self.proxy = f"http://{proxy_host}:{proxy_port}"

    def start(self, session_number: int = 3) -> None:
        """启动客户端的事件循环"""
        if not self.loop:
            self.loop = get_event_loop()

        start_event_loop(self.loop)

    def stop(self) -> None:
        """停止客户端的事件循环"""
        if self.loop and self.loop.is_running():
            self.loop.stop()

    def join(self) -> None:
        """等待子线程退出"""
        pass

    def add_request(
        self,
        method: str,
        path: str,
        callback: CALLBACK_TYPE,
        params: dict = None,
        data: Union[dict, str, bytes] = None,
        headers: dict = None,
        on_failed: ON_FAILED_TYPE = None,
        on_error: ON_ERROR_TYPE = None,
        extra: Any = None,
    ) -> Request:
        """添加新的请求任务"""
        request: Request = Request(
            method,
            path,
            params,
            data,
            headers,
            callback,
            on_failed,
            on_error,
            extra,
        )

        coro: coroutine = self._process_request(request)
        run_coroutine_threadsafe(coro, self.loop)
        return request

    def request(
        self,
        method: str,
        path: str,
        params: dict = None,
        data: dict = None,
        headers: dict = None,
    ) -> Response:
        """同步请求函数"""
        request: Request = Request(method, path, params, data, headers)
        coro: coroutine = self._get_response(request)
        fut: Future = run_coroutine_threadsafe(coro, self.loop)
        return fut.result()

    def sign(self, request: Request) -> None:
        """签名函数（由用户继承实现具体签名逻辑）"""
        return request

    def on_failed(self, status_code: int, request: Request) -> None:
        """请求失败的默认回调"""
        print("RestClient on failed" + "-" * 10)
        print(str(request))

    def on_error(
        self,
        exception_type: type,
        exception_value: Exception,
        tb,
        request: Optional[Request],
    ) -> None:
        """请求触发异常的默认回调"""
        try:
            print("RestClient on error" + "-" * 10)
            print(self.exception_detail(exception_type, exception_value, tb, request))
        except Exception:
            traceback.print_exc()

    def exception_detail(
        self,
        exception_type: type,
        exception_value: Exception,
        tb,
        request: Optional[Request],
    ) -> None:
        """将异常信息转化生成字符串"""
        text = "[{}]: Unhandled RestClient Error:{}\n".format(
            datetime.now().isoformat(), exception_type
        )
        text += "request:{}\n".format(request)
        text += "Exception trace: \n"
        text += "".join(
            traceback.format_exception(exception_type, exception_value, tb)
        )
        return text

    async def _get_response(self, request: Request) -> Response:
        """发送请求到服务器，并返回处理结果对象"""
        request = self.sign(request)
        url = self._make_full_url(request.path)

        cr: ClientResponse = await self.session.request(
            request.method,
            url,
            headers=request.headers,
            params=request.params,
            data=request.data,
            proxy=self.proxy
        )

        text: str = await cr.text()
        status_code = cr.status

        request.response = Response(status_code, text)
        return request.response

    async def _process_request(self, request: Request) -> None:
        """发送请求到服务器，并对返回进行后续处理"""
        try:
            response: Response = await self._get_response(request)
            status_code: int = response.status_code

            # 2xx的代码表示处理成功
            if status_code // 100 == 2:
                request.callback(response.json(), request)
            # 否则说明处理失败
            else:
                # 设置了专用失败回调
                if request.on_failed:
                    request.on_failed(status_code, request)
                # 否则使用全局失败回调
                else:
                    self.on_failed(status_code, request)
        except Exception:
            t, v, tb = sys.exc_info()
            # 设置了专用异常回调
            if request.on_error:
                request.on_error(t, v, tb, request)
            # 否则使用全局异常回调
            else:
                self.on_error(t, v, tb, request)

    def _make_full_url(self, path: str) -> str:
        """组合根地址生成完整的请求路径"""
        url: str = self.url_base + path
        return url


def start_event_loop(loop: AbstractEventLoop) -> None:
    """启动事件循环"""
    # 如果事件循环未运行，则创建后台线程来运行
    if not loop.is_running():
        thread = Thread(target=run_event_loop, args=(loop,))
        thread.daemon = True
        thread.start()


def run_event_loop(loop: AbstractEventLoop) -> None:
    """运行事件循环"""
    set_event_loop(loop)
    loop.run_forever()
