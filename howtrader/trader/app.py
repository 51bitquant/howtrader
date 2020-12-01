""""""

from abc import ABC


class BaseApp(ABC):
    """
    Abstract class for app.
    """

    app_name: str = ""           # Unique name used for creating engine and widget
    app_module: str = ""         # App module string used in import_module
    app_path: str = ""           # Absolute path of app folder
    display_name: str = ""       # Name for display on the menu.
    engine_class = None     # App engine class
    widget_name: str = ""        # Class name of app widget
    icon_name: str = ""          # Icon file name of app widget
