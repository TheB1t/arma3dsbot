from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import threading

from .db_tables import Base

class Database:

    def __init__(self, host: str, port: int, user: str, passwd: str, db: str):
        self._semaphore = threading.Semaphore(15)

        self.engine = create_engine('mysql+mysqlconnector://{}:{}@{}:{}/{}'.format(user, passwd, host, port, db), connect_args={'connect_timeout': 10})
        self.Session = sessionmaker(bind=self.engine)

        Base.metadata.create_all(self.engine)