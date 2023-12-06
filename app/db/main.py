from sqlmodel import create_engine

from app.const import DB_URL


connect_args = {"check_same_thread": False}
engine = create_engine(DB_URL, echo=True, connect_args=connect_args)
