"""
use binance api to get the kline datas.
author: 51bitquant

discord: 51bitquant#8078
"""

import pandas as pd
import time
from datetime import datetime
import requests
import pytz
from howtrader.trader.database import BaseDatabase, get_database

pd.set_option('expand_frame_repr', False)  #
from howtrader.trader.object import BarData, Interval, Exchange

BINANCE_SPOT_LIMIT = 1000
BINANCE_FUTURE_LIMIT = 1500

CHINA_TZ = pytz.timezone("Asia/Shanghai")
from threading import Thread


database: BaseDatabase = get_database()


def generate_datetime(timestamp: float) -> datetime:
    """
    :param timestamp:
    :return:
    """
    dt = datetime.fromtimestamp(timestamp / 1000)
    dt = CHINA_TZ.localize(dt)
    return dt


def get_binance_data(symbol: str, exchange: str, start_time: str, end_time: str, gate_way: str="BINANCE_USDT"):
    """
    crawl binance exchange data
    :param symbol: BTCUSDT.
    :param exchange: spot、usdt_future, inverse_future.
    :param start_time: format :2020-1-1 or 2020-01-01 year-month-day
    :param end_time: format: 2020-1-1 or 2020-01-01 year-month-day
    :param gate_way the gateway name for binance is:BINANCE_SPOT, BINANCE_USDT, BINANCE_INVERSE
    :return:
    """

    api_url = ''
    save_symbol = symbol


    if exchange == 'spot':
        print("spot")
        limit = BINANCE_SPOT_LIMIT
        save_symbol = symbol.lower()
        gate_way = 'BINANCE'
        api_url = f'https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1m&limit={limit}'

    elif exchange == 'usdt_future':
        print('usdt_future')
        limit = BINANCE_FUTURE_LIMIT
        api_url = f'https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval=1m&limit={limit}'

    elif exchange == 'inverse_future':
        print("inverse_future")
        limit = BINANCE_FUTURE_LIMIT
        f'https://dapi.binance.com/dapi/v1/klines?symbol={symbol}&interval=1m&limit={limit}'

    else:
        raise Exception('the exchange name should be one of ：spot, usdt_future, inverse_future')

    start_time = int(datetime.strptime(start_time, '%Y-%m-%d').timestamp() * 1000)
    end_time = int(datetime.strptime(end_time, '%Y-%m-%d').timestamp() * 1000)

    while True:
        try:
            print(start_time)
            url = f'{api_url}&startTime={start_time}'
            print(url)
            datas = requests.get(url=url, timeout=10, proxies=proxies).json()

            """
            [
                [
                    1591258320000,      // 开盘时间
                    "9640.7",           // 开盘价
                    "9642.4",           // 最高价
                    "9640.6",           // 最低价
                    "9642.0",           // 收盘价(当前K线未结束的即为最新价)
                    "206",              // 成交量
                    1591258379999,      // 收盘时间
                    "2.13660389",       // 成交额(标的数量)
                    48,                 // 成交笔数
                    "119",              // 主动买入成交量
                    "1.23424865",      // 主动买入成交额(标的数量)
                    "0"                 // 请忽略该参数
                ]

            """

            buf = []

            for row in datas:
                bar: BarData = BarData(
                    symbol=save_symbol,
                    exchange=Exchange.BINANCE,
                    datetime=generate_datetime(row[0]),
                    interval=Interval.MINUTE,
                    volume=float(row[5]),
                    turnover=float(row[7]),
                    open_price=float(row[1]),
                    high_price=float(row[2]),
                    low_price=float(row[3]),
                    close_price=float(row[4]),
                    gateway_name=gate_way
                )
                buf.append(bar)

            database.save_bar_data(buf)

            # 到结束时间就退出, 后者收盘价大于当前的时间.
            if (datas[-1][0] > end_time) or datas[-1][6] >= (int(time.time() * 1000) - 60 * 1000):
                break

            start_time = datas[-1][0]

        except Exception as error:
            print(error)
            time.sleep(10)


def download_spot(symbol):
    """
    下载现货数据的方法.
    :return:
    """
    t1 = Thread(target=get_binance_data, args=(symbol, 'spot', "2018-1-1", "2019-1-1"))

    t2 = Thread(target=get_binance_data, args=(symbol, 'spot', "2019-1-1", "2020-1-1"))

    t3 = Thread(target=get_binance_data, args=(symbol, 'spot', "2020-1-1", "2020-11-16"))

    t1.start()
    t2.start()
    t3.start()

    t1.join()
    t2.join()
    t3.join()


def download_usdt_future(symbol):
    """
    下载合约数据的方法。
    :return:
    """
    t1 = Thread(target=get_binance_data, args=(symbol, 'usdt_future', "2019-9-10", "2020-3-1"))
    t2 = Thread(target=get_binance_data, args=(symbol, 'usdt_future', "2019-3-1", "2020-11-16"))

    t1.start()
    t2.start()

    t1.join()
    t2.join()


if __name__ == '__main__':

    # 如果你有代理你就设置，如果没有你就设置为 None 或者空的字符串 "",
    # 但是你要确保你的电脑网络能访问币安交易所，你可以通过 ping api.binance.com 看看过能否ping得通
    proxy_host = "127.0.0.1"  # 如果没有就设置为"", 如果有就设置为你的代理主机如：127.0.0.1
    proxy_port = 1087  # 设置你的代理端口号如: 1087, 没有你修改为0,但是要保证你能访问api.binance.com这个主机。

    proxies = None
    if proxy_host and proxy_port:
        proxy = f'http://{proxy_host}:{proxy_port}'
        proxies = {'http': proxy, 'https': proxy}

    symbol = "BTCUSDT"

    # download_spot(symbol) # 下载现货的数据.

    download_usdt_future(symbol)  # 下载合约的数据
