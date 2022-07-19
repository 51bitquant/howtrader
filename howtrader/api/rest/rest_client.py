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


CALLBACK_TYPE = Callable[[Union[dict, list], "Request"], None]
ON_FAILED_TYPE = Callable[[int, "Request"], None]
ON_ERROR_TYPE = Callable[[Type, Exception, TracebackType, "Request"], None]


class Request(object):
    """
    Request Object

    method: request api method（GET, POST, PUT, DELETE, QUERY）
    path: request path, not include the api host
    callback: callback function
    params: parameters in dict format
    data: post data, will convert into json if it's dict object
    headers: request headers
    on_failed: request failed callback function
    on_error: request error callback function
    extra: extra data, you may customize it
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
        """display in str"""
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
    """Response object"""

    def __init__(self, status_code: int, text: str) -> None:
        """"""
        self.status_code: int = status_code
        self.text: str = text

    def json(self) -> dict:
        """convert str into json format"""
        data = loads(self.text)
        return data


class RestClient(object):
    """
    RestClient

    * reload sign method, for api request require api secret and api key
    * reload on_failed method
    * reload on_error method
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
        """base url or api end point"""
        self.url_base = url_base

        if proxy_host and proxy_port:
            self.proxy = f"http://{proxy_host}:{proxy_port}"

    def start(self) -> None:
        """start event loop"""
        if not self.loop:
            self.loop = get_event_loop()

        start_event_loop(self.loop)

    def stop(self) -> None:
        """stop event loop"""
        if self.loop and self.loop.is_running():
            self.loop.stop()

    def join(self) -> None:
        """wait for thread to exit"""
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
        """add new request task"""
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
        if self.loop:
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
        """synchronous request function"""
        request: Request = Request(method, path, params, data, headers)
        coro: coroutine = self._get_response(request)
        fut: Future = run_coroutine_threadsafe(coro, self.loop)
        return fut.result()

    def sign(self, request: Request) -> Request:
        """sign function"""
        return request

    def on_failed(self, status_code: int, request: Request) -> None:
        """on failed"""
        print(f"RestClient on failed " + "-" * 10)
        print(str(request))

    def on_error(
        self,
        exception_type: type,
        exception_value: Exception,
        tb,
        request: Optional[Request],
    ) -> None:
        """on error"""
        try:
            print("RestClient on error " + "-" * 10)
            print(self.exception_detail(exception_type, exception_value, tb, request))
        except Exception:
            traceback.print_exc()

    def exception_detail(
        self,
        exception_type: type,
        exception_value: Exception,
        tb,
        request: Optional[Request],
    ) -> str:
        """convert exception msg into str"""
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
        """send the request to server then resolve the response data"""
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
        """process request"""
        try:
            response: Response = await self._get_response(request)
            status_code: int = response.status_code

            # 2xx code means success
            if status_code // 100 == 2:
                request.callback(response.json(), request)
            # failed
            else:
                # if on_failed request, then call the callback
                if request.on_failed:
                    request.on_failed(status_code, request)

                else:
                    self.on_failed(status_code, request)
        except Exception:
            t, v, tb = sys.exc_info()
            # on error.
            if request.on_error:
                request.on_error(t, v, tb, request)

            else:
                self.on_error(t, v, tb, request)

    def _make_full_url(self, path: str) -> str:
        """make the full request url"""
        url: str = self.url_base + path
        return url


def start_event_loop(loop: AbstractEventLoop) -> None:
    """start event loop"""
    # if the event loop is not running, then create the thread to run
    if not loop.is_running():
        thread = Thread(target=run_event_loop, args=(loop,))
        thread.daemon = True
        thread.start()


def run_event_loop(loop: AbstractEventLoop) -> None:
    """run event loop"""
    set_event_loop(loop)
    loop.run_forever()