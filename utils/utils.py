import threading
import asyncio
import typing
import aiohttp
from discord.ext import commands
from functools import wraps
from db import Database

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

def threaded(func):
    def wrapper(*args, **kwargs):
        t = threading.Thread(target=func, args=args, kwargs=kwargs)
        t.start()
        return t
    return wrapper

def to_thread(func: typing.Callable) -> typing.Coroutine:
    @wraps(func)
    async def wrapper(*args, **kwargs):
        return await asyncio.to_thread(func, *args, **kwargs)
    return wrapper

def to_task(func):
    def wrapper(*args, **kwargs):
        return asyncio.create_task(func(*args, **kwargs))
    return wrapper

async def fetch_url(url):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                return await response.text()

def get_file_extension(filename):
    parts = filename.split(".")
    if len(parts) > 1:
        return parts[-1]
    else:
        return None
    
def split_array(array, chunk_size):
    return [array[i:i+chunk_size] for i in range(0, len(array), chunk_size)]