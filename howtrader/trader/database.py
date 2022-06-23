from abc import ABC, abstractmethod
from datetime import datetime
from types import ModuleType
from typing import List
from pytz import timezone
from dataclasses import dataclass
from importlib import import_module

from .constant import Interval, Exchange
from .object import BarData, TickData
from .setting import SETTINGS


DB_TZ = timezone(SETTINGS["database.timezone"])


def convert_tz(dt: datetime) -> datetime:
    """
    Convert timezone of datetime object to DB_TZ.
    """
    dt: datetime = dt.astimezone(DB_TZ)
    return dt.replace(tzinfo=None)


@dataclass
class BarOverview:
    """
    Overview of bar data stored in database.
    """

    symbol: str = ""
    exchange: Exchange = None
    interval: Interval = None
    count: int = 0
    start: datetime = None
    end: datetime = None


class BaseDatabase(ABC):
    """
    Abstract database class for connecting to different database.
    """

    @abstractmethod
    def save_bar_data(self, bars: List[BarData]) -> bool:
        """
        Save bar data into database.
        """
        pass

    @abstractmethod
    def save_tick_data(self, ticks: List[TickData]) -> bool:
        """
        Save tick data into database.
        """
        pass

    @abstractmethod
    def load_bar_data(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval,
        start: datetime,
        end: datetime
    ) -> List[BarData]:
        """
        Load bar data from database.
        """
        pass

    @abstractmethod
    def load_tick_data(
        self,
        symbol: str,
        exchange: Exchange,
        start: datetime,
        end: datetime
    ) -> List[TickData]:
        """
        Load tick data from database.
        """
        pass

    @abstractmethod
    def delete_bar_data(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval
    ) -> int:
        """
        Delete all bar data with given symbol + exchange + interval.
        """
        pass

    @abstractmethod
    def delete_tick_data(
        self,
        symbol: str,
        exchange: Exchange
    ) -> int:
        """
        Delete all tick data with given symbol + exchange.
        """
        pass

    @abstractmethod
    def get_bar_overview(self) -> List[BarOverview]:
        """
        Return data avaible in database.
        """
        pass


database: BaseDatabase = None


def get_database() -> BaseDatabase:
    """"""
    # Return database object if already inited
    global database
    if database:
        return database

    # Read database related global setting
    database_name: str = SETTINGS["database.name"]

    if database_name == 'mysql':
        from howtrader.trader.dbconnectors import MysqlDatabase as Database

    elif database_name == 'sqlite':
        from howtrader.trader.dbconnectors import SqliteDatabase as Database

    elif database_name == 'mongo':
        from howtrader.trader.dbconnectors import MongodbDatabase as Database

    else:
        raise Exception("database.name in settings should be one of mysql、sqlite、mongo")

    database = Database()
    return database
