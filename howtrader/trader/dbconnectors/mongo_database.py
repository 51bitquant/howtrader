""""""
from datetime import datetime
from typing import List

from pymongo import ASCENDING, MongoClient, ReplaceOne
from pymongo.database import Database
from pymongo.cursor import Cursor
from pymongo.collection import Collection
from pymongo.results import DeleteResult

from howtrader.trader.constant import Exchange, Interval
from howtrader.trader.object import BarData, TickData
from howtrader.trader.database import BaseDatabase, BarOverview, DB_TZ
from howtrader.trader.setting import SETTINGS


class MongodbDatabase(BaseDatabase):
    """MongoDB database connector"""

    def __init__(self) -> None:
        """"""
        # read the settings
        self.database: str = SETTINGS["database.database"]
        self.host: str = SETTINGS["database.host"]
        self.port: int = SETTINGS["database.port"]
        self.username: str = SETTINGS["database.user"]
        self.password: str = SETTINGS["database.password"]

        # create MongoClient
        if self.username and self.password:
            self.client: MongoClient = MongoClient(
                host=self.host,
                port=self.port,
                tz_aware=True,
                username=self.username,
                password=self.password,
                tzinfo=DB_TZ
            )
        else:
            self.client: MongoClient = MongoClient(
                host=self.host,
                port=self.port,
                tz_aware=True,
                tzinfo=DB_TZ
            )

        # initialize the database
        self.db: Database = self.client[self.database]

        # Kline Collection
        self.bar_collection: Collection = self.db["bar_data"]
        self.bar_collection.create_index(
            [
                ("exchange", ASCENDING),
                ("symbol", ASCENDING),
                ("interval", ASCENDING),
                ("datetime", ASCENDING),
            ],
            unique=True
        )

        # Tick Collection
        self.tick_collection: Collection = self.db["tick_data"]
        self.tick_collection.create_index(
            [
                ("exchange", ASCENDING),
                ("symbol", ASCENDING),
                ("datetime", ASCENDING),
            ],
            unique=True
        )

        # Kline/Bar overview
        self.overview_collection: Collection = self.db["bar_overview"]
        self.overview_collection.create_index(
            [
                ("exchange", ASCENDING),
                ("symbol", ASCENDING),
                ("interval", ASCENDING),
            ],
            unique=True
        )

    def save_bar_data(self, bars: List[BarData]) -> bool:
        """save Kline/Bar data"""
        requests: List[ReplaceOne] = []

        for bar in bars:
            # insert into database.
            filter: dict = {
                "symbol": bar.symbol,
                "exchange": bar.exchange.value,
                "datetime": bar.datetime,
                "interval": bar.interval.value,
            }

            d: dict = {
                "symbol": bar.symbol,
                "exchange": bar.exchange.value,
                "datetime": bar.datetime,
                "interval": bar.interval.value,
                "volume": bar.volume,
                "turnover": bar.turnover,
                "open_interest": bar.open_interest,
                "open_price": bar.open_price,
                "high_price": bar.high_price,
                "low_price": bar.low_price,
                "close_price": bar.close_price,
            }

            requests.append(ReplaceOne(filter, d, upsert=True))

        self.bar_collection.bulk_write(requests, ordered=False)

        # update overview
        filter: dict = {
            "symbol": bar.symbol,
            "exchange": bar.exchange.value,
            "interval": bar.interval.value
        }

        overview: dict = self.overview_collection.find_one(filter)

        if not overview:
            overview = {
                "symbol": bar.symbol,
                "exchange": bar.exchange.value,
                "interval": bar.interval.value,
                "count": len(bars),
                "start": bars[0].datetime,
                "end": bars[-1].datetime
            }
        else:
            overview["start"] = min(bars[0].datetime, overview["start"])
            overview["end"] = max(bars[-1].datetime, overview["end"])
            overview["count"] = self.bar_collection.count_documents(filter)

        self.overview_collection.update_one(filter, {"$set": overview}, upsert=True)

        return True

    def save_tick_data(self, ticks: List[TickData]) -> bool:
        """Save tikc data"""
        requests: List[ReplaceOne] = []

        for tick in ticks:
            filter: dict = {
                "symbol": tick.symbol,
                "exchange": tick.exchange.value,
                "datetime": tick.datetime,
            }

            d: dict = {
                "symbol": tick.symbol,
                "exchange": tick.exchange.value,
                "datetime": tick.datetime,
                "name": tick.name,
                "volume": tick.volume,
                "turnover": tick.turnover,
                "open_interest": tick.open_interest,
                "last_price": tick.last_price,
                "last_volume": tick.last_volume,
                "limit_up": tick.limit_up,
                "limit_down": tick.limit_down,
                "open_price": tick.open_price,
                "high_price": tick.high_price,
                "low_price": tick.low_price,
                "pre_close": tick.pre_close,
                "bid_price_1": tick.bid_price_1,
                "bid_price_2": tick.bid_price_2,
                "bid_price_3": tick.bid_price_3,
                "bid_price_4": tick.bid_price_4,
                "bid_price_5": tick.bid_price_5,
                "ask_price_1": tick.ask_price_1,
                "ask_price_2": tick.ask_price_2,
                "ask_price_3": tick.ask_price_3,
                "ask_price_4": tick.ask_price_4,
                "ask_price_5": tick.ask_price_5,
                "bid_volume_1": tick.bid_volume_1,
                "bid_volume_2": tick.bid_volume_2,
                "bid_volume_3": tick.bid_volume_3,
                "bid_volume_4": tick.bid_volume_4,
                "bid_volume_5": tick.bid_volume_5,
                "ask_volume_1": tick.ask_volume_1,
                "ask_volume_2": tick.ask_volume_2,
                "ask_volume_3": tick.ask_volume_3,
                "ask_volume_4": tick.ask_volume_4,
                "ask_volume_5": tick.ask_volume_5,
                "localtime": tick.localtime,
            }

            requests.append(ReplaceOne(filter, d, upsert=True))

        self.tick_collection.bulk_write(requests, ordered=False)

        return True

    def load_bar_data(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval,
        start: datetime,
        end: datetime
    ) -> List[BarData]:
        """Load Kline/Bar data"""
        filter: dict = {
            "symbol": symbol,
            "exchange": exchange.value,
            "interval": interval.value,
            "datetime": {
                "$gte": start.astimezone(DB_TZ),
                "$lte": end.astimezone(DB_TZ)
            }
        }

        c: Cursor = self.bar_collection.find(filter)

        bars: List[BarData] = []
        for d in c:
            d["exchange"] = Exchange(d["exchange"])
            d["interval"] = Interval(d["interval"])
            d["gateway_name"] = "DB"
            d.pop("_id")

            bar = BarData(**d)
            bars.append(bar)

        return bars

    def load_tick_data(
        self,
        symbol: str,
        exchange: Exchange,
        start: datetime,
        end: datetime
    ) -> List[TickData]:
        """load tick data"""
        filter: dict = {
            "symbol": symbol,
            "exchange": exchange.value,
            "datetime": {
                "$gte": start.astimezone(DB_TZ),
                "$lte": end.astimezone(DB_TZ)
            }
        }

        c: Cursor = self.tick_collection.find(filter)

        ticks: List[TickData] = []
        for d in c:
            d["exchange"] = Exchange(d["exchange"])
            d["gateway_name"] = "DB"
            d.pop("_id")

            tick: TickData = TickData(**d)
            ticks.append(tick)

        return ticks

    def delete_bar_data(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval
    ) -> int:
        """delete bar data"""
        filter: dict = {
            "symbol": symbol,
            "exchange": exchange.value,
            "interval": interval.value,
        }

        result: DeleteResult = self.bar_collection.delete_many(filter)
        self.overview_collection.delete_one(filter)

        return result.deleted_count

    def delete_tick_data(
        self,
        symbol: str,
        exchange: Exchange
    ) -> int:
        """Delete tick data"""
        filter: dict = {
            "symbol": symbol,
            "exchange": exchange.value
        }

        result: DeleteResult = self.tick_collection.delete_many(filter)
        return result.deleted_count

    def get_bar_overview(self) -> List[BarOverview]:
        """query kline overview data"""
        c: Cursor = self.overview_collection.find()

        overviews: List[BarOverview] = []
        for d in c:
            d["exchange"] = Exchange(d["exchange"])
            d["interval"] = Interval(d["interval"])
            d.pop("_id")

            overview: BarOverview = BarOverview(**d)
            overviews.append(overview)

        return overviews