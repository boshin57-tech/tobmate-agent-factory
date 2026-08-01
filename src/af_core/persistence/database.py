from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase,sessionmaker

class Base(DeclarativeBase):
    pass

def sqlite_url(path):
    p=Path(path).expanduser().resolve()
    p.parent.mkdir(parents=True,exist_ok=True)
    return f"sqlite:///{p}"

def create_database_engine(url):
    return create_engine(
        url,
        future=True,
        connect_args={"check_same_thread":False},
    )

def create_session_factory(engine):
    return sessionmaker(bind=engine,expire_on_commit=False)

def initialize_database(engine):
    from . import tables
    Base.metadata.create_all(engine)
