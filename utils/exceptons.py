from functools import wraps

class BotInternalException(Exception):
    def __init__(self, message):
        super().__init__(message)