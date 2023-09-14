from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import threading

from db_tables import Admin, Base
from utils import semaphored, sessioned, threaded

class Database:

    def __init__(self, host, port, user, passwd, db):
        self._semaphore = threading.Semaphore(15)
        
        self.engine = create_engine('mysql+mysqlconnector://{}:{}@{}:{}/{}'.format(user, passwd, host, port, db))
        self.Session = sessionmaker(bind=self.engine)

        Base.metadata.create_all(self.engine)

    def getAdminByUID(self, session, uid):
        return session.query(Admin).filter_by(uid=uid).first()
    
    @sessioned
    def isAdmin(self, session, uid):
        uid = str(uid)
        
        return self.getAdminByUID(session, uid) if True else False

    @sessioned
    def addAdmin(self, session, uid):
        uid = str(uid)

        admin = self.getAdminByUID(session, uid)

        if not admin:
            new_admin = Admin(uid=uid)
            session.add(new_admin)
            session.commit()

            return True
        
        return False
    
    @sessioned
    def delAdmin(self, session, uid):
        uid = str(uid)

        admin = self.getAdminByUID(session, uid)

        if admin:
            session.delete(admin)
            session.commit()

            return True
    
        return False