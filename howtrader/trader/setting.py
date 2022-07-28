"""
Global setting of the trading platform.
"""

from logging import CRITICAL, INFO, DEBUG
from typing import Dict, Any
from tzlocal import get_localzone_name

from .utility import load_json


SETTINGS: Dict[str, Any] = {
    "font.family": "",
    "font.size": 12,

    "log.active": True,
    "log.level": CRITICAL,
    "log.console": True,
    "log.file": True,

    "email.server": "smtp.qq.com",
    "email.port": 465,
    "email.username": "",
    "email.password": "",
    "email.sender": "",
    "email.receiver": "",

    "update_interval": 600,
    "passphrase": "howtrader",  # tv passphrase
    "port": 9999, # tv server port

    "datafeed.name": "",
    "datafeed.username": "",
    "datafeed.password": "",

    "database.timezone": get_localzone_name(),
    "database.name": "sqlite",
    "database.database": "database.db",
    "database.host": "",
    "database.port": 0,
    "database.user": "",
    "database.password": ""
}

# Load global setting from json file.
SETTING_FILENAME: str = "vt_setting.json"
SETTINGS.update(load_json(SETTING_FILENAME))


def get_settings(prefix: str = "") -> Dict[str, Any]:
    prefix_length: int = len(prefix)
    return {k[prefix_length:]: v for k, v in SETTINGS.items() if k.startswith(prefix)}


QUICK_TRADER_SETTINGS: Dict = load_json("quick_trader_setting.json")