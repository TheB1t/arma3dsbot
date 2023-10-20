import sqlalchemy as sa
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import class_mapper

Base = declarative_base()

class Wrapper():
    def to_dict(self):
        return {c.key: getattr(self, c.key) for c in class_mapper(self.__class__).mapped_table.c}

class Admin(Base, Wrapper):
    __tablename__ = "bot_admins"

    id = sa.Column(sa.Integer, primary_key=True, autoincrement=True)
    uid = sa.Column(sa.VARCHAR(100), nullable=False)
    priv_level = sa.Column(sa.Integer, nullable=False)

class Mod(Base, Wrapper):
    __tablename__ = "mods"

    id = sa.Column(sa.Integer, primary_key=True, autoincrement=True)
    folder_name = sa.Column(sa.Text, nullable=False)
    mod_id = sa.Column(sa.Text, nullable=False)

class ZeusUser(Base, Wrapper):
    __tablename__ = "player_access"

    id = sa.Column(sa.Integer, primary_key=True, autoincrement=True)
    nickname = sa.Column(sa.Text, nullable=False)
    steamid = sa.Column(sa.Text, nullable=False)
    is_zeus = sa.Column(sa.Integer, nullable=True, default=0)