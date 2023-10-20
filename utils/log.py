import datetime as dt

from enum import Enum, auto

class LogLevel(Enum):
    INFO        = auto()
    WARN        = auto()
    ERR         = auto()
    FATAL       = auto()


class Log:

    def log(self, message, level: LogLevel = LogLevel.INFO):
        now = dt.datetime.now()
        now_string = now.strftime("%d-%m-%Y %H:%M:%S")

        print(f"[{now_string}][{self.__class__.__name__:>20s}][{level.name}]: {message}")