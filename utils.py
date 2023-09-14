import threading
from functools import wraps

def mutexed(func):
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return func(self, *args, **kwargs)
    return wrapper

def semaphored(func):
    def wrapper(self, *args, **kwargs):
        with self._semaphore:
            return func(self, *args, **kwargs)
    return wrapper

def sessioned(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        with self.Session() as session:
            return func(self, session, *args, **kwargs)
    return wrapper

def threaded(func):
    def wrapper(*args, **kwargs):
        t = threading.Thread(target=func, args=args, kwargs=kwargs)
        t.start()
        return t
    return wrapper